import pytest

from app.services.scoring import accuracy_for, score_answer
from app.services.state_machine import (
    ALLOWED,
    IllegalTransitionError,
    RoomState,
    assert_transition,
    can_transition,
)


def _score(chosen: list[str], remaining: int = 20_000, streak: int = 0, **kw):  # type: ignore[no-untyped-def]
    return score_answer(
        correct_ids=kw.pop("correct", ["B"]),
        chosen_ids=chosen,
        base_points=1000,
        time_remaining_ms=remaining,
        time_limit_ms=20_000,
        previous_streak=streak,
        **kw,
    )


def test_full_speed_gets_full_points() -> None:
    r = _score(["B"], remaining=20_000)
    assert (r.points, r.is_correct, r.new_streak) == (1000, True, 1)


def test_zero_time_remaining_gets_half() -> None:
    assert _score(["B"], remaining=0).points == 500


def test_half_time_gets_750() -> None:
    assert _score(["B"], remaining=10_000).points == 750


def test_wrong_answer_zero_and_streak_reset() -> None:
    r = _score(["A"], streak=4)
    assert (r.points, r.is_correct, r.new_streak) == (0, False, 0)


def test_streak_multiplier_and_cap() -> None:
    assert _score(["B"], streak=3).points == 1300
    assert _score(["B"], streak=5).points == 1500
    assert _score(["B"], streak=20).points == 1500  # capped at +50%


def test_speed_bonus_can_be_disabled_per_quiz() -> None:
    assert _score(["B"], remaining=0, config={"speed_bonus": False}).points == 1000


def test_custom_streak_config() -> None:
    assert _score(["B"], streak=2, config={"streak_step": 0.25, "streak_cap": 1.0}).points == 1500


def test_remaining_time_clamped() -> None:
    assert _score(["B"], remaining=999_999).points == 1000
    assert _score(["B"], remaining=-5).points == 500


def test_multi_select_partial_credit() -> None:
    correct = ["A", "C", "D"]
    full = _score(["A", "C", "D"], correct=correct)
    assert full.is_correct and full.points == 1000
    partial = _score(["A", "C"], correct=correct)
    assert not partial.is_correct and partial.points == round(1000 * 2 / 3)
    assert partial.new_streak == 0  # partial answers break the streak
    penalised = _score(["A", "C", "B"], correct=correct)  # 2 right, 1 wrong -> 1/3
    assert penalised.points == round(1000 / 3)
    assert _score(["B"], correct=correct).points == 0
    assert _score(["B", "E"], correct=correct).points == 0  # never negative


def test_partial_credit_gets_no_streak_bonus() -> None:
    r = _score(["A", "C"], correct=["A", "C", "D"], streak=5)
    assert r.points == round(1000 * 2 / 3)


def test_accuracy_for() -> None:
    assert accuracy_for({"A"}, {"A"}) == 1.0
    assert accuracy_for({"A", "B"}, {"A"}) == 0.5
    assert accuracy_for(set(), {"A"}) == 0.0


# -- state machine ---------------------------------------------------------------------------
LEGAL = [
    (RoomState.CREATED, RoomState.LOBBY),
    (RoomState.LOBBY, RoomState.QUESTION_ACTIVE),
    (RoomState.QUESTION_ACTIVE, RoomState.QUESTION_CLOSED),
    (RoomState.QUESTION_ACTIVE, RoomState.PAUSED),
    (RoomState.PAUSED, RoomState.QUESTION_ACTIVE),
    (RoomState.QUESTION_CLOSED, RoomState.LEADERBOARD),
    (RoomState.LEADERBOARD, RoomState.QUESTION_ACTIVE),
    (RoomState.LEADERBOARD, RoomState.FINISHED),
    (RoomState.FINISHED, RoomState.ARCHIVED),
]
ILLEGAL = [
    (RoomState.CREATED, RoomState.QUESTION_ACTIVE),
    (RoomState.LOBBY, RoomState.LEADERBOARD),
    (RoomState.QUESTION_CLOSED, RoomState.QUESTION_ACTIVE),
    (RoomState.QUESTION_CLOSED, RoomState.PAUSED),
    (RoomState.LEADERBOARD, RoomState.PAUSED),
    (RoomState.FINISHED, RoomState.LOBBY),
    (RoomState.ARCHIVED, RoomState.LOBBY),
    (RoomState.ARCHIVED, RoomState.FINISHED),
]


@pytest.mark.parametrize(("a", "b"), LEGAL)
def test_legal_transitions(a: RoomState, b: RoomState) -> None:
    assert can_transition(a, b)
    assert_transition(a, b)


@pytest.mark.parametrize(("a", "b"), ILLEGAL)
def test_illegal_transitions_rejected(a: RoomState, b: RoomState) -> None:
    assert not can_transition(a, b)
    with pytest.raises(IllegalTransitionError):
        assert_transition(a, b)


def test_every_state_defined_and_archived_is_terminal() -> None:
    assert set(ALLOWED) == set(RoomState)
    assert ALLOWED[RoomState.ARCHIVED] == frozenset()
    for state in RoomState:
        if state not in (RoomState.FINISHED, RoomState.ARCHIVED):
            assert RoomState.FINISHED in ALLOWED[state]  # host can always end early
