"""Post-game analytics: per-question, per-student and per-subtopic stats, plus the AI summary."""

import csv
import io
import json
import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.prompt_loader import load_prompt
from app.llm.provider import LLMProvider
from app.llm.retry import call_with_fallback
from app.models import Answer, GameSession, Question, Quiz, SessionPlayer
from app.services.moderation import sanitize_input

WEAK_THRESHOLD_PCT = 70


async def _played_questions(
    db: AsyncSession, gs: GameSession, answered_ids: set[uuid.UUID]
) -> list[Question]:
    """The questions that were actually shown, in order, including ones nobody answered.

    New games record how many were shown ("questions_played"). Older sessions did not, so for
    those we fall back to the questions that received at least one answer.
    """
    played = (gs.settings or {}).get("questions_played")
    if isinstance(played, int) and played >= 0:
        every = list(
            await db.scalars(
                select(Question).where(Question.quiz_id == gs.quiz_id).order_by(Question.position)
            )
        )
        return every[:played]
    if not answered_ids:
        return []
    found = list(await db.scalars(select(Question).where(Question.id.in_(answered_ids))))
    return sorted(found, key=lambda q: q.position)


def _pct(num: float, den: float) -> int:
    return round(100 * num / den) if den else 0


async def build_report(db: AsyncSession, session_id: uuid.UUID) -> dict[str, Any]:
    gs = await db.get(GameSession, session_id)
    if gs is None:
        raise LookupError("session not found")
    quiz = await db.get(Quiz, gs.quiz_id)
    players = list(
        await db.scalars(select(SessionPlayer).where(SessionPlayer.session_id == session_id))
    )
    answers = list(await db.scalars(select(Answer).where(Answer.session_id == session_id)))
    questions = await _played_questions(db, gs, {a.question_id for a in answers})
    qmap = {q.id: q for q in questions}
    active_players = [p for p in players if not p.banned]
    n_players = len(active_players)

    by_q: dict[uuid.UUID, list[Answer]] = defaultdict(list)
    by_p: dict[uuid.UUID, list[Answer]] = defaultdict(list)
    for a in answers:
        by_q[a.question_id].append(a)
        by_p[a.player_id].append(a)

    per_question: list[dict[str, Any]] = []
    for q in questions:
        rows = by_q[q.id]
        dist: dict[str, int] = {o["id"]: 0 for o in q.options}
        for a in rows:
            for oid in a.chosen_option_ids:
                dist[oid] = dist.get(oid, 0) + 1
        correct = sum(1 for a in rows if a.is_correct)
        per_question.append(
            {
                "question_id": str(q.id),
                "position": q.position,
                "text": q.text,
                "subtopic": q.subtopic,
                "type": q.type,
                "answered": len(rows),
                "correct": correct,
                "accuracy_pct": _pct(correct, n_players or len(rows)),
                "avg_response_ms": round(sum(a.response_ms for a in rows) / len(rows))
                if rows
                else 0,
                "distribution": dist,
                "correct_option_ids": q.correct_option_ids,
            }
        )

    sub: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # subtopic -> [correct, attempts]
    for a in answers:
        question = qmap.get(a.question_id)
        if question is None:
            continue
        key = question.subtopic or "General"
        sub[key][1] += 1
        sub[key][0] += 1 if a.is_correct else 0
    subtopics: list[dict[str, Any]] = sorted(
        ({"subtopic": k, "accuracy_pct": _pct(c, n), "attempts": n} for k, (c, n) in sub.items()),
        key=lambda s: s["accuracy_pct"],
    )

    per_student: list[dict[str, Any]] = []
    for p in sorted(active_players, key=lambda p: (p.final_rank or 10**6, -p.final_score)):
        rows = by_p.get(p.id, [])
        correct = sum(1 for a in rows if a.is_correct)
        per_student.append(
            {
                "player_id": str(p.id),
                "nickname": p.nickname,
                "avatar": p.avatar,
                "rank": p.final_rank,
                "score": p.final_score,
                "answered": len(rows),
                "correct": correct,
                "accuracy_pct": _pct(correct, len(questions)),
                "avg_response_ms": round(sum(a.response_ms for a in rows) / len(rows))
                if rows
                else 0,
            }
        )

    ranked = sorted(per_question, key=lambda q: q["accuracy_pct"])
    total_ans = len(answers)
    return {
        "session_id": str(session_id),
        "title": quiz.title if quiz else "",
        "topic": quiz.topic if quiz else "",
        "language": quiz.language if quiz else "en",
        "overall": {
            "players": n_players,
            "questions": len(questions),
            "avg_score": round(sum(p["score"] for p in per_student) / n_players)
            if n_players
            else 0,
            "accuracy_pct": _pct(sum(1 for a in answers if a.is_correct), total_ans),
            "avg_response_ms": round(sum(a.response_ms for a in answers) / total_ans)
            if total_ans
            else 0,
            "participation_pct": _pct(total_ans, n_players * len(questions)),
        },
        "per_question": per_question,
        "per_student": per_student,
        "subtopics": subtopics,
        "weak_subtopics": [s for s in subtopics if s["accuracy_pct"] < WEAK_THRESHOLD_PCT],
        "hardest": [q["question_id"] for q in ranked[:3]],
        "easiest": [q["question_id"] for q in reversed(ranked[-3:])],
    }


async def build_student_report(
    db: AsyncSession, session_id: uuid.UUID, player_id: uuid.UUID
) -> dict[str, Any]:
    player = await db.get(SessionPlayer, player_id)
    if player is None or player.session_id != session_id:
        raise LookupError("player not found")
    answers = list(
        await db.scalars(
            select(Answer).where(Answer.session_id == session_id, Answer.player_id == player_id)
        )
    )
    gs = await db.get(GameSession, session_id)
    if gs is None:
        raise LookupError("session not found")
    questions = await _played_questions(db, gs, {a.question_id for a in answers})
    amap = {a.question_id: a for a in answers}
    sub: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    review: list[dict[str, Any]] = []
    for q in questions:
        a = amap.get(q.id)  # None = the student did not answer this one: it counts as missed
        key = q.subtopic or "General"
        sub[key][1] += 1
        sub[key][0] += 1 if a is not None and a.is_correct else 0
        if a is None or not a.is_correct:
            review.append(
                {
                    "question_id": str(q.id),
                    "text": q.text,
                    "options": q.options,
                    "chosen": a.chosen_option_ids if a is not None else [],
                    "correct_option_ids": q.correct_option_ids,
                    "explanation": q.explanation,
                    "subtopic": q.subtopic,
                }
            )
    correct = sum(1 for a in answers if a.is_correct)
    return {
        "nickname": player.nickname,
        "score": player.final_score,
        "rank": player.final_rank,
        "answered": len(answers),
        "correct": correct,
        "accuracy_pct": _pct(correct, len(questions)),
        "subtopics": sorted(
            (
                {"subtopic": k, "accuracy_pct": _pct(c, n), "attempts": n}
                for k, (c, n) in sub.items()
            ),
            key=lambda s: s["accuracy_pct"],
        ),
        "review": review,
    }


def report_to_csv(report: dict[str, Any]) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Section", "Name", "Rank", "Score", "Correct", "Accuracy %", "Avg response ms"])
    for s in report["per_student"]:
        w.writerow(
            [
                "student",
                _csv_safe(s["nickname"]),
                s["rank"],
                s["score"],
                s["correct"],
                s["accuracy_pct"],
                s["avg_response_ms"],
            ]
        )
    w.writerow([])
    w.writerow(["Section", "Question", "Subtopic", "Answered", "Correct", "Accuracy %", "Avg ms"])
    for q in report["per_question"]:
        w.writerow(
            [
                "question",
                _csv_safe(q["text"]),
                _csv_safe(q["subtopic"]),
                q["answered"],
                q["correct"],
                q["accuracy_pct"],
                q["avg_response_ms"],
            ]
        )
    return out.getvalue()


def _csv_safe(value: str) -> str:
    """Neutralise spreadsheet formula injection from student-chosen nicknames."""
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


def report_to_pdf(report: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=f"LiveQuiz report - {report['title']}")

    def esc(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def table(rows: list[list[str]]) -> Table:
        t = Table(rows, repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4f46e5")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                ]
            )
        )
        return t

    o = report["overall"]
    flow: list[Any] = [
        Paragraph(esc(f"LiveQuiz report: {report['title']}"), styles["Title"]),
        Paragraph(
            f"Players: {o['players']} | Questions: {o['questions']} | "
            f"Class accuracy: {o['accuracy_pct']}% | Avg score: {o['avg_score']}",
            styles["Normal"],
        ),
        Spacer(1, 12),
        Paragraph("Students", styles["Heading2"]),
        table(
            [["Rank", "Name", "Score", "Correct", "Acc %"]]
            + [
                [
                    str(s["rank"] or "-"),
                    esc(s["nickname"])[:30],
                    str(s["score"]),
                    str(s["correct"]),
                    str(s["accuracy_pct"]),
                ]
                for s in report["per_student"]
            ]
        ),
        Spacer(1, 12),
        Paragraph("Questions", styles["Heading2"]),
        table(
            [["#", "Question", "Subtopic", "Acc %", "Avg s"]]
            + [
                [
                    str(q["position"] + 1),
                    Paragraph(esc(q["text"])[:120], styles["BodyText"]),
                    esc(q["subtopic"])[:25],
                    str(q["accuracy_pct"]),
                    f"{q['avg_response_ms'] / 1000:.1f}",
                ]
                for q in report["per_question"]
            ]
        ),
    ]
    if report["weak_subtopics"]:
        flow += [Spacer(1, 12), Paragraph("Weak subtopics", styles["Heading2"])]
        flow += [
            Paragraph(esc(f"{s['subtopic']}: {s['accuracy_pct']}%"), styles["Normal"])
            for s in report["weak_subtopics"]
        ]
    summary = report.get("ai_summary")
    if summary:
        flow += [Spacer(1, 12), Paragraph("AI class insight", styles["Heading2"])]
        flow.append(Paragraph(esc(summary.get("class_insight", "")), styles["Normal"]))
        for r in summary.get("reteach", []):
            flow.append(Paragraph(esc(f"- {r}"), styles["Normal"]))
    doc.build(flow)
    return buf.getvalue()


def _validate_summary(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or not isinstance(data.get("class_insight"), str):
        raise ValueError("expected an object with a class_insight string")
    reteach = data.get("reteach", [])
    tips = data.get("study_tips", {})
    if not isinstance(reteach, list) or not isinstance(tips, dict):
        raise ValueError("reteach must be a list and study_tips an object")
    return {
        "class_insight": data["class_insight"][:1200],
        "reteach": [str(r)[:300] for r in reteach][:5],
        "study_tips": {str(k)[:200]: str(v)[:400] for k, v in tips.items()},
    }


async def generate_ai_summary(provider: LLMProvider, report: dict[str, Any]) -> dict[str, Any]:
    """LLM-written class insight. Only aggregated, anonymous data leaves the system."""
    stats = {
        "overall": report["overall"],
        "subtopics": report["subtopics"],
        "hardest_questions": [
            {
                "text": sanitize_input(q["text"], 200),
                "accuracy_pct": q["accuracy_pct"],
                "distribution": q["distribution"],
                "correct": q["correct_option_ids"],
            }
            for q in report["per_question"]
            if q["question_id"] in report["hardest"]
        ],
    }
    tpl = load_prompt("summary_v1")
    system, user = tpl.render(
        language=report.get("language", "en"),
        topic=sanitize_input(report["topic"], 200),
        stats=json.dumps(stats, ensure_ascii=False),
    )
    value, _ = await call_with_fallback(
        provider,
        system=system,
        user=user,
        temperature=tpl.temperature,
        validate=_validate_summary,
        max_tokens=1024,
    )
    return value  # type: ignore[no-any-return]
