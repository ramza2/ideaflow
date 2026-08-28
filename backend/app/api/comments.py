"""Comment HTTP endpoints (Step 10)."""

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
    CommentCreateRequest,
    CommentListResponse,
    CommentPublic,
    CommentUpdateRequest,
    EligibleReviewerList,
)
from app.services import comment as comment_service

router = APIRouter(
    prefix="/workspaces/{workspace_id}/ideas/{idea_id}",
    tags=["comments"],
)


@router.get("/mention-candidates", response_model=EligibleReviewerList)
def mention_candidates(
    idea_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> EligibleReviewerList:
    return comment_service.list_mention_candidates(
        db,
        workspace_id=ctx.workspace.id,
        idea_id=idea_id,
        user_id=ctx.user.id,
    )


@router.get("/comments", response_model=CommentListResponse)
def list_comments(
    idea_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CommentListResponse:
    return comment_service.list_comments(
        db,
        workspace_id=ctx.workspace.id,
        idea_id=idea_id,
        user_id=ctx.user.id,
        limit=limit,
        offset=offset,
    )


@router.post("/comments", response_model=CommentPublic, status_code=status.HTTP_201_CREATED)
def create_comment(
    idea_id: UUID,
    body: CommentCreateRequest,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> CommentPublic:
    del auth
    try:
        result = comment_service.create_comment(
            db,
            workspace_id=ctx.workspace.id,
            idea_id=idea_id,
            user_id=ctx.user.id,
            payload=body,
        )
        db.commit()
        return result
    except AppError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


@router.patch("/comments/{comment_id}", response_model=CommentPublic)
def update_comment(
    idea_id: UUID,
    comment_id: UUID,
    body: CommentUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> CommentPublic:
    del auth
    try:
        result = comment_service.update_comment(
            db,
            workspace_id=ctx.workspace.id,
            idea_id=idea_id,
            comment_id=comment_id,
            user_id=ctx.user.id,
            payload=body,
        )
        db.commit()
        return result
    except AppError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(
    idea_id: UUID,
    comment_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> None:
    del auth
    try:
        comment_service.delete_comment(
            db,
            workspace_id=ctx.workspace.id,
            idea_id=idea_id,
            comment_id=comment_id,
            user_id=ctx.user.id,
        )
        db.commit()
    except AppError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
