"""Application settings (pydantic-settings, prefix VILLAGE_, read from data/.env).

Secrets live only in data/.env (mode 600). They are never stored in the DB,
logged, or returned by the API.
"""

from __future__ import annotations

import ipaddress
import os
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


def env_file_path() -> Path:
    """Location of the secrets file. VILLAGE_ENV_FILE overrides it (used by tests)."""
    override = os.environ.get("VILLAGE_ENV_FILE")
    return Path(override) if override else ROOT_DIR / "data" / ".env"


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VILLAGE_", env_file_encoding="utf-8", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8000
    db_path: Path = Path("data/village.db")
    log_dir: Path = Path("logs")
    frontend_dist: Path = Path("frontend/dist")
    secret_key: SecretStr
    anthropic_api_key: SecretStr | None = None

    @field_validator("host")
    @classmethod
    def _loopback_only(cls, value: str) -> str:
        if not _is_loopback(value):
            raise ValueError("host must be a loopback address (127.0.0.1); the Village is local-only")
        return value

    @field_validator("port")
    @classmethod
    def _valid_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("port must be between 1 and 65535")
        return value

    @field_validator("secret_key")
    @classmethod
    def _secret_not_empty(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 16:
            raise ValueError("secret_key must be at least 16 characters")
        return value

    @field_validator("anthropic_api_key", mode="before")
    @classmethod
    def _blank_key_is_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def demo_mode(self) -> bool:
        """Demo Mode is active whenever no Anthropic key is configured."""
        return self.anthropic_api_key is None

    def _abs(self, path: Path) -> Path:
        return path if path.is_absolute() else ROOT_DIR / path

    @property
    def db_file(self) -> Path:
        return self._abs(self.db_path)

    @property
    def log_path(self) -> Path:
        return self._abs(self.log_dir)

    @property
    def dist_path(self) -> Path:
        return self._abs(self.frontend_dist)


@lru_cache
def get_settings() -> Settings:
    return Settings(_env_file=env_file_path())  # type: ignore[call-arg]


def save_env_value(key: str, value: str) -> None:
    """Set KEY=value in the secrets file, atomically, keeping mode 600.

    Other lines are preserved. The value must be a single line.
    """
    if any(ch in value for ch in "\r\n") or not key.isidentifier():
        raise ValueError("invalid env entry")
    path = env_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    entry = f"{key}={value}"
    replaced = False
    for index, line in enumerate(lines):
        if line.split("=", 1)[0].strip() == key:
            lines[index] = entry
            replaced = True
    if not replaced:
        lines.append(entry)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".env.")  # created with mode 600
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    get_settings.cache_clear()


def _main() -> int:
    """Print non-secret runtime settings as key=value lines for the ./village CLI."""
    try:
        settings = get_settings()
    except ValidationError as exc:
        for error in exc.errors():
            field = ".".join(str(part) for part in error["loc"])
            print(f"config error: VILLAGE_{field.upper()}: {error['msg']}", file=sys.stderr)
        return 2
    print(f"host={settings.host}")
    print(f"port={settings.port}")
    print(f"db_file={settings.db_file}")
    print(f"log_dir={settings.log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
