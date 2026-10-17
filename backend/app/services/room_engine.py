"""Realtime game engine: room state machine on Redis, server-authoritative timing and scoring.

All room state lives in Redis so any API instance can serve any room. Messages are fanned out
through Redis pub/sub (see app/ws/manager.py). A per-room timer runs on one instance at a time
(Redis lease); another instance takes over if the owner disappears.
"""

import asyncio
import contextlib
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from redis.asyncio import Redis
from sqlalchemy import update

from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.models import Answer, GameSession, SessionPlayer
from app.services.scoring import score_answer
from app.services.state_machine import (
    IllegalTransitionError,
    RoomState,
    assert_transition,
)
from app.ws import protocol as P
from app.ws.manager import ConnectionManager, channel_for

log = logging.getLogger("livequiz.engine")

TICK_MS = 1000
LEASE_MS = 3000
DRAIN_MS = 50
FINISHED_KEEP_SEC = 3600
JANITOR_INTERVAL_SEC = 2.0


def now_ms() -> int:
    return int(time.time() * 1000)


class CommandError(Exception):
    """A rejected client command. Sent back to the caller as an `error` event."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code


class JoinError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


class RoomSettings(BaseModel):
    auto_reveal: bool = True
    live_leaderboard: bool = False
    show_distribution: bool = True
    auto_close: bool = True  # close early once everybody has answered


class RoomRecord(BaseModel):
    room_id: str
    session_id: str
    host_id: str
    pin: str
    title: str = ""
    state: RoomState = RoomState.CREATED
    q_index: int = -1
    total_questions: int
    locked: bool = False
    revealed: bool = False
    q_start_ms: int = 0
    q_end_at_ms: int = 0
    q_limit_ms: int = 0
    paused_remaining_ms: int | None = None
    paused_at_ms: int | None = None
    pause_reason: str = ""
    started_ms: int | None = None
    finished_ms: int | None = None
    max_players: int = 300
    settings: RoomSettings = Field(default_factory=RoomSettings)


# -- redis keys ------------------------------------------------------------------------------
def k_state(r: str) -> str:
    return f"room:{r}:state"


def k_quiz(r: str) -> str:
    return f"room:{r}:quiz"


def k_players(r: str) -> str:
    return f"room:{r}:players"


def k_player(r: str, p: str) -> str:
    return f"room:{r}:p:{p}"


def k_lb(r: str) -> str:
    return f"room:{r}:lb"


def k_answers(r: str, n: int) -> str:
    return f"room:{r}:q:{n}:answers"


def k_dist(r: str, n: int) -> str:
    return f"room:{r}:q:{n}:dist"


def k_prev(r: str) -> str:
    return f"room:{r}:prev_rank"


def k_conn(r: str) -> str:
    return f"room:{r}:conn"


def k_nicks(r: str) -> str:
    return f"room:{r}:nicks"


def k_banned(r: str) -> str:
    return f"room:{r}:banned_nicks"


def k_devices(r: str) -> str:
    return f"room:{r}:devices"


def k_kicked(r: str) -> str:
    return f"room:{r}:kicked"


def k_seq(r: str) -> str:
    return f"room:{r}:seq"


def k_lock(r: str) -> str:
    return f"room:{r}:lock"


def k_timer(r: str) -> str:
    return f"room:{r}:timer"


def k_closed(r: str, n: int) -> str:
    return f"room:{r}:closed:{n}"


def k_pin(pin: str) -> str:
    return f"pin:{pin}"


def public_question(q: dict[str, Any], rec: RoomRecord) -> dict[str, Any]:
    """The question as clients may see it while it is live: never includes the answer."""
    return {
        "index": rec.q_index,
        "total": rec.total_questions,
        "question_id": q["id"],
        "type": q["type"],
        "text": q["text"],
        "options": q["options"],
        "time_limit_sec": q["time_limit_sec"],
        "points": q["points"],
        "started_at": rec.q_start_ms,
        "question_end_at": rec.q_end_at_ms,
        "server_time": now_ms(),
    }


class RoomEngine:
    def __init__(self, redis: Redis, manager: ConnectionManager) -> None:
        self.r = redis
        self.manager = manager
        self.instance_id = uuid.uuid4().hex[:12]
        self._timers: dict[str, asyncio.Task[None]] = {}
        self._quiz_cache: dict[str, dict[str, Any]] = {}
        self._bg: set[asyncio.Task[None]] = set()
        self._janitor: asyncio.Task[None] | None = None

    # ==== lifecycle ===========================================================================
    async def start(self) -> None:
        self._janitor = asyncio.create_task(self._janitor_loop())

    async def shutdown(self) -> None:
        """Graceful shutdown: pause live questions (state persists in Redis), tell clients."""
        if self._janitor:
            self._janitor.cancel()
            with contextlib.suppress(BaseException):
                await self._janitor
        for rid in self.manager.local_room_ids():
            with contextlib.suppress(Exception):
                async with self.room_lock(rid):
                    rec = await self.get_state(rid)
                    if rec and rec.state == RoomState.QUESTION_ACTIVE:
                        await self._pause_locked(rid, rec, reason="server_restarting")
        for t in list(self._timers.values()):
            t.cancel()
        await self.manager.close_all(P.CLOSE_SERVER_RESTART, "server restarting")
        for t in list(self._bg):
            with contextlib.suppress(BaseException):
                await asyncio.wait_for(t, timeout=5)

    async def _janitor_loop(self) -> None:
        """Take over timers for rooms we hold sockets for whose timer owner has vanished."""
        while True:
            await asyncio.sleep(JANITOR_INTERVAL_SEC)
            for rid in self.manager.local_room_ids():
                try:
                    rec = await self.get_state(rid)
                    if rec and rec.state == RoomState.QUESTION_ACTIVE:
                        self.ensure_timer(rid)
                except Exception:
                    log.exception("janitor error")

    def _spawn(self, coro: Any) -> None:
        task = asyncio.create_task(coro)
        self._bg.add(task)
        task.add_done_callback(self._bg.discard)

    # ==== low-level helpers ===================================================================
    @asynccontextmanager
    async def room_lock(self, rid: str) -> AsyncIterator[None]:
        token = uuid.uuid4().hex
        for _ in range(100):
            if await self.r.set(k_lock(rid), token, nx=True, px=5000):
                break
            await asyncio.sleep(0.02)
        else:
            raise CommandError("busy", "Room is busy, try again")
        try:
            yield
        finally:
            if await self.r.get(k_lock(rid)) == token:
                await self.r.delete(k_lock(rid))

    async def get_state(self, rid: str) -> RoomRecord | None:
        raw = await self.r.get(k_state(rid))
        if raw is None:
            return None
        try:
            return RoomRecord.model_validate_json(raw)
        except ValidationError:
            log.error("corrupt room state for %s", rid)
            return None

    async def _save(self, rec: RoomRecord) -> None:
        await self.r.set(
            k_state(rec.room_id), rec.model_dump_json(), ex=get_settings().room_ttl_sec
        )

    async def _require(self, rid: str) -> RoomRecord:
        rec = await self.get_state(rid)
        if rec is None:
            raise CommandError("room_not_found", "Room not found")
        return rec

    async def get_quiz(self, rid: str) -> dict[str, Any]:
        cached = self._quiz_cache.get(rid)
        if cached is not None:
            return cached
        raw = await self.r.get(k_quiz(rid))
        if raw is None:
            raise CommandError("room_not_found", "Room not found")
        quiz: dict[str, Any] = json.loads(raw)
        self._quiz_cache[rid] = quiz
        return quiz

    @staticmethod
    def _set_state(rec: RoomRecord, target: RoomState) -> None:
        try:
            assert_transition(rec.state, target)
        except IllegalTransitionError as exc:
            raise CommandError("illegal_transition", str(exc)) from exc
        rec.state = target

    async def emit_many(self, rid: str, items: list[tuple[str, dict[str, Any], str]]) -> None:
        if not items:
            return
        n = len(items)
        last = await self.r.incrby(k_seq(rid), n)
        ts = now_ms()
        pipe = self.r.pipeline(transaction=False)
        for i, (typ, payload, to) in enumerate(items):
            env = {
                "v": P.PROTOCOL_VERSION,
                "type": typ,
                "seq": last - n + 1 + i,
                "ts": ts,
                "payload": payload,
            }
            pipe.publish(channel_for(rid), f"{to}|{json.dumps(env, separators=(',', ':'))}")
        await pipe.execute()

    async def emit(self, rid: str, typ: str, payload: dict[str, Any], to: str = "all") -> None:
        await self.emit_many(rid, [(typ, payload, to)])

    async def make_envelope(self, rid: str, typ: str, payload: dict[str, Any]) -> str:
        seq = await self.r.incr(k_seq(rid))
        env = {"v": P.PROTOCOL_VERSION, "type": typ, "seq": seq, "ts": now_ms(), "payload": payload}
        return json.dumps(env, separators=(",", ":"))

    async def _db_update_session(self, session_id: str, **fields: Any) -> None:
        try:
            async with get_sessionmaker()() as db:
                await db.execute(
                    update(GameSession)
                    .where(GameSession.id == uuid.UUID(session_id))
                    .values(**fields)
                )
                await db.commit()
        except Exception:
            log.exception("could not update session row")

    # ==== room creation & joining =============================================================
    async def create_room(
        self,
        *,
        session_id: str,
        host_id: str,
        pin: str,
        title: str,
        questions: list[dict[str, Any]],
        scoring: dict[str, Any],
        settings: RoomSettings,
    ) -> RoomRecord:
        s = get_settings()
        rec = RoomRecord(
            room_id=session_id,
            session_id=session_id,
            host_id=host_id,
            pin=pin,
            title=title,
            total_questions=len(questions),
            max_players=s.max_players_per_room,
            settings=settings,
        )
        pipe = self.r.pipeline(transaction=False)
        pipe.set(k_state(session_id), rec.model_dump_json(), ex=s.room_ttl_sec)
        pipe.set(
            k_quiz(session_id),
            json.dumps({"title": title, "questions": questions, "scoring": scoring}),
            ex=s.room_ttl_sec,
        )
        pipe.set(k_seq(session_id), 0, ex=s.room_ttl_sec)
        await pipe.execute()
        return rec

    async def reserve_pin(self, session_id: str) -> str:
        import secrets

        for _ in range(50):
            pin = f"{secrets.randbelow(900000) + 100000}"
            if await self.r.set(k_pin(pin), session_id, nx=True, ex=get_settings().room_ttl_sec):
                return pin
        raise RuntimeError("could not allocate a PIN")

    async def room_for_pin(self, pin: str) -> str | None:
        return await self.r.get(k_pin(pin))

    async def find_device_player(self, rid: str, device_id: str) -> tuple[str, str] | None:
        pid = await self.r.hget(k_devices(rid), device_id)
        if not pid:
            return None
        nick = await self.r.hget(k_player(rid, pid), "nickname")
        return (pid, nick) if nick else None

    async def add_player(
        self, rid: str, player_id: str, nickname: str, avatar: str, device_id: str | None
    ) -> int:
        """Reserve nickname atomically and register the player. Returns player count."""
        rec = await self.get_state(rid)
        if rec is None or rec.state in (RoomState.FINISHED, RoomState.ARCHIVED):
            raise JoinError("room_not_found", "Game not found or already finished", 404)
        if rec.state == RoomState.CREATED:
            raise JoinError("not_open", "The host hasn't opened the lobby yet", 409)
        if rec.locked:
            raise JoinError("locked", "This game is locked", 403)
        if await self.r.scard(k_players(rid)) >= rec.max_players:
            raise JoinError("full", "This game is full", 403)

        lowered = nickname.lower()
        if await self.r.sismember(k_banned(rid), lowered):
            raise JoinError("nickname_banned", "That nickname isn't available", 403)
        if not await self.r.hsetnx(k_nicks(rid), lowered, player_id):
            raise JoinError("nickname_taken", "That nickname is already taken", 409)

        ttl = get_settings().room_ttl_sec
        pipe = self.r.pipeline(transaction=False)
        pipe.hset(
            k_player(rid, player_id),
            mapping={
                "id": player_id,
                "nickname": nickname,
                "avatar": avatar,
                "streak": 0,
                "best_streak": 0,
                "correct": 0,
                "answered": 0,
                "kicked": 0,
                "joined_ms": now_ms(),
            },
        )
        pipe.expire(k_player(rid, player_id), ttl)
        pipe.sadd(k_players(rid), player_id)
        pipe.expire(k_players(rid), ttl)
        pipe.zadd(k_lb(rid), {player_id: 0}, nx=True)
        pipe.expire(k_lb(rid), ttl)
        pipe.expire(k_nicks(rid), ttl)
        if device_id:
            pipe.hset(k_devices(rid), device_id, player_id)
            pipe.expire(k_devices(rid), ttl)
        await pipe.execute()
        count = await self.r.scard(k_players(rid))

        to = "all" if rec.state == RoomState.LOBBY else "host"
        await self.emit(
            rid,
            P.PLAYER_JOINED,
            {"player": {"id": player_id, "nickname": nickname, "avatar": avatar}, "count": count},
            to,
        )
        return count

    async def release_nickname(self, rid: str, nickname: str, player_id: str) -> None:
        """Roll back a reservation when the DB insert fails after add_player."""
        pipe = self.r.pipeline(transaction=False)
        pipe.hdel(k_nicks(rid), nickname.lower())
        pipe.srem(k_players(rid), player_id)
        pipe.zrem(k_lb(rid), player_id)
        pipe.delete(k_player(rid, player_id))
        await pipe.execute()

    # ==== connections =========================================================================
    async def player_can_connect(self, rid: str, pid: str) -> str | None:
        """None if allowed, else a short reason code."""
        rec = await self.get_state(rid)
        if rec is None:
            return "room_not_found"
        kicked = await self.r.hget(k_player(rid, pid), "kicked")
        if kicked == "1":
            return "kicked"
        if not await self.r.sismember(k_players(rid), pid):
            return "not_a_player"
        return None

    async def player_connected(self, rid: str, pid: str) -> None:
        await self.r.hset(k_conn(rid), pid, self.instance_id)
        await self.r.expire(k_conn(rid), get_settings().room_ttl_sec)
        snap = await self.build_snapshot(rid, "player", pid)
        await self.emit(rid, P.ROOM_STATE, snap, f"p:{pid}")
        nick = await self.r.hget(k_player(rid, pid), "nickname")
        await self.emit(
            rid,
            P.PLAYER_JOINED,
            {"player": {"id": pid, "nickname": nick}, "connected": True},
            "host",
        )
        rec = await self.get_state(rid)
        if rec and rec.state == RoomState.QUESTION_ACTIVE:
            self.ensure_timer(rid)

    async def player_disconnected(self, rid: str, pid: str) -> None:
        await self.r.hdel(k_conn(rid), pid)
        await self.emit(rid, P.PLAYER_LEFT, {"player_id": pid, "reason": "disconnected"}, "host")

    async def host_connected(self, rid: str) -> None:
        async with self.room_lock(rid):
            rec = await self._require(rid)
            if rec.state == RoomState.CREATED:
                self._set_state(rec, RoomState.LOBBY)
                await self._save(rec)
                await self._db_update_session(rec.session_id, status="lobby")
        snap = await self.build_snapshot(rid, "host")
        await self.emit(rid, P.ROOM_STATE, snap, "host")
        rec = await self._require(rid)
        if rec.state == RoomState.QUESTION_ACTIVE:
            self.ensure_timer(rid)

    # ==== snapshots (reconnection) ============================================================
    async def _ranking(self, rid: str, limit: int | None = None) -> list[tuple[str, float]]:
        stop = -1 if limit is None else limit - 1
        return await self.r.zrevrange(k_lb(rid), 0, stop, withscores=True)  # type: ignore[no-any-return]

    async def _leaderboard_entries(
        self, rid: str, limit: int | None = None
    ) -> tuple[list[dict[str, Any]], int]:
        ranking = await self._ranking(rid, limit)
        total = await self.r.zcard(k_lb(rid))
        if not ranking:
            return [], total
        pipe = self.r.pipeline(transaction=False)
        for pid, _ in ranking:
            pipe.hmget(k_player(rid, pid), "nickname", "avatar", "streak")
        pipe.hgetall(k_prev(rid))
        results = await pipe.execute()
        prev: dict[str, str] = results[-1]
        entries = []
        for i, ((pid, score), fields) in enumerate(zip(ranking, results[:-1], strict=True)):
            rank = i + 1
            prev_rank = int(prev[pid]) if pid in prev else rank
            entries.append(
                {
                    "rank": rank,
                    "player_id": pid,
                    "nickname": fields[0] or "?",
                    "avatar": fields[1] or "",
                    "score": int(score),
                    "streak": int(fields[2] or 0),
                    "rank_change": prev_rank - rank,
                }
            )
        return entries, total

    async def _players_list(self, rid: str) -> list[dict[str, Any]]:
        pids = sorted(await self.r.smembers(k_players(rid)))
        if not pids:
            return []
        pipe = self.r.pipeline(transaction=False)
        for pid in pids:
            pipe.hmget(k_player(rid, pid), "nickname", "avatar")
        pipe.hgetall(k_conn(rid))
        res = await pipe.execute()
        conn = res[-1]
        return [
            {"id": pid, "nickname": f[0], "avatar": f[1], "connected": pid in conn}
            for pid, f in zip(pids, res[:-1], strict=True)
        ]

    async def _my_result(self, rid: str, rec: RoomRecord, pid: str) -> dict[str, Any]:
        raw = await self.r.hget(k_answers(rid, rec.q_index), pid)
        ans = json.loads(raw) if raw else None
        ranking = await self._ranking(rid)
        rank = next((i + 1 for i, (p, _) in enumerate(ranking) if p == pid), None)
        score = next((int(sc) for p, sc in ranking if p == pid), 0)
        prev = await self.r.hget(k_prev(rid), pid)
        streak = int(await self.r.hget(k_player(rid, pid), "streak") or 0)
        return {
            "answered": ans is not None,
            "chosen": ans["chosen"] if ans else [],
            "is_correct": bool(ans and ans["correct"]),
            "accuracy": ans["accuracy"] if ans else 0.0,
            "points": ans["points"] if ans else 0,
            "streak": streak,
            "score": score,
            "rank": rank,
            "rank_change": (int(prev) - rank) if (prev and rank) else 0,
        }

    async def build_snapshot(self, rid: str, role: str, pid: str | None = None) -> dict[str, Any]:
        rec = await self._require(rid)
        quiz = await self.get_quiz(rid)
        count = await self.r.scard(k_players(rid))
        snap: dict[str, Any] = {
            "role": role,
            "room_id": rid,
            "title": rec.title,
            "state": rec.state.value,
            "locked": rec.locked,
            "q_index": rec.q_index,
            "total_questions": rec.total_questions,
            "players_count": count,
            "server_time": now_ms(),
            "settings": rec.settings.model_dump(),
        }
        if role == "host":
            snap["pin"] = rec.pin
            snap["players"] = await self._players_list(rid)
        if rec.state in (RoomState.QUESTION_ACTIVE, RoomState.PAUSED) and rec.q_index >= 0:
            q = quiz["questions"][rec.q_index]
            snap["question"] = public_question(q, rec)
            snap["answered"] = await self.r.hlen(k_answers(rid, rec.q_index))
            if rec.state == RoomState.PAUSED:
                snap["remaining_ms"] = rec.paused_remaining_ms
                snap["pause_reason"] = rec.pause_reason
            if role == "player" and pid:
                raw = await self.r.hget(k_answers(rid, rec.q_index), pid)
                snap["my_answer"] = {
                    "answered": raw is not None,
                    "chosen": json.loads(raw)["chosen"] if raw else [],
                }
            if role == "host" and rec.settings.show_distribution:
                snap["distribution"] = await self.r.hgetall(k_dist(rid, rec.q_index))
        if rec.state in (RoomState.QUESTION_CLOSED, RoomState.LEADERBOARD) and rec.q_index >= 0:
            q = quiz["questions"][rec.q_index]
            snap["question"] = {**public_question(q, rec)}
            if rec.revealed:
                snap["reveal"] = {
                    "correct_option_ids": q["correct_option_ids"],
                    "explanation": q["explanation"],
                    "distribution": await self.r.hgetall(k_dist(rid, rec.q_index)),
                }
                if role == "player" and pid:
                    snap["you"] = await self._my_result(rid, rec, pid)
        if rec.state in (
            RoomState.QUESTION_CLOSED,
            RoomState.LEADERBOARD,
            RoomState.FINISHED,
            RoomState.ARCHIVED,
            RoomState.QUESTION_ACTIVE,
            RoomState.PAUSED,
        ):
            limit = None if role == "host" else 5
            entries, total = await self._leaderboard_entries(rid, limit)
            snap["leaderboard"] = entries
            snap["total_players"] = total
        if rec.state in (RoomState.FINISHED, RoomState.ARCHIVED):
            snap["podium"] = (await self._leaderboard_entries(rid, 3))[0]
            if role == "player" and pid:
                snap["me"] = await self._final_me(rid, rec, pid)
        return snap

    # ==== host commands =======================================================================
    async def handle_host(self, rid: str, typ: str, payload: dict[str, Any]) -> None:
        async with self.room_lock(rid):
            rec = await self._require(rid)
            if typ == P.HOST_START:
                await self._cmd_start(rid, rec)
            elif typ == P.HOST_NEXT:
                await self._cmd_next(rid, rec)
            elif typ == P.HOST_SKIP:
                await self._cmd_skip(rid, rec)
            elif typ == P.HOST_PAUSE:
                await self._pause_locked(rid, rec, reason="host")
            elif typ == P.HOST_RESUME:
                await self._cmd_resume(rid, rec)
            elif typ == P.HOST_END:
                await self._finish_locked(rid, rec, reason="host_ended")
            elif typ == P.HOST_REVEAL:
                await self._cmd_reveal(rid, rec)
            elif typ == P.HOST_KICK:
                await self._cmd_kick(rid, rec, P.KickPayload.model_validate(payload))
            elif typ == P.HOST_LOCK:
                lock = P.LockPayload.model_validate(payload)
                rec.locked = lock.locked
                await self._save(rec)
                await self.emit(rid, P.ROOM_STATE, await self.build_snapshot(rid, "host"), "host")
            elif typ == P.HOST_SETTINGS:
                st = P.SettingsPayload.model_validate(payload)
                rec.settings = rec.settings.model_copy(update=st.model_dump(exclude_none=True))
                await self._save(rec)
                await self.emit(rid, P.ROOM_STATE, await self.build_snapshot(rid, "host"), "host")
            else:
                raise CommandError("unknown_type", f"Unknown command {typ}")

    async def _cmd_start(self, rid: str, rec: RoomRecord) -> None:
        if rec.state != RoomState.LOBBY:
            raise CommandError("illegal_transition", f"cannot start from {rec.state.value}")
        if await self.r.scard(k_players(rid)) < 1:
            raise CommandError("no_players", "Wait for at least one player to join")
        if rec.total_questions < 1:
            raise CommandError("no_questions", "This quiz has no questions")
        rec.started_ms = now_ms()
        await self._db_update_session(rec.session_id, status="active", started_at=datetime.now(UTC))
        await self.emit(rid, P.GAME_STARTED, {"total_questions": rec.total_questions})
        await self._start_question_locked(rid, rec, 0)

    async def _cmd_next(self, rid: str, rec: RoomRecord) -> None:
        if rec.state == RoomState.QUESTION_CLOSED:
            if not rec.revealed:
                raise CommandError("not_revealed", "Reveal the answer first")
            self._set_state(rec, RoomState.LEADERBOARD)
            await self._save(rec)
            host_entries, total = await self._leaderboard_entries(rid)
            await self.emit_many(
                rid,
                [
                    (
                        P.LEADERBOARD_UPDATE,
                        self._lb_payload(rec, host_entries, total, "leaderboard"),
                        "host",
                    ),
                    (
                        P.LEADERBOARD_UPDATE,
                        self._lb_payload(rec, host_entries[:5], total, "leaderboard"),
                        "players",
                    ),
                ],
            )
        elif rec.state == RoomState.LEADERBOARD:
            nxt = rec.q_index + 1
            if nxt >= rec.total_questions:
                await self._finish_locked(rid, rec, reason="completed")
            else:
                await self._start_question_locked(rid, rec, nxt)
        else:
            raise CommandError("illegal_transition", f"cannot advance from {rec.state.value}")

    async def _cmd_skip(self, rid: str, rec: RoomRecord) -> None:
        if rec.state == RoomState.PAUSED:
            self._set_state(rec, RoomState.QUESTION_ACTIVE)
            rec.q_end_at_ms = now_ms()
            rec.paused_remaining_ms = None
        if rec.state != RoomState.QUESTION_ACTIVE:
            raise CommandError("illegal_transition", "No question is running")
        await self._close_locked(rid, rec)

    async def _cmd_reveal(self, rid: str, rec: RoomRecord) -> None:
        if rec.state != RoomState.QUESTION_CLOSED or rec.revealed:
            raise CommandError("illegal_transition", "Nothing to reveal")
        await self._reveal_locked(rid, rec)

    async def _cmd_resume(self, rid: str, rec: RoomRecord) -> None:
        if rec.state != RoomState.PAUSED:
            raise CommandError("illegal_transition", "Game is not paused")
        now = now_ms()
        remaining = rec.paused_remaining_ms or 0
        paused_for = now - (rec.paused_at_ms or now)
        self._set_state(rec, RoomState.QUESTION_ACTIVE)
        rec.q_end_at_ms = now + remaining
        rec.q_start_ms += paused_for  # keep response times independent of the pause
        rec.paused_remaining_ms = None
        rec.paused_at_ms = None
        rec.pause_reason = ""
        await self._save(rec)
        await self.emit(
            rid,
            P.GAME_RESUMED,
            {"question_end_at": rec.q_end_at_ms, "server_time": now, "remaining_ms": remaining},
        )
        self.ensure_timer(rid)

    async def _cmd_kick(self, rid: str, rec: RoomRecord, kick: P.KickPayload) -> None:
        pid = kick.player_id
        if not await self.r.sismember(k_players(rid), pid):
            raise CommandError("player_not_found", "Player not found")
        nick = await self.r.hget(k_player(rid, pid), "nickname") or ""
        pipe = self.r.pipeline(transaction=False)
        pipe.sadd(k_banned(rid), nick.lower())
        pipe.sadd(k_kicked(rid), pid)
        pipe.expire(k_kicked(rid), get_settings().room_ttl_sec)
        pipe.expire(k_banned(rid), get_settings().room_ttl_sec)
        pipe.srem(k_players(rid), pid)
        pipe.zrem(k_lb(rid), pid)
        pipe.hset(k_player(rid, pid), "kicked", 1)
        pipe.hdel(k_conn(rid), pid)
        await pipe.execute()
        count = await self.r.scard(k_players(rid))
        await self.emit_many(
            rid,
            [
                (P.PLAYER_KICKED, {"reason": "kicked by host"}, f"p:{pid}"),
                ("kick", {}, f"kick:{pid}"),  # control message: closes the socket on any instance
                (P.PLAYER_LEFT, {"player_id": pid, "reason": "kicked", "count": count}, "all"),
            ],
        )
        if rec.state == RoomState.QUESTION_ACTIVE:
            await self._maybe_close_early(rid, rec)

    # ==== question flow =======================================================================
    async def _start_question_locked(self, rid: str, rec: RoomRecord, index: int) -> None:
        quiz = await self.get_quiz(rid)
        q = quiz["questions"][index]
        now = now_ms()
        self._set_state(rec, RoomState.QUESTION_ACTIVE)
        rec.q_index = index
        rec.q_start_ms = now
        rec.q_limit_ms = int(q["time_limit_sec"]) * 1000
        rec.q_end_at_ms = now + rec.q_limit_ms
        rec.revealed = False
        rec.paused_remaining_ms = None
        rec.paused_at_ms = None

        # Snapshot ranks so the reveal can show up/down arrows.
        ranking = await self._ranking(rid)
        pipe = self.r.pipeline(transaction=False)
        pipe.delete(k_prev(rid))
        if ranking:
            pipe.hset(k_prev(rid), mapping={pid: i + 1 for i, (pid, _) in enumerate(ranking)})
            pipe.expire(k_prev(rid), get_settings().room_ttl_sec)
        await pipe.execute()

        await self._save(rec)
        await self.emit(rid, P.QUESTION_SHOW, public_question(q, rec))
        self.ensure_timer(rid)

    async def _pause_locked(self, rid: str, rec: RoomRecord, reason: str) -> None:
        if rec.state != RoomState.QUESTION_ACTIVE:
            raise CommandError("illegal_transition", "Can only pause a running question")
        now = now_ms()
        self._set_state(rec, RoomState.PAUSED)
        rec.paused_at_ms = now
        rec.paused_remaining_ms = max(0, rec.q_end_at_ms - now)
        rec.pause_reason = reason
        await self._save(rec)
        await self.emit(
            rid,
            P.GAME_PAUSED,
            {"remaining_ms": rec.paused_remaining_ms, "reason": reason, "server_time": now},
        )

    async def _maybe_close_early(self, rid: str, rec: RoomRecord) -> None:
        if not rec.settings.auto_close or rec.state != RoomState.QUESTION_ACTIVE:
            return
        answered = await self.r.hlen(k_answers(rid, rec.q_index))
        total = await self.r.scard(k_players(rid))
        if total > 0 and answered >= total:
            await self.close_question(rid, rec.q_index)

    async def close_question(self, rid: str, q_index: int) -> bool:
        """Close the question (timer expiry or everyone answered). Idempotent across instances."""
        if not await self.r.set(k_closed(rid, q_index), self.instance_id, nx=True, ex=600):
            return False
        async with self.room_lock(rid):
            rec = await self.get_state(rid)
            if rec is None or rec.state != RoomState.QUESTION_ACTIVE or rec.q_index != q_index:
                await self.r.delete(k_closed(rid, q_index))  # state moved on (e.g. paused)
                return False
            await self._close_locked(rid, rec)
        return True

    async def _close_locked(self, rid: str, rec: RoomRecord) -> None:
        self._set_state(rec, RoomState.QUESTION_CLOSED)
        await self.r.set(k_closed(rid, rec.q_index), self.instance_id, nx=True, ex=600)
        await self._save(rec)
        answered = await self.r.hlen(k_answers(rid, rec.q_index))
        total = await self.r.scard(k_players(rid))
        await self.emit(
            rid,
            P.QUESTION_CLOSED,
            {"question_index": rec.q_index, "answered": answered, "total": total},
        )
        if rec.settings.auto_reveal:
            await asyncio.sleep(DRAIN_MS / 1000)  # let in-flight answer writes land
            await self._reveal_locked(rid, rec)

    async def _reveal_locked(self, rid: str, rec: RoomRecord) -> None:
        qn = rec.q_index
        quiz = await self.get_quiz(rid)
        q = quiz["questions"][qn]
        raw_answers = await self.r.hgetall(k_answers(rid, qn))
        answers = {pid: json.loads(v) for pid, v in raw_answers.items()}
        players = await self.r.smembers(k_players(rid))

        pipe = self.r.pipeline(transaction=False)
        for pid, a in answers.items():
            if pid in players and not a.get("applied") and a["points"]:
                pipe.zincrby(k_lb(rid), a["points"], pid)
        for pid in players - answers.keys():
            pipe.hset(k_player(rid, pid), "streak", 0)  # unanswered breaks the streak
        await pipe.execute()

        ranking = await self._ranking(rid)
        rank_of = {pid: i + 1 for i, (pid, _) in enumerate(ranking)}
        score_of = {pid: int(sc) for pid, sc in ranking}
        prev = await self.r.hgetall(k_prev(rid))

        pipe = self.r.pipeline(transaction=False)
        for pid in players:
            pipe.hget(k_player(rid, pid), "streak")
        streak_res = await pipe.execute()
        streak_of = dict(zip(players, (int(s or 0) for s in streak_res), strict=True))

        dist: dict[str, int] = {o["id"]: 0 for o in q["options"]}
        correct_n = 0
        ms_sum = 0
        for a in answers.values():
            for oid in a["chosen"]:
                dist[oid] = dist.get(oid, 0) + 1
            if a["correct"]:
                correct_n += 1
            ms_sum += a["ms"]
        avg_ms = int(ms_sum / len(answers)) if answers else 0
        common = {
            "question_index": qn,
            "question_id": q["id"],
            "correct_option_ids": q["correct_option_ids"],
            "explanation": q["explanation"],
        }
        stats = {
            "distribution": dist,
            "answered": len(answers),
            "total": len(players),
            "correct_count": correct_n,
            "avg_response_ms": avg_ms,
        }

        items: list[tuple[str, dict[str, Any], str]] = [
            (P.ANSWER_REVEAL, {**common, **stats, "role": "host"}, "host")
        ]
        for pid in players:
            a = answers.get(pid)
            rank = rank_of.get(pid)
            prev_rank = int(prev[pid]) if pid in prev else rank
            you = {
                "answered": a is not None,
                "chosen": a["chosen"] if a else [],
                "is_correct": bool(a and a["correct"]),
                "accuracy": a["accuracy"] if a else 0.0,
                "points": a["points"] if a else 0,
                "streak": streak_of.get(pid, 0),
                "score": score_of.get(pid, 0),
                "rank": rank,
                "rank_change": (prev_rank - rank) if (prev_rank and rank) else 0,
            }
            payload = {**common, "you": you, "role": "player"}
            if rec.settings.show_distribution:
                payload["distribution"] = dist
            items.append((P.ANSWER_REVEAL, payload, f"p:{pid}"))

        host_entries, total = await self._leaderboard_entries(rid)
        items.append(
            (P.LEADERBOARD_UPDATE, self._lb_payload(rec, host_entries, total, "reveal"), "host")
        )
        items.append(
            (
                P.LEADERBOARD_UPDATE,
                self._lb_payload(rec, host_entries[:5], total, "reveal"),
                "players",
            )
        )
        rec.revealed = True
        await self._save(rec)
        await self.emit_many(rid, items)

    @staticmethod
    def _lb_payload(
        rec: RoomRecord, entries: list[dict[str, Any]], total: int, phase: str
    ) -> dict[str, Any]:
        return {
            "question_index": rec.q_index,
            "phase": phase,
            "entries": entries,
            "total_players": total,
            "is_last": rec.q_index + 1 >= rec.total_questions,
        }

    # ==== answers =============================================================================
    async def submit_answer(self, rid: str, pid: str, payload: dict[str, Any]) -> None:
        try:
            body = P.AnswerPayload.model_validate(payload)
        except ValidationError as exc:
            raise CommandError("bad_payload", "Invalid answer payload") from exc

        async def ack(accepted: bool, reason: str = "") -> None:
            await self.emit(
                rid,
                P.ANSWER_ACK,
                {"question_id": body.question_id, "accepted": accepted, "reason": reason},
                f"p:{pid}",
            )

        rec = await self.get_state(rid)
        if rec is None:
            raise CommandError("room_not_found", "Room not found")
        if rec.state == RoomState.PAUSED:
            return await ack(False, "paused")
        if rec.state != RoomState.QUESTION_ACTIVE:
            return await ack(False, "not_active")
        quiz = await self.get_quiz(rid)
        q = quiz["questions"][rec.q_index]
        if body.question_id != q["id"]:
            return await ack(False, "wrong_question")

        now = now_ms()
        if now > rec.q_end_at_ms + get_settings().answer_grace_ms:
            return await ack(False, "late")

        valid_ids = {o["id"] for o in q["options"]}
        chosen = list(dict.fromkeys(body.option_ids))  # de-duplicate, keep order
        if not set(chosen) <= valid_ids:
            return await ack(False, "invalid_option")
        if q["type"] != "multi_select" and len(chosen) != 1:
            return await ack(False, "invalid_option")

        player = await self.r.hmget(k_player(rid, pid), "streak", "best_streak", "kicked")
        if player[0] is None or player[2] == "1":
            raise CommandError("not_a_player", "You are not in this game")
        prev_streak = int(player[0])

        result = score_answer(
            correct_ids=q["correct_option_ids"],
            chosen_ids=chosen,
            base_points=int(q["points"]),
            time_remaining_ms=max(0, rec.q_end_at_ms - now),
            time_limit_ms=rec.q_limit_ms,
            previous_streak=prev_streak,
            config=quiz.get("scoring"),
        )
        live = rec.settings.live_leaderboard
        record = {
            "chosen": chosen,
            "correct": result.is_correct,
            "accuracy": result.accuracy,
            "points": result.points,
            "ms": max(0, now - rec.q_start_ms),
            "at": now,
            "applied": live,
        }
        key = k_answers(rid, rec.q_index)
        if not await self.r.hsetnx(key, pid, json.dumps(record)):
            return await ack(False, "duplicate")  # first answer wins; duplicates are ignored

        # Re-check: if the question was already tallied while we were writing, withdraw it.
        after = await self.get_state(rid)
        keep = (
            after is not None
            and after.q_index == rec.q_index
            and (
                after.state in (RoomState.QUESTION_ACTIVE, RoomState.PAUSED)
                or (after.state == RoomState.QUESTION_CLOSED and not after.revealed)
            )
        )
        if not keep:
            await self.r.hdel(key, pid)
            return await ack(False, "late")

        pipe = self.r.pipeline(transaction=False)
        pipe.expire(key, get_settings().room_ttl_sec)
        for option_id in chosen:
            pipe.hincrby(k_dist(rid, rec.q_index), option_id, 1)
        pipe.expire(k_dist(rid, rec.q_index), get_settings().room_ttl_sec)
        pphash = k_player(rid, pid)
        pipe.hset(pphash, "streak", result.new_streak)
        if result.new_streak > int(player[1] or 0):
            pipe.hset(pphash, "best_streak", result.new_streak)
        pipe.hincrby(pphash, "answered", 1)
        if result.is_correct:
            pipe.hincrby(pphash, "correct", 1)
        if live and result.points:
            pipe.zincrby(k_lb(rid), result.points, pid)
        await pipe.execute()

        await ack(True)
        answered = await self.r.hlen(key)
        await self.emit(
            rid, P.QUESTION_TICK, {"answered": answered, "question_index": rec.q_index}, "host"
        )
        if live:
            entries, total = await self._leaderboard_entries(rid)
            await self.emit_many(
                rid,
                [
                    (P.LEADERBOARD_UPDATE, self._lb_payload(rec, entries, total, "live"), "host"),
                    (
                        P.LEADERBOARD_UPDATE,
                        self._lb_payload(rec, entries[:5], total, "live"),
                        "players",
                    ),
                ],
            )
        await self._maybe_close_early(rid, rec)

    # ==== timer ===============================================================================
    def ensure_timer(self, rid: str) -> None:
        task = self._timers.get(rid)
        if task is not None and not task.done():
            return
        self._timers[rid] = asyncio.create_task(self._timer_loop(rid))

    async def _timer_loop(self, rid: str) -> None:
        grace = get_settings().answer_grace_ms
        try:
            if not await self.r.set(k_timer(rid), self.instance_id, nx=True, px=LEASE_MS) and (
                await self.r.get(k_timer(rid)) != self.instance_id
            ):
                return  # another instance owns this room's timer
            while True:
                rec = await self.get_state(rid)
                if rec is None or rec.state != RoomState.QUESTION_ACTIVE:
                    return
                now = now_ms()
                if now >= rec.q_end_at_ms + grace:
                    await self.close_question(rid, rec.q_index)
                    return
                await self.r.set(k_timer(rid), self.instance_id, px=LEASE_MS)
                answered = await self.r.hlen(k_answers(rid, rec.q_index))
                base = {
                    "question_index": rec.q_index,
                    "remaining_ms": max(0, rec.q_end_at_ms - now),
                    "question_end_at": rec.q_end_at_ms,
                    "server_time": now,
                    "answered": answered,
                }
                host_payload = dict(base)
                if rec.settings.show_distribution:
                    host_payload["distribution"] = await self.r.hgetall(k_dist(rid, rec.q_index))
                await self.emit_many(
                    rid,
                    [(P.QUESTION_TICK, host_payload, "host"), (P.QUESTION_TICK, base, "players")],
                )
                wait = min(TICK_MS, rec.q_end_at_ms + grace - now) / 1000
                await asyncio.sleep(max(wait, 0.01))
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("timer loop crashed for room %s", rid)
        finally:
            if self._timers.get(rid) is asyncio.current_task():
                self._timers.pop(rid, None)
            with contextlib.suppress(Exception):
                if await self.r.get(k_timer(rid)) == self.instance_id:
                    await self.r.delete(k_timer(rid))

    # ==== finish & archive ====================================================================
    async def _final_me(self, rid: str, rec: RoomRecord, pid: str) -> dict[str, Any]:
        ranking = await self._ranking(rid)
        rank = next((i + 1 for i, (p, _) in enumerate(ranking) if p == pid), None)
        score = next((int(sc) for p, sc in ranking if p == pid), 0)
        f = await self.r.hmget(k_player(rid, pid), "correct", "answered", "best_streak", "nickname")
        correct, answered = int(f[0] or 0), int(f[1] or 0)
        return {
            "nickname": f[3],
            "rank": rank,
            "score": score,
            "correct": correct,
            "answered": answered,
            "total_questions": rec.total_questions,
            "accuracy_pct": round(100 * correct / rec.total_questions)
            if rec.total_questions
            else 0,
            "best_streak": int(f[2] or 0),
        }

    async def _finish_locked(self, rid: str, rec: RoomRecord, reason: str) -> None:
        if rec.state in (RoomState.QUESTION_ACTIVE, RoomState.PAUSED):
            # Ending mid-question: tally the question first so scores stay consistent.
            if rec.state == RoomState.PAUSED:
                self._set_state(rec, RoomState.QUESTION_ACTIVE)
            self._set_state(rec, RoomState.QUESTION_CLOSED)
            rec.settings.auto_reveal = True
            await self._save(rec)
            await asyncio.sleep(DRAIN_MS / 1000)
            await self._reveal_locked(rid, rec)
        elif rec.state == RoomState.QUESTION_CLOSED and not rec.revealed:
            await self._reveal_locked(rid, rec)

        self._set_state(rec, RoomState.FINISHED)
        rec.finished_ms = now_ms()
        await self._save(rec)

        podium = (await self._leaderboard_entries(rid, 3))[0]
        host_entries, total = await self._leaderboard_entries(rid)
        players = await self.r.smembers(k_players(rid))
        items: list[tuple[str, dict[str, Any], str]] = [
            (
                P.GAME_FINISHED,
                {
                    "reason": reason,
                    "podium": podium,
                    "leaderboard": host_entries,
                    "total_players": total,
                },
                "host",
            )
        ]
        for pid in players:
            items.append(
                (
                    P.GAME_FINISHED,
                    {
                        "reason": reason,
                        "podium": podium,
                        "leaderboard": host_entries[:5],
                        "total_players": total,
                        "me": await self._final_me(rid, rec, pid),
                    },
                    f"p:{pid}",
                )
            )
        await self.emit_many(rid, items)
        await self.r.delete(k_pin(rec.pin))
        timer = self._timers.pop(rid, None)
        if timer:
            timer.cancel()
        self._spawn(self._archive(rid))

    async def _archive(self, rid: str) -> None:
        """Persist results to Postgres, then mark the room ARCHIVED (kept briefly in Redis)."""
        try:
            rec = await self.get_state(rid)
            if rec is None:
                return
            quiz = await self.get_quiz(rid)
            ranking = await self._ranking(rid)
            all_pids = await self.r.smembers(k_players(rid))
            kicked = list(await self.r.smembers(k_kicked(rid)))
            sid = uuid.UUID(rec.session_id)
            async with get_sessionmaker()() as db:
                for i, (pid, score) in enumerate(ranking):
                    await db.execute(
                        update(SessionPlayer)
                        .where(SessionPlayer.id == uuid.UUID(pid))
                        .values(final_score=int(score), final_rank=i + 1)
                    )
                for pid in kicked:
                    await db.execute(
                        update(SessionPlayer)
                        .where(SessionPlayer.id == uuid.UUID(pid))
                        .values(banned=True)
                    )
                rows: list[Answer] = []
                for n, q in enumerate(quiz["questions"]):
                    for pid, raw in (await self.r.hgetall(k_answers(rid, n))).items():
                        if pid not in all_pids:
                            continue
                        a = json.loads(raw)
                        rows.append(
                            Answer(
                                session_id=sid,
                                player_id=uuid.UUID(pid),
                                question_id=uuid.UUID(q["id"]),
                                chosen_option_ids=a["chosen"],
                                is_correct=a["correct"],
                                response_ms=a["ms"],
                                points=a["points"],
                                accuracy=a["accuracy"],
                                answered_at=datetime.fromtimestamp(a["at"] / 1000, UTC),
                            )
                        )
                db.add_all(rows)
                gs = await db.get(GameSession, sid)
                # Remember how many questions were shown so reports include unanswered ones.
                played = max(0, min(rec.q_index + 1, rec.total_questions))
                await db.execute(
                    update(GameSession)
                    .where(GameSession.id == sid)
                    .values(
                        status="finished",
                        ended_at=datetime.now(UTC),
                        settings={
                            **((gs.settings if gs else None) or {}),
                            "questions_played": played,
                        },
                    )
                )
                await db.commit()
            rec = await self._require(rid)
            self._set_state(rec, RoomState.ARCHIVED)
            await self._save(rec)
            await self._expire_room(rid, rec)
        except Exception:
            log.exception("archive failed for room %s", rid)

    async def _expire_room(self, rid: str, rec: RoomRecord) -> None:
        """Keep final-state keys readable for a while so late reconnects still get results."""
        pids = await self.r.smembers(k_players(rid))
        keys = [
            k_state(rid),
            k_quiz(rid),
            k_players(rid),
            k_lb(rid),
            k_prev(rid),
            k_conn(rid),
            k_nicks(rid),
            k_banned(rid),
            k_devices(rid),
            k_seq(rid),
            k_kicked(rid),
        ]
        keys += [k_player(rid, p) for p in pids]
        for n in range(rec.total_questions):
            keys += [k_answers(rid, n), k_dist(rid, n)]
        pipe = self.r.pipeline(transaction=False)
        for key in keys:
            pipe.expire(key, FINISHED_KEEP_SEC)
        await pipe.execute()
