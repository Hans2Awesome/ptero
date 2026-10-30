"""Authentication routes."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request, status

from finance_core.db.users import (
    AppUser,
    bump_token_version,
    create_mobile_user,
    get_user_by_email,
    get_user_by_id,
)

from ..auth.dependencies import get_current_user, get_db
from ..auth.jwt_handler import (
    REFRESH_TOKEN_TYPE,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from ..auth.jwt_handler import (
    token_version as claimed_token_version,
)
from ..auth.rate_limit import login_limiter, refresh_limiter, register_limiter
from ..config import get_settings
from ..models.schemas import (
    RefreshRequest,
    TokenResponse,
    UserLogin,
    UserRegister,
    UserResponse,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def _client_host(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _rate_limit_key(request: Request, email: str) -> str:
    return f"{_client_host(request)}:{email.strip().lower()}"


def _build_token_response(user: AppUser) -> TokenResponse:
    settings = get_settings()
    return TokenResponse(
        access_token=create_access_token(subject=user.id, token_version=user.token_version),
        refresh_token=create_refresh_token(subject=user.id, token_version=user.token_version),
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserResponse.model_validate(user),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(
    payload: UserRegister,
    request: Request,
    db: sqlite3.Connection = Depends(get_db),
) -> TokenResponse:
    """Register a new user account."""

    limiter_key = f"register:{_client_host(request)}"
    if register_limiter.is_blocked(limiter_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Terlalu banyak pendaftaran dari alamat ini. Coba lagi nanti.",
            headers={"Retry-After": "3600"},
        )
    register_limiter.register_failure(limiter_key)

    if get_user_by_email(db, payload.email) is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email sudah terdaftar.",
        )

    user = create_mobile_user(
        db,
        email=payload.email,
        password_hash=hash_password(payload.password),
        first_name=payload.first_name,
        timezone=payload.timezone,
        currency=payload.currency,
    )
    return _build_token_response(user)


@router.post("/login", response_model=TokenResponse)
def login(
    payload: UserLogin,
    request: Request,
    db: sqlite3.Connection = Depends(get_db),
) -> TokenResponse:
    """Log in with email and password, with brute-force throttling."""

    limiter_key = _rate_limit_key(request, payload.email)
    if login_limiter.is_blocked(limiter_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Terlalu banyak percobaan login. Coba lagi dalam 15 menit.",
            headers={"Retry-After": "900"},
        )

    user = get_user_by_email(db, payload.email)
    if user is None or not user.password_hash or not verify_password(
        payload.password, user.password_hash
    ):
        login_limiter.register_failure(limiter_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email atau kata sandi salah.",
        )

    login_limiter.reset(limiter_key)
    return _build_token_response(user)


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    payload: RefreshRequest,
    request: Request,
    db: sqlite3.Connection = Depends(get_db),
) -> TokenResponse:
    """Exchange a valid refresh token for a new token pair."""

    limiter_key = f"refresh:{_client_host(request)}"
    if refresh_limiter.is_blocked(limiter_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Terlalu banyak percobaan refresh. Coba lagi nanti.",
            headers={"Retry-After": "900"},
        )

    claims = decode_token(payload.refresh_token, expected_type=REFRESH_TOKEN_TYPE)
    if claims is None:
        refresh_limiter.register_failure(limiter_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token tidak valid atau sudah kedaluwarsa.",
        )

    try:
        user_id = int(claims["sub"])
    except (KeyError, ValueError):
        refresh_limiter.register_failure(limiter_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token tidak valid atau sudah kedaluwarsa.",
        ) from None

    user = get_user_by_id(db, user_id)
    if user is None:
        refresh_limiter.register_failure(limiter_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Pengguna tidak ditemukan.",
        )
    if claimed_token_version(claims) != user.token_version:
        refresh_limiter.register_failure(limiter_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token sudah tidak berlaku. Silakan login kembali.",
        )

    refresh_limiter.reset(limiter_key)
    return _build_token_response(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    current_user: AppUser = Depends(get_current_user),
    db: sqlite3.Connection = Depends(get_db),
) -> None:
    """Revoke every access and refresh token issued to the current user."""

    bump_token_version(db, user_id=current_user.id)


@router.get("/me", response_model=UserResponse)
def get_profile(current_user: AppUser = Depends(get_current_user)) -> UserResponse:
    """Get the profile of the currently logged-in user."""

    return UserResponse.model_validate(current_user)