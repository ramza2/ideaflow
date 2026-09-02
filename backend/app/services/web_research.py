"""Web research domain service (Step 9)."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.llm.research_prompts import IDEA_RESEARCH_REFINE_PROMPT_VERSION
from app.llm.research_schemas import (
    EvidenceInput,
    RESEARCH_REFINABLE_FIELDS,
    merge_refinement_provenance,
    validate_refinement_result,
)
from app.models.ai import AiJob, IdeaAiSession
from app.models.enums import (
    AiJobStatus,
    AiJobType,
    IdeaAiSessionStatus,
    WebResearchRunStatus,
)
from app.models.idea import Idea
from app.models.research import WebEvidence, WebResearchRun
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.research import (
    IdeaEvidenceItem,
    IdeaEvidenceResponse,
    SanitizationNotePublic,
    WebEvidencePublic,
    WebResearchFailurePublic,
    WebResearchLatestResponse,
    WebResearchPreviewRequest,
    WebResearchRunPublic,
)
from app.services import ai_session as ai_session_service
from app.services import system_setting as system_setting_service
from app.web_search.sanitize import validate_and_sanitize_queries

logger = logging.getLogger(__name__)

_PREVIEW_DRAFT_FIELDS = frozenset(
    {
        "title",
        "one_line_definition",
        "background",
        "problem",
        "core_concept",
        "major_features",
        "expected_effect",
        "target_users",
        "scenarios",
        "challenges",
        "minimum_validation",
        "related_project",
        "category_slug",
        "priority",
        "feasibility",
        "tags",
    }
)

_USER_EDITABLE_FIELDS = frozenset(RESEARCH_REFINABLE_FIELDS)


def sanitize_preview_draft(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return {key: raw[key] for key in _PREVIEW_DRAFT_FIELDS if key in raw}


def sanitize_user_edited_fields(raw: list[str] | None) -> list[str]:
    if not raw:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        field = item.strip()
        if not field or field not in _USER_EDITABLE_FIELDS or field in seen:
            continue
        seen.add(field)
        out.append(field)
    return out

_ACTIVE_RUN_STATUSES = {
    WebResearchRunStatus.AWAITING_APPROVAL.value,
    WebResearchRunStatus.QUEUED.value,
    WebResearchRunStatus.SEARCHING.value,
    WebResearchRunStatus.REFINING.value,
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _require_web_search_enabled(db: Session, workspace: Workspace) -> None:
    system_setting_service.require_global_llm_enabled(db)
    system_setting_service.require_global_web_search_enabled(db)
    if not workspace.allow_llm:
        raise AppError(
            "LLM is disabled for this workspace.",
            code="WORKSPACE_LLM_DISABLED",
            status_code=403,
        )
    if not workspace.allow_web_search:
        raise AppError(
            "Web search is disabled for this workspace.",
            code="WORKSPACE_WEB_SEARCH_DISABLED",
            status_code=403,
        )


def _require_llm_enabled(db: Session, workspace: Workspace) -> None:
    system_setting_service.require_global_llm_enabled(db)
    if not workspace.allow_llm:
        raise AppError(
            "LLM is disabled for this workspace.",
            code="WORKSPACE_LLM_DISABLED",
            status_code=403,
        )


def _get_run_for_requester(
    db: Session,
    *,
    workspace_id: UUID,
    session_id: UUID,
    run_id: UUID,
    user_id: UUID,
    for_update: bool = False,
) -> WebResearchRun:
    session = ai_session_service.get_session_for_requester(
        db,
        workspace_id=workspace_id,
        session_id=session_id,
        user_id=user_id,
    )
    stmt = select(WebResearchRun).where(
        WebResearchRun.id == run_id,
        WebResearchRun.session_id == session.id,
        WebResearchRun.requester_id == user_id,
    )
    if for_update:
        stmt = stmt.with_for_update()
    run = db.execute(stmt).scalar_one_or_none()
    if run is None:
        raise AppError(
            "Research run not found.",
            code="AI_RESEARCH_NOT_FOUND",
            status_code=404,
        )
    return run


def _assert_session_ready(session: IdeaAiSession) -> None:
    if session.status != IdeaAiSessionStatus.READY_FOR_REVIEW.value:
        raise AppError(
            "AI session is not ready for research.",
            code="AI_SESSION_INVALID_STATE",
            status_code=409,
        )


def _active_run_exists(db: Session, session_id: UUID) -> bool:
    existing = db.execute(
        select(WebResearchRun.id).where(
            WebResearchRun.session_id == session_id,
            WebResearchRun.status.in_(_ACTIVE_RUN_STATUSES),
        )
    ).scalar_one_or_none()
    return existing is not None


def has_active_research(db: Session, session_id: UUID) -> bool:
    return db.execute(
        select(WebResearchRun.id).where(
            WebResearchRun.session_id == session_id,
            WebResearchRun.status.in_(
                {
                    WebResearchRunStatus.QUEUED.value,
                    WebResearchRunStatus.SEARCHING.value,
                    WebResearchRunStatus.REFINING.value,
                }
            ),
        )
    ).scalar_one_or_none() is not None


def preview_research_run(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    session_id: UUID,
    payload: WebResearchPreviewRequest,
    settings: Settings | None = None,
) -> WebResearchRun:
    _require_web_search_enabled(db, workspace)
    _require_llm_enabled(db, workspace)
    cfg = settings or get_settings()

    session = ai_session_service.get_session_for_requester(
        db,
        workspace_id=workspace.id,
        session_id=session_id,
        user_id=user.id,
        for_update=True,
    )
    _assert_session_ready(session)

    if _active_run_exists(db, session.id):
        raise AppError(
            "An active research run already exists for this session.",
            code="AI_RESEARCH_ALREADY_ACTIVE",
            status_code=409,
        )

    sanitized = validate_and_sanitize_queries(payload.queries, settings=cfg)
    provider = cfg.web_search_provider.strip() or "http_json"

    run = WebResearchRun(
        session_id=session.id,
        requester_id=user.id,
        status=WebResearchRunStatus.AWAITING_APPROVAL.value,
        queries_to_send=sanitized.queries,
        sanitization_notes=[
            {"query_index": n.query_index, "changed": n.changed} for n in sanitized.notes
        ],
        base_draft_payload=sanitize_preview_draft(payload.current_draft),
        base_field_provenance=dict(session.field_provenance or {}),
        user_edited_fields=sanitize_user_edited_fields(payload.user_edited_fields),
        provider=provider,
    )
    db.add(run)
    db.flush()
    return run


def approve_research_run(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    session_id: UUID,
    run_id: UUID,
    settings: Settings | None = None,
) -> WebResearchRun:
    _require_web_search_enabled(db, workspace)
    _require_llm_enabled(db, workspace)
    cfg = settings or get_settings()

    session = ai_session_service.get_session_for_requester(
        db,
        workspace_id=workspace.id,
        session_id=session_id,
        user_id=user.id,
        for_update=True,
    )
    _assert_session_ready(session)

    run = _get_run_for_requester(
        db,
        workspace_id=workspace.id,
        session_id=session_id,
        run_id=run_id,
        user_id=user.id,
        for_update=True,
    )
    if run.status != WebResearchRunStatus.AWAITING_APPROVAL.value:
        raise AppError(
            "Research run is not awaiting approval.",
            code="AI_RESEARCH_INVALID_STATE",
            status_code=409,
        )

    now = utcnow()
    run.status = WebResearchRunStatus.QUEUED.value
    run.approved_at = now

    job = AiJob(
        session_id=session.id,
        research_run_id=run.id,
        job_type=AiJobType.WEB_RESEARCH.value,
        status=AiJobStatus.QUEUED.value,
        attempts=0,
        max_attempts=cfg.ai_job_max_attempts,
        available_at=now,
    )
    db.add(job)
    db.flush()
    return run


def cancel_research_run(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    session_id: UUID,
    run_id: UUID,
) -> WebResearchRun:
    run = _get_run_for_requester(
        db,
        workspace_id=workspace.id,
        session_id=session_id,
        run_id=run_id,
        user_id=user.id,
        for_update=True,
    )
    if run.status != WebResearchRunStatus.AWAITING_APPROVAL.value:
        raise AppError(
            "Only preview research runs can be cancelled.",
            code="AI_RESEARCH_INVALID_STATE",
            status_code=409,
        )
    run.status = WebResearchRunStatus.CANCELLED.value
    run.completed_at = utcnow()
    db.flush()
    return run


def retry_research_run(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    session_id: UUID,
    run_id: UUID,
    settings: Settings | None = None,
) -> WebResearchRun:
    _require_web_search_enabled(db, workspace)
    _require_llm_enabled(db, workspace)
    cfg = settings or get_settings()

    session = ai_session_service.get_session_for_requester(
        db,
        workspace_id=workspace.id,
        session_id=session_id,
        user_id=user.id,
        for_update=True,
    )
    _assert_session_ready(session)

    run = _get_run_for_requester(
        db,
        workspace_id=workspace.id,
        session_id=session_id,
        run_id=run_id,
        user_id=user.id,
        for_update=True,
    )
    if run.status != WebResearchRunStatus.FAILED.value:
        raise AppError(
            "Only failed research runs can be retried.",
            code="AI_RESEARCH_INVALID_STATE",
            status_code=409,
        )

    if _active_run_exists(db, session.id):
        raise AppError(
            "An active research run already exists for this session.",
            code="AI_RESEARCH_ALREADY_ACTIVE",
            status_code=409,
        )

    run.status = WebResearchRunStatus.QUEUED.value
    failed_phase = run.failure_phase
    run.failure_phase = failed_phase
    run.failure_code = None
    run.failure_message = None
    run.completed_at = None

    db.add(
        AiJob(
            session_id=session.id,
            research_run_id=run.id,
            job_type=AiJobType.WEB_RESEARCH.value,
            status=AiJobStatus.QUEUED.value,
            attempts=0,
            max_attempts=cfg.ai_job_max_attempts,
            available_at=utcnow(),
        )
    )
    db.flush()
    return run


def _evidence_to_public(ev: WebEvidence) -> WebEvidencePublic:
    related = ev.related_fields if isinstance(ev.related_fields, list) else []
    return WebEvidencePublic(
        id=ev.id,
        query=ev.query,
        title=ev.title,
        url=ev.url,
        domain=ev.domain,
        source_name=ev.source_name,
        snippet=ev.snippet,
        published_at=ev.published_at,
        fetched_at=ev.fetched_at,
        rank=ev.rank,
        related_fields=[str(f) for f in related],
    )


def to_public(db: Session, run: WebResearchRun, *, include_evidence: bool = True) -> WebResearchRunPublic:
    failure = None
    if run.status == WebResearchRunStatus.FAILED.value:
        failure = WebResearchFailurePublic(
            phase=run.failure_phase,
            code=run.failure_code,
            message=run.failure_message,
        )

    notes_raw = run.sanitization_notes or []
    notes = [
        SanitizationNotePublic(query_index=int(n.get("query_index", 0)), changed=bool(n.get("changed")))
        for n in notes_raw
        if isinstance(n, dict)
    ]

    evidence: list[WebEvidencePublic] = []
    if include_evidence:
        rows = list(
            db.scalars(
                select(WebEvidence)
                .where(WebEvidence.research_run_id == run.id)
                .order_by(WebEvidence.rank.asc(), WebEvidence.created_at.asc())
            )
        )
        evidence = [_evidence_to_public(ev) for ev in rows]

    queries = run.queries_to_send if isinstance(run.queries_to_send, list) else []

    return WebResearchRunPublic(
        id=run.id,
        session_id=run.session_id,
        status=WebResearchRunStatus(run.status),
        queries_to_send=[str(q) for q in queries],
        sanitization_notes=notes,
        provider=run.provider,
        result_count=run.result_count,
        research_summary=run.research_summary,
        failure=failure,
        evidence=evidence,
        approved_at=run.approved_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


def get_research_run(
    db: Session,
    *,
    workspace_id: UUID,
    session_id: UUID,
    run_id: UUID,
    user_id: UUID,
) -> WebResearchRunPublic:
    run = _get_run_for_requester(
        db,
        workspace_id=workspace_id,
        session_id=session_id,
        run_id=run_id,
        user_id=user_id,
    )
    return to_public(db, run)


def get_latest_research_run(
    db: Session,
    *,
    workspace_id: UUID,
    session_id: UUID,
    user_id: UUID,
) -> WebResearchLatestResponse:
    session = ai_session_service.get_session_for_requester(
        db,
        workspace_id=workspace_id,
        session_id=session_id,
        user_id=user_id,
    )
    run = db.execute(
        select(WebResearchRun)
        .where(WebResearchRun.session_id == session.id)
        .order_by(WebResearchRun.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if run is None:
        return WebResearchLatestResponse(run=None)
    return WebResearchLatestResponse(run=to_public(db, run))


def get_idea_evidence(
    db: Session,
    *,
    workspace_id: UUID,
    idea_id: UUID,
    user_id: UUID,
) -> IdeaEvidenceResponse:
    from app.services import idea as idea_service

    idea, _share = idea_service.get_readable_idea(
        db,
        workspace_id=workspace_id,
        idea_id=idea_id,
        user_id=user_id,
    )

    session = db.execute(
        select(IdeaAiSession).where(
            IdeaAiSession.result_idea_id == idea.id,
            IdeaAiSession.status == IdeaAiSessionStatus.CONFIRMED.value,
        )
    ).scalar_one_or_none()
    if session is None:
        return IdeaEvidenceResponse(items=[])

    runs = list(
        db.scalars(
            select(WebResearchRun).where(
                WebResearchRun.session_id == session.id,
                WebResearchRun.status == WebResearchRunStatus.READY.value,
            )
        )
    )
    if not runs:
        return IdeaEvidenceResponse(items=[])

    run_ids = [r.id for r in runs]
    evidence_rows = list(
        db.scalars(
            select(WebEvidence)
            .where(WebEvidence.research_run_id.in_(run_ids))
            .order_by(WebEvidence.fetched_at.asc(), WebEvidence.rank.asc())
        )
    )

    items = [
        IdeaEvidenceItem(
            id=ev.id,
            title=ev.title,
            url=ev.url,
            domain=ev.domain,
            source_name=ev.source_name,
            snippet=ev.snippet,
            published_at=ev.published_at,
            fetched_at=ev.fetched_at,
            related_fields=[
                str(f) for f in (ev.related_fields or []) if isinstance(ev.related_fields, list)
            ]
            if isinstance(ev.related_fields, list)
            else [],
        )
        for ev in evidence_rows
    ]
    return IdeaEvidenceResponse(items=items)


def url_hash(url: str) -> str:
    normalized = url.strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def domain_from_url(url: str) -> str | None:
    try:
        host = urlparse(url).netloc
        return host[:255] if host else None
    except Exception:  # noqa: BLE001
        return None


def update_evidence_related_fields(
    db: Session,
    *,
    run_id: UUID,
    evidence_links: dict[str, list[str]],
) -> None:
    field_to_ids: dict[str, list[str]] = {}
    for field, ids in evidence_links.items():
        for eid in ids:
            field_to_ids.setdefault(eid, []).append(field)

    rows = list(db.scalars(select(WebEvidence).where(WebEvidence.research_run_id == run_id)))
    for ev in rows:
        ev.related_fields = field_to_ids.get(str(ev.id), [])
    db.flush()


def _clean_refinement_text(text: str | None, *, max_len: int) -> str | None:
    if text is None:
        return None
    cleaned = "".join(ch for ch in text if ord(ch) >= 32 or ch in "\n\t").strip()
    if not cleaned:
        return None
    return cleaned[:max_len]


def refinement_evidence_serialized_chars(evidence: list[EvidenceInput]) -> int:
    import json

    total = 0
    for ev in evidence:
        total += len(
            json.dumps(
                {
                    "evidence_id": str(ev.evidence_id),
                    "title": ev.title,
                    "source": ev.source,
                    "published_at": ev.published_at,
                    "snippet": ev.snippet,
                },
                ensure_ascii=False,
            )
        )
    return total


def _apply_refinement_evidence_char_budget(
    inputs: list[EvidenceInput],
    *,
    max_total_chars: int,
) -> list[EvidenceInput]:
    if not inputs:
        return inputs

    result = list(inputs)
    while result:
        if refinement_evidence_serialized_chars(result) <= max_total_chars:
            return result

        last = result[-1]
        if last.snippet:
            snippet = last.snippet
            while snippet:
                snippet = snippet[: max(0, len(snippet) - max(1, len(snippet) // 10 or 1))]
                trimmed = EvidenceInput(
                    evidence_id=last.evidence_id,
                    title=last.title,
                    source=last.source,
                    published_at=last.published_at,
                    snippet=snippet or None,
                )
                trial = result[:-1] + [trimmed]
                if refinement_evidence_serialized_chars(trial) <= max_total_chars:
                    return trial
            trimmed = EvidenceInput(
                evidence_id=last.evidence_id,
                title=last.title,
                source=last.source,
                published_at=last.published_at,
                snippet=None,
            )
            trial = result[:-1] + [trimmed]
            if refinement_evidence_serialized_chars(trial) <= max_total_chars:
                return trial
        result.pop()

    return []


def build_refinement_evidence_inputs(
    evidence_rows: list[WebEvidence],
    settings: Settings | None = None,
) -> list[EvidenceInput]:
    """Select and trim WebEvidence for LLM refinement only (DB rows unchanged)."""
    cfg = settings or get_settings()
    max_items = cfg.web_research_refine_max_evidence_items
    max_snippet = cfg.web_research_refine_max_snippet_chars
    max_total_chars = cfg.web_research_refine_max_evidence_chars

    ordered = sorted(evidence_rows, key=lambda row: row.rank)
    inputs: list[EvidenceInput] = []
    for row in ordered[:max_items]:
        title = _clean_refinement_text(row.title, max_len=200) or ""
        if not title:
            fallback = row.domain or domain_from_url(row.url) or row.url
            title = _clean_refinement_text(fallback, max_len=200) or "Untitled"
        snippet = _clean_refinement_text(row.snippet, max_len=max_snippet)
        published = row.published_at.isoformat() if row.published_at else None
        inputs.append(
            EvidenceInput(
                evidence_id=row.id,
                title=title,
                source=row.source_name,
                published_at=published,
                snippet=snippet,
            )
        )

    return _apply_refinement_evidence_char_budget(
        inputs,
        max_total_chars=max_total_chars,
    )
