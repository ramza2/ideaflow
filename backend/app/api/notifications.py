"""Notification HTTP endpoints (Step 10)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, require_csrf
from app.api.workspace_deps import WorkspaceContext, get_workspace_context
from app.core.errors import AppError
from app.db.session import get_db
from app.schemas.collaboration import (
    NotificationListResponse,
    NotificationPublic,
    NotificationUnreadCount,
)
from app.services import notification as notification_service

router = APIRouter(prefix="/workspaces/{workspace_id}/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    unread_only: Annotated[bool, Query()] = False,
) -> NotificationListResponse:
    return notification_service.list_notifications(
        db,
        workspace_id=ctx.workspace.id,
        user_id=ctx.user.id,
        limit=limit,
        offset=offset,
        unread_only=unread_only,
    )


@router.get("/unread-count", response_model=NotificationUnreadCount)
def unread_count(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> NotificationUnreadCount:
    count = notification_service.unread_count(
        db,
        workspace_id=ctx.workspace.id,
        user_id=ctx.user.id,
    )
    return NotificationUnreadCount(count=count)


@router.post("/{notification_id}/read", response_model=NotificationPublic)
def mark_read(
    notification_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> NotificationPublic:
    del auth
    try:
        result = notification_service.mark_read(
            db,
            workspace_id=ctx.workspace.id,
            user_id=ctx.user.id,
            notification_id=notification_id,
        )
        db.commit()
        return result
    except AppError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
def mark_all_read(
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> None:
    del auth
    try:
        notification_service.mark_all_read(
            db,
            workspace_id=ctx.workspace.id,
            user_id=ctx.user.id,
        )
        db.commit()
    except AppError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
