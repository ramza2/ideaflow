"""Workspace-scoped FastAPI dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy.orm import Session

from app.api.deps import require_password_changed
from app.core.errors import AppError
from app.db.session import get_db
from app.models.enums import WorkspaceRole
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.services import workspace as workspace_service


@dataclass
class WorkspaceContext:
    workspace: Workspace
    membership: WorkspaceMember
    user: User


def get_workspace_context(
    workspace_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(require_password_changed)],
) -> WorkspaceContext:
    workspace, membership = workspace_service.get_workspace_for_member(
        db,
        workspace_id=workspace_id,
        user=user,
    )
    return WorkspaceContext(workspace=workspace, membership=membership, user=user)


def require_workspace_admin(
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> WorkspaceContext:
    if ctx.membership.role != WorkspaceRole.ADMIN.value:
        raise AppError(
            "Workspace admin required.",
            code="WORKSPACE_ADMIN_REQUIRED",
            status_code=403,
        )
    return ctx
