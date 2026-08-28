"""Web research run and evidence ORM models (Step 9)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID as PyUUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import WebResearchRunStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class WebResearchRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "web_research_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ("
            "'AWAITING_APPROVAL', 'QUEUED', 'SEARCHING', 'REFINING', "
            "'READY', 'FAILED', 'CANCELLED')",
            name="web_research_run_status",
        ),
        Index("ix_web_research_runs_session_id", "session_id"),
        Index("ix_web_research_runs_requester_id", "requester_id"),
        Index("ix_web_research_runs_status", "status"),
    )

    session_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("idea_ai_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    requester_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=WebResearchRunStatus.AWAITING_APPROVAL.value,
        server_default=WebResearchRunStatus.AWAITING_APPROVAL.value,
    )

    queries_to_send: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    sanitization_notes: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)

    base_draft_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    base_field_provenance: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    user_edited_fields: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)

    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)

    failure_phase: Mapped[str | None] = mapped_column(String(32), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(String(512), nullable=True)

    result_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    research_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    llm_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)

    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WebEvidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "web_evidence"
    __table_args__ = (
        UniqueConstraint("research_run_id", "url_hash", name="uq_web_evidence_run_url_hash"),
        Index("ix_web_evidence_research_run_id", "research_run_id"),
    )

    research_run_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("web_research_runs.id", ondelete="CASCADE"),
        nullable=False,
    )

    query: Mapped[str] = mapped_column(String(200), nullable=False)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    url_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    snippet: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)

    related_fields: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
