import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api import auth, quizzes, reports, sessions
from app.core import metrics
from app.core.config import get_settings
from app.core.logging import request_id_var, setup_logging
from app.core.redis import make_redis
from app.db.session import dispose_engine, get_sessionmaker
from app.ws import endpoints as ws_endpoints
from app.ws.runtime import ensure_engine, shutdown_engine

log = logging.getLogger("livequiz")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    s = get_settings()
    setup_logging(s.log_level)
    if s.is_prod and (problems := s.production_problems()):
        raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))
    if not hasattr(app.state, "redis"):
        app.state.redis = make_redis(s)
    get_sessionmaker()  # lazily initialises the engine unless one was already configured
    await ensure_engine(app)
    log.info("startup complete", extra={"env": s.env})
    yield
    await shutdown_engine(app)
    await app.state.redis.aclose()
    await dispose_engine()
    log.info("shutdown complete")


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title=s.app_name, version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        rid = (request.headers.get("x-request-id") or "")[:64] or uuid.uuid4().hex[:12]
        request_id_var.set(rid)
        start = time.perf_counter()
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > s.max_body_bytes:
            return JSONResponse({"detail": "Request body too large"}, status_code=413)
        try:
            response = await call_next(request)
        except Exception:
            log.exception("unhandled error", extra={"path": request.url.path})
            response = JSONResponse(
                {"detail": "Something went wrong on our side. Please try again."},
                status_code=500,
            )
        response.headers["X-Request-ID"] = rid
        for k, v in SECURITY_HEADERS.items():
            response.headers[k] = v
        elapsed = time.perf_counter() - start
        metrics.inc("livequiz_http_requests_total", status=f"{response.status_code // 100}xx")
        metrics.inc("livequiz_http_request_seconds_total", elapsed)
        if s.is_prod:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        log.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return response

    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/metrics", tags=["ops"], include_in_schema=False)
    async def metrics_endpoint(request: Request) -> Response:
        token = get_settings().metrics_token
        if token and request.headers.get("authorization") != f"Bearer {token}":
            raise HTTPException(401, "Metrics token required")
        manager = getattr(request.app.state, "manager", None)
        rooms = manager.local_room_ids() if manager else []
        players = sum(len(manager.local_player_ids(r)) for r in rooms) if manager else 0
        text = metrics.render(
            {"livequiz_active_rooms": len(rooms), "livequiz_connected_players": players}
        )
        return Response(text, media_type="text/plain; version=0.0.4")

    @app.get("/ready", tags=["ops"])
    async def ready(request: Request, response: Response) -> dict[str, str]:
        checks: dict[str, str] = {}
        try:
            async with get_sessionmaker()() as db:
                await db.execute(text("SELECT 1"))
            checks["postgres"] = "ok"
        except Exception:
            checks["postgres"] = "down"
        try:
            await request.app.state.redis.ping()
            checks["redis"] = "ok"
        except Exception:
            checks["redis"] = "down"
        if "down" in checks.values():
            response.status_code = 503
        return checks

    app.include_router(auth.router)
    app.include_router(quizzes.router)
    app.include_router(sessions.router)
    app.include_router(reports.router)
    app.include_router(ws_endpoints.router)
    return app


app = create_app()
