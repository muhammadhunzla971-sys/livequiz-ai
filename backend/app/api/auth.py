from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.net import client_ip
from app.core.rate_limit import enforce, hit
from app.core.security import (
    create_access_token,
    hash_password,
    hash_token,
    new_refresh_token,
    verify_password,
)
from app.db.base import utcnow
from app.models import RefreshToken, User
from app.schemas.auth import LoginIn, RefreshIn, RegisterIn, TokenPair, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Verified against when the email is unknown so response time doesn't reveal which emails exist.
_DUMMY_HASH = hash_password("dummy-password-for-timing")


async def _issue_tokens(db: AsyncSession, user: User) -> TokenPair:
    s = get_settings()
    refresh = new_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(refresh),
            expires_at=utcnow() + timedelta(days=s.refresh_token_days),
        )
    )
    await db.commit()
    return TokenPair(
        access_token=create_access_token(user.id),
        refresh_token=refresh,
        expires_in=s.access_token_minutes * 60,
    )


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterIn, request: Request, db: DbSession) -> TokenPair:
    await enforce(request.app.state.redis, f"register:{client_ip(request)}", 10, 3600)
    email = body.email.lower()
    existing = await db.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(
        email=email,
        password_hash=hash_password(body.password),
        display_name=body.display_name.strip(),
    )
    db.add(user)
    await db.flush()
    return await _issue_tokens(db, user)


@router.post("/login", response_model=TokenPair)
async def login(body: LoginIn, request: Request, db: DbSession) -> TokenPair:
    redis = request.app.state.redis
    email = body.email.lower()
    await enforce(redis, f"login-ip:{client_ip(request)}", 30, 60)
    # Wrong passwords for one account are capped, so guessing can't be spread over time either.
    fails = await redis.get(f"rl:login-fail:{email}")
    if fails is not None and int(fails) >= 8:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many failed logins. Try again in 15 minutes.",
            headers={"Retry-After": "900"},
        )
    user = await db.scalar(select(User).where(User.email == email))
    ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not ok or not user.is_active:
        await hit(redis, f"login-fail:{email}", 10_000, 900)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    await redis.delete(f"rl:login-fail:{email}")
    return await _issue_tokens(db, user)


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshIn, request: Request, db: DbSession) -> TokenPair:
    """Rotate: the presented refresh token is revoked and a new pair is issued."""
    await enforce(request.app.state.redis, f"refresh:{client_ip(request)}", 60, 60)
    row = await db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(body.refresh_token))
    )
    now = utcnow()
    if (
        row is None
        or row.revoked_at is not None
        or row.expires_at.replace(tzinfo=row.expires_at.tzinfo or now.tzinfo) < now
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    user = await db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    row.revoked_at = now
    return await _issue_tokens(db, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshIn, db: DbSession) -> None:
    row = await db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(body.refresh_token))
    )
    if row is not None and row.revoked_at is None:
        row.revoked_at = utcnow()
        await db.commit()


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> User:
    return user
