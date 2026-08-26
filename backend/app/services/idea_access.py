"""Idea ACL helpers — SQL predicates and access calculation."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, and_, exists, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

from app.models.enums import IdeaSharePermission, IdeaVisibility
from app.models.idea import Idea
from app.models.relations import IdeaShare

ACCESS_OWNER = "OWNER"
ACCESS_EDIT = "EDIT"
ACCESS_READ = "READ"


def readable_idea_predicate(user_id: UUID) -> ColumnElement[bool]:
    """SQL predicate: Idea rows the user may read (soft-deleted excluded by caller)."""
    share_exists = exists(
        select(IdeaShare.id).where(
            IdeaShare.idea_id == Idea.id,
            IdeaShare.user_id == user_id,
        )
    )
    return or_(
        and_(
            Idea.visibility == IdeaVisibility.PRIVATE.value,
            Idea.author_id == user_id,
        ),
        Idea.visibility == IdeaVisibility.WORKSPACE.value,
        and_(
            Idea.visibility == IdeaVisibility.SELECTED_USERS.value,
            or_(Idea.author_id == user_id, share_exists),
        ),
    )


def apply_readable_filter(stmt: Select, user_id: UUID) -> Select:
    return stmt.where(
        Idea.deleted_at.is_(None),
        readable_idea_predicate(user_id),
    )


def get_idea_share(db: Session, idea_id: UUID, user_id: UUID) -> IdeaShare | None:
    return db.scalar(
        select(IdeaShare).where(
            IdeaShare.idea_id == idea_id,
            IdeaShare.user_id == user_id,
        )
    )


def compute_access(idea: Idea, user_id: UUID, share: IdeaShare | None) -> str:
    if idea.author_id == user_id:
        return ACCESS_OWNER
    if (
        idea.visibility == IdeaVisibility.SELECTED_USERS.value
        and share is not None
        and share.permission == IdeaSharePermission.EDIT.value
    ):
        return ACCESS_EDIT
    return ACCESS_READ


def can_read_idea(idea: Idea, user_id: UUID, share: IdeaShare | None) -> bool:
    if idea.deleted_at is not None:
        return False
    if idea.visibility == IdeaVisibility.PRIVATE.value:
        return idea.author_id == user_id
    if idea.visibility == IdeaVisibility.WORKSPACE.value:
        return True  # ACTIVE membership already required by workspace dependency
    if idea.visibility == IdeaVisibility.SELECTED_USERS.value:
        return idea.author_id == user_id or share is not None
    return False


def can_edit_idea(idea: Idea, user_id: UUID, share: IdeaShare | None) -> bool:
    if idea.deleted_at is not None:
        return False
    if idea.author_id == user_id:
        return True
    return (
        idea.visibility == IdeaVisibility.SELECTED_USERS.value
        and share is not None
        and share.permission == IdeaSharePermission.EDIT.value
    )


def is_owner(idea: Idea, user_id: UUID) -> bool:
    return idea.author_id == user_id and idea.deleted_at is None
