"""IdeaValidation ORM model (Step 14)."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID as PyUUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import IdeaValidationStatus
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class IdeaValidation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "idea_validations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'READY', 'RUNNING', 'COMPLETED', 'CANCELLED')",
            name="idea_validation_status",
        ),
        CheckConstraint(
            "outcome IS NULL OR outcome IN ('PASS', 'PARTIAL', 'FAIL', 'INCONCLUSIVE')",
            name="idea_validation_outcome",
        ),
        CheckConstraint(
            "("
            "  (status = 'COMPLETED' AND outcome IS NOT NULL AND result_summary IS NOT NULL AND completed_at IS NOT NULL)"
            "  OR"
            "  (status <> 'COMPLETED' AND outcome IS NULL)"
            ")",
            name="idea_validation_completed_invariant",
        ),
        CheckConstraint(
            "("
            "  (status = 'RUNNING' AND started_at IS NOT NULL)"
            "  OR"
            "  (status IN ('DRAFT', 'READY') AND started_at IS NULL AND completed_at IS NULL)"
            "  OR"
            "  (status IN ('COMPLETED', 'CANCELLED'))"
            ")",
            name="idea_validation_timing_invariant",
        ),
        Index("ix_idea_validations_idea_id", "idea_id"),
        Index("ix_idea_validations_created_by", "created_by"),
        Index("ix_idea_validations_status", "status"),
        Index("ix_idea_validations_idea_created", "idea_id", "created_at"),
    )

    idea_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ideas.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    hypothesis: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    success_criteria: Mapped[str] = mapped_column(Text, nullable=False)
    planned_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=IdeaValidationStatus.DRAFT.value,
        server_default=IdeaValidationStatus.DRAFT.value,
    )
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)

    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
