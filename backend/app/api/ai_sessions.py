"""AI Session HTTP endpoints (workspace-scoped)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, require_csrf
from app.api.workspace_deps import WorkspaceContext, get_workspace_context
from app.core.errors import AppError
from app.db.session import get_db
from app.schemas.ai import (
    AiRefineApplyRequest,
    AiRefineApplyResponse,
    AiSessionConfirmRequest,
    AiSessionConfirmResponse,
    AiSessionCreate,
    AiSessionPublic,
    AiSessionRegenerateResponse,
    AiSessionReviewDraftSaveRequest,
    ClarificationSubmit,
)
from app.services import ai_session as ai_session_service

router = APIRouter(
    prefix="/workspaces/{workspace_id}/ai-sessions",
    tags=["ai-sessions"],
)


@router.post("", response_model=AiSessionPublic, status_code=status.HTTP_202_ACCEPTED)
def create_ai_session(
    body: AiSessionCreate,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> AiSessionPublic:
    del auth  # CSRF + membership already enforced
    try:
        session = ai_session_service.create_ai_session(
            db,
            workspace=ctx.workspace,
            requester=ctx.user,
            payload=body,
        )
        db.commit()
        db.refresh(session)
    except AppError:
        db.rollback()
        raise
    response.status_code = status.HTTP_202_ACCEPTED
    return ai_session_service.to_public(session)


@router.get("/{session_id}", response_model=AiSessionPublic)
def get_ai_session(
    session_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> AiSessionPublic:
    # GET does not require allow_llm — existing drafts remain readable.
    session = ai_session_service.get_session_for_requester(
        db,
        workspace_id=ctx.workspace.id,
        session_id=session_id,
        user_id=ctx.user.id,
    )
    return ai_session_service.to_public(session)


@router.post("/{session_id}/clarifications", response_model=AiSessionPublic)
def submit_clarifications(
    session_id: UUID,
    body: ClarificationSubmit,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> AiSessionPublic:
    del auth
    try:
        session = ai_session_service.submit_clarifications(
            db,
            workspace=ctx.workspace,
            user_id=ctx.user.id,
            session_id=session_id,
            payload=body,
        )
        db.commit()
        db.refresh(session)
    except AppError:
        db.rollback()
        raise
    return ai_session_service.to_public(session)


@router.post("/{session_id}/retry", response_model=AiSessionPublic)
def retry_ai_session(
    session_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> AiSessionPublic:
    del auth
    try:
        session = ai_session_service.retry_ai_session(
            db,
            workspace=ctx.workspace,
            user_id=ctx.user.id,
            session_id=session_id,
        )
        db.commit()
        db.refresh(session)
    except AppError:
        db.rollback()
        raise
    return ai_session_service.to_public(session)


@router.post("/{session_id}/confirm", response_model=AiSessionConfirmResponse)
def confirm_ai_session(
    session_id: UUID,
    body: AiSessionConfirmRequest,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> AiSessionConfirmResponse:
    del auth
    # Confirm does not call LLM; allow_llm is not required.
    try:
        result = ai_session_service.confirm_ai_session(
            db,
            workspace=ctx.workspace,
            user=ctx.user,
            session_id=session_id,
            payload=body,
        )
        db.commit()
    except AppError:
        db.rollback()
        raise
    return result


@router.post("/{session_id}/apply-refinement", response_model=AiRefineApplyResponse)
def apply_refinement(
    session_id: UUID,
    body: AiRefineApplyRequest,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> AiRefineApplyResponse:
    del auth
    # Apply does not call the LLM; allow_llm is not required.
    try:
        result = ai_session_service.apply_refinement(
            db,
            workspace=ctx.workspace,
            user=ctx.user,
            session_id=session_id,
            payload=body,
        )
        db.commit()
    except AppError:
        db.rollback()
        raise
    return result


@router.put("/{session_id}/review-draft", response_model=AiSessionPublic)
def save_review_draft(
    session_id: UUID,
    body: AiSessionReviewDraftSaveRequest,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> AiSessionPublic:
    del auth
    try:
        session = ai_session_service.save_review_draft(
            db,
            workspace=ctx.workspace,
            user_id=ctx.user.id,
            session_id=session_id,
            payload=body,
        )
        db.commit()
        db.refresh(session)
    except AppError:
        db.rollback()
        raise
    return ai_session_service.to_public(session)


@router.post("/{session_id}/regenerate", response_model=AiSessionRegenerateResponse)
def regenerate_ai_session(
    session_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> AiSessionRegenerateResponse:
    del auth
    try:
        session = ai_session_service.regenerate_ai_session(
            db,
            workspace=ctx.workspace,
            requester=ctx.user,
            session_id=session_id,
        )
        db.commit()
        db.refresh(session)
    except AppError:
        db.rollback()
        raise
    return AiSessionRegenerateResponse(session=ai_session_service.to_public(session))
