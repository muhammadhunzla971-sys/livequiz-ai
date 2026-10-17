import logging

import pytest
from starlette.requests import Request

from app.core.config import Settings, get_settings
from app.core.logging import RedactSecrets
from app.core.net import client_ip


def _req(headers: dict[str, str], host: str = "10.0.0.9") -> Request:
    scope = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (host, 1234),
    }
    return Request(scope)


def test_forwarded_header_ignored_without_trusted_proxy(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "0")
    get_settings.cache_clear()
    assert client_ip(_req({"X-Forwarded-For": "1.2.3.4"})) == "10.0.0.9"


def test_forwarded_header_uses_proxy_appended_entry(monkeypatch):
    monkeypatch.setenv("TRUSTED_PROXY_HOPS", "1")
    get_settings.cache_clear()
    # The client forged 6.6.6.6; the one proxy we trust appended the real address last.
    assert client_ip(_req({"X-Forwarded-For": "6.6.6.6, 203.0.113.7"})) == "203.0.113.7"
    get_settings.cache_clear()


def test_log_filter_redacts_tokens():
    rec = logging.LogRecord(
        "uvicorn.error",
        logging.INFO,
        "",
        0,
        '%s - "WebSocket %s" [accepted]',
        ("1.1.1.1:1", "/ws/player/r?token=abc.def.ghi&x=1"),
        None,
    )
    assert RedactSecrets().filter(rec)
    assert "abc.def.ghi" not in rec.getMessage()
    assert "token=[redacted]&x=1" in rec.getMessage()


def test_production_config_checks():
    bad = Settings(env="prod", jwt_secret="change-me-in-production", cors_origins="*")
    assert len(bad.production_problems()) == 3
    good = Settings(
        env="prod",
        jwt_secret="x" * 40,
        cors_origins="https://quiz.example.com",
        frontend_url="https://quiz.example.com",
    )
    assert good.production_problems() == []


@pytest.mark.asyncio
async def test_login_is_rate_limited_per_account(client):
    await client.post(
        "/api/auth/register",
        json={"email": "t@x.com", "password": "correct-horse-1", "display_name": "T"},
    )
    codes = []
    for _ in range(10):
        r = await client.post(
            "/api/auth/login", json={"email": "t@x.com", "password": "wrong-password"}
        )
        codes.append(r.status_code)
    assert codes[:8] == [401] * 8
    assert codes[8] == 429
    # Even the right password is refused while locked, so guessing can't continue.
    ok = await client.post(
        "/api/auth/login", json={"email": "t@x.com", "password": "correct-horse-1"}
    )
    assert ok.status_code == 429


@pytest.mark.asyncio
async def test_successful_login_clears_failures(client):
    await client.post(
        "/api/auth/register",
        json={"email": "u@x.com", "password": "correct-horse-1", "display_name": "U"},
    )
    for _ in range(3):
        await client.post("/api/auth/login", json={"email": "u@x.com", "password": "nope-nope-1"})
    assert (
        await client.post(
            "/api/auth/login", json={"email": "u@x.com", "password": "correct-horse-1"}
        )
    ).status_code == 200


@pytest.mark.asyncio
async def test_oversized_body_rejected(client):
    r = await client.post(
        "/api/auth/login", content=b"x" * 2_000_000, headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 413


@pytest.mark.asyncio
async def test_register_is_rate_limited(client):
    last = 0
    for i in range(12):
        r = await client.post(
            "/api/auth/register",
            json={"email": f"n{i}@x.com", "password": "correct-horse-1", "display_name": "N"},
        )
        last = r.status_code
    assert last == 429


@pytest.mark.asyncio
async def test_metrics_endpoint_counts_requests(client):
    await client.get("/health")
    r = await client.get("/metrics")
    assert r.status_code == 200
    assert 'livequiz_http_requests_total{status="2xx"}' in r.text
    assert "livequiz_active_rooms 0" in r.text


@pytest.mark.asyncio
async def test_metrics_requires_token_when_configured(client, monkeypatch):
    monkeypatch.setenv("METRICS_TOKEN", "s3cret-metrics-token")
    get_settings.cache_clear()
    assert (await client.get("/metrics")).status_code == 401
    ok = await client.get("/metrics", headers={"Authorization": "Bearer s3cret-metrics-token"})
    assert ok.status_code == 200
    get_settings.cache_clear()


def test_database_url_is_normalised_for_managed_hosts():
    s = Settings(database_url="postgres://u:p@host:5432/db?sslmode=require")
    assert s.database_url == "postgresql+asyncpg://u:p@host:5432/db?ssl=require"
    ok = "postgresql+asyncpg://u:p@h/db"
    assert Settings(database_url=ok).database_url == ok
    assert Settings(database_url="sqlite+aiosqlite:///x.db").database_url.startswith("sqlite")
