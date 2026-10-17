"""Pure room lifecycle rules. No I/O, so it is trivially unit-testable."""

from enum import StrEnum


class RoomState(StrEnum):
    CREATED = "created"
    LOBBY = "lobby"
    QUESTION_ACTIVE = "question_active"
    QUESTION_CLOSED = "question_closed"
    LEADERBOARD = "leaderboard"
    PAUSED = "paused"
    FINISHED = "finished"
    ARCHIVED = "archived"


class IllegalTransitionError(Exception):
    def __init__(self, current: RoomState, target: RoomState) -> None:
        super().__init__(f"cannot go from {current.value} to {target.value}")
        self.current = current
        self.target = target


ALLOWED: dict[RoomState, frozenset[RoomState]] = {
    RoomState.CREATED: frozenset({RoomState.LOBBY, RoomState.FINISHED}),
    RoomState.LOBBY: frozenset({RoomState.QUESTION_ACTIVE, RoomState.FINISHED}),
    RoomState.QUESTION_ACTIVE: frozenset(
        {RoomState.QUESTION_CLOSED, RoomState.PAUSED, RoomState.FINISHED}
    ),
    RoomState.QUESTION_CLOSED: frozenset({RoomState.LEADERBOARD, RoomState.FINISHED}),
    RoomState.LEADERBOARD: frozenset({RoomState.QUESTION_ACTIVE, RoomState.FINISHED}),
    RoomState.PAUSED: frozenset({RoomState.QUESTION_ACTIVE, RoomState.FINISHED}),
    RoomState.FINISHED: frozenset({RoomState.ARCHIVED}),
    RoomState.ARCHIVED: frozenset(),
}


def can_transition(current: RoomState, target: RoomState) -> bool:
    return target in ALLOWED[current]


def assert_transition(current: RoomState, target: RoomState) -> None:
    if not can_transition(current, target):
        raise IllegalTransitionError(current, target)
