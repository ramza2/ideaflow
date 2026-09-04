"""Idea HTTP endpoints (workspace-scoped)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, require_csrf
from app.api.workspace_deps import WorkspaceContext, get_workspace_context
from app.core.errors import AppError
from app.db.session import get_db
from app.schemas.ai import AiRefineSessionCreate, AiSessionPublic
from app.schemas.idea import (
    IdeaCreate,
    IdeaDetail,
    IdeaListResponse,
    IdeaSharePublic,
    IdeaShareReplace,
    IdeaUpdate,
)
from app.schemas.research import IdeaEvidenceResponse
from app.services import ai_session as ai_session_service
from app.services import idea as idea_service
from app.services import idea_access
from app.services import idea_search
from app.services import web_research as web_research_service

router = APIRouter(
    prefix="/workspaces/{workspace_id}/ideas",
    tags=["ideas"],
)


@router.get("", response_model=IdeaListResponse)
def list_ideas(
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
    q: Annotated[str | None, Query()] = None,
    stage_id: Annotated[UUID | None, Query()] = None,
    category_id: Annotated[UUID | None, Query()] = None,
    priority: Annotated[str | None, Query()] = None,
    feasibility: Annotated[str | None, Query()] = None,
    visibility: Annotated[str | None, Query()] = None,
    author_id: Annotated[UUID | None, Query()] = None,
    assignee_id: Annotated[UUID | None, Query()] = None,
    search_mode: Annotated[str, Query()] = "keyword",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> IdeaListResponse:
    return idea_search.list_ideas_with_search_mode(
        db,
        workspace_id=ctx.workspace.id,
        user_id=ctx.user.id,
        q=q,
        search_mode=search_mode,
        stage_id=stage_id,
        category_id=category_id,
        priority=priority,
        feasibility=feasibility,
        visibility=visibility,
        author_id=author_id,
        assignee_id=assignee_id,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=IdeaDetail, status_code=status.HTTP_201_CREATED)
def create_idea(
    body: IdeaCreate,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> IdeaDetail:
    del auth
    try:
        idea = idea_service.create_idea(
            db,
            workspace_id=ctx.workspace.id,
            author=ctx.user,
            payload=body,
        )
        db.commit()
        db.refresh(idea)
        return idea_service.to_detail(db, idea, user_id=ctx.user.id, share=None)
    except AppError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


@router.get("/{idea_id}", response_model=IdeaDetail)
def get_idea(
    idea_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> IdeaDetail:
    idea, share = idea_service.get_readable_idea(
        db,
        workspace_id=ctx.workspace.id,
        idea_id=idea_id,
        user_id=ctx.user.id,
    )
    return idea_service.to_detail(db, idea, user_id=ctx.user.id, share=share)


@router.get("/{idea_id}/evidence", response_model=IdeaEvidenceResponse)
def get_idea_evidence(
    idea_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> IdeaEvidenceResponse:
    return web_research_service.get_idea_evidence(
        db,
        workspace_id=ctx.workspace.id,
        idea_id=idea_id,
        user_id=ctx.user.id,
    )


@router.patch("/{idea_id}", response_model=IdeaDetail)
def patch_idea(
    idea_id: UUID,
    body: IdeaUpdate,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> IdeaDetail:
    del auth
    try:
        idea, share, access = idea_service.require_idea_edit(
            db,
            workspace_id=ctx.workspace.id,
            idea_id=idea_id,
            user_id=ctx.user.id,
        )
        old_assignee_id = idea.assignee_id
        idea = idea_service.update_idea(db, idea=idea, access=access, payload=body)
        if "assignee_id" in body.model_fields_set:
            from app.services import notification as notification_service

            if (
                idea.assignee_id is not None
                and idea.assignee_id != old_assignee_id
                and idea.assignee_id != ctx.user.id
            ):
                notification_service.emit_assigned(
                    db,
                    workspace_id=ctx.workspace.id,
                    idea=idea,
                    assignee_id=idea.assignee_id,
                    actor_id=ctx.user.id,
                )
        db.commit()
        db.refresh(idea)
        share = idea_access.get_idea_share(db, idea.id, ctx.user.id)
        return idea_service.to_detail(db, idea, user_id=ctx.user.id, share=share)
    except AppError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


@router.delete("/{idea_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_idea(
    idea_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> None:
    del auth
    try:
        idea = idea_service.require_idea_owner(
            db,
            workspace_id=ctx.workspace.id,
            idea_id=idea_id,
            user_id=ctx.user.id,
        )
        idea_service.soft_delete_idea(db, idea)
        db.commit()
    except AppError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


@router.post(
    "/{idea_id}/ai-refine-sessions",
    response_model=AiSessionPublic,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_ai_refine_session(
    idea_id: UUID,
    body: AiRefineSessionCreate,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> AiSessionPublic:
    del auth
    try:
        session = ai_session_service.create_refine_ai_session(
            db,
            workspace=ctx.workspace,
            requester=ctx.user,
            idea_id=idea_id,
            direction=body.direction,
        )
        db.commit()
        db.refresh(session)
    except AppError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    return ai_session_service.to_public(session)


@router.get("/{idea_id}/shares", response_model=list[IdeaSharePublic])
def get_shares(
    idea_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> list[IdeaSharePublic]:
    idea = idea_service.require_idea_owner(
        db,
        workspace_id=ctx.workspace.id,
        idea_id=idea_id,
        user_id=ctx.user.id,
    )
    return idea_service.list_shares(db, idea)


@router.put("/{idea_id}/shares", response_model=list[IdeaSharePublic])
def put_shares(
    idea_id: UUID,
    body: IdeaShareReplace,
    db: Annotated[Session, Depends(get_db)],
    auth: Annotated[AuthContext, Depends(require_csrf)],
    ctx: Annotated[WorkspaceContext, Depends(get_workspace_context)],
) -> list[IdeaSharePublic]:
    del auth
    try:
        idea = idea_service.require_idea_owner(
            db,
            workspace_id=ctx.workspace.id,
            idea_id=idea_id,
            user_id=ctx.user.id,
        )
        if idea.visibility != "SELECTED_USERS" and body.shares:
            # Allow clearing shares always; setting shares requires SELECTED_USERS.
            raise AppError(
                "Shares require SELECTED_USERS visibility.",
                code="INVALID_IDEA_REFERENCE",
                status_code=400,
            )
        if idea.visibility == "SELECTED_USERS":
            idea_service.replace_shares(db, idea=idea, shares=body.shares)
        else:
            idea_service.clear_shares(db, idea.id)
        db.commit()
        return idea_service.list_shares(db, idea)
    except AppError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
