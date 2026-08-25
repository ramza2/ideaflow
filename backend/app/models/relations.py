"""Idea association / share / participant tables."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID as PyUUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import IdeaSharePermission
from app.models.mixins import UUIDPrimaryKeyMixin


class IdeaTag(Base):
    """Composite PK (idea_id, tag_id) enforces uniqueness and idea_id lookup.

    Keep ix_idea_tags_tag_id for Tag → Idea reverse lookups only.
    """

    __tablename__ = "idea_tags"
    __table_args__ = (Index("ix_idea_tags_tag_id", "tag_id"),)

    idea_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ideas.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    )


class IdeaShare(UUIDPrimaryKeyMixin, Base):
    """Explicit ACL grants for SELECTED_USERS (and optional assignee/participant shares).

    IdeaParticipant is NOT an ACL table — use IdeaShare for access.
    """

    __tablename__ = "idea_shares"
    __table_args__ = (
        UniqueConstraint("idea_id", "user_id", name="uq_idea_shares_idea_user"),
        CheckConstraint("permission IN ('READ', 'EDIT')", name="idea_share_permission"),
        Index("ix_idea_shares_idea_id", "idea_id"),
        Index("ix_idea_shares_user_id", "user_id"),
    )

    idea_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ideas.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    permission: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=IdeaSharePermission.READ.value,
        server_default=IdeaSharePermission.READ.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class IdeaParticipant(Base):
    """Collaboration membership — not an ACL table.

    Composite PK (idea_id, user_id) enforces uniqueness and idea_id lookup.
    Keep ix_idea_participants_user_id for User → Idea reverse lookups only.
    """

    __tablename__ = "idea_participants"
    __table_args__ = (Index("ix_idea_participants_user_id", "user_id"),)

    idea_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ideas.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
