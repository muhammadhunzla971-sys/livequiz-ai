"""WebSocket endpoints: /ws/host/{room_id} and /ws/player/{room_id}.

Auth is a token in the query string (browsers can't set headers on WebSocket). Teachers use
their access JWT; players use the token returned by POST /api/join. Roles are verified against
server state, never trusted from the client.
"""

import asyncio
import contextlib
import logging
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.core.config import get_settings
from app.core.security import TokenError, decode_token
from app.services.room_engine import CommandError, RoomEngine
from app.services.state_machine import IllegalTransitionError
from app.ws import protocol as P
from app.ws.manager import Connection, TokenBucket
from app.ws.runtime import get_engine_ws

log = logging.getLogger("livequiz.ws")
router = APIRouter()


async def _reject(ws: WebSocket, code: int, reason: str) -> None:
    await ws.accept()
    await ws.close(code=code, reason=reason)


async def _send_error(engine: RoomEngine, rid: str, to: str, code: str, message: str = "") -> None:
    await engine.emit(rid, P.ERROR, {"code": code, "message": message or code}, to)


async def _read_loop(
    ws: WebSocket, conn: Connection, engine: RoomEngine, rid: str, allowed: frozenset[str]
) -> None:
    s = get_settings()
    bucket = TokenBucket(s.ws_max_msgs_per_sec)
    to = "host" if conn.role == "host" else f"p:{conn.player_id}"
    while True:
        text = await ws.receive_text()
        if len(text) > s.ws_max_payload_bytes:
            await conn.close(P.CLOSE_TOO_BIG, "message too large")
            return
        if not bucket.allow():
            await conn.close(P.CLOSE_RATE_LIMITED, "slow down")
            return
        try:
            msg = P.ClientMessage.model_validate_json(text)
        except ValidationError:
            await _send_error(engine, rid, to, "bad_message", "Malformed message")
            continue
        if msg.type not in allowed:
            await _send_error(engine, rid, to, "forbidden", f"{msg.type} not allowed")
            continue
        try:
            await _dispatch(conn, engine, rid, msg)
        except CommandError as exc:
            await _send_error(engine, rid, to, exc.code, exc.message)
        except IllegalTransitionError as exc:
            await _send_error(engine, rid, to, "illegal_transition", str(exc))
        except ValidationError:
            await _send_error(engine, rid, to, "bad_payload", "Invalid payload")
        except Exception:
            log.exception("handler failed for %s", msg.type)
            await _send_error(engine, rid, to, "internal", "Something went wrong")


async def _dispatch(conn: Connection, engine: RoomEngine, rid: str, msg: P.ClientMessage) -> None:
    payload: dict[str, Any] = msg.payload
    if msg.type == P.PING:
        env = await engine.make_envelope(
            rid, P.PONG, {"client_ts": payload.get("client_ts"), "server_time": _now()}
        )
        conn.enqueue(env)
    elif conn.role == "host":
        await engine.handle_host(rid, msg.type, payload)
    elif msg.type == P.PLAYER_ANSWER:
        assert conn.player_id is not None
        await engine.submit_answer(rid, conn.player_id, payload)
    elif msg.type == P.PLAYER_JOIN:
        # Joining happens over REST; over WS this just asks for a fresh snapshot.
        assert conn.player_id is not None
        snap = await engine.build_snapshot(rid, "player", conn.player_id)
        await engine.emit(rid, P.ROOM_STATE, snap, f"p:{conn.player_id}")


def _now() -> int:
    from app.services.room_engine import now_ms

    return now_ms()


@router.websocket("/ws/host/{room_id}")
async def host_ws(ws: WebSocket, room_id: str, token: str = Query(default="")) -> None:
    engine = await get_engine_ws(ws)
    try:
        claims = decode_token(token, "access")
    except TokenError:
        return await _reject(ws, P.CLOSE_UNAUTHORIZED, "unauthorized")
    rec = await engine.get_state(room_id)
    if rec is None:
        return await _reject(ws, P.CLOSE_NOT_FOUND, "room not found")
    if rec.host_id != claims["sub"]:
        return await _reject(ws, P.CLOSE_FORBIDDEN, "not the host of this room")

    await ws.accept()
    conn = Connection(ws=ws, room_id=room_id, role="host")
    await engine.manager.add_host(conn)
    try:
        await engine.host_connected(room_id)
        await _read_loop(ws, conn, engine, room_id, P.HOST_MESSAGES)
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("host socket error")
    finally:
        engine.manager.remove(conn)
        await conn.close()


@router.websocket("/ws/player/{room_id}")
async def player_ws(ws: WebSocket, room_id: str, token: str = Query(default="")) -> None:
    engine = await get_engine_ws(ws)
    try:
        claims = decode_token(token, "player")
    except TokenError:
        return await _reject(ws, P.CLOSE_UNAUTHORIZED, "unauthorized")
    if claims.get("room") != room_id:
        return await _reject(ws, P.CLOSE_FORBIDDEN, "token is for another room")
    pid = str(claims["sub"])
    reason = await engine.player_can_connect(room_id, pid)
    if reason is not None:
        code = P.CLOSE_KICKED if reason == "kicked" else P.CLOSE_NOT_FOUND
        return await _reject(ws, code, reason)

    await ws.accept()
    conn = Connection(ws=ws, room_id=room_id, role="player", player_id=pid)
    await engine.manager.add_player(conn)
    try:
        await engine.player_connected(room_id, pid)
        await _read_loop(ws, conn, engine, room_id, P.PLAYER_MESSAGES)
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("player socket error")
    finally:
        was_current = engine.manager.remove(conn)
        await conn.close()
        if was_current:
            with contextlib.suppress(Exception):
                await engine.player_disconnected(room_id, pid)
            await asyncio.sleep(0)
