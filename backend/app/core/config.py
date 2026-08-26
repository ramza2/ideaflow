"""Application settings via pydantic-settings."""

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> repository root is three levels up
_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = _REPO_ROOT / ".env"


def repo_root() -> Path:
    """Return the IdeaFlow repository root (absolute)."""
    return _REPO_ROOT


def env_file_path() -> Path:
    """Return the repository-root `.env` path (absolute, cwd-independent)."""
    return _ENV_FILE


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="development", alias="APP_ENV")
    app_name: str = Field(default="IdeaFlow API", alias="APP_NAME")
    app_version: str = Field(default="0.1.0", alias="APP_VERSION")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    cors_origins: str = Field(
        default="http://localhost:5173",
        alias="CORS_ORIGINS",
        description="Comma-separated allowed CORS origins (no wildcard with credentials).",
    )
    database_url: str = Field(
        default="",
        alias="DATABASE_URL",
        description="SQLAlchemy URL, e.g. postgresql+psycopg://user:pass@host:5432/ideaflow",
    )

    # Auth / session cookies
    auth_session_cookie_name: str = Field(default="ideaflow_session", alias="AUTH_SESSION_COOKIE_NAME")
    auth_csrf_cookie_name: str = Field(default="ideaflow_csrf", alias="AUTH_CSRF_COOKIE_NAME")
    auth_session_idle_seconds: int = Field(default=604800, alias="AUTH_SESSION_IDLE_SECONDS")
    auth_session_absolute_seconds: int = Field(default=2592000, alias="AUTH_SESSION_ABSOLUTE_SECONDS")
    auth_session_touch_interval_seconds: int = Field(
        default=900, alias="AUTH_SESSION_TOUCH_INTERVAL_SECONDS"
    )
    auth_login_max_failures: int = Field(default=5, alias="AUTH_LOGIN_MAX_FAILURES")
    auth_login_lock_seconds: int = Field(default=900, alias="AUTH_LOGIN_LOCK_SECONDS")
    auth_cookie_secure: bool = Field(default=False, alias="AUTH_COOKIE_SECURE")
    auth_cookie_samesite: str = Field(default="lax", alias="AUTH_COOKIE_SAMESITE")

    @field_validator("auth_cookie_samesite", mode="before")
    @classmethod
    def normalize_cookie_samesite(cls, value: Any) -> str:
        if value is None:
            return "lax"
        normalized = str(value).strip().lower()
        if normalized not in {"lax", "strict", "none"}:
            return "lax"
        return normalized

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
