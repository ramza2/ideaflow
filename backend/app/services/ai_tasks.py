"""Aggregate in-progress / recently finished AI tasks for the current user.

Step 19: no new DB table — compose IdeaAiSession + WebResearchRun rows.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.ai import IdeaAiSession
from app.models.enums import (
    IdeaAiSessionPurpose,
    IdeaAiSessionStatus,
    WebResearchRunStatus,
)
from app.models.idea import Idea
from app.models.research import WebResearchRun
from app.schemas.ai_tasks import AiTaskListResponse, AiTaskPublic

# Keep recently finished tasks visible in the header list briefly.
RECENT_TERMINAL_WINDOW = timedelta(minutes=30)

_SESSION_ACTIVE = {IdeaAiSessionStatus.PROCESSING.value}
_SESSION_RECENT_TERMINAL = {
    IdeaAiSessionStatus.NEEDS_CLARIFICATION.value,
    IdeaAiSessionStatus.READY_FOR_REVIEW.value,
    IdeaAiSessionStatus.FAILED.value,
}
_RESEARCH_ACTIVE = {
    WebResearchRunStatus.QUEUED.value,
    WebResearchRunStatus.SEARCHING.value,
    WebResearchRunStatus.REFINING.value,
}
_RESEARCH_RECENT_TERMINAL = {
    WebResearchRunStatus.READY.value,
    WebResearchRunStatus.FAILED.value,
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_title(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _title_from_payload(payload: dict[str, Any] | None) -> str | None:
    if not payload:
        return None
    return _safe_title(payload.get("title"))


def _truncate_input(text: str, *, limit: int = 48) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 1]}…"


def _resolve_idea_title(
    *,
    session: IdeaAiSession,
    idea_titles: dict[UUID, str],
) -> tuple[UUID | None, str | None]:
    """Return (idea_id, title) for display / deep-link."""
    if session.purpose == IdeaAiSessionPurpose.CREATE.value:
        if session.result_idea_id and session.result_idea_id in idea_titles:
            return session.result_idea_id, idea_titles[session.result_idea_id]
        title = _title_from_payload(session.draft_payload) or _truncate_input(session.input_text)
        return session.result_idea_id, title

    idea_id = session.source_idea_id
    if idea_id and idea_id in idea_titles:
        return idea_id, idea_titles[idea_id]
    title = (
        _title_from_payload(session.source_idea_snapshot)
        or _title_from_payload(session.draft_payload)
        or _truncate_input(session.input_text)
    )
    return idea_id, title


def _session_task(session: IdeaAiSession, *, idea_titles: dict[UUID, str]) -> AiTaskPublic:
    idea_id, idea_title = _resolve_idea_title(session=session, idea_titles=idea_titles)
    is_active = session.status in _SESSION_ACTIVE
    completed_at = None
    if not is_active:
        completed_at = session.ready_at or session.updated_at
    failure_message = None
    if session.status == IdeaAiSessionStatus.FAILED.value:
        failure_message = session.failure_message
    return AiTaskPublic(
        id=f"session:{session.id}",
        type=session.purpose,  # CREATE | REFINE
        status=session.status,
        is_active=is_active,
        session_id=session.id,
        idea_id=idea_id,
        idea_title=idea_title,
        failure_message=failure_message,
        started_at=session.created_at,
        completed_at=completed_at,
        updated_at=session.updated_at,
    )


def _research_task(
    run: WebResearchRun,
    session: IdeaAiSession,
    *,
    idea_titles: dict[UUID, str],
) -> AiTaskPublic:
    idea_id, idea_title = _resolve_idea_title(session=session, idea_titles=idea_titles)
    is_active = run.status in _RESEARCH_ACTIVE
    failure_message = None
    if run.status == WebResearchRunStatus.FAILED.value:
        failure_message = run.failure_message
    return AiTaskPublic(
        id=f"research:{run.id}",
        type="RESEARCH",
        status=run.status,
        is_active=is_active,
        session_id=session.id,
        idea_id=idea_id,
        idea_title=idea_title,
        failure_message=failure_message,
        started_at=run.approved_at or run.started_at or run.created_at,
        completed_at=run.completed_at if not is_active else None,
        updated_at=run.updated_at,
    )


def list_ai_tasks(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    recent_window: timedelta = RECENT_TERMINAL_WINDOW,
) -> AiTaskListResponse:
    """Return active + recently terminal AI tasks for the requester."""
    cutoff = _utc_now() - recent_window

    session_rows = list(
        db.scalars(
            select(IdeaAiSession).where(
                IdeaAiSession.workspace_id == workspace_id,
                IdeaAiSession.requester_id == user_id,
                IdeaAiSession.purpose.in_(
                    (
                        IdeaAiSessionPurpose.CREATE.value,
                        IdeaAiSessionPurpose.REFINE.value,
                    )
                ),
                or_(
                    IdeaAiSession.status.in_(tuple(_SESSION_ACTIVE)),
                    and_(
                        IdeaAiSession.status.in_(tuple(_SESSION_RECENT_TERMINAL)),
                        IdeaAiSession.updated_at >= cutoff,
                    ),
                ),
            )
        ).all()
    )

    research_pairs = list(
        db.execute(
            select(WebResearchRun, IdeaAiSession)
            .join(IdeaAiSession, IdeaAiSession.id == WebResearchRun.session_id)
            .where(
                IdeaAiSession.workspace_id == workspace_id,
                WebResearchRun.requester_id == user_id,
                or_(
                    WebResearchRun.status.in_(tuple(_RESEARCH_ACTIVE)),
                    and_(
                        WebResearchRun.status.in_(tuple(_RESEARCH_RECENT_TERMINAL)),
                        or_(
                            and_(
                                WebResearchRun.completed_at.is_not(None),
                                WebResearchRun.completed_at >= cutoff,
                            ),
                            and_(
                                WebResearchRun.completed_at.is_(None),
                                WebResearchRun.updated_at >= cutoff,
                            ),
                        ),
                    ),
                ),
            )
        ).all()
    )

    idea_ids: set[UUID] = set()
    for session in session_rows:
        if session.result_idea_id:
            idea_ids.add(session.result_idea_id)
        if session.source_idea_id:
            idea_ids.add(session.source_idea_id)
    for _run, session in research_pairs:
        if session.result_idea_id:
            idea_ids.add(session.result_idea_id)
        if session.source_idea_id:
            idea_ids.add(session.source_idea_id)

    idea_titles: dict[UUID, str] = {}
    if idea_ids:
        for idea in db.scalars(select(Idea).where(Idea.id.in_(tuple(idea_ids)))).all():
            idea_titles[idea.id] = idea.title

    items: list[AiTaskPublic] = [
        _session_task(session, idea_titles=idea_titles) for session in session_rows
    ]
    items.extend(
        _research_task(run, session, idea_titles=idea_titles) for run, session in research_pairs
    )

    # Active first, then most recently updated.
    items.sort(key=lambda t: (not t.is_active, -(t.updated_at.timestamp())))

    active_count = sum(1 for item in items if item.is_active)
    return AiTaskListResponse(items=items, active_count=active_count)
