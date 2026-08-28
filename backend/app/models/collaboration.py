"""Review, comment, and notification ORM models (Step 10)."""

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
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import ReviewKind, ReviewResult, ReviewStatus
from app.models.mixins import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class IdeaReviewRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "idea_review_requests"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('GENERAL', 'NEEDS_INFO', 'NEXT_STAGE')",
            name="idea_review_request_kind",
        ),
        CheckConstraint(
            "status IN ('OPEN', 'COMPLETED', 'CANCELLED')",
            name="idea_review_request_status",
        ),
        CheckConstraint(
            "result IS NULL OR result IN ("
            "'ADVANCE_RECOMMENDED', 'KEEP', 'HOLD', 'NEEDS_INFO')",
            name="idea_review_request_result",
        ),
        Index("ix_review_workspace", "workspace_id"),
        Index("ix_review_idea", "idea_id"),
        Index("ix_review_reviewer_status", "reviewer_id", "status"),
        Index("ix_review_requested_by", "requested_by"),
        Index("ix_review_due_date", "due_date"),
        Index(
            "uq_review_open_idea_reviewer",
            "idea_id",
            "reviewer_id",
            unique=True,
            postgresql_where=text("status = 'OPEN'"),
        ),
    )

    workspace_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
    )
    idea_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ideas.id", ondelete="RESTRICT"),
        nullable=False,
    )
    requested_by: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reviewer_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ReviewStatus.OPEN.value,
        server_default=ReviewStatus.OPEN.value,
    )
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    result: Mapped[str | None] = mapped_column(String(32), nullable=True)
    completion_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_next_review_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IdeaComment(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "idea_comments"
    __table_args__ = (
        Index("ix_comments_idea_created", "idea_id", "created_at"),
        Index("ix_comments_author", "author_id"),
    )

    workspace_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
    )
    idea_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ideas.id", ondelete="RESTRICT"),
        nullable=False,
    )
    author_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)


class IdeaCommentMention(Base):
    __tablename__ = "idea_comment_mentions"
    __table_args__ = (
        Index("ix_comment_mentions_user", "user_id"),
    )

    comment_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("idea_comments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class Notification(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "type IN ("
            "'REVIEW_REQUESTED', 'REVIEW_COMPLETED', 'COMMENT_ADDED', "
            "'MENTION', 'ASSIGNED')",
            name="notification_type",
        ),
        UniqueConstraint("recipient_id", "dedupe_key", name="uq_notification_dedupe"),
        Index("ix_notifications_recipient_created", "recipient_id", "created_at"),
        Index("ix_notifications_recipient_read", "recipient_id", "read_at"),
        Index("ix_notifications_workspace_recipient", "workspace_id", "recipient_id"),
    )

    workspace_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
    )
    recipient_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    actor_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)

    idea_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ideas.id", ondelete="RESTRICT"),
        nullable=True,
    )
    comment_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("idea_comments.id", ondelete="RESTRICT"),
        nullable=True,
    )
    review_request_id: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("idea_review_requests.id", ondelete="RESTRICT"),
        nullable=True,
    )

    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )
