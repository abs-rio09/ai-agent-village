"""Admin login, logout, current user, and "Devices & sessions" (list and revoke)."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import audit
from app.db import as_utc, get_session, utcnow
from app.models import AdminUser, AuditLog, UserSession
from app.security import (
    AuthContext,
    burn_verification,
    clear_session_cookie,
    create_session,
    current_auth,
    device_label,
    is_secure_request,
    log,
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


class SessionOut(BaseModel):
    id: int
    device: str  # "Chrome on Android"; "Unknown device" for sessions older than this feature
    created_at: datetime
    last_seen_at: datetime | None
    expires_at: datetime
    current: bool  # the session this request was made with ("this device")


class RevokeResult(BaseModel):
    revoked: int


UNKNOWN_USER = "unknown user"
_AUDIT_QUIET = timedelta(seconds=60)


def _audit_login_problem(db: Session, action: str, actor: str, summary: str, device: str) -> None:
    """Failed and locked-out logins go to the audit log — but the log is append-only, so the
    same actor gets at most one such entry a minute. The typed username is never written: people
    sometimes type their password into that field. Only a name that really is an admin is named."""
    recent = db.execute(
        select(AuditLog.id)
        .where(AuditLog.action == action, AuditLog.actor == actor, AuditLog.created_at > utcnow() - _AUDIT_QUIET)
        .limit(1)
    ).first()
    if recent is None:
        audit.record(db, action, actor=actor, decision="denied", summary=summary, details={"device": device})
        db.commit()


@router.post("/login", response_model=UserResponse)
def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_session)) -> UserResponse:
    username = body.username.strip().lower()
    # Every attempt is counted before the password is looked at; a correct password gives the
    # attempts back. The count lives in SQLite, so restarting the server does not reset it.
    device = device_label(request.headers.get("user-agent"))
    retry_after = login_limiter.attempt(db, username)
    user = db.execute(select(AdminUser).where(AdminUser.username == username)).scalar_one_or_none()
    actor = audit.chairman(user.username) if user is not None else UNKNOWN_USER
    if retry_after:
        log.warning("login locked out for %s second(s) after repeated failures", retry_after)
        _audit_login_problem(db, "auth.login_locked", actor, "Login refused: too many failed attempts.", device)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed login attempts. Try again in {max(1, round(retry_after / 60))} minute(s).",
            headers={"Retry-After": str(retry_after)},
        )

    if user is None:
        burn_verification(body.password)
        valid = False
    else:
        valid = verify_password(user.password_hash, body.password)
    if not valid or user is None:
        _audit_login_problem(db, "auth.login_failed", actor, "Login failed: wrong username or password.", device)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    login_limiter.reset(db, username)
    now = utcnow()
    db.execute(delete(UserSession).where(UserSession.expires_at < now))  # housekeeping
    token = create_session(db, user, request.headers.get("user-agent"))
    user.last_login_at = now
    audit.record(db, "auth.login", actor=actor, decision="allowed", summary=f"Logged in from {device}.", details={"device": device})
    db.commit()
    set_session_cookie(response, token, secure=is_secure_request(request))
    return UserResponse(username=user.username, last_login_at=as_utc(user.last_login_at))


@router.post("/logout", response_model=OkResponse)
def logout(
    request: Request,
    response: Response,
    auth: AuthContext = Depends(current_auth),
    db: Session = Depends(get_session),
) -> OkResponse:
    auth.session.revoked_at = utcnow()
    audit.record(
        db,
        "auth.logout",
        actor=audit.chairman(auth.user.username),
        summary=f"Logged out ({auth.session.device_label or 'Unknown device'}).",
    )
    db.commit()
    clear_session_cookie(response, secure=is_secure_request(request))
    return OkResponse()


@router.get("/me", response_model=UserResponse)
def me(auth: AuthContext = Depends(current_auth)) -> UserResponse:
    return UserResponse(username=auth.user.username, last_login_at=as_utc(auth.user.last_login_at))


# ---------------------------------------------------------------- devices & sessions


def _active_sessions(db: Session, user_id: int):  # noqa: ANN202
    now = utcnow()
    return select(UserSession).where(
        UserSession.user_id == user_id, UserSession.revoked_at.is_(None), UserSession.expires_at > now
    )


def _audit_revoke(db: Session, auth: AuthContext, row: UserSession, how: str) -> None:
    audit.record(
        db,
        "auth.session_revoked",
        actor=audit.chairman(auth.user.username),
        summary=f"Session #{row.id} ({row.device_label or 'Unknown device'}) was logged out: {how}.",
    )


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(auth: AuthContext = Depends(current_auth), db: Session = Depends(get_session)) -> list[SessionOut]:
    """The devices that are logged in right now: this one first, then the most recently seen."""
    rows = db.execute(_active_sessions(db, auth.user.id)).scalars().all()
    rows.sort(key=lambda row: (row.id != auth.session.id, -(row.last_seen_at or row.created_at).timestamp()))
    return [
        SessionOut(
            id=row.id,
            device=row.device_label or "Unknown device",
            created_at=as_utc(row.created_at),  # type: ignore[arg-type]
            last_seen_at=as_utc(row.last_seen_at),
            expires_at=as_utc(row.expires_at),  # type: ignore[arg-type]
            current=row.id == auth.session.id,
        )
        for row in rows
    ]


@router.post("/sessions/revoke-others", response_model=RevokeResult)
def revoke_other_sessions(
    auth: AuthContext = Depends(current_auth), db: Session = Depends(get_session)
) -> RevokeResult:
    """Log out every other device. This device stays logged in."""
    others = db.execute(_active_sessions(db, auth.user.id).where(UserSession.id != auth.session.id)).scalars().all()
    now = utcnow()
    for row in others:
        row.revoked_at = now
        _audit_revoke(db, auth, row, "log out all other devices")
    db.commit()
    for row in others:  # also in the application log (never a token)
        log.info("session %s (%s) revoked by %s: log out all other devices", row.id, row.device_label or "Unknown device", auth.user.username)
    return RevokeResult(revoked=len(others))


@router.post("/sessions/{session_id}/revoke", response_model=RevokeResult)
def revoke_session(
    session_id: int,
    request: Request,
    response: Response,
    auth: AuthContext = Depends(current_auth),
    db: Session = Depends(get_session),
) -> RevokeResult:
    """Log one device out. Its cookie stops working with the very next request."""
    row = db.execute(_active_sessions(db, auth.user.id).where(UserSession.id == session_id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found or already logged out")
    row.revoked_at = utcnow()
    _audit_revoke(db, auth, row, "revoked from Devices & sessions")
    db.commit()
    log.info("session %s (%s) revoked by %s", row.id, row.device_label or "Unknown device", auth.user.username)
    if row.id == auth.session.id:
        clear_session_cookie(response, secure=is_secure_request(request))
    return RevokeResult(revoked=1)
