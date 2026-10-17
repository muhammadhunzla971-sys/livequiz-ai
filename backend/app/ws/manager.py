"""Local WebSocket connections plus a Redis pub/sub bridge for horizontal scaling.

Every outbound message goes through Redis (`room:{id}:events`) so any API instance can emit to
a room and every instance delivers to the sockets it holds. Wire format on the channel is
"<audience>|<envelope-json>" so the envelope is serialised once and forwarded verbatim.
Audiences: all | host | players | p:<player_id>
"""

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket
from redis.asyncio import Redis

from app.ws import protocol as P

log = logging.getLogger("livequiz.ws")

SEND_QUEUE_MAX = 256
CHANNEL_PATTERN = "room:*:events"


def channel_for(room_id: str) -> str:
    return f"room:{room_id}:events"


class TokenBucket:
    """Per-connection message rate limiter."""

    def __init__(self, rate_per_sec: float, burst: float | None = None) -> None:
        self.rate = rate_per_sec
        self.capacity = burst if burst is not None else rate_per_sec * 2
        self.tokens = self.capacity
        self.updated = time.monotonic()

    def allow(self) -> bool:
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
        self.updated = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False


@dataclass(eq=False)
class Connection:
    ws: WebSocket
    room_id: str
    role: str  # "host" | "player"
    player_id: str | None = None
    queue: asyncio.Queue[str | None] = field(default_factory=lambda: asyncio.Queue(SEND_QUEUE_MAX))
    writer: asyncio.Task[None] | None = None
    closed: bool = False

    def enqueue(self, text: str) -> bool:
        """Non-blocking; False means the client is too slow and should be dropped."""
        if self.closed:
            return False
        try:
            self.queue.put_nowait(text)
            return True
        except asyncio.QueueFull:
            return False

    async def _write_loop(self) -> None:
        try:
            while True:
                text = await self.queue.get()
                if text is None:
                    return
                await self.ws.send_text(text)
        except Exception:
            self.closed = True

    def start(self) -> None:
        self.writer = asyncio.create_task(self._write_loop())

    async def close(self, code: int = 1000, reason: str = "") -> None:
        if self.closed and self.writer is None:
            return
        self.closed = True
        with contextlib.suppress(Exception):
            self.queue.put_nowait(None)
        if self.writer is not None:
            # Let already-queued messages (e.g. player.kicked) flush before closing the socket.
            try:
                await asyncio.wait_for(asyncio.shield(self.writer), timeout=1.0)
            except (TimeoutError, asyncio.CancelledError, Exception):
                self.writer.cancel()
                with contextlib.suppress(BaseException):
                    await self.writer
            self.writer = None
        with contextlib.suppress(Exception):
            await self.ws.close(code=code, reason=reason[:100])


@dataclass
class RoomConnections:
    hosts: set[Connection] = field(default_factory=set)
    players: dict[str, Connection] = field(default_factory=dict)


class ConnectionManager:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._rooms: dict[str, RoomConnections] = {}
        self._listener: asyncio.Task[None] | None = None
        self._pubsub: Any = None

    # -- lifecycle ---------------------------------------------------------------------------
    async def start(self) -> None:
        self._pubsub = self._redis.pubsub()
        await self._pubsub.psubscribe(CHANNEL_PATTERN)
        self._listener = asyncio.create_task(self._listen())

    async def stop(self) -> None:
        if self._listener:
            self._listener.cancel()
            with contextlib.suppress(BaseException):
                await self._listener
        if self._pubsub is not None:
            with contextlib.suppress(Exception):
                await self._pubsub.aclose()

    async def close_all(self, code: int, reason: str) -> None:
        for room in list(self._rooms.values()):
            for conn in [*room.hosts, *room.players.values()]:
                await conn.close(code, reason)
        self._rooms.clear()

    # -- registration ------------------------------------------------------------------------
    def _room(self, room_id: str) -> RoomConnections:
        return self._rooms.setdefault(room_id, RoomConnections())

    async def add_host(self, conn: Connection) -> None:
        self._room(conn.room_id).hosts.add(conn)
        conn.start()

    async def add_player(self, conn: Connection) -> None:
        """A newer connection for the same player replaces the old one (e.g. page refresh)."""
        assert conn.player_id is not None
        room = self._room(conn.room_id)
        old = room.players.get(conn.player_id)
        room.players[conn.player_id] = conn
        conn.start()
        if old is not None and old is not conn:
            await old.close(P.CLOSE_REPLACED, "replaced by a newer connection")

    def remove(self, conn: Connection) -> bool:
        """Returns True if this connection was still the registered one for its slot."""
        room = self._rooms.get(conn.room_id)
        if room is None:
            return False
        current = False
        if conn.role == "host":
            current = conn in room.hosts
            room.hosts.discard(conn)
        elif conn.player_id is not None and room.players.get(conn.player_id) is conn:
            del room.players[conn.player_id]
            current = True
        if not room.hosts and not room.players:
            self._rooms.pop(conn.room_id, None)
        return current

    def local_player_ids(self, room_id: str) -> set[str]:
        room = self._rooms.get(room_id)
        return set(room.players) if room else set()

    def local_room_ids(self) -> list[str]:
        return list(self._rooms)

    async def disconnect_player(self, room_id: str, player_id: str, code: int, reason: str) -> None:
        room = self._rooms.get(room_id)
        conn = room.players.get(player_id) if room else None
        if conn is not None:
            await conn.close(code, reason)

    # -- publishing --------------------------------------------------------------------------
    async def _listen(self) -> None:
        assert self._pubsub is not None
        while True:
            try:
                msg = await self._pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("pubsub listener error; retrying")
                await asyncio.sleep(0.5)
                continue
            if msg is None:
                await asyncio.sleep(0)
                continue
            try:
                channel = msg["channel"]
                room_id = channel.split(":")[1]
                audience, _, envelope = msg["data"].partition("|")
                self._deliver(room_id, audience, envelope)
            except Exception:
                log.exception("failed to dispatch pubsub message")

    def _deliver(self, room_id: str, audience: str, envelope: str) -> None:
        room = self._rooms.get(room_id)
        if room is None:
            return
        targets: list[Connection] = []
        if audience in ("all", "host"):
            targets.extend(room.hosts)
        if audience in ("all", "players"):
            targets.extend(room.players.values())
        elif audience.startswith("p:"):
            conn = room.players.get(audience[2:])
            if conn is not None:
                targets.append(conn)
        elif audience.startswith("kick:"):
            conn = room.players.get(audience[5:])
            if conn is not None:
                asyncio.create_task(conn.close(P.CLOSE_KICKED, "kicked by host"))
            return
        for conn in targets:
            if not conn.enqueue(envelope):
                # Slow consumer: drop it rather than let memory grow without bound.
                asyncio.create_task(conn.close(P.CLOSE_OVERLOADED, "too slow"))
