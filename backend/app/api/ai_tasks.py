"""AI task aggregation HTTP endpoints (Step 19)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.workspace_deps import WorkspaceContext, get_workspace_context
from app.db.session import get_db
from app.schemas.ai_tasks import AiTaskListResponse
from app.services import ai_tasks as ai_tasks_service

router = APIRouter(prefix="/workspaces/{workspace_id}/ai-tasks", tags=["ai-tasks"])


@router.get("", response_model=AiTaskListResponse)
def list_ai_tasks(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> AiTaskListResponse:
    """List the current user's active and recently finished AI tasks."""
    return ai_tasks_service.list_ai_tasks(
        db,
        workspace_id=ctx.workspace.id,
        user_id=ctx.user.id,
    )
