"""Idea ORM model.

Workspace integrity for stage_id / category_id / tags:
Approach B — plain FKs; Step 4/5 Service Layer MUST verify that
stage, category, and tags belong to the same workspace as the Idea.
Composite FKs were avoided to keep ORM relations maintainable.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID as PyUUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import IdeaFeasibility, IdeaPriority, IdeaVisibility
from app.models.mixins import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Idea(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "ideas"
    __table_args__ = (
        UniqueConstraint("workspace_id", "idea_code", name="uq_ideas_workspace_idea_code"),
        CheckConstraint("priority IN ('HIGH', 'MEDIUM', 'LOW')", name="idea_priority"),
        CheckConstraint(
            "feasibility IN ('HIGH', 'MEDIUM', 'LOW', 'UNKNOWN')",
            name="idea_feasibility",
        ),
        CheckConstraint(
            "visibility IN ('PRIVATE', 'WORKSPACE', 'SELECTED_USERS')",
            name="idea_visibility",
        ),
        Index("ix_ideas_workspace_id", "workspace_id"),
        Index("ix_ideas_author_id", "author_id"),
        Index("ix_ideas_stage_id", "stage_id"),
        Index("ix_ideas_category_id", "category_id"),
        Index("ix_ideas_workspace_updated_at", "workspace_id", "updated_at"),
        Index("ix_ideas_workspace_stage_id", "workspace_id", "stage_id"),
        Index("ix_ideas_next_review_date", "next_review_date"),
    )

    idea_code: Mapped[str] = mapped_column(String(32), nullable=False)
    workspace_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
    )
    author_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    one_line_definition: Mapped[str | None] = mapped_column(String(500), nullable=True)
    original_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    background: Mapped[str | None] = mapped_column(Text, nullable=True)
    problem: Mapped[str | None] = mapped_column(Text, nullable=True)
    core_concept: Mapped[str | None] = mapped_column(Text, nullable=True)
    major_features: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_effect: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_users: Mapped[str | None] = mapped_column(Text, nullable=True)
    scenarios: Mapped[str | None] = mapped_column(Text, nullable=True)
    challenges: Mapped[str | None] = mapped_column(Text, nullable=True)
    minimum_validation: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_project: Mapped[str | None] = mapped_column(Text, nullable=True)

    category_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspace_categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    stage_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspace_stages.id", ondelete="RESTRICT"),
        nullable=False,
    )

    priority: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=IdeaPriority.MEDIUM.value,
        server_default=IdeaPriority.MEDIUM.value,
    )
    feasibility: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=IdeaFeasibility.UNKNOWN.value,
        server_default=IdeaFeasibility.UNKNOWN.value,
    )
    visibility: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=IdeaVisibility.WORKSPACE.value,
        server_default=IdeaVisibility.WORKSPACE.value,
    )

    assignee_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    next_review_date: Mapped[date | None] = mapped_column(Date, nullable=True)
