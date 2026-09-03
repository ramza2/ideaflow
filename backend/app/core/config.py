"""Application settings via pydantic-settings."""

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> repository root is three levels up
_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = _REPO_ROOT / ".env"

# Fixed pgvector schema dimension (changing requires a new migration).
EMBEDDING_DIMENSION = 1024


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

    # LLM (OpenAI-compatible)
    llm_api_url: str = Field(default="https://alzi-llm.openlink.kr", alias="LLM_API_URL")
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_model_name: str = Field(default="Qwen3-14B", alias="LLM_MODEL_NAME")
    llm_chat_completions_path: str = Field(
        default="/v1/chat/completions", alias="LLM_CHAT_COMPLETIONS_PATH"
    )
    llm_timeout_seconds: float = Field(default=120.0, alias="LLM_TIMEOUT_SECONDS")
    llm_connect_timeout_seconds: float = Field(default=10.0, alias="LLM_CONNECT_TIMEOUT_SECONDS")
    llm_temperature: float = Field(default=0.2, alias="LLM_TEMPERATURE")
    llm_max_tokens: int = Field(default=2500, alias="LLM_MAX_TOKENS")
    # Optional OpenAI-compatible chat_template_kwargs.enable_thinking (Qwen/vLLM).
    # None/unset → omit field; False/True → send explicit boolean.
    # IdeaFlow default False disables thinking for strict JSON structuring.
    llm_enable_thinking: bool | None = Field(default=False, alias="LLM_ENABLE_THINKING")

    # AI worker / job queue
    ai_worker_enabled: bool = Field(default=True, alias="AI_WORKER_ENABLED")
    ai_job_poll_interval_seconds: float = Field(default=1.0, alias="AI_JOB_POLL_INTERVAL_SECONDS")
    ai_job_lease_seconds: int = Field(default=300, alias="AI_JOB_LEASE_SECONDS")
    ai_job_max_attempts: int = Field(default=3, alias="AI_JOB_MAX_ATTEMPTS")
    ai_job_retry_base_seconds: float = Field(default=2.0, alias="AI_JOB_RETRY_BASE_SECONDS")

    # Web Search (Step 9+)
    web_search_provider: str = Field(default="http_json", alias="WEB_SEARCH_PROVIDER")
    web_search_api_url: str = Field(default="", alias="WEB_SEARCH_API_URL")
    web_search_api_key: str = Field(default="", alias="WEB_SEARCH_API_KEY")
    web_search_timeout_seconds: float = Field(default=20.0, alias="WEB_SEARCH_TIMEOUT_SECONDS")
    web_search_connect_timeout_seconds: float = Field(
        default=5.0, alias="WEB_SEARCH_CONNECT_TIMEOUT_SECONDS"
    )
    web_search_max_queries: int = Field(default=5, alias="WEB_SEARCH_MAX_QUERIES")
    web_search_max_results_per_query: int = Field(
        default=5, alias="WEB_SEARCH_MAX_RESULTS_PER_QUERY"
    )
    web_search_max_total_results: int = Field(default=20, alias="WEB_SEARCH_MAX_TOTAL_RESULTS")
    web_research_refine_max_evidence_items: int = Field(
        default=6, alias="WEB_RESEARCH_REFINE_MAX_EVIDENCE_ITEMS"
    )
    web_research_refine_max_snippet_chars: int = Field(
        default=600, alias="WEB_RESEARCH_REFINE_MAX_SNIPPET_CHARS"
    )
    web_research_refine_max_evidence_chars: int = Field(
        default=4000, alias="WEB_RESEARCH_REFINE_MAX_EVIDENCE_CHARS"
    )
    web_research_refine_max_prompt_chars: int = Field(
        default=6000, alias="WEB_RESEARCH_REFINE_MAX_PROMPT_CHARS"
    )
    web_research_refine_max_tokens: int = Field(
        default=1200, alias="WEB_RESEARCH_REFINE_MAX_TOKENS"
    )

    # Embeddings (Step 13 — separate from LLM)
    embedding_enabled: bool = Field(default=False, alias="EMBEDDING_ENABLED")
    embedding_provider: str = Field(default="openai_compatible", alias="EMBEDDING_PROVIDER")
    embedding_api_url: str = Field(default="", alias="EMBEDDING_API_URL")
    embedding_api_key: str = Field(default="", alias="EMBEDDING_API_KEY")
    embedding_model_name: str = Field(default="BAAI/bge-m3", alias="EMBEDDING_MODEL_NAME")
    embedding_path: str = Field(default="/v1/embeddings", alias="EMBEDDING_PATH")
    embedding_dimension: int = Field(default=EMBEDDING_DIMENSION, alias="EMBEDDING_DIMENSION")
    embedding_timeout_seconds: float = Field(default=30.0, alias="EMBEDDING_TIMEOUT_SECONDS")
    embedding_connect_timeout_seconds: float = Field(
        default=5.0, alias="EMBEDDING_CONNECT_TIMEOUT_SECONDS"
    )
    embedding_max_input_chars: int = Field(default=20000, alias="EMBEDDING_MAX_INPUT_CHARS")

    # Embedding worker
    embedding_worker_enabled: bool = Field(default=True, alias="EMBEDDING_WORKER_ENABLED")
    embedding_job_poll_interval_seconds: float = Field(
        default=1.0, alias="EMBEDDING_JOB_POLL_INTERVAL_SECONDS"
    )
    embedding_job_lease_seconds: int = Field(default=120, alias="EMBEDDING_JOB_LEASE_SECONDS")
    embedding_job_max_attempts: int = Field(default=3, alias="EMBEDDING_JOB_MAX_ATTEMPTS")
    embedding_job_retry_base_seconds: float = Field(
        default=2.0, alias="EMBEDDING_JOB_RETRY_BASE_SECONDS"
    )

    @field_validator("llm_enable_thinking", mode="before")
    @classmethod
    def parse_enable_thinking(cls, value: Any) -> bool | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text == "":
            return None
        if text in {"true", "1", "yes", "on"}:
            return True
        if text in {"false", "0", "no", "off"}:
            return False
        raise ValueError("LLM_ENABLE_THINKING must be true, false, or empty")

    @field_validator("auth_cookie_samesite", mode="before")
    @classmethod
    def normalize_cookie_samesite(cls, value: Any) -> str:
        if value is None:
            return "lax"
        normalized = str(value).strip().lower()
        if normalized not in {"lax", "strict", "none"}:
            return "lax"
        return normalized

    @field_validator(
        "llm_timeout_seconds",
        "llm_connect_timeout_seconds",
        "ai_job_poll_interval_seconds",
        "ai_job_retry_base_seconds",
        "web_search_timeout_seconds",
        "web_search_connect_timeout_seconds",
        "embedding_timeout_seconds",
        "embedding_connect_timeout_seconds",
        "embedding_job_poll_interval_seconds",
        "embedding_job_retry_base_seconds",
        mode="after",
    )
    @classmethod
    def positive_float(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("must be > 0")
        return value

    @field_validator(
        "ai_job_lease_seconds",
        "ai_job_max_attempts",
        "llm_max_tokens",
        "web_search_max_queries",
        "web_search_max_results_per_query",
        "web_search_max_total_results",
        "web_research_refine_max_evidence_items",
        "web_research_refine_max_snippet_chars",
        "web_research_refine_max_evidence_chars",
        "web_research_refine_max_prompt_chars",
        "web_research_refine_max_tokens",
        "embedding_job_lease_seconds",
        "embedding_job_max_attempts",
        "embedding_max_input_chars",
        mode="after",
    )
    @classmethod
    def positive_int(cls, value: int) -> int:
        if value < 1:
            raise ValueError("must be >= 1")
        return value

    @field_validator("llm_temperature", mode="after")
    @classmethod
    def temperature_range(cls, value: float) -> float:
        if value < 0 or value > 2:
            raise ValueError("LLM_TEMPERATURE must be between 0 and 2")
        return value

    @model_validator(mode="after")
    def lease_vs_timeout(self) -> "Settings":
        # Lease should outlive a single LLM call and web search + refine attempt.
        if self.ai_job_lease_seconds <= self.llm_timeout_seconds:
            raise ValueError("AI_JOB_LEASE_SECONDS must be greater than LLM_TIMEOUT_SECONDS")
        search_budget = (
            self.web_search_timeout_seconds * max(self.web_search_max_queries, 1)
            + self.llm_timeout_seconds
        )
        if self.ai_job_lease_seconds <= search_budget:
            raise ValueError(
                "AI_JOB_LEASE_SECONDS must exceed worst-case WEB_SEARCH + LLM timeout budget"
            )
        if self.web_search_max_queries < 1 or self.web_search_max_queries > 10:
            raise ValueError("WEB_SEARCH_MAX_QUERIES must be between 1 and 10")
        if self.web_search_max_results_per_query < 1 or self.web_search_max_results_per_query > 10:
            raise ValueError("WEB_SEARCH_MAX_RESULTS_PER_QUERY must be between 1 and 10")
        if self.web_search_max_total_results < 1:
            raise ValueError("WEB_SEARCH_MAX_TOTAL_RESULTS must be >= 1")
        if self.embedding_dimension != EMBEDDING_DIMENSION:
            raise ValueError(
                f"EMBEDDING_DIMENSION must be {EMBEDDING_DIMENSION} for the current schema"
            )
        if self.embedding_enabled and not self.embedding_api_url.strip():
            raise ValueError("EMBEDDING_API_URL is required when EMBEDDING_ENABLED=true")
        if self.embedding_job_lease_seconds <= self.embedding_timeout_seconds:
            raise ValueError(
                "EMBEDDING_JOB_LEASE_SECONDS must be greater than EMBEDDING_TIMEOUT_SECONDS"
            )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def llm_chat_completions_url(self) -> str:
        base = self.llm_api_url.rstrip("/")
        path = self.llm_chat_completions_path.strip() or "/v1/chat/completions"
        if not path.startswith("/"):
            path = "/" + path
        return f"{base}{path}"

    @property
    def embedding_api_url_resolved(self) -> str:
        return self.embedding_api_url.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()
