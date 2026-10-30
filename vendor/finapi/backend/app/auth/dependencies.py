"""FastAPI dependencies for database access and authentication."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from finance_core.db.connection import connect
from finance_core.db.users import AppUser, get_user_by_id

from ..config import get_settings
from .jwt_handler import decode_access_token
from .jwt_handler import token_version as claimed_token_version

security = HTTPBearer(auto_error=True)


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Provide one database connection per request.

    The schema is migrated once at startup, never here. ``check_same_thread``
    is disabled because FastAPI may run the dependency and the endpoint in
    different thread-pool threads; the connection itself is request-scoped.

    Repositories do not commit. The request is the transaction boundary: a
    successful response commits, an exception rolls back.
    """

    connection = connect(get_settings().database_path, check_same_thread=False)
    try:
        yield connection
    except BaseException:
        connection.rollback()
        raise
    else:
        connection.commit()
    finally:
        connection.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: sqlite3.Connection = Depends(get_db),
) -> AppUser:
    """Validate the Bearer token and return the authenticated user."""

    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise _unauthorized("Token tidak valid atau sudah kedaluwarsa.")

    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError):
        raise _unauthorized("Subjek token tidak valid.")

    user = get_user_by_id(db, user_id)
    if user is None:
        raise _unauthorized("Pengguna tidak ditemukan.")

    if claimed_token_version(payload) != user.token_version:
        raise _unauthorized("Token sudah tidak berlaku. Silakan login kembali.")

    return user


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )