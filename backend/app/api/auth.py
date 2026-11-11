"""Admin login, logout and current user."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import as_utc, get_session, utcnow
from app.models import AdminUser, UserSession
from app.security import (
    AuthContext,
    burn_verification,
    clear_session_cookie,
    create_session,
    current_auth,
    login_limiter,
    set_session_cookie,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserResponse(BaseModel):
    username: str
    last_login_at: datetime | None


class OkResponse(BaseModel):
    ok: bool = True


@router.post("/login", response_model=UserResponse)
def login(body: LoginRequest, response: Response, db: Session = Depends(get_session)) -> UserResponse:
    username = body.username.strip().lower()
    retry_after = login_limiter.retry_after(username)
    if retry_after:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed login attempts. Try again in {max(1, round(retry_after / 60))} minute(s).",
            headers={"Retry-After": str(retry_after)},
        )

    user = db.execute(select(AdminUser).where(AdminUser.username == username)).scalar_one_or_none()
    if user is None:
        burn_verification(body.password)
        valid = False
    else:
        valid = verify_password(user.password_hash, body.password)
    if not valid or user is None:
        login_limiter.record_failure(username)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    login_limiter.reset(username)
    now = utcnow()
    db.execute(delete(UserSession).where(UserSession.expires_at < now))  # housekeeping
    token = create_session(db, user)
    user.last_login_at = now
    db.commit()
    set_session_cookie(response, token)
    return UserResponse(username=user.username, last_login_at=as_utc(user.last_login_at))


@router.post("/logout", response_model=OkResponse)
def logout(
    response: Response,
    auth: AuthContext = Depends(current_auth),
    db: Session = Depends(get_session),
) -> OkResponse:
    auth.session.revoked_at = utcnow()
    db.commit()
    clear_session_cookie(response)
    return OkResponse()


@router.get("/me", response_model=UserResponse)
def me(auth: AuthContext = Depends(current_auth)) -> UserResponse:
    return UserResponse(username=auth.user.username, last_login_at=as_utc(auth.user.last_login_at))
