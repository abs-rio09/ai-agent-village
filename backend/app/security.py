"""Password hashing, session tokens, login lockout and the auth dependencies.

Nothing in this module logs or returns passwords, session tokens or API keys.
"""

from __future__ import annotations

import hashlib
import logging
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error, InvalidHashError
from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import get_session, utcnow
from app.models import AdminUser, LoginFailure, UserSession

log = logging.getLogger("village.security")

SESSION_COOKIE = "village_session"
SESSION_TTL = timedelta(days=7)
# "Last seen" is written at most this often per session, so normal use costs no extra writes.
LAST_SEEN_STEP = timedelta(seconds=60)

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


_BROWSERS = (  # first match wins: the more specific names come before "Chrome" and "Safari"
    ("Edge", r"Edg(?:e|A|iOS)?/"),
    ("Opera", r"OPR/|Opera"),
    ("Samsung Internet", r"SamsungBrowser/"),
    ("Firefox", r"Firefox/|FxiOS/"),
    ("Chrome", r"Chrome/|CriOS/|Chromium/"),
    ("Safari", r"Safari/"),
)
_SYSTEMS = (
    ("Android", r"Android"),
    ("iPhone", r"iPhone"),
    ("iPad", r"iPad"),
    ("Windows", r"Windows"),
    ("ChromeOS", r"CrOS"),
    ("macOS", r"Macintosh|Mac OS X"),
    ("Linux", r"Linux|X11"),
)


def device_label(user_agent: str | None) -> str:
    """A short, readable name for a session's device, such as "Chrome on Android".

    Only this label is stored — never the User-Agent string itself.
    """
    agent = (user_agent or "")[:400]
    browser = next((name for name, pattern in _BROWSERS if re.search(pattern, agent)), None)
    system = next((name for name, pattern in _SYSTEMS if re.search(pattern, agent)), None)
    if browser and system:
        return f"{browser} on {system}"
    if browser or system:
        return browser or f"Unknown browser on {system}"
    return "Unknown device"


def create_session(db: Session, user: AdminUser, user_agent: str | None = None) -> str:
    """Add a session row for `user` (caller commits) and return the raw cookie token."""
    token = secrets.token_urlsafe(32)
    now = utcnow()
    db.add(
        UserSession(
            token_hash=hash_token(token),
            user_id=user.id,
            created_at=now,
            expires_at=now + SESSION_TTL,
            device_label=device_label(user_agent),
            last_seen_at=now,
        )
    )
    return token


def is_secure_request(request: Request) -> bool:
    """True when the browser reached the Village over HTTPS (through the Tailscale proxy).
    Decided by the local-requests middleware in app.main; plain http on localhost is False."""
    return bool(getattr(request.state, "secure", False))


def set_session_cookie(response: Response, token: str, *, secure: bool = False) -> None:
    """HttpOnly + SameSite=Strict always; Secure as well when the request arrived over HTTPS."""
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_TTL.total_seconds()),
        path="/",
        httponly=True,
        samesite="strict",
        secure=secure,
    )


def clear_session_cookie(response: Response, *, secure: bool = False) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="strict", secure=secure)


# ---------------------------------------------------------------- login lockout


class LoginRateLimiter:
    """Lockout: `max_failures` counted attempts per `window_seconds`, per username.

    The attempts are rows in SQLite (`login_failure`), so a restart does not forget them.
    An attempt is counted BEFORE the password is checked and removed again by a successful
    login: checking the limit and taking a slot is one transaction, so parallel guesses cannot
    slip past the limit together.
    """

    def __init__(
        self,
        max_failures: int = 5,
        window_seconds: float = 300.0,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._clock = clock

    def _recent(self, db: Session, key: str, now: datetime) -> list[datetime]:
        cutoff = now - timedelta(seconds=self.window_seconds)
        return list(
            db.execute(
                select(LoginFailure.failed_at)
                .where(LoginFailure.username == key, LoginFailure.failed_at > cutoff)
                .order_by(LoginFailure.failed_at.desc())
                .limit(self.max_failures)
            ).scalars()
        )

    def _wait(self, recent: list[datetime], now: datetime) -> int:
        if len(recent) < self.max_failures:
            return 0
        return max(1, int(self.window_seconds - (now - recent[-1]).total_seconds()) + 1)

    def retry_after(self, db: Session, key: str) -> int:
        """Seconds until `key` may try again; 0 when it is not locked out. Read-only."""
        now = self._clock()
        return self._wait(self._recent(db, key, now), now)

    def attempt(self, db: Session, key: str) -> int:
        """Take one of `key`'s attempts. Returns 0 when the login may go ahead, otherwise the
        seconds to wait (and nothing is counted). Commits."""
        now = self._clock()
        # The DELETE comes first on purpose: it takes SQLite's write lock, so a parallel
        # request waits here instead of reading the same count. It also keeps the table small.
        db.execute(delete(LoginFailure).where(LoginFailure.failed_at <= now - timedelta(seconds=self.window_seconds)))
        wait = self._wait(self._recent(db, key, now), now)
        if wait == 0:
            db.add(LoginFailure(username=key, failed_at=now))
        db.commit()
        return wait

    def reset(self, db: Session, key: str) -> None:
        """A successful login forgives the earlier failures. The caller commits."""
        db.execute(delete(LoginFailure).where(LoginFailure.username == key))


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
            session = row[0]
            now = utcnow()
            if session.last_seen_at is None or now - session.last_seen_at >= LAST_SEEN_STEP:
                session.last_seen_at = now  # for "Devices & sessions"; at most one write a minute
                db.commit()
            context = AuthContext(user=row[1], session=session)
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
