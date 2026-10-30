"""JWT access/refresh token and password hashing utilities."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from ..config import get_settings

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"

BCRYPT_MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    """Hash a plain text password using bcrypt.

    Raises ``ValueError`` instead of silently truncating at bcrypt's 72-byte
    limit, which would let two different passwords share one hash.
    """

    password_bytes = password.encode("utf-8")
    if len(password_bytes) > BCRYPT_MAX_PASSWORD_BYTES:
        raise ValueError(
            f"Password must be at most {BCRYPT_MAX_PASSWORD_BYTES} bytes when UTF-8 encoded."
        )
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against the stored bcrypt hash."""

    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8")[:BCRYPT_MAX_PASSWORD_BYTES],
            hashed_password.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


def _encode_token(
    subject: str | int,
    token_type: str,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
    token_version: int = 0,
) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": token_type,
        "ver": token_version,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_access_token(
    subject: str | int,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
    *,
    token_version: int = 0,
) -> str:
    """Create a short-lived signed access token."""

    settings = get_settings()
    return _encode_token(
        subject,
        ACCESS_TOKEN_TYPE,
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes),
        extra_claims,
        token_version,
    )


def create_refresh_token(
    subject: str | int,
    expires_delta: timedelta | None = None,
    *,
    token_version: int = 0,
) -> str:
    """Create a long-lived signed refresh token."""

    settings = get_settings()
    return _encode_token(
        subject,
        REFRESH_TOKEN_TYPE,
        expires_delta or timedelta(days=settings.refresh_token_expire_days),
        token_version=token_version,
    )


def decode_token(token: str, *, expected_type: str | None = None) -> dict[str, Any] | None:
    """Decode and validate a token, optionally enforcing its type claim."""

    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except (jwt.PyJWTError, ValueError):
        return None

    if "sub" not in payload:
        return None

    if expected_type is not None and payload.get("type") != expected_type:
        return None

    return payload


def token_version(claims: dict[str, Any]) -> int:
    """Return the revocation counter carried by a token, defaulting to 0."""

    try:
        return int(claims.get("ver", 0))
    except (TypeError, ValueError):
        return -1


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decode an access token, rejecting refresh tokens."""

    return decode_token(token, expected_type=ACCESS_TOKEN_TYPE)