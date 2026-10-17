"""Quiz <-> CSV, so teachers can edit in a spreadsheet or move questions between quizzes.

One row per question: type, text, option_a..option_e, correct (e.g. "B" or "A;C"),
explanation, difficulty, subtopic, time_limit_sec, points.
"""

import csv
import io
from typing import Any

from pydantic import ValidationError

from app.schemas.quiz import OPTION_IDS, QuestionIn

HEADER = [
    "type",
    "text",
    *[f"option_{c.lower()}" for c in OPTION_IDS],
    "correct",
    "explanation",
    "difficulty",
    "subtopic",
    "time_limit_sec",
    "points",
]
MAX_ROWS = 60
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _safe(value: str) -> str:
    """Stop spreadsheet apps from running a cell that starts with = + - @ as a formula."""
    return "'" + value if value[:1] in _FORMULA_START else value


def _unsafe(value: str) -> str:
    return value[1:] if value[:1] == "'" and value[1:2] in _FORMULA_START else value


def questions_to_csv(questions: list[Any]) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(HEADER)
    for q in questions:
        by_id = {o["id"]: o["text"] for o in q.options}
        w.writerow(
            [
                q.type,
                _safe(q.text),
                *[_safe(by_id.get(c, "")) for c in OPTION_IDS],
                ";".join(q.correct_option_ids),
                _safe(q.explanation),
                q.difficulty,
                _safe(q.subtopic),
                q.time_limit_sec,
                q.points,
            ]
        )
    return out.getvalue()


def _int(value: str, default: int) -> int:
    value = value.strip()
    return int(value) if value else default


def parse_quiz_csv(text: str) -> tuple[list[QuestionIn], list[str]]:
    """Returns (valid questions, human-readable errors). Any error means nothing is imported."""
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    if not reader.fieldnames or not {"type", "text", "correct"} <= {
        f.strip().lower() for f in reader.fieldnames
    }:
        return [], ["The first row must be a header containing at least: type, text, correct"]
    questions: list[QuestionIn] = []
    errors: list[str] = []
    for line, raw in enumerate(reader, start=2):
        if len(questions) + len(errors) >= MAX_ROWS:
            errors.append(f"Too many rows: at most {MAX_ROWS} questions per quiz")
            break
        row = {(k or "").strip().lower(): _unsafe((v or "").strip()) for k, v in raw.items()}
        if not any(row.values()):
            continue
        options = [
            {"id": c, "text": row[f"option_{c.lower()}"]}
            for c in OPTION_IDS
            if row.get(f"option_{c.lower()}")
        ]
        try:
            questions.append(
                QuestionIn.model_validate(
                    {
                        "type": row.get("type", "").lower().replace("-", "_"),
                        "text": row.get("text", ""),
                        "options": options,
                        "correct_option_ids": [
                            c.strip().upper()
                            for c in row.get("correct", "").replace(",", ";").split(";")
                            if c.strip()
                        ],
                        "explanation": row.get("explanation", ""),
                        "difficulty": _int(row.get("difficulty", ""), 1),
                        "subtopic": row.get("subtopic", ""),
                        "time_limit_sec": _int(row.get("time_limit_sec", ""), 20),
                        "points": _int(row.get("points", ""), 1000),
                    }
                )
            )
        except (ValidationError, ValueError) as exc:
            msg = exc.errors()[0]["msg"] if isinstance(exc, ValidationError) else str(exc)
            errors.append(f"Row {line}: {msg.removeprefix('Value error, ')}")
    if not questions and not errors:
        errors.append("The file has no question rows")
    return questions, errors
