"""Server-authoritative scoring. Pure functions; the client never sends a score.

points = base * accuracy * speed * streak
  accuracy : 1.0 for a fully correct answer; for multi-select, partial credit
             max(0, (correct_chosen - wrong_chosen) / total_correct)
  speed    : 0.5 + 0.5 * (time_remaining / time_limit)   (1.0 if speed_bonus is off)
  streak   : 1 + min(streak_step * previous_streak, streak_cap)   (fully correct answers only)
"""

from dataclasses import dataclass
from typing import Any

from app.schemas.quiz import DEFAULT_SCORING_CONFIG


@dataclass(frozen=True)
class ScoreResult:
    is_correct: bool
    accuracy: float
    points: int
    new_streak: int


def accuracy_for(correct_ids: set[str], chosen_ids: set[str]) -> float:
    if not correct_ids:
        return 0.0
    right = len(chosen_ids & correct_ids)
    wrong = len(chosen_ids - correct_ids)
    return max(0.0, (right - wrong) / len(correct_ids))


def score_answer(
    *,
    correct_ids: list[str],
    chosen_ids: list[str],
    base_points: int,
    time_remaining_ms: int,
    time_limit_ms: int,
    previous_streak: int,
    config: dict[str, Any] | None = None,
) -> ScoreResult:
    cfg = {**DEFAULT_SCORING_CONFIG, **(config or {})}
    correct, chosen = set(correct_ids), set(chosen_ids)
    accuracy = accuracy_for(correct, chosen)
    is_correct = chosen == correct

    if accuracy <= 0:
        return ScoreResult(False, 0.0, 0, 0)

    if cfg["speed_bonus"] and time_limit_ms > 0:
        ratio = min(max(time_remaining_ms / time_limit_ms, 0.0), 1.0)
        speed = 0.5 + 0.5 * ratio
    else:
        speed = 1.0

    streak_mult = 1.0
    if is_correct:
        streak_mult += min(float(cfg["streak_step"]) * previous_streak, float(cfg["streak_cap"]))

    points = round(base_points * accuracy * speed * streak_mult)
    return ScoreResult(is_correct, accuracy, points, previous_streak + 1 if is_correct else 0)
