"""Workspace HTTP endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, require_csrf, require_password_changed
from app.api.workspace_deps import (
    WorkspaceContext,
    get_workspace_context,
    require_workspace_admin,
)
from app.core.errors import AppError
from app.db.session import get_db
from app.models.user import User
from app.schemas.workspace import (
    CategoryPublic,
    MemberAddRequest,
    MemberPublic,
    MemberRoleUpdate,
    StagePublic,
    TeamWorkspaceCreate,
    WorkspacePublic,
    WorkspaceUpdate,
)
from app.services import system_setting as system_setting_service
from app.services import workspace as workspace_service

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def _workspace_public(db: Session, workspace, role: str) -> WorkspacePublic:
    return WorkspacePublic(
        id=workspace.id,
        name=workspace.name,
        type=workspace.type,
        owner_id=workspace.owner_id,
        allow_llm=workspace.allow_llm,
        allow_web_search=workspace.allow_web_search,
        effective_allow_llm=system_setting_service.effective_allow_llm(db, workspace),
        effective_allow_web_search=system_setting_service.effective_allow_web_search(
            db, workspace
        ),
        current_user_role=role,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
    )


def _member_public(membership, user: User) -> MemberPublic:
    return MemberPublic(
        user_id=membership.user_id,
        email=user.email,
        name=user.name,
        role=membership.role,
        status=membership.status,
        created_at=membership.created_at,
        updated_at=membership.updated_at,
    )


@router.get("", response_model=list[WorkspacePublic])
def list_workspaces(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_password_changed)],
) -> list[WorkspacePublic]:
    items = workspace_service.list_workspaces_for_user(db, user)
    return [_workspace_public(db, item.workspace, item.current_user_role) for item in items]


@router.post("", response_model=WorkspacePublic, status_code=status.HTTP_201_CREATED)
def create_team_workspace(
    body: TeamWorkspaceCreate,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    user: Annotated[User, Depends(require_password_changed)],
) -> WorkspacePublic:
    del auth  # CSRF validated via require_csrf
    try:
        workspace = workspace_service.create_team_workspace(
            db,
            owner=user,
            name=body.name,
            allow_llm=body.allow_llm,
            allow_web_search=body.allow_web_search,
        )
        db.commit()
        db.refresh(workspace)
    except AppError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    return _workspace_public(db, workspace, "ADMIN")


@router.get("/{workspace_id}", response_model=WorkspacePublic)
def get_workspace(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> WorkspacePublic:
    return _workspace_public(db, ctx.workspace, ctx.membership.role)


@router.patch("/{workspace_id}", response_model=WorkspacePublic)
def patch_workspace(
    body: WorkspaceUpdate,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    ctx: Annotated[WorkspaceContext, Depends(require_workspace_admin)],
) -> WorkspacePublic:
    del auth
    try:
        workspace = workspace_service.update_workspace(
            db,
            ctx.workspace,
            name=body.name,
            allow_llm=body.allow_llm,
            allow_web_search=body.allow_web_search,
        )
        db.commit()
        db.refresh(workspace)
    except AppError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    return _workspace_public(db, workspace, ctx.membership.role)


@router.get("/{workspace_id}/members", response_model=list[MemberPublic])
def list_members(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> list[MemberPublic]:
    rows = workspace_service.list_members(
        db,
        workspace=ctx.workspace,
        viewer_membership=ctx.membership,
    )
    return [_member_public(membership, user) for membership, user in rows]


@router.post(
    "/{workspace_id}/members",
    response_model=MemberPublic,
    status_code=status.HTTP_201_CREATED,
)
def add_member(
    body: MemberAddRequest,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    ctx: Annotated[WorkspaceContext, Depends(require_workspace_admin)],
) -> MemberPublic:
    del auth
    try:
        membership, target, created_or_reactivated = workspace_service.add_or_reactivate_member(
            db,
            workspace=ctx.workspace,
            actor=ctx.user,
            email=str(body.email),
            role=body.role.value,
        )
        db.commit()
        db.refresh(membership)
        db.refresh(target)
    except AppError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

    if not created_or_reactivated:
        response.status_code = status.HTTP_200_OK
    return _member_public(membership, target)


@router.patch("/{workspace_id}/members/{user_id}", response_model=MemberPublic)
def patch_member_role(
    user_id: UUID,
    body: MemberRoleUpdate,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    ctx: Annotated[WorkspaceContext, Depends(require_workspace_admin)],
) -> MemberPublic:
    del auth
    try:
        membership = workspace_service.change_member_role(
            db,
            workspace=ctx.workspace,
            target_user_id=user_id,
            role=body.role.value,
        )
        db.commit()
        db.refresh(membership)
        target = db.get(User, membership.user_id)
        assert target is not None
    except AppError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    return _member_public(membership, target)


@router.delete(
    "/{workspace_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_member(
    user_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    ctx: Annotated[WorkspaceContext, Depends(require_workspace_admin)],
) -> None:
    del auth
    try:
        workspace_service.deactivate_member(
            db,
            workspace=ctx.workspace,
            target_user_id=user_id,
        )
        db.commit()
    except AppError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


@router.get("/{workspace_id}/stages", response_model=list[StagePublic])
def get_stages(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> list[StagePublic]:
    stages = workspace_service.list_stages(db, ctx.workspace.id)
    return [StagePublic.model_validate(stage) for stage in stages]


@router.get("/{workspace_id}/categories", response_model=list[CategoryPublic])
def get_categories(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> list[CategoryPublic]:
    categories = workspace_service.list_categories(db, ctx.workspace.id)
    return [CategoryPublic.model_validate(category) for category in categories]
