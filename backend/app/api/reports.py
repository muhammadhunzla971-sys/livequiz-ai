"""Teacher reports (JSON / CSV / PDF), AI summary, and the student's own post-game report."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import delete, func, select

from app.api.deps import CurrentUser, DbSession, bearer
from app.api.quizzes import LLM
from app.core.config import get_settings
from app.core.rate_limit import enforce
from app.core.security import TokenError, decode_token
from app.llm.provider import LLMError
from app.models import Answer, GameSession, Quiz, Report, SessionPlayer
from app.services.analytics import (
    build_report,
    build_student_report,
    generate_ai_summary,
    report_to_csv,
    report_to_pdf,
)

router = APIRouter(prefix="/api", tags=["reports"])


async def _finished_session(db: DbSession, session_id: uuid.UUID, user: CurrentUser) -> GameSession:
    gs = await db.get(GameSession, session_id)
    if gs is None or gs.host_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    if gs.status != "finished":
        raise HTTPException(status.HTTP_409_CONFLICT, "Report is available once the game ends")
    return gs


async def _load_report(db: DbSession, gs: GameSession, refresh: bool = False) -> dict[str, Any]:
    row = await db.scalar(select(Report).where(Report.session_id == gs.id))
    if row is None or refresh:
        data = await build_report(db, gs.id)
        if row is None:
            row = Report(session_id=gs.id, data=data)
            db.add(row)
        else:
            row.data = data
        await db.commit()
    return {**row.data, "ai_summary": row.ai_summary}


@router.get("/reports")
async def list_reports(db: DbSession, user: CurrentUser) -> list[dict[str, Any]]:
    """The teacher's finished games, newest first, for the "Past games" list."""
    rows = (
        await db.execute(
            select(GameSession, Quiz.title, func.count(SessionPlayer.id))
            .join(Quiz, Quiz.id == GameSession.quiz_id)
            .outerjoin(SessionPlayer, SessionPlayer.session_id == GameSession.id)
            .where(GameSession.host_id == user.id, GameSession.status == "finished")
            .group_by(GameSession.id, Quiz.title)
            .order_by(GameSession.created_at.desc())
            .limit(100)
        )
    ).all()
    return [
        {
            "id": str(gs.id),
            "quiz_id": str(gs.quiz_id),
            "title": title,
            "pin": gs.pin,
            "players": int(players),
            "created_at": gs.created_at.isoformat(),
        }
        for gs, title, players in rows
    ]


@router.get("/sessions/{session_id}/report")
async def get_report(session_id: uuid.UUID, db: DbSession, user: CurrentUser) -> dict[str, Any]:
    gs = await _finished_session(db, session_id, user)
    return await _load_report(db, gs)


@router.post("/sessions/{session_id}/report/summary")
async def create_summary(
    session_id: uuid.UUID, request: Request, db: DbSession, user: CurrentUser, provider: LLM
) -> dict[str, Any]:
    gs = await _finished_session(db, session_id, user)
    await enforce(
        request.app.state.redis, f"gen:{user.id}", get_settings().generation_rate_per_hour, 3600
    )
    report = await _load_report(db, gs)
    try:
        summary = await generate_ai_summary(provider, report)
    except (LLMError, ValueError) as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The AI summary is unavailable right now. The report itself is still complete.",
        ) from exc
    row = await db.scalar(select(Report).where(Report.session_id == gs.id))
    assert row is not None
    row.ai_summary = summary
    await db.commit()
    return summary


@router.get("/sessions/{session_id}/report.csv")
async def report_csv(session_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Response:
    gs = await _finished_session(db, session_id, user)
    csv_text = report_to_csv(await _load_report(db, gs))
    return Response(
        csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="report-{session_id}.csv"'},
    )


@router.get("/sessions/{session_id}/report.pdf")
async def report_pdf(session_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Response:
    gs = await _finished_session(db, session_id, user)
    pdf = report_to_pdf(await _load_report(db, gs))
    return Response(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="report-{session_id}.pdf"'},
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: uuid.UUID, db: DbSession, user: CurrentUser) -> None:
    """GDPR-style delete: removes the session, its players, answers and report."""
    gs = await db.get(GameSession, session_id)
    if gs is None or gs.host_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    # Explicit child deletes so this also holds on databases without FK enforcement.
    await db.execute(delete(Answer).where(Answer.session_id == session_id))
    await db.execute(delete(Report).where(Report.session_id == session_id))
    await db.execute(delete(SessionPlayer).where(SessionPlayer.session_id == session_id))
    await db.delete(gs)
    await db.commit()


async def _player_claims(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> dict[str, Any]:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        return decode_token(creds.credentials, "player")
    except TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from exc


@router.get("/play/report")
async def my_report(
    db: DbSession, claims: Annotated[dict[str, Any], Depends(_player_claims)]
) -> dict[str, Any]:
    """A student's own report. Only available once the game has finished (it reveals answers)."""
    sid = uuid.UUID(claims["room"])
    gs = await db.get(GameSession, sid)
    if gs is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Game not found")
    if gs.status != "finished":
        raise HTTPException(status.HTTP_409_CONFLICT, "Your report is ready when the game ends")
    try:
        return await build_student_report(db, sid, uuid.UUID(claims["sub"]))
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Player not found") from exc
