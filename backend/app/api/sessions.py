"""Live sessions: teacher creates/lists them, students join by PIN (no account)."""

import io
import logging
import uuid
from typing import Annotated, Any

import qrcode
import qrcode.image.svg
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.api.quizzes import get_owned_quiz
from app.core.config import get_settings
from app.core.net import client_ip
from app.core.rate_limit import enforce, hit
from app.core.security import create_player_token, hash_token
from app.models import GameSession, SessionPlayer
from app.schemas.quiz import DEFAULT_SCORING_CONFIG
from app.services.moderation import clean_nickname, is_clean_nickname
from app.services.room_engine import JoinError, RoomEngine, RoomSettings
from app.ws.runtime import get_engine

log = logging.getLogger("livequiz.sessions")
router = APIRouter(prefix="/api", tags=["sessions"])
Engine = Annotated[RoomEngine, Depends(get_engine)]


def _redis(request: Request) -> Redis:
    return request.app.state.redis  # type: ignore[no-any-return]


def join_url(pin: str) -> str:
    return f"{get_settings().frontend_url.rstrip('/')}/join?pin={pin}"


class SessionCreate(BaseModel):
    quiz_id: uuid.UUID
    auto_reveal: bool = True
    live_leaderboard: bool = False
    show_distribution: bool = True
    auto_close: bool = True


class SessionOut(BaseModel):
    id: uuid.UUID
    quiz_id: uuid.UUID
    pin: str
    status: str
    join_url: str
    title: str = ""
    players: int = 0


class JoinIn(BaseModel):
    pin: str = Field(pattern=r"^\d{6}$")
    nickname: str = Field(min_length=1, max_length=20)
    avatar: str = Field(default="", max_length=16)
    device_id: str | None = Field(default=None, max_length=64)


class JoinOut(BaseModel):
    room_id: str
    player_id: str
    player_token: str
    nickname: str
    rejoined: bool = False


@router.post("/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: SessionCreate, db: DbSession, user: CurrentUser, engine: Engine
) -> SessionOut:
    quiz = await get_owned_quiz(db, body.quiz_id, user)
    if not quiz.questions:
        raise HTTPException(422, "Quiz has no questions")
    sid = uuid.uuid4()
    pin = await engine.reserve_pin(str(sid))
    settings = RoomSettings(
        auto_reveal=body.auto_reveal,
        live_leaderboard=body.live_leaderboard,
        show_distribution=body.show_distribution,
        auto_close=body.auto_close,
    )
    scoring: dict[str, Any] = {**DEFAULT_SCORING_CONFIG, **(quiz.scoring_config or {})}
    questions = [
        {
            "id": str(q.id),
            "type": q.type,
            "text": q.text,
            "options": q.options,
            "correct_option_ids": q.correct_option_ids,
            "explanation": q.explanation,
            "difficulty": q.difficulty,
            "bloom_level": q.bloom_level,
            "subtopic": q.subtopic,
            "time_limit_sec": q.time_limit_sec,
            "points": q.points,
        }
        for q in quiz.questions
    ]
    db.add(
        GameSession(
            id=sid,
            quiz_id=quiz.id,
            host_id=user.id,
            pin=pin,
            status="created",
            settings=settings.model_dump(),
        )
    )
    await db.commit()
    await engine.create_room(
        session_id=str(sid),
        host_id=str(user.id),
        pin=pin,
        title=quiz.title,
        questions=questions,
        scoring=scoring,
        settings=settings,
    )
    return SessionOut(
        id=sid, quiz_id=quiz.id, pin=pin, status="created", join_url=join_url(pin), title=quiz.title
    )


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(db: DbSession, user: CurrentUser) -> list[SessionOut]:
    rows = await db.scalars(
        select(GameSession)
        .where(GameSession.host_id == user.id)
        .order_by(GameSession.created_at.desc())
        .limit(100)
    )
    return [
        SessionOut(id=s.id, quiz_id=s.quiz_id, pin=s.pin, status=s.status, join_url=join_url(s.pin))
        for s in rows
    ]


@router.get("/sessions/{session_id}", response_model=SessionOut)
async def get_session(
    session_id: uuid.UUID, db: DbSession, user: CurrentUser, engine: Engine
) -> SessionOut:
    s = await db.get(GameSession, session_id)
    if s is None or s.host_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    rec = await engine.get_state(str(session_id))
    count = await engine.r.scard(f"room:{session_id}:players") if rec else 0
    return SessionOut(
        id=s.id,
        quiz_id=s.quiz_id,
        pin=s.pin,
        status=rec.state.value if rec else s.status,
        join_url=join_url(s.pin),
        title=rec.title if rec else "",
        players=int(count),
    )


@router.get("/join/qr/{pin}.svg")
async def join_qr(pin: str) -> Response:
    if not (pin.isdigit() and len(pin) == 6):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    img = qrcode.make(join_url(pin), image_factory=qrcode.image.svg.SvgPathImage, box_size=10)
    buf = io.BytesIO()
    img.save(buf)
    return Response(buf.getvalue(), media_type="image/svg+xml")


@router.get("/join/{pin}")
async def lookup_pin(pin: str, request: Request, engine: Engine) -> dict[str, Any]:
    """Cheap check used by the landing page before asking for a nickname."""
    redis = _redis(request)
    ip = client_ip(request)
    await enforce(redis, f"lookup:{ip}", 60, 60)
    await _check_pin_lockout(redis, ip)
    rid = await engine.room_for_pin(pin) if pin.isdigit() and len(pin) == 6 else None
    rec = await engine.get_state(rid) if rid else None
    if rec is None:
        await _record_pin_failure(redis, ip)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Game not found")
    return {"title": rec.title, "state": rec.state.value, "locked": rec.locked}


async def _check_pin_lockout(redis: Redis, ip: str) -> None:
    n = await redis.get(f"rl:pinfail:{ip}")
    if n is not None and int(n) >= 10:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many wrong PINs. Try again in a few minutes.",
            headers={"Retry-After": "300"},
        )


async def _record_pin_failure(redis: Redis, ip: str) -> None:
    await hit(redis, f"pinfail:{ip}", 10_000, 300)


@router.post("/join", response_model=JoinOut)
async def join_game(body: JoinIn, request: Request, db: DbSession, engine: Engine) -> JoinOut:
    redis = _redis(request)
    ip = client_ip(request)
    await enforce(redis, f"join:{ip}", get_settings().join_rate_per_min, 60)
    await _check_pin_lockout(redis, ip)

    rid = await engine.room_for_pin(body.pin)
    if rid is None:
        await _record_pin_failure(redis, ip)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Game not found")

    # Same device coming back (refresh / lost token): resume the existing player.
    if body.device_id:
        existing = await engine.find_device_player(rid, body.device_id)
        if existing is not None:
            pid, nick = existing
            if await engine.player_can_connect(rid, pid) is None:
                return JoinOut(
                    room_id=rid,
                    player_id=pid,
                    player_token=create_player_token(rid, pid),
                    nickname=nick,
                    rejoined=True,
                )

    nickname = clean_nickname(body.nickname)
    if not nickname:
        raise HTTPException(422, "Please choose a nickname")
    if not is_clean_nickname(nickname):
        raise HTTPException(422, "Please pick a friendlier name")

    pid = str(uuid.uuid4())
    token = create_player_token(rid, pid)
    try:
        await engine.add_player(rid, pid, nickname, body.avatar, body.device_id)
    except JoinError as exc:
        raise HTTPException(exc.http_status, {"code": exc.code, "message": exc.message}) from exc
    try:
        db.add(
            SessionPlayer(
                id=uuid.UUID(pid),
                session_id=uuid.UUID(rid),
                nickname=nickname,
                avatar=body.avatar,
                token_hash=hash_token(token),
            )
        )
        await db.commit()
    except Exception:
        await db.rollback()
        await engine.release_nickname(rid, nickname, pid)
        log.exception("could not persist player")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Could not join") from None
    return JoinOut(room_id=rid, player_id=pid, player_token=token, nickname=nickname)
