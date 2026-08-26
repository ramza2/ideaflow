"""Workspace provisioning, membership, and RBAC helpers."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.defaults import DEFAULT_WORKSPACE_CATEGORIES, DEFAULT_WORKSPACE_STAGES
from app.models.enums import (
    UserStatus,
    WorkspaceMemberStatus,
    WorkspaceRole,
    WorkspaceType,
)
from app.models.user import User
from app.models.workspace import (
    Workspace,
    WorkspaceCategory,
    WorkspaceMember,
    WorkspaceStage,
)
from app.services.auth import normalize_email

PERSONAL_WORKSPACE_NAME = "내 작업공간"


@dataclass
class WorkspaceListItem:
    workspace: Workspace
    current_user_role: str


def seed_workspace_defaults(db: Session, workspace_id: UUID) -> None:
    """Insert the 10 default stages and 8 default categories for a workspace."""
    for stage in DEFAULT_WORKSPACE_STAGES:
        db.add(
            WorkspaceStage(
                workspace_id=workspace_id,
                slug=stage["slug"],
                label=stage["label"],
                sort_order=stage["sort_order"],
                is_default=stage["is_default"],
                is_terminal=stage["is_terminal"],
            )
        )
    for category in DEFAULT_WORKSPACE_CATEGORIES:
        db.add(
            WorkspaceCategory(
                workspace_id=workspace_id,
                slug=category["slug"],
                name=category["name"],
                sort_order=category["sort_order"],
            )
        )
    db.flush()


def _create_workspace_bundle(
    db: Session,
    *,
    owner: User,
    name: str,
    workspace_type: str,
    allow_llm: bool = True,
    allow_web_search: bool = True,
) -> Workspace:
    workspace = Workspace(
        name=name.strip(),
        type=workspace_type,
        owner_id=owner.id,
        allow_llm=allow_llm,
        allow_web_search=allow_web_search,
    )
    db.add(workspace)
    db.flush()

    db.add(
        WorkspaceMember(
            workspace_id=workspace.id,
            user_id=owner.id,
            role=WorkspaceRole.ADMIN.value,
            status=WorkspaceMemberStatus.ACTIVE.value,
            invited_by=None,
        )
    )
    seed_workspace_defaults(db, workspace.id)
    db.flush()
    return workspace


def get_active_personal_workspace(db: Session, user_id: UUID) -> Workspace | None:
    return db.scalar(
        select(Workspace).where(
            Workspace.owner_id == user_id,
            Workspace.type == WorkspaceType.PERSONAL.value,
            Workspace.deleted_at.is_(None),
        )
    )


def ensure_personal_workspace_for_user(db: Session, user: User) -> tuple[Workspace, bool]:
    """Idempotent PERSONAL workspace provisioning.

    Returns (workspace, created).
    """
    existing = get_active_personal_workspace(db, user.id)
    if existing is not None:
        return existing, False

    try:
        with db.begin_nested():
            workspace = _create_workspace_bundle(
                db,
                owner=user,
                name=PERSONAL_WORKSPACE_NAME,
                workspace_type=WorkspaceType.PERSONAL.value,
            )
            return workspace, True
    except IntegrityError:
        # Concurrent create raced on partial unique index — return the winner.
        existing = get_active_personal_workspace(db, user.id)
        if existing is None:
            raise
        return existing, False


def create_team_workspace(
    db: Session,
    *,
    owner: User,
    name: str,
    allow_llm: bool = True,
    allow_web_search: bool = True,
) -> Workspace:
    return _create_workspace_bundle(
        db,
        owner=owner,
        name=name,
        workspace_type=WorkspaceType.TEAM.value,
        allow_llm=allow_llm,
        allow_web_search=allow_web_search,
    )


def list_workspaces_for_user(db: Session, user: User) -> list[WorkspaceListItem]:
    rows = db.execute(
        select(Workspace, WorkspaceMember)
        .join(
            WorkspaceMember,
            WorkspaceMember.workspace_id == Workspace.id,
        )
        .where(
            WorkspaceMember.user_id == user.id,
            WorkspaceMember.status == WorkspaceMemberStatus.ACTIVE.value,
            Workspace.deleted_at.is_(None),
        )
    ).all()

    items = [
        WorkspaceListItem(workspace=ws, current_user_role=member.role) for ws, member in rows
    ]
    items.sort(
        key=lambda item: (
            0 if item.workspace.type == WorkspaceType.PERSONAL.value else 1,
            item.workspace.created_at,
            item.workspace.name.lower(),
        )
    )
    return items


def get_active_membership(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
) -> WorkspaceMember | None:
    return db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.status == WorkspaceMemberStatus.ACTIVE.value,
        )
    )


def get_workspace_for_member(
    db: Session,
    *,
    workspace_id: UUID,
    user: User,
) -> tuple[Workspace, WorkspaceMember]:
    workspace = db.get(Workspace, workspace_id)
    if workspace is None or workspace.deleted_at is not None:
        raise AppError("Workspace not found.", code="WORKSPACE_NOT_FOUND", status_code=404)

    membership = get_active_membership(db, workspace_id=workspace_id, user_id=user.id)
    if membership is None:
        raise AppError("Workspace not found.", code="WORKSPACE_NOT_FOUND", status_code=404)

    return workspace, membership


def update_workspace(
    db: Session,
    workspace: Workspace,
    *,
    name: str | None = None,
    allow_llm: bool | None = None,
    allow_web_search: bool | None = None,
) -> Workspace:
    if name is not None:
        workspace.name = name.strip()
    if allow_llm is not None:
        workspace.allow_llm = allow_llm
    if allow_web_search is not None:
        workspace.allow_web_search = allow_web_search
    db.flush()
    return workspace


def list_members(
    db: Session,
    *,
    workspace: Workspace,
    viewer_membership: WorkspaceMember,
) -> list[tuple[WorkspaceMember, User]]:
    stmt = (
        select(WorkspaceMember, User)
        .join(User, User.id == WorkspaceMember.user_id)
        .where(WorkspaceMember.workspace_id == workspace.id)
        .order_by(WorkspaceMember.created_at.asc())
    )
    if viewer_membership.role != WorkspaceRole.ADMIN.value:
        stmt = stmt.where(WorkspaceMember.status == WorkspaceMemberStatus.ACTIVE.value)
    return list(db.execute(stmt).all())


def _require_team_workspace_for_membership_mutation(workspace: Workspace) -> None:
    if workspace.type == WorkspaceType.PERSONAL.value:
        raise AppError(
            "Personal workspace membership cannot be modified.",
            code="PERSONAL_WORKSPACE_MEMBERSHIP_IMMUTABLE",
            status_code=409,
        )


def add_or_reactivate_member(
    db: Session,
    *,
    workspace: Workspace,
    actor: User,
    email: str,
    role: str,
) -> tuple[WorkspaceMember, User, bool]:
    """Add an existing ACTIVE user, or reactivate an INACTIVE membership.

    Returns (membership, target_user, created_or_reactivated).
    Already-ACTIVE memberships are returned unchanged (idempotent).
    """
    _require_team_workspace_for_membership_mutation(workspace)

    if role not in {
        WorkspaceRole.ADMIN.value,
        WorkspaceRole.MEMBER.value,
        WorkspaceRole.VIEWER.value,
    }:
        raise AppError("Invalid role.", code="INVALID_ROLE", status_code=400)

    target = db.scalar(select(User).where(User.email == normalize_email(email)))
    if target is None:
        raise AppError("User not found.", code="USER_NOT_FOUND", status_code=404)
    if target.deleted_at is not None or target.status != UserStatus.ACTIVE.value:
        raise AppError(
            "User is not eligible for workspace membership.",
            code="USER_NOT_ELIGIBLE",
            status_code=400,
        )

    existing = db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.user_id == target.id,
        )
    )
    if existing is not None:
        if existing.status == WorkspaceMemberStatus.ACTIVE.value:
            return existing, target, False
        existing.status = WorkspaceMemberStatus.ACTIVE.value
        existing.role = role
        existing.invited_by = actor.id
        db.flush()
        return existing, target, True

    membership = WorkspaceMember(
        workspace_id=workspace.id,
        user_id=target.id,
        role=role,
        status=WorkspaceMemberStatus.ACTIVE.value,
        invited_by=actor.id,
    )
    db.add(membership)
    db.flush()
    return membership, target, True


def change_member_role(
    db: Session,
    *,
    workspace: Workspace,
    target_user_id: UUID,
    role: str,
) -> WorkspaceMember:
    _require_team_workspace_for_membership_mutation(workspace)

    if role not in {
        WorkspaceRole.ADMIN.value,
        WorkspaceRole.MEMBER.value,
        WorkspaceRole.VIEWER.value,
    }:
        raise AppError("Invalid role.", code="INVALID_ROLE", status_code=400)

    if target_user_id == workspace.owner_id and role != WorkspaceRole.ADMIN.value:
        raise AppError(
            "Workspace owner role cannot be changed.",
            code="WORKSPACE_OWNER_ROLE_IMMUTABLE",
            status_code=409,
        )

    membership = db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.user_id == target_user_id,
        )
    )
    if membership is None or membership.status == WorkspaceMemberStatus.INACTIVE.value:
        raise AppError("Member not found.", code="MEMBER_NOT_FOUND", status_code=404)

    membership.role = role
    db.flush()
    return membership


def deactivate_member(
    db: Session,
    *,
    workspace: Workspace,
    target_user_id: UUID,
) -> None:
    _require_team_workspace_for_membership_mutation(workspace)

    if target_user_id == workspace.owner_id:
        raise AppError(
            "Workspace owner membership cannot be removed.",
            code="WORKSPACE_OWNER_MEMBERSHIP_IMMUTABLE",
            status_code=409,
        )

    membership = db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.user_id == target_user_id,
        )
    )
    if membership is None or membership.status == WorkspaceMemberStatus.INACTIVE.value:
        raise AppError("Member not found.", code="MEMBER_NOT_FOUND", status_code=404)

    membership.status = WorkspaceMemberStatus.INACTIVE.value
    db.flush()


def list_stages(db: Session, workspace_id: UUID) -> list[WorkspaceStage]:
    return list(
        db.scalars(
            select(WorkspaceStage)
            .where(
                WorkspaceStage.workspace_id == workspace_id,
                WorkspaceStage.deleted_at.is_(None),
            )
            .order_by(WorkspaceStage.sort_order.asc())
        )
    )


def list_categories(db: Session, workspace_id: UUID) -> list[WorkspaceCategory]:
    return list(
        db.scalars(
            select(WorkspaceCategory)
            .where(
                WorkspaceCategory.workspace_id == workspace_id,
                WorkspaceCategory.deleted_at.is_(None),
            )
            .order_by(WorkspaceCategory.sort_order.asc())
        )
    )


@dataclass
class BackfillResult:
    created: int = 0
    existing: int = 0
    failed: int = 0


def backfill_personal_workspaces(db: Session) -> BackfillResult:
    """Ensure PERSONAL workspaces for all non-deleted users."""
    result = BackfillResult()
    users = list(db.scalars(select(User).where(User.deleted_at.is_(None)).order_by(User.created_at)))
    for user in users:
        try:
            _workspace, created = ensure_personal_workspace_for_user(db, user)
            if created:
                result.created += 1
            else:
                result.existing += 1
        except Exception:
            result.failed += 1
    return result
