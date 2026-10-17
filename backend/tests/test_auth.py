import httpx

from app.core.security import create_access_token, decode_token, hash_password, verify_password


async def test_register_login_me(client: httpx.AsyncClient, teacher_creds: dict[str, str]) -> None:
    r = await client.post("/api/auth/register", json=teacher_creds)
    assert r.status_code == 201
    assert {"access_token", "refresh_token"} <= r.json().keys()

    r = await client.post(
        "/api/auth/login",
        json={"email": teacher_creds["email"], "password": teacher_creds["password"]},
    )
    assert r.status_code == 200
    me = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["email"] == teacher_creds["email"]
    assert "password" not in me.text


async def test_duplicate_email_rejected(
    client: httpx.AsyncClient, teacher_creds: dict[str, str]
) -> None:
    await client.post("/api/auth/register", json=teacher_creds)
    r = await client.post(
        "/api/auth/register", json={**teacher_creds, "email": "TEACHER@example.com"}
    )
    assert r.status_code == 409


async def test_weak_password_rejected(
    client: httpx.AsyncClient, teacher_creds: dict[str, str]
) -> None:
    r = await client.post("/api/auth/register", json={**teacher_creds, "password": "short"})
    assert r.status_code == 422


async def test_wrong_password_and_unknown_user_same_error(
    client: httpx.AsyncClient, teacher_creds: dict[str, str]
) -> None:
    await client.post("/api/auth/register", json=teacher_creds)
    bad = await client.post(
        "/api/auth/login", json={"email": teacher_creds["email"], "password": "nope-nope-nope"}
    )
    ghost = await client.post(
        "/api/auth/login", json={"email": "ghost@example.com", "password": "nope-nope-nope"}
    )
    assert bad.status_code == ghost.status_code == 401
    assert bad.json() == ghost.json()


async def test_me_requires_valid_token(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/auth/me")).status_code == 401
    r = await client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401


async def test_refresh_rotates_and_old_token_dies(
    client: httpx.AsyncClient, teacher_creds: dict[str, str]
) -> None:
    first = (await client.post("/api/auth/register", json=teacher_creds)).json()
    r = await client.post("/api/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert r.status_code == 200
    second = r.json()
    assert second["refresh_token"] != first["refresh_token"]
    reuse = await client.post("/api/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert reuse.status_code == 401


async def test_logout_revokes_refresh(
    client: httpx.AsyncClient, teacher_creds: dict[str, str]
) -> None:
    tokens = (await client.post("/api/auth/register", json=teacher_creds)).json()
    assert (
        await client.post("/api/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    ).status_code == 204
    r = await client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 401


def test_password_hash_roundtrip() -> None:
    h = hash_password("s3cret-pass")
    assert h != "s3cret-pass"
    assert verify_password("s3cret-pass", h)
    assert not verify_password("other", h)
    assert not verify_password("x", "not-a-hash")


def test_token_type_enforced() -> None:
    import uuid

    import pytest

    from app.core.security import TokenError

    token = create_access_token(uuid.uuid4())
    assert decode_token(token, "access")["typ"] == "access"
    with pytest.raises(TokenError):
        decode_token(token, "player")
