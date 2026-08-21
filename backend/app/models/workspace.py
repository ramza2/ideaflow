"""Workspace-scoped ORM models."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID as PyUUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import WorkspaceMemberStatus, WorkspaceRole
from app.models.mixins import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Workspace(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "workspaces"
    __table_args__ = (
        CheckConstraint("type IN ('PERSONAL', 'TEAM')", name="workspace_type"),
        # At most one active PERSONAL workspace per owner (soft-deleted excluded).
        Index(
            "uq_workspaces_one_personal_per_owner",
            "owner_id",
            unique=True,
            postgresql_where=text("type = 'PERSONAL' AND deleted_at IS NULL"),
        ),
        Index("ix_workspaces_owner_id", "owner_id"),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    owner_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    allow_llm: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    allow_web_search: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class WorkspaceMember(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "workspace_members"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_members_workspace_user"),
        CheckConstraint("role IN ('ADMIN', 'MEMBER', 'VIEWER')", name="workspace_member_role"),
        CheckConstraint(
            "status IN ('PENDING', 'ACTIVE', 'INACTIVE')",
            name="workspace_member_status",
        ),
        Index("ix_workspace_members_workspace_id", "workspace_id"),
        Index("ix_workspace_members_user_id", "user_id"),
    )

    workspace_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=WorkspaceRole.MEMBER.value,
        server_default=WorkspaceRole.MEMBER.value,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=WorkspaceMemberStatus.ACTIVE.value,
        server_default=WorkspaceMemberStatus.ACTIVE.value,
    )
    invited_by: Mapped[PyUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


class WorkspaceStage(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "workspace_stages"
    __table_args__ = (
        UniqueConstraint("workspace_id", "slug", name="uq_workspace_stages_workspace_slug"),
        Index("ix_workspace_stages_workspace_id", "workspace_id"),
    )

    workspace_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_terminal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )


class WorkspaceCategory(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "workspace_categories"
    __table_args__ = (
        UniqueConstraint("workspace_id", "slug", name="uq_workspace_categories_workspace_slug"),
        Index("ix_workspace_categories_workspace_id", "workspace_id"),
    )

    workspace_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)


class Tag(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_tags_workspace_name"),
        Index("ix_tags_workspace_id", "workspace_id"),
    )

    workspace_id: Mapped[PyUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    color: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
