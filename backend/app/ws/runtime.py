"""Lazy construction of the ConnectionManager + RoomEngine pair, held on app.state.

Created lazily so REST-only tests (which skip the ASGI lifespan) still work, and so the Redis
client can be swapped (fakeredis) before first use.
"""

import asyncio

from fastapi import FastAPI, Request, WebSocket

from app.services.room_engine import RoomEngine
from app.ws.manager import ConnectionManager

_lock = asyncio.Lock()


async def ensure_engine(app: FastAPI) -> RoomEngine:
    engine: RoomEngine | None = getattr(app.state, "engine", None)
    if engine is not None:
        return engine
    async with _lock:
        engine = getattr(app.state, "engine", None)
        if engine is None:
            manager = ConnectionManager(app.state.redis)
            await manager.start()
            engine = RoomEngine(app.state.redis, manager)
            await engine.start()
            app.state.manager = manager
            app.state.engine = engine
    return engine


async def shutdown_engine(app: FastAPI) -> None:
    engine: RoomEngine | None = getattr(app.state, "engine", None)
    if engine is None:
        return
    await engine.shutdown()
    await app.state.manager.stop()
    del app.state.engine
    del app.state.manager


async def get_engine(request: Request) -> RoomEngine:
    return await ensure_engine(request.app)


async def get_engine_ws(ws: WebSocket) -> RoomEngine:
    return await ensure_engine(ws.app)
