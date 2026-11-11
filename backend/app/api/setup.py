"""First-run setup wizard API.

POST /api/setup works exactly once. In ONE database transaction it creates the village
and the admin account, flips setup_completed and opens a session. An optional Anthropic
key is written to data/.env only — never to the database — and is NOT tested here.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal
from urllib.parse import urlsplit
from zoneinfo import available_timezones

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, SecretStr, StringConstraints, field_validator, model_validator
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.api.village import AiMode, DefaultStructure, VillageResponse, village_response
from app.config import get_settings, save_env_value
from app.db import get_session, utcnow
from app.models import AdminUser, AppMeta, Village, get_meta
from app.security import create_session, hash_password, set_session_cookie

router = APIRouter(prefix="/setup", tags=["setup"])

ANTHROPIC_ENV_KEY = "VILLAGE_ANTHROPIC_API_KEY"
_USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,31}$")
_API_KEY_RE = re.compile(r"^[A-Za-z0-9_\-]{20,256}$")
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class SetupStatus(BaseModel):
    setup_completed: bool


class SetupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    village_name: Name
    chairman_name: Name
    username: str
    password: str = Field(min_length=10, max_length=128)
    timezone: str = "Asia/Dhaka"
    ai_mode: AiMode = "demo"
    ollama_url: str | None = None
    anthropic_api_key: SecretStr | None = None
    default_structure: DefaultStructure = "standard"

    @field_validator("username")
    @classmethod
    def _username(cls, value: str) -> str:
        value = value.strip().lower()
        if not _USERNAME_RE.fullmatch(value):
            raise ValueError("must be 3-32 characters: letters, digits, '.', '_' or '-', starting with a letter or digit")
        return value

    @field_validator("timezone")
    @classmethod
    def _timezone(cls, value: str) -> str:
        value = value.strip()
        if value not in available_timezones():
            raise ValueError("unknown timezone (use an IANA name such as Asia/Dhaka)")
        return value

    @field_validator("ollama_url")
    @classmethod
    def _ollama_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip()
        message = "must be an http:// URL on localhost, for example http://127.0.0.1:11434"
        if len(value) > 255:
            raise ValueError(message)
        try:
            parts = urlsplit(value)
            _ = parts.port  # raises ValueError for a malformed port
        except ValueError:
            raise ValueError(message) from None
        if (
            parts.scheme != "http"
            or parts.hostname not in _LOCAL_HOSTS
            or parts.username is not None
            or parts.password is not None
            or parts.query
            or parts.fragment
        ):
            raise ValueError(message)
        return value.rstrip("/")

    @field_validator("anthropic_api_key")
    @classmethod
    def _api_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        key = value.get_secret_value().strip()
        if not key:
            return None
        if not _API_KEY_RE.fullmatch(key):
            # Deliberately generic: the message must never contain the key.
            raise ValueError("does not look like an API key (20-256 letters, digits, '-' or '_')")
        return SecretStr(key)

    @model_validator(mode="after")
    def _ollama_needs_url(self) -> SetupRequest:
        if self.ai_mode == "ollama" and self.ollama_url is None:
            raise ValueError("ollama_url is required when ai_mode is 'ollama'")
        return self


class SetupResponse(BaseModel):
    setup_completed: bool
    username: str
    village: VillageResponse
    anthropic_api_key: Literal["saved, not tested", "not provided"]


def _already_done() -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Setup has already been completed")


@router.get("/status", response_model=SetupStatus)
def setup_status(db: Session = Depends(get_session)) -> SetupStatus:
    return SetupStatus(setup_completed=get_meta(db, "setup_completed") == "true")


@router.post("", response_model=SetupResponse, status_code=status.HTTP_201_CREATED)
def run_setup(body: SetupRequest, response: Response, db: Session = Depends(get_session)) -> SetupResponse:
    if get_meta(db, "setup_completed") == "true":
        raise _already_done()

    api_key = body.anthropic_api_key.get_secret_value() if body.anthropic_api_key else None
    if body.ai_mode == "anthropic" and api_key is None and get_settings().anthropic_api_key is None:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["body", "anthropic_api_key"],
                    "msg": "an API key is required when ai_mode is 'anthropic'",
                    "type": "value_error",
                }
            ],
        )

    password_hash = hash_password(body.password)  # slow on purpose; done before the transaction
    now = utcnow()
    try:
        # Claiming the flag first takes the write lock and makes concurrent setups lose cleanly.
        claimed = db.execute(
            update(AppMeta)
            .where(AppMeta.key == "setup_completed", AppMeta.value == "false")
            .values(value="true", updated_at=now)
        )
        if claimed.rowcount != 1:
            db.rollback()
            raise _already_done()

        village = Village(
            name=body.village_name,
            chairman_name=body.chairman_name,
            timezone=body.timezone,
            ai_mode=body.ai_mode,
            ollama_url=body.ollama_url,
            default_structure=body.default_structure,  # stored only; generation happens in M2
            created_at=now,
        )
        admin = AdminUser(username=body.username, password_hash=password_hash, created_at=now, last_login_at=now)
        db.add_all([village, admin])
        db.flush()
        token = create_session(db, admin)
        db.flush()

        if api_key is not None:
            try:
                save_env_value(ANTHROPIC_ENV_KEY, api_key)
            except OSError:
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Could not write the API key to the secrets file. Setup was not completed.",
                ) from None
        db.commit()
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise

    set_session_cookie(response, token)
    return SetupResponse(
        setup_completed=True,
        username=admin.username,
        village=village_response(village),
        anthropic_api_key="saved, not tested" if api_key is not None else "not provided",
    )
