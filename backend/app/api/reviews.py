"""Review HTTP endpoints (Step 10)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, require_csrf
from app.api.workspace_deps import WorkspaceContext, get_workspace_context
from app.core.errors import AppError
from app.db.session import get_db
from app.schemas.collaboration import (
    EligibleReviewerList,
    ReviewCompleteRequest,
    ReviewCreateRequest,
    ReviewInboxCounts,
    ReviewInboxResponse,
    ReviewRequestPublic,
)
from app.services import review as review_service

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["reviews"])


@router.get("/ideas/{idea_id}/eligible-reviewers", response_model=EligibleReviewerList)
def eligible_reviewers(
    idea_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> EligibleReviewerList:
    return review_service.list_eligible_reviewers(
        db,
        workspace_id=ctx.workspace.id,
        idea_id=idea_id,
        user_id=ctx.user.id,
    )


@router.post(
    "/ideas/{idea_id}/reviews",
    response_model=ReviewRequestPublic,
    status_code=status.HTTP_201_CREATED,
)
def create_review(
    idea_id: UUID,
    body: ReviewCreateRequest,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> ReviewRequestPublic:
    del auth
    try:
        result = review_service.create_review_request(
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
    except IntegrityError:
        db.rollback()
        raise AppError(
            "An open review already exists for this reviewer.",
            code="REVIEW_ALREADY_OPEN",
            status_code=409,
        )
    except Exception:
        db.rollback()
        raise


@router.get("/ideas/{idea_id}/reviews", response_model=list[ReviewRequestPublic])
def list_idea_reviews(
    idea_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> list[ReviewRequestPublic]:
    return review_service.list_idea_reviews(
        db,
        workspace_id=ctx.workspace.id,
        idea_id=idea_id,
        user_id=ctx.user.id,
    )


@router.post("/reviews/{review_id}/complete", response_model=ReviewRequestPublic)
def complete_review(
    review_id: UUID,
    body: ReviewCompleteRequest,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> ReviewRequestPublic:
    del auth
    try:
        result = review_service.complete_review(
            db,
            workspace_id=ctx.workspace.id,
            review_id=review_id,
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


@router.post("/reviews/{review_id}/cancel", response_model=ReviewRequestPublic)
def cancel_review(
    review_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> ReviewRequestPublic:
    del auth
    try:
        result = review_service.cancel_review(
            db,
            workspace_id=ctx.workspace.id,
            review_id=review_id,
            user_id=ctx.user.id,
        )
        db.commit()
        return result
    except AppError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


@router.get("/review-inbox", response_model=ReviewInboxResponse)
def review_inbox(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    tab: Annotated[str, Query()] = "scheduled",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReviewInboxResponse:
    return review_service.list_review_inbox(
        db,
        workspace_id=ctx.workspace.id,
        user_id=ctx.user.id,
        tab=tab,
        limit=limit,
        offset=offset,
    )


@router.get("/review-inbox/counts", response_model=ReviewInboxCounts)
def review_inbox_counts(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> ReviewInboxCounts:
    return review_service.review_inbox_counts(
        db,
        workspace_id=ctx.workspace.id,
        user_id=ctx.user.id,
    )
