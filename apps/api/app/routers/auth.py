from __future__ import annotations

import jwt
from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from app.core.config import get_settings
from app.core.deps import DB, CurrentUser
from app.core.ratelimit import limiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models import User
from app.schemas.auth import LoginIn, RegisterIn, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])
REFRESH_COOKIE = "refresh_token"


def _set_refresh_cookie(response: Response, token: str) -> None:
    s = get_settings()
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=s.refresh_token_days * 86400,
        httponly=True,
        secure=s.cookie_secure,
        samesite="none" if s.cookie_secure else "lax",
        domain=s.cookie_domain,
        path="/auth",
    )


@router.post("/register", response_model=TokenOut, status_code=201)
@limiter.limit("5/minute")
async def register(request: Request, response: Response, body: RegisterIn, db: DB):
    email = body.email.lower()
    if (await db.execute(select(User).where(User.email == email))).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(email=email, password_hash=hash_password(body.password))
    db.add(user)
    await db.commit()
    _set_refresh_cookie(response, create_refresh_token(user.id, user.refresh_token_version))
    return TokenOut(access_token=create_access_token(user.id))


@router.post("/login", response_model=TokenOut)
@limiter.limit("10/minute")
async def login(request: Request, response: Response, body: LoginIn, db: DB):
    user = (
        await db.execute(select(User).where(User.email == body.email.lower()))
    ).scalar_one_or_none()
    # Constant-ish time: always verify against a hash to avoid user enumeration by timing.
    ok = verify_password(body.password, user.password_hash if user else hash_password("x" * 12))
    if not user or not ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    _set_refresh_cookie(response, create_refresh_token(user.id, user.refresh_token_version))
    return TokenOut(access_token=create_access_token(user.id))


@router.post("/refresh", response_model=TokenOut)
@limiter.limit("30/minute")
async def refresh(request: Request, response: Response, db: DB):
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No refresh token")
    try:
        payload = decode_token(raw, "refresh")
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token") from None
    user = await db.get(User, payload["sub"])
    if user is None or payload.get("ver") != user.refresh_token_version:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token revoked")
    _set_refresh_cookie(
        response, create_refresh_token(user.id, user.refresh_token_version)
    )  # rotate
    return TokenOut(access_token=create_access_token(user.id))


@router.post("/logout", status_code=204)
async def logout(response: Response, user: CurrentUser, db: DB):
    user.refresh_token_version += 1  # revokes every outstanding refresh token
    await db.commit()
    response.delete_cookie(REFRESH_COOKIE, path="/auth")


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser):
    return user
