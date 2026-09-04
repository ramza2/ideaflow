"""Admin API schemas (Step 11)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import SystemRole, UserStatus


class AdminUserRef(BaseModel):
    id: UUID
    name: str


class AdminUserPublic(BaseModel):
    id: UUID
    email: str
    name: str
    status: UserStatus
    system_role: SystemRole
    must_change_password: bool
    failed_login_count: int
    locked_until: datetime | None
    temporary_login_locked: bool
    active_session_count: int
    last_seen_at: datetime | None
    created_at: datetime
    updated_at: datetime
    is_current_user: bool


class AdminUserListResponse(BaseModel):
    items: list[AdminUserPublic]
    total: int


class AdminUserCreateRequest(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=100)
    temporary_password: str = Field(min_length=10, max_length=256)
    system_role: SystemRole = SystemRole.USER

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must not be empty")
        return stripped


class AdminUserUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    status: UserStatus | None = None
    system_role: SystemRole | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must not be empty")
        return stripped


class AdminPasswordResetRequest(BaseModel):
    temporary_password: str = Field(min_length=10, max_length=256)


class SettingMetadata(BaseModel):
    source: str
    updated_at: datetime | None
    updated_by: AdminUserRef | None


class SystemSettingsResponse(BaseModel):
    global_llm_enabled: bool
    global_web_search_enabled: bool
    default_team_allow_llm: bool
    default_team_allow_web_search: bool
    metadata: dict[str, SettingMetadata]


class SystemSettingsUpdateRequest(BaseModel):
    global_llm_enabled: bool | None = None
    global_web_search_enabled: bool | None = None
    default_team_allow_llm: bool | None = None
    default_team_allow_web_search: bool | None = None

    model_config = ConfigDict(extra="forbid")


class LlmIntegrationConfig(BaseModel):
    provider: str
    api_url: str
    chat_completions_path: str
    model_name: str
    api_key_configured: bool
    timeout_seconds: float
    connect_timeout_seconds: float
    max_tokens: int
    temperature: float
    enable_thinking: bool | None
    configuration_source: str


class WebSearchIntegrationConfig(BaseModel):
    provider: str
    api_url: str | None
    api_key_configured: bool
    timeout_seconds: float
    connect_timeout_seconds: float
    max_queries: int
    max_results_per_query: int
    max_total_results: int
    configured: bool
    configuration_source: str


class EmbeddingJobCounts(BaseModel):
    queued: int = 0
    running: int = 0
    succeeded: int = 0
    failed: int = 0


class EmbeddingIntegrationConfig(BaseModel):
    enabled: bool
    provider: str
    api_url: str | None
    embedding_path: str
    api_key_configured: bool
    model_name: str
    dimension: int
    timeout_seconds: float
    connect_timeout_seconds: float
    max_input_chars: int
    worker_enabled: bool
    configured: bool
    configuration_source: str
    stored_embedding_count: int = 0
    job_counts: EmbeddingJobCounts = Field(default_factory=EmbeddingJobCounts)


class AdminIntegrationConfigResponse(BaseModel):
    llm: LlmIntegrationConfig
    web_search: WebSearchIntegrationConfig
    embedding: EmbeddingIntegrationConfig
    global_llm_enabled: bool
    global_web_search_enabled: bool


class LlmConnectionTestResult(BaseModel):
    status: str
    provider: str | None = None
    model: str | None = None
    latency_ms: int | None = None
    tested_at: datetime
    error_code: str | None = None
    retryable: bool | None = None
    safe_message: str | None = None


class EmbeddingConnectionTestResult(BaseModel):
    status: str
    provider: str | None = None
    model: str | None = None
    dimension: int | None = None
    latency_ms: int | None = None
    tested_at: datetime
    error_code: str | None = None
    retryable: bool | None = None
    safe_message: str | None = None



class WebSearchTestResultItem(BaseModel):
    title: str
    url: str
    source: str | None = None
    published_at: str | None = None


class WebSearchConnectionTestRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)

    @field_validator("query")
    @classmethod
    def strip_query(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("query must not be empty")
        return stripped


class WebSearchConnectionTestResult(BaseModel):
    status: str
    provider: str | None = None
    latency_ms: int | None = None
    result_count: int | None = None
    tested_at: datetime
    error_code: str | None = None
    retryable: bool | None = None
    safe_message: str | None = None
    results: list[WebSearchTestResultItem] | None = None
