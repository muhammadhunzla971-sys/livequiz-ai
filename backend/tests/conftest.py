import os
from collections.abc import AsyncIterator

os.environ.setdefault("JWT_SECRET", "test-secret-key-at-least-16-chars")
os.environ.setdefault("ENV", "test")

import fakeredis.aioredis  # noqa: E402
import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db import session as db_session  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import *  # noqa: E402,F401,F403


@pytest_asyncio.fixture
async def app(tmp_path):  # type: ignore[no-untyped-def]
    get_settings.cache_clear()
    engine = db_session.init_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    application = create_app()
    application.state.redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield application
    await application.state.redis.aclose()
    await db_session.dispose_engine()


@pytest_asyncio.fixture
async def client(app) -> AsyncIterator[httpx.AsyncClient]:  # type: ignore[no-untyped-def]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def teacher_creds() -> dict[str, str]:
    return {
        "email": "teacher@example.com",
        "password": "correct-horse-battery",
        "display_name": "Ms. T",
    }


@pytest_asyncio.fixture
async def auth_headers(client: httpx.AsyncClient, teacher_creds: dict[str, str]) -> dict[str, str]:
    r = await client.post("/api/auth/register", json=teacher_creds)
    assert r.status_code == 201
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(autouse=True)
def _fast_backoff(monkeypatch):  # type: ignore[no-untyped-def]
    """Skip real exponential-backoff sleeps in retry logic."""
    import asyncio

    real_sleep = asyncio.sleep

    async def fast(_seconds: float) -> None:
        await real_sleep(0)

    monkeypatch.setattr("app.llm.retry.asyncio.sleep", fast)


@pytest.fixture
def llm(app):  # type: ignore[no-untyped-def]
    from app.api.quizzes import get_llm
    from tests.fakes import FakeLLM

    fake = FakeLLM()
    app.dependency_overrides[get_llm] = lambda: fake
    return fake
