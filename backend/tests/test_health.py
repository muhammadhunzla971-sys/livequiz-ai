import httpx


async def test_health(client: httpx.AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-request-id"]


async def test_ready_checks_dependencies(client: httpx.AsyncClient) -> None:
    r = await client.get("/ready")
    assert r.status_code == 200
    assert r.json() == {"postgres": "ok", "redis": "ok"}
