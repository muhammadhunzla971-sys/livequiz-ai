"""WebSocket protocol v1.

Every message: {"v": 1, "type": str, "seq": int, "ts": server_ms, "payload": {}}.

See docs/PROTOCOL.md for the full catalogue with example payloads.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

PROTOCOL_VERSION = 1

# --- server -> client ---------------------------------------------------------------------
ROOM_STATE = "room.state"
PLAYER_JOINED = "player.joined"
PLAYER_LEFT = "player.left"
PLAYER_KICKED = "player.kicked"
GAME_STARTED = "game.started"
QUESTION_SHOW = "question.show"
QUESTION_TICK = "question.tick"
QUESTION_CLOSED = "question.closed"
ANSWER_ACK = "answer.ack"
ANSWER_REVEAL = "answer.reveal"
LEADERBOARD_UPDATE = "leaderboard.update"
GAME_PAUSED = "game.paused"
GAME_RESUMED = "game.resumed"
GAME_FINISHED = "game.finished"
ERROR = "error"
PONG = "pong"

# --- client -> server ---------------------------------------------------------------------
PLAYER_JOIN = "player.join"
PLAYER_ANSWER = "player.answer"
PING = "ping"

HOST_START = "host.start"
HOST_NEXT = "host.next"
HOST_SKIP = "host.skip"
HOST_PAUSE = "host.pause"
HOST_RESUME = "host.resume"
HOST_KICK = "host.kick"
HOST_END = "host.end"
HOST_LOCK = "host.lock"
HOST_REVEAL = "host.reveal"
HOST_SETTINGS = "host.settings"

PLAYER_MESSAGES = frozenset({PLAYER_JOIN, PLAYER_ANSWER, PING})
HOST_MESSAGES = frozenset(
    {
        HOST_START,
        HOST_NEXT,
        HOST_SKIP,
        HOST_PAUSE,
        HOST_RESUME,
        HOST_KICK,
        HOST_END,
        HOST_LOCK,
        HOST_REVEAL,
        HOST_SETTINGS,
        PING,
    }
)

# Application-level WebSocket close codes
CLOSE_UNAUTHORIZED = 4401
CLOSE_FORBIDDEN = 4403
CLOSE_NOT_FOUND = 4404
CLOSE_REPLACED = 4409
CLOSE_KICKED = 4410
CLOSE_RATE_LIMITED = 4429
CLOSE_TOO_BIG = 1009
CLOSE_SERVER_RESTART = 1012
CLOSE_OVERLOADED = 1013


class ClientMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    v: int = PROTOCOL_VERSION
    type: str = Field(min_length=1, max_length=40)
    seq: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class AnswerPayload(BaseModel):
    question_id: str = Field(min_length=1, max_length=64)
    option_ids: list[str] = Field(min_length=1, max_length=5)


class KickPayload(BaseModel):
    player_id: str = Field(min_length=1, max_length=64)


class LockPayload(BaseModel):
    locked: bool = True


class SettingsPayload(BaseModel):
    auto_reveal: bool | None = None
    live_leaderboard: bool | None = None
    show_distribution: bool | None = None
    auto_close: bool | None = None
