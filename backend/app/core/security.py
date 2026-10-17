import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import get_settings

_hasher = PasswordHasher()


class TokenError(Exception):
    """Raised when a JWT is invalid, expired, or of the wrong type."""


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def hash_token(token: str) -> str:
    """SHA-256 of a high-entropy token; safe to store (tokens are random, not passwords)."""
    return hashlib.sha256(token.encode()).hexdigest()


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def _encode(claims: dict[str, Any], expires: timedelta) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {**claims, "iat": now, "exp": now + expires, "jti": uuid.uuid4().hex}
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def create_access_token(user_id: uuid.UUID) -> str:
    s = get_settings()
    return _encode(
        {"sub": str(user_id), "typ": "access", "role": "teacher"},
        timedelta(minutes=s.access_token_minutes),
    )


def create_player_token(room_id: str, player_id: str) -> str:
    s = get_settings()
    return _encode(
        {"sub": player_id, "room": room_id, "typ": "player", "role": "player"},
        timedelta(hours=s.player_token_hours),
    )


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    s = get_settings()
    try:
        data = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    if data.get("typ") != expected_type:
        raise TokenError("wrong token type")
    return data
