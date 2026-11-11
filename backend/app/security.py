"""Password hashing, session tokens, login lockout and the auth dependencies.

Nothing in this module logs or returns passwords, session tokens or API keys.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache
from threading import Lock

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error, InvalidHashError
from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session, utcnow
from app.models import AdminUser, UserSession

SESSION_COOKIE = "village_session"
SESSION_TTL = timedelta(days=7)

# The only /api paths reachable without a valid session. Everything else is default-deny.
PUBLIC_PATHS = frozenset({"/api/health", "/api/setup/status", "/api/setup", "/api/auth/login"})

_hasher = PasswordHasher()  # argon2id with the library's recommended parameters


# ---------------------------------------------------------------- passwords


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (Argon2Error, InvalidHashError):
        return False


@lru_cache
def _dummy_hash() -> str:
    return hash_password(secrets.token_urlsafe(16))


def burn_verification(password: str) -> None:
    """Spend the same time as a real check, so unknown usernames are not distinguishable."""
    verify_password(_dummy_hash(), password)


# ---------------------------------------------------------------- session tokens


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(db: Session, user: AdminUser) -> str:
    """Add a session row for `user` (caller commits) and return the raw cookie token."""
    token = secrets.token_urlsafe(32)
    now = utcnow()
    db.add(UserSession(token_hash=hash_token(token), user_id=user.id, created_at=now, expires_at=now + SESSION_TTL))
    return token


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_TTL.total_seconds()),
        path="/",
        httponly=True,
        samesite="strict",
        secure=False,  # the Village is served over plain http on localhost
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="strict", secure=False)


# ---------------------------------------------------------------- login lockout


class LoginRateLimiter:
    """In-memory lockout: `max_failures` failed logins per `window_seconds`, per username."""

    def __init__(
        self,
        max_failures: int = 5,
        window_seconds: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._clock = clock
        self._failures: dict[str, deque[float]] = {}
        self._lock = Lock()

    def _prune(self, key: str, now: float) -> deque[float] | None:
        attempts = self._failures.get(key)
        if attempts is None:
            return None
        while attempts and now - attempts[0] >= self.window_seconds:
            attempts.popleft()
        if not attempts:
            del self._failures[key]
            return None
        return attempts

    def retry_after(self, key: str) -> int:
        """Seconds until `key` may try again; 0 when it is not locked out."""
        with self._lock:
            now = self._clock()
            attempts = self._prune(key, now)
            if attempts is None or len(attempts) < self.max_failures:
                return 0
            return max(1, int(self.window_seconds - (now - attempts[0])) + 1)

    def record_failure(self, key: str) -> None:
        with self._lock:
            now = self._clock()
            if len(self._failures) > 1000:  # bound memory against username spraying
                for other in list(self._failures):
                    self._prune(other, now)
            self._failures.setdefault(key, deque(maxlen=self.max_failures)).append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._failures.clear()


login_limiter = LoginRateLimiter()


# ---------------------------------------------------------------- auth dependencies


@dataclass
class AuthContext:
    user: AdminUser
    session: UserSession


_UNAUTHORIZED = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


def _resolve_auth(request: Request, db: Session) -> AuthContext | None:
    if hasattr(request.state, "auth"):
        return request.state.auth
    context: AuthContext | None = None
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        row = db.execute(
            select(UserSession, AdminUser)
            .join(AdminUser, AdminUser.id == UserSession.user_id)
            .where(
                UserSession.token_hash == hash_token(token),
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > utcnow(),
            )
        ).first()
        if row is not None:
            context = AuthContext(user=row[1], session=row[0])
    request.state.auth = context
    return context


def enforce_auth(request: Request, db: Session = Depends(get_session)) -> None:
    """Router-level guard for everything under /api: public allowlist, otherwise a session."""
    if request.url.path in PUBLIC_PATHS:
        return
    if _resolve_auth(request, db) is None:
        raise _UNAUTHORIZED


def current_auth(request: Request, db: Session = Depends(get_session)) -> AuthContext:
    """Endpoint dependency: the logged-in admin and their session."""
    context = _resolve_auth(request, db)
    if context is None:
        raise _UNAUTHORIZED
    return context
