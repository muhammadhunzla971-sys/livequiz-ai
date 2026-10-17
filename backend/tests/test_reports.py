"""Analytics + reports. Finished sessions are seeded straight into the DB (no sockets needed)."""

import json
import uuid
from typing import Any

import httpx
import pytest_asyncio
from sqlalchemy import select

from app.core.security import create_player_token
from app.db.base import utcnow
from app.db.session import get_sessionmaker
from app.models import Answer, GameSession, Question, Quiz, SessionPlayer, User
from tests.fakes import FakeLLM, make_q


@pytest_asyncio.fixture
async def finished(client: httpx.AsyncClient, auth_headers: dict[str, str]) -> dict[str, Any]:
    quiz = (
        await client.post(
            "/api/quizzes",
            json={
                "title": "Cells",
                "topic": "Biology",
                "questions": [
                    {**make_q(1), "subtopic": "Organelles"},
                    {**make_q(2), "subtopic": "Organelles"},
                    {**make_q(3), "subtopic": "Division"},
                ],
            },
            headers=auth_headers,
        )
    ).json()
    async with get_sessionmaker()() as db:
        user = await db.scalar(select(User))
        assert user is not None
        sid = uuid.uuid4()
        db.add(
            GameSession(
                id=sid,
                quiz_id=uuid.UUID(quiz["id"]),
                host_id=user.id,
                pin="123456",
                status="finished",
                settings={},
            )
        )
        pids = {}
        for nick, score, rank in (("ann", 2500, 1), ("bob", 900, 2), ("=cmd", 0, 3)):
            pid = uuid.uuid4()
            pids[nick] = pid
            db.add(
                SessionPlayer(
                    id=pid,
                    session_id=sid,
                    nickname=nick,
                    token_hash="x",
                    final_score=score,
                    final_rank=rank,
                )
            )
        await db.flush()
        # ann: all right. bob: right, wrong, wrong. "=cmd": all wrong.
        plan = {"ann": [True, True, True], "bob": [True, False, False], "=cmd": [False] * 3}
        for nick, results in plan.items():
            for q, ok in zip(quiz["questions"], results, strict=True):
                correct = q["correct_option_ids"]
                wrong = [o["id"] for o in q["options"] if o["id"] not in correct][:1]
                db.add(
                    Answer(
                        session_id=sid,
                        player_id=pids[nick],
                        question_id=uuid.UUID(q["id"]),
                        chosen_option_ids=correct if ok else wrong,
                        is_correct=ok,
                        response_ms=4000,
                        points=800 if ok else 0,
                        accuracy=1.0 if ok else 0.0,
                        answered_at=utcnow(),
                    )
                )
        await db.commit()
    return {"id": str(sid), "pids": {k: str(v) for k, v in pids.items()}, "quiz": quiz}


async def test_report_numbers(
    client: httpx.AsyncClient, auth_headers: dict[str, str], finished: dict[str, Any]
) -> None:
    r = await client.get(f"/api/sessions/{finished['id']}/report", headers=auth_headers)
    assert r.status_code == 200
    rep = r.json()
    assert rep["overall"]["players"] == 3 and rep["overall"]["questions"] == 3
    assert rep["overall"]["accuracy_pct"] == 44  # 4 of 9 answers correct
    qs = rep["per_question"]
    assert [q["accuracy_pct"] for q in qs] == [67, 33, 33]
    sub = {s["subtopic"]: s["accuracy_pct"] for s in rep["subtopics"]}
    assert sub == {"Organelles": 50, "Division": 33}
    assert {s["subtopic"] for s in rep["weak_subtopics"]} == {"Organelles", "Division"}
    ann = next(s for s in rep["per_student"] if s["nickname"] == "ann")
    assert ann["accuracy_pct"] == 100 and ann["rank"] == 1
    assert rep["ai_summary"] is None


async def test_report_only_for_owner_and_finished(
    client: httpx.AsyncClient, auth_headers: dict[str, str], finished: dict[str, Any]
) -> None:
    other = (
        await client.post(
            "/api/auth/register",
            json={
                "email": "x@example.com",
                "password": "correct-horse-battery",
                "display_name": "X",
            },
        )
    ).json()["access_token"]
    r = await client.get(
        f"/api/sessions/{finished['id']}/report", headers={"Authorization": f"Bearer {other}"}
    )
    assert r.status_code == 404
    assert (
        await client.get(f"/api/sessions/{uuid.uuid4()}/report", headers=auth_headers)
    ).status_code == 404
    async with get_sessionmaker()() as db:
        gs = await db.get(GameSession, uuid.UUID(finished["id"]))
        assert gs is not None
        gs.status = "active"
        await db.commit()
    r = await client.get(f"/api/sessions/{finished['id']}/report", headers=auth_headers)
    assert r.status_code == 409


async def test_csv_neutralises_formula_injection_and_pdf_renders(
    client: httpx.AsyncClient, auth_headers: dict[str, str], finished: dict[str, Any]
) -> None:
    r = await client.get(f"/api/sessions/{finished['id']}/report.csv", headers=auth_headers)
    assert r.status_code == 200 and "text/csv" in r.headers["content-type"]
    assert "'=cmd" in r.text and ",=cmd" not in r.text
    pdf = await client.get(f"/api/sessions/{finished['id']}/report.pdf", headers=auth_headers)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


async def test_ai_summary_and_graceful_failure(
    client: httpx.AsyncClient,
    auth_headers: dict[str, str],
    finished: dict[str, Any],
    llm: FakeLLM,
) -> None:
    good = {
        "class_insight": "Most students mixed up division stages.",
        "reteach": ["Review mitosis phases"],
        "study_tips": {"Division": "Draw each stage."},
    }
    llm.script["generate"] = [json.dumps(good)]  # FakeLLM routes unknown prompts to "generate"
    r = await client.post(f"/api/sessions/{finished['id']}/report/summary", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["class_insight"].startswith("Most students")
    rep = (await client.get(f"/api/sessions/{finished['id']}/report", headers=auth_headers)).json()
    assert rep["ai_summary"]["reteach"] == ["Review mitosis phases"]

    llm.fail_models = {"llama-3.3-70b-versatile", "llama-3.1-8b-instant"}
    from app.core.config import get_settings

    llm.fail_models = {get_settings().llm_primary_model, get_settings().llm_fallback_model}
    r = await client.post(f"/api/sessions/{finished['id']}/report/summary", headers=auth_headers)
    assert r.status_code == 503  # degrades gracefully; report data is untouched
    assert (
        await client.get(f"/api/sessions/{finished['id']}/report", headers=auth_headers)
    ).status_code == 200


async def test_student_report_and_delete(
    client: httpx.AsyncClient, auth_headers: dict[str, str], finished: dict[str, Any]
) -> None:
    token = create_player_token(finished["id"], finished["pids"]["bob"])
    r = await client.get("/api/play/report", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    me = r.json()
    assert me["nickname"] == "bob" and me["correct"] == 1 and me["rank"] == 2
    assert len(me["review"]) == 2 and all(x["explanation"] for x in me["review"])
    assert (await client.get("/api/play/report")).status_code == 401
    # a teacher token is not a player token
    assert (await client.get("/api/play/report", headers=auth_headers)).status_code == 401

    assert (
        await client.delete(f"/api/sessions/{finished['id']}", headers=auth_headers)
    ).status_code == 204
    async with get_sessionmaker()() as db:
        assert (await db.scalars(select(Answer))).first() is None
        assert (await db.scalars(select(SessionPlayer))).first() is None
        assert (
            await db.scalar(
                select(Question).where(Question.quiz_id == uuid.UUID(finished["quiz"]["id"]))
            )
            is not None
        )
        assert await db.get(Quiz, uuid.UUID(finished["quiz"]["id"])) is not None


async def test_report_list_only_shows_own_finished_games(
    client: httpx.AsyncClient, auth_headers: dict[str, str], finished: dict[str, Any]
) -> None:
    r = await client.get("/api/reports", headers=auth_headers)
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["id"] == finished["id"] and rows[0]["title"] == "Cells"
    assert rows[0]["players"] == 3
    assert (await client.get("/api/reports")).status_code == 401
    other = (
        await client.post(
            "/api/auth/register",
            json={
                "email": "other2@example.com",
                "password": "correct-horse-battery",
                "display_name": "O",
            },
        )
    ).json()["access_token"]
    mine = await client.get("/api/reports", headers={"Authorization": f"Bearer {other}"})
    assert mine.json() == []


async def test_unanswered_questions_still_appear_in_reports(
    client: httpx.AsyncClient, auth_headers: dict[str, str], finished: dict[str, Any]
) -> None:
    """Question 3 was shown but nobody answered it: it must still count (as 0%), not vanish."""
    q3 = finished["quiz"]["questions"][2]["id"]
    async with get_sessionmaker()() as db:
        for a in await db.scalars(select(Answer).where(Answer.question_id == uuid.UUID(q3))):
            await db.delete(a)
        gs = await db.get(GameSession, uuid.UUID(finished["id"]))
        assert gs is not None
        gs.settings = {"questions_played": 3}
        await db.commit()

    rep = (await client.get(f"/api/sessions/{finished['id']}/report", headers=auth_headers)).json()
    assert rep["overall"]["questions"] == 3
    last = rep["per_question"][2]
    assert last["question_id"] == q3 and last["answered"] == 0 and last["accuracy_pct"] == 0
    assert rep["overall"]["participation_pct"] == 67  # 6 of 9 possible answers

    token = create_player_token(finished["id"], finished["pids"]["bob"])
    me = (await client.get("/api/play/report", headers={"Authorization": f"Bearer {token}"})).json()
    missed = {r["question_id"]: r for r in me["review"]}
    assert q3 in missed and missed[q3]["chosen"] == []  # unanswered counts as missed
    assert me["accuracy_pct"] == 33  # 1 right out of 3 questions shown


async def test_zero_answer_game_report_lists_the_questions(
    client: httpx.AsyncClient, auth_headers: dict[str, str], finished: dict[str, Any]
) -> None:
    async with get_sessionmaker()() as db:
        for a in await db.scalars(select(Answer)):
            await db.delete(a)
        gs = await db.get(GameSession, uuid.UUID(finished["id"]))
        assert gs is not None
        gs.settings = {"questions_played": 2}
        await db.commit()
    rep = (await client.get(f"/api/sessions/{finished['id']}/report", headers=auth_headers)).json()
    assert rep["overall"]["questions"] == 2 and len(rep["per_question"]) == 2
    assert rep["overall"]["accuracy_pct"] == 0 and rep["overall"]["participation_pct"] == 0
