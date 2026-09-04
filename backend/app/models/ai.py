"""IdeaAiSession and AiJob ORM models (Step 7)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID as PyUUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import (
    AiJobStatus,
    AiJobType,
    IdeaAiSessionPurpose,
    IdeaAiSessionStatus,
)
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class IdeaAiSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "idea_ai_sessions"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('CREATE', 'REFINE', 'RESEARCH')",
            name="idea_ai_session_purpose",
        ),
        CheckConstraint(
            "status IN ("
            "'PROCESSING', 'NEEDS_CLARIFICATION', 'READY_FOR_REVIEW', "
            "'CONFIRMED', 'FAILED', 'CANCELLED')",
            name="idea_ai_session_status",
        ),
        Index("ix_idea_ai_sessions_workspace_id", "workspace_id"),
        Index("ix_idea_ai_sessions_requester_id", "requester_id"),
        Index("ix_idea_ai_sessions_status", "status"),
        Index("ix_idea_ai_sessions_result_idea_id", "result_idea_id"),
        Index("ix_idea_ai_sessions_source_idea_id", "source_idea_id"),
        CheckConstraint(
            "refine_direction IS NULL OR refine_direction IN ("
            "'EXPAND_DETAIL', 'TECHNICAL_IMPLEMENTATION', 'BUSINESS_PERSPECTIVE', "
            "'USER_PERSPECTIVE', 'COUNTER_PERSPECTIVE', 'RISK_ANALYSIS', "
            "'MINIMUM_VALIDATION', 'NEXT_ACTIONS')",
            name="idea_ai_session_refine_direction",
        ),
    )

    workspace_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
    )
    requester_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    purpose: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=IdeaAiSessionPurpose.CREATE.value,
        server_default=IdeaAiSessionPurpose.CREATE.value,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=IdeaAiSessionStatus.PROCESSING.value,
        server_default=IdeaAiSessionStatus.PROCESSING.value,
    )

    input_text: Mapped[str] = mapped_column(Text, nullable=False)

    clarifying_questions: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    clarification_answers: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)

    draft_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    field_provenance: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    research_recommended: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    research_topics: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)

    confirmed_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    result_idea_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ideas.id", ondelete="SET NULL"),
        nullable=True,
    )

    source_idea_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ideas.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_idea_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_idea_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    refine_direction: Mapped[str | None] = mapped_column(String(64), nullable=True)

    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(String(512), nullable=True)

    llm_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)

    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    review_state: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    review_saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AiJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_jobs"
    __table_args__ = (
        CheckConstraint(
            "job_type IN ('STRUCTURE_IDEA', 'REFINE_IDEA', 'WEB_RESEARCH')",
            name="ai_job_type",
        ),
        CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED')",
            name="ai_job_status",
        ),
        CheckConstraint(
            "(job_type IN ('STRUCTURE_IDEA', 'REFINE_IDEA') AND research_run_id IS NULL) OR "
            "(job_type = 'WEB_RESEARCH' AND research_run_id IS NOT NULL)",
            name="ai_job_research_run_type",
        ),
        Index("ix_ai_jobs_session_id", "session_id"),
        Index("ix_ai_jobs_status_available_at", "status", "available_at"),
        Index("ix_ai_jobs_lease_until", "lease_until"),
        Index("ix_ai_jobs_research_run_id", "research_run_id"),
    )

    session_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("idea_ai_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    research_run_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("web_research_runs.id", ondelete="CASCADE"),
        nullable=True,
    )

    job_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=AiJobType.STRUCTURE_IDEA.value,
        server_default=AiJobType.STRUCTURE_IDEA.value,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=AiJobStatus.QUEUED.value,
        server_default=AiJobStatus.QUEUED.value,
    )

    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3, server_default="3")

    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(String(512), nullable=True)
