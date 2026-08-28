"""Web research HTTP endpoints (workspace-scoped, requester-only)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, require_csrf
from app.api.workspace_deps import WorkspaceContext, get_workspace_context
from app.core.errors import AppError
from app.db.session import get_db
from app.schemas.research import (
    WebResearchLatestResponse,
    WebResearchPreviewRequest,
    WebResearchRunPublic,
)
from app.services import web_research as web_research_service

router = APIRouter(
    prefix="/workspaces/{workspace_id}/ai-sessions/{session_id}/research-runs",
    tags=["web-research"],
)


@router.post("/preview", response_model=WebResearchRunPublic, status_code=status.HTTP_201_CREATED)
def preview_research_run(
    body: WebResearchPreviewRequest,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    session_id: UUID,
) -> WebResearchRunPublic:
    del auth
    try:
        run = web_research_service.preview_research_run(
            db,
            workspace=ctx.workspace,
            user=ctx.user,
            session_id=session_id,
            payload=body,
        )
        db.commit()
        db.refresh(run)
    except AppError:
        db.rollback()
        raise
    return web_research_service.to_public(db, run)


@router.get("/latest", response_model=WebResearchLatestResponse)
def get_latest_research_run(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    session_id: UUID,
) -> WebResearchLatestResponse:
    return web_research_service.get_latest_research_run(
        db,
        workspace_id=ctx.workspace.id,
        session_id=session_id,
        user_id=ctx.user.id,
    )


@router.get("/{run_id}", response_model=WebResearchRunPublic)
def get_research_run(
    run_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    session_id: UUID,
) -> WebResearchRunPublic:
    return web_research_service.get_research_run(
        db,
        workspace_id=ctx.workspace.id,
        session_id=session_id,
        run_id=run_id,
        user_id=ctx.user.id,
    )


@router.post("/{run_id}/approve", response_model=WebResearchRunPublic)
def approve_research_run(
    run_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    session_id: UUID,
) -> WebResearchRunPublic:
    del auth
    try:
        run = web_research_service.approve_research_run(
            db,
            workspace=ctx.workspace,
            user=ctx.user,
            session_id=session_id,
            run_id=run_id,
        )
        db.commit()
        db.refresh(run)
    except AppError:
        db.rollback()
        raise
    return web_research_service.to_public(db, run)


@router.post("/{run_id}/cancel", response_model=WebResearchRunPublic)
def cancel_research_run(
    run_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    session_id: UUID,
) -> WebResearchRunPublic:
    del auth
    try:
        run = web_research_service.cancel_research_run(
            db,
            workspace=ctx.workspace,
            user=ctx.user,
            session_id=session_id,
            run_id=run_id,
        )
        db.commit()
        db.refresh(run)
    except AppError:
        db.rollback()
        raise
    return web_research_service.to_public(db, run)


@router.post("/{run_id}/retry", response_model=WebResearchRunPublic)
def retry_research_run(
    run_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    session_id: UUID,
) -> WebResearchRunPublic:
    del auth
    try:
        run = web_research_service.retry_research_run(
            db,
            workspace=ctx.workspace,
            user=ctx.user,
            session_id=session_id,
            run_id=run_id,
        )
        db.commit()
        db.refresh(run)
    except AppError:
        db.rollback()
        raise
    return web_research_service.to_public(db, run)
