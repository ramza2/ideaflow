"""Idea Validation HTTP endpoints (Step 14)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, require_csrf
from app.api.workspace_deps import WorkspaceContext, get_workspace_context
from app.core.errors import AppError
from app.db.session import get_db
from app.schemas.validation import (
    IdeaValidationCompleteRequest,
    IdeaValidationCreateRequest,
    IdeaValidationListResponse,
    IdeaValidationPublic,
    IdeaValidationStartResponse,
    IdeaValidationUpdateRequest,
)
from app.services import validation as validation_service

router = APIRouter(
    prefix="/workspaces/{workspace_id}/ideas/{idea_id}/validations",
    tags=["validations"],
)


@router.get("", response_model=IdeaValidationListResponse)
def list_validations(
    idea_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> IdeaValidationListResponse:
    return validation_service.list_validations(
        db,
        workspace_id=ctx.workspace.id,
        idea_id=idea_id,
        user_id=ctx.user.id,
    )


@router.post("", response_model=IdeaValidationPublic, status_code=status.HTTP_201_CREATED)
def create_validation(
    idea_id: UUID,
    body: IdeaValidationCreateRequest,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> IdeaValidationPublic:
    del auth
    try:
        result = validation_service.create_validation(
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


@router.get("/{validation_id}", response_model=IdeaValidationPublic)
def get_validation(
    idea_id: UUID,
    validation_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> IdeaValidationPublic:
    return validation_service.get_validation(
        db,
        workspace_id=ctx.workspace.id,
        idea_id=idea_id,
        validation_id=validation_id,
        user_id=ctx.user.id,
    )


@router.patch("/{validation_id}", response_model=IdeaValidationPublic)
def patch_validation(
    idea_id: UUID,
    validation_id: UUID,
    body: IdeaValidationUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> IdeaValidationPublic:
    del auth
    try:
        result = validation_service.update_validation(
            db,
            workspace_id=ctx.workspace.id,
            idea_id=idea_id,
            validation_id=validation_id,
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


@router.post("/{validation_id}/ready", response_model=IdeaValidationPublic)
def mark_ready(
    idea_id: UUID,
    validation_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> IdeaValidationPublic:
    del auth
    try:
        result = validation_service.mark_ready(
            db,
            workspace_id=ctx.workspace.id,
            idea_id=idea_id,
            validation_id=validation_id,
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


@router.post("/{validation_id}/start", response_model=IdeaValidationStartResponse)
def start_validation(
    idea_id: UUID,
    validation_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> IdeaValidationStartResponse:
    del auth
    try:
        result = validation_service.start_validation(
            db,
            workspace_id=ctx.workspace.id,
            idea_id=idea_id,
            validation_id=validation_id,
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


@router.post("/{validation_id}/complete", response_model=IdeaValidationPublic)
def complete_validation(
    idea_id: UUID,
    validation_id: UUID,
    body: IdeaValidationCompleteRequest,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> IdeaValidationPublic:
    del auth
    try:
        result = validation_service.complete_validation(
            db,
            workspace_id=ctx.workspace.id,
            idea_id=idea_id,
            validation_id=validation_id,
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


@router.post("/{validation_id}/cancel", response_model=IdeaValidationPublic)
def cancel_validation(
    idea_id: UUID,
    validation_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> IdeaValidationPublic:
    del auth
    try:
        result = validation_service.cancel_validation(
            db,
            workspace_id=ctx.workspace.id,
            idea_id=idea_id,
            validation_id=validation_id,
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
