"""DB-backed in-process AI job worker (Step 7)."""

from __future__ import annotations

import logging
import os
import socket
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.db.session import get_session_factory
from app.llm.base import LlmProvider
from app.llm.exceptions import LlmError, LlmResearchRefineInputTooLargeError, LlmResponseValidationError, LlmUnavailableError
from app.llm.factory import get_llm_provider
from app.llm.prompts import IDEA_STRUCTURE_PROMPT_VERSION, categories_from_rows
from app.llm.refine_prompts import IDEA_REFINE_PROMPT_VERSION
from app.llm.refine_schemas import (
    IdeaRefinementRequest,
    IdeaRefinementResult,
    LlmRefineInputTooLargeError,
    merge_refinement_patch,
    merged_draft_differs_from_source,
    prepare_refine_prompt_request,
    validate_refinement_against_source,
)
from app.llm.research_prompts import IDEA_RESEARCH_REFINE_PROMPT_VERSION
from app.llm.research_schemas import (
    RESEARCH_REFINABLE_FIELDS,
    filter_user_edited_refinement_fields,
    merge_refinement_provenance,
    validate_refinement_result,
)
from app.llm.schemas import IdeaStructuringRequest
from app.models.ai import AiJob, IdeaAiSession
from app.models.enums import (
    AiJobStatus,
    AiJobType,
    AiLlmDecision,
    FieldProvenanceSource,
    IdeaAiSessionPurpose,
    IdeaAiSessionStatus,
    WebResearchRunStatus,
)
from app.models.research import WebEvidence, WebResearchRun
from app.models.workspace import Workspace, WorkspaceCategory
from app.services import ai_session as ai_session_service
from app.services import web_research as web_research_service
from app.web_search.base import WebSearchProvider
from app.web_search.exceptions import WebSearchError
from app.web_search.factory import get_web_search_provider

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def make_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def backoff_seconds(base: float, attempt: int) -> float:
    """Exponential backoff: base * 2^(attempt-1). attempt is 1-based after claim."""
    exp = max(attempt - 1, 0)
    return base * (2**exp)


_ACTIVE_WEB_RESEARCH_RUN_STATUSES = {
    WebResearchRunStatus.QUEUED.value,
    WebResearchRunStatus.SEARCHING.value,
    WebResearchRunStatus.REFINING.value,
}


def _web_research_retry_phase(run_status: str) -> str:
    return (
        "REFINE"
        if run_status == WebResearchRunStatus.REFINING.value
        else "SEARCH"
    )


def _apply_stale_web_research_run(
    run: WebResearchRun,
    *,
    requeue: bool,
    retry_phase: str,
    now: datetime,
) -> None:
    if requeue:
        run.status = WebResearchRunStatus.QUEUED.value
        run.failure_phase = retry_phase
        return

    run.status = WebResearchRunStatus.FAILED.value
    run.failure_phase = retry_phase
    run.failure_code = "LLM_LEASE_EXPIRED"
    run.failure_message = "Worker lease expired."
    run.completed_at = now


def recover_stale_jobs(db: Session, *, settings: Settings | None = None) -> int:
    """Requeue or fail RUNNING jobs whose lease expired (lock-safe)."""
    cfg = settings or get_settings()
    now = utcnow()
    recovered = 0

    # Claim stale rows one-by-one with SKIP LOCKED so concurrent recoveries
    # cannot both rewrite the same RUNNING job.
    while True:
        job = db.execute(
            select(AiJob)
            .where(
                AiJob.status == AiJobStatus.RUNNING.value,
                AiJob.lease_until.is_not(None),
                AiJob.lease_until < now,
            )
            .order_by(AiJob.lease_until.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        ).scalar_one_or_none()
        if job is None:
            break

        session = db.get(IdeaAiSession, job.session_id)

        run: WebResearchRun | None = None
        retry_phase: str | None = None
        if job.job_type == AiJobType.WEB_RESEARCH.value and job.research_run_id is not None:
            run = db.get(WebResearchRun, job.research_run_id)
            if run is not None and run.status in _ACTIVE_WEB_RESEARCH_RUN_STATUSES:
                retry_phase = _web_research_retry_phase(run.status)

        if job.attempts < job.max_attempts:
            job.status = AiJobStatus.QUEUED.value
            job.available_at = now
            job.locked_at = None
            job.lease_until = None
            job.worker_id = None
            job.started_at = None
            job.last_error_code = "LLM_LEASE_EXPIRED"
            job.last_error_message = "Worker lease expired; job requeued."
            if run is not None and retry_phase is not None:
                _apply_stale_web_research_run(
                    run,
                    requeue=True,
                    retry_phase=retry_phase,
                    now=now,
                )
            recovered += 1
        else:
            job.status = AiJobStatus.FAILED.value
            job.finished_at = now
            job.locked_at = None
            job.lease_until = None
            job.worker_id = None
            job.last_error_code = "LLM_LEASE_EXPIRED"
            job.last_error_message = "Worker lease expired; max attempts reached."
            if session is not None and session.status == IdeaAiSessionStatus.PROCESSING.value:
                session.status = IdeaAiSessionStatus.FAILED.value
                session.failure_code = "LLM_UNAVAILABLE"
                session.failure_message = "AI 처리 중 일시적인 오류가 발생했습니다."
            if run is not None and retry_phase is not None:
                _apply_stale_web_research_run(
                    run,
                    requeue=False,
                    retry_phase=retry_phase,
                    now=now,
                )
            recovered += 1

    if recovered:
        db.commit()
    else:
        db.rollback()
    return recovered


def claim_next_job(
    db: Session,
    *,
    worker_id: str,
    settings: Settings | None = None,
) -> AiJob | None:
    """Claim one QUEUED job with FOR UPDATE SKIP LOCKED. Short transaction."""
    cfg = settings or get_settings()
    now = utcnow()
    job = db.execute(
        select(AiJob)
        .where(
            AiJob.status == AiJobStatus.QUEUED.value,
            AiJob.available_at <= now,
        )
        .order_by(AiJob.created_at.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    ).scalar_one_or_none()
    if job is None:
        return None

    job.status = AiJobStatus.RUNNING.value
    job.attempts = int(job.attempts) + 1
    job.locked_at = now
    job.lease_until = now + timedelta(seconds=cfg.ai_job_lease_seconds)
    job.worker_id = worker_id
    job.started_at = now
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _load_categories(db: Session, workspace_id: UUID) -> list[WorkspaceCategory]:
    return list(
        db.scalars(
            select(WorkspaceCategory).where(
                WorkspaceCategory.workspace_id == workspace_id,
                WorkspaceCategory.deleted_at.is_(None),
            )
        )
    )


def _job_owned_by_worker(job: AiJob, *, worker_id: str, now: datetime) -> bool:
    if job.status != AiJobStatus.RUNNING.value:
        return False
    if job.worker_id != worker_id:
        return False
    if job.lease_until is None:
        return False
    lease = job.lease_until
    if lease.tzinfo is None:
        lease = lease.replace(tzinfo=timezone.utc)
    return lease >= now


def _apply_success(
    db: Session,
    *,
    job: AiJob,
    session: IdeaAiSession,
    result,
    provider: LlmProvider,
) -> None:
    draft = result.draft.model_dump(mode="json")
    draft = ai_session_service.sanitize_draft_category(
        db, workspace_id=session.workspace_id, draft=draft
    )
    provenance = {
        key: entry.model_dump(mode="json") for key, entry in result.field_provenance.items()
    }
    questions_raw = [q.model_dump(mode="json") for q in result.clarifying_questions]

    session.draft_payload = draft
    session.field_provenance = provenance
    session.research_recommended = bool(result.research_recommended)
    session.research_topics = list(result.research_topics)
    session.llm_provider = getattr(provider, "provider_name", "openai_compatible")
    session.llm_model = getattr(provider, "model_name", None)
    session.prompt_version = getattr(provider, "prompt_version", IDEA_STRUCTURE_PROMPT_VERSION)
    session.failure_code = None
    session.failure_message = None

    if result.decision == AiLlmDecision.NEEDS_CLARIFICATION:
        session.status = IdeaAiSessionStatus.NEEDS_CLARIFICATION.value
        session.clarifying_questions = ai_session_service.assign_question_ids(questions_raw)
    else:
        session.status = IdeaAiSessionStatus.READY_FOR_REVIEW.value
        session.clarifying_questions = []
        session.ready_at = utcnow()

    job.status = AiJobStatus.SUCCEEDED.value
    job.finished_at = utcnow()
    job.locked_at = None
    job.lease_until = None
    job.last_error_code = None
    job.last_error_message = None


def _apply_refine_success(
    db: Session,
    *,
    job: AiJob,
    session: IdeaAiSession,
    result: IdeaRefinementResult,
    provider: LlmProvider,
    source_snapshot: dict[str, Any],
) -> None:
    draft = merge_refinement_patch(source_snapshot, result.draft_patch)
    if "category_slug" in result.draft_patch:
        # An unknown slug proposed by the LLM must not clear the source category.
        checked = ai_session_service.sanitize_draft_category(
            db, workspace_id=session.workspace_id, draft=draft
        )
        if checked.get("category_slug") is None:
            checked["category_slug"] = source_snapshot.get("category_slug")
        draft = checked

    if result.decision == AiLlmDecision.READY_FOR_REVIEW and not merged_draft_differs_from_source(
        source_snapshot, draft
    ):
        # e.g. invalid category_slug-only patch that sanitizes back to source.
        raise LlmResponseValidationError("Refinement produced no effective changes vs source")

    provenance = dict(session.field_provenance or {})
    for key in result.draft_patch:
        entry = result.field_provenance.get(key)
        provenance[key] = (
            entry.model_dump(mode="json")
            if entry is not None
            else {"source": FieldProvenanceSource.LLM_INFERENCE.value, "note": None}
        )
    questions_raw = [q.model_dump(mode="json") for q in result.clarifying_questions]

    session.draft_payload = draft
    session.field_provenance = provenance
    session.research_recommended = bool(result.research_recommended)
    session.research_topics = list(result.research_topics)
    session.llm_provider = getattr(provider, "provider_name", "openai_compatible")
    session.llm_model = getattr(provider, "model_name", None)
    session.prompt_version = (
        getattr(provider, "refine_prompt_version", None) or IDEA_REFINE_PROMPT_VERSION
    )
    session.failure_code = None
    session.failure_message = None

    if result.decision == AiLlmDecision.NEEDS_CLARIFICATION:
        session.status = IdeaAiSessionStatus.NEEDS_CLARIFICATION.value
        session.clarifying_questions = ai_session_service.assign_question_ids(questions_raw)
    else:
        session.status = IdeaAiSessionStatus.READY_FOR_REVIEW.value
        session.clarifying_questions = []
        session.ready_at = utcnow()

    job.status = AiJobStatus.SUCCEEDED.value
    job.finished_at = utcnow()
    job.locked_at = None
    job.lease_until = None
    job.last_error_code = None
    job.last_error_message = None


def _apply_failure(
    db: Session,
    *,
    job: AiJob,
    session: IdeaAiSession | None,
    error: LlmError,
    settings: Settings,
) -> None:
    now = utcnow()
    if isinstance(error, LlmResponseValidationError):
        safe_msg = LlmResponseValidationError.safe_message
    else:
        safe_msg = (error.safe_message or "AI 처리 중 오류가 발생했습니다.")[:512]
    code = error.code

    if error.retryable and job.attempts < job.max_attempts:
        delay = backoff_seconds(settings.ai_job_retry_base_seconds, job.attempts)
        job.status = AiJobStatus.QUEUED.value
        job.available_at = now + timedelta(seconds=delay)
        job.locked_at = None
        job.lease_until = None
        job.worker_id = None
        job.started_at = None
        job.last_error_code = code
        job.last_error_message = safe_msg
        # Session stays PROCESSING
        return

    job.status = AiJobStatus.FAILED.value
    job.finished_at = now
    job.locked_at = None
    job.lease_until = None
    job.last_error_code = code
    job.last_error_message = safe_msg
    if session is not None and session.status == IdeaAiSessionStatus.PROCESSING.value:
        session.status = IdeaAiSessionStatus.FAILED.value
        session.failure_code = code
        session.failure_message = safe_msg


def _apply_web_research_failure(
    db: Session,
    *,
    job: AiJob,
    run: WebResearchRun,
    error: WebSearchError | LlmError,
    settings: Settings,
    failure_phase: str,
) -> None:
    now = utcnow()
    if isinstance(error, LlmResponseValidationError):
        safe_msg = LlmResponseValidationError.safe_message
    else:
        safe_msg = (error.safe_message or "웹 조사 중 오류가 발생했습니다.")[:512]
    code = error.code
    retryable = getattr(error, "retryable", False)

    if retryable and job.attempts < job.max_attempts:
        delay = backoff_seconds(settings.ai_job_retry_base_seconds, job.attempts)
        job.status = AiJobStatus.QUEUED.value
        job.available_at = now + timedelta(seconds=delay)
        job.locked_at = None
        job.lease_until = None
        job.worker_id = None
        job.started_at = None
        job.last_error_code = code
        job.last_error_message = safe_msg
        run.status = WebResearchRunStatus.QUEUED.value
        run.failure_phase = failure_phase
        return

    job.status = AiJobStatus.FAILED.value
    job.finished_at = now
    job.locked_at = None
    job.lease_until = None
    job.last_error_code = code
    job.last_error_message = safe_msg

    run.status = WebResearchRunStatus.FAILED.value
    run.failure_phase = failure_phase
    run.failure_code = code
    run.failure_message = safe_msg
    run.completed_at = now


def process_web_research_job(
    db: Session,
    *,
    job_id: UUID,
    worker_id: str,
    provider: LlmProvider,
    search_provider: WebSearchProvider,
    settings: Settings | None = None,
) -> None:
    cfg = settings or get_settings()
    job = db.get(AiJob, job_id)
    if job is None or job.status != AiJobStatus.RUNNING.value or job.worker_id != worker_id:
        return
    if job.research_run_id is None:
        job.status = AiJobStatus.FAILED.value
        job.finished_at = utcnow()
        job.last_error_code = "AI_RESEARCH_NOT_FOUND"
        job.last_error_message = "Missing research_run_id."
        db.commit()
        return

    run = db.get(WebResearchRun, job.research_run_id)
    session = db.get(IdeaAiSession, job.session_id)
    workspace = db.get(Workspace, session.workspace_id) if session else None

    if run is None or session is None or workspace is None:
        job.status = AiJobStatus.FAILED.value
        job.finished_at = utcnow()
        job.last_error_code = "AI_RESEARCH_NOT_FOUND"
        job.last_error_message = "Research run or session missing."
        db.commit()
        return

    if session.status != IdeaAiSessionStatus.READY_FOR_REVIEW.value:
        job.status = AiJobStatus.FAILED.value
        job.finished_at = utcnow()
        job.last_error_code = "AI_SESSION_INVALID_STATE"
        job.last_error_message = "Session not READY_FOR_REVIEW."
        db.commit()
        return

    if not workspace.allow_web_search or not workspace.allow_llm:
        job.status = AiJobStatus.FAILED.value
        job.finished_at = utcnow()
        job.last_error_code = "WORKSPACE_WEB_SEARCH_DISABLED"
        job.last_error_message = "Web search or LLM disabled."
        run.status = WebResearchRunStatus.FAILED.value
        run.failure_phase = "SEARCH"
        run.failure_code = "WORKSPACE_WEB_SEARCH_DISABLED"
        run.failure_message = "Web search or LLM disabled."
        run.completed_at = utcnow()
        db.commit()
        return

    run_id = run.id
    session_id = session.id
    queries = list(run.queries_to_send or [])
    base_draft = dict(run.base_draft_payload or {})
    base_provenance = dict(run.base_field_provenance or {})
    user_edited = list(run.user_edited_fields or [])
    skip_search = (
        run.failure_phase == "REFINE"
        and db.execute(
            select(WebEvidence.id).where(WebEvidence.research_run_id == run.id).limit(1)
        ).scalar_one_or_none()
        is not None
    )

    search_error: WebSearchError | None = None
    collected: list[tuple[str, Any]] = []

    if not skip_search:
        run.status = WebResearchRunStatus.SEARCHING.value
        if run.started_at is None:
            run.started_at = utcnow()
        db.commit()

        max_per_query = cfg.web_search_max_results_per_query
        max_total = cfg.web_search_max_total_results
        total = 0
        rank = 0

        try:
            for query in queries:
                if total >= max_total:
                    break
                remaining = max_total - total
                batch = search_provider.search(
                    query=str(query),
                    max_results=min(max_per_query, remaining),
                )
                for item in batch:
                    if total >= max_total:
                        break
                    collected.append((str(query), item))
                    total += 1
                    rank += 1
        except WebSearchError as exc:
            search_error = exc

        now = utcnow()
        job = db.execute(select(AiJob).where(AiJob.id == job_id).with_for_update()).scalar_one_or_none()
        if job is None or not _job_owned_by_worker(job, worker_id=worker_id, now=now):
            db.rollback()
            return

        run = db.execute(
            select(WebResearchRun).where(WebResearchRun.id == run_id).with_for_update()
        ).scalar_one_or_none()
        if run is None:
            db.rollback()
            return

        if search_error is not None:
            _apply_web_research_failure(
                db,
                job=job,
                run=run,
                error=search_error,
                settings=cfg,
                failure_phase="SEARCH",
            )
            db.commit()
            return

        fetched_at = utcnow()
        seen_hashes: set[str] = set()
        evidence_rows: list[WebEvidence] = []
        for query, item in collected:
            uhash = web_research_service.url_hash(item.url)
            if uhash in seen_hashes:
                continue
            seen_hashes.add(uhash)
            evidence_rows.append(
                WebEvidence(
                    research_run_id=run.id,
                    query=query[:200],
                    title=item.title[:500],
                    url=item.url[:2048],
                    url_hash=uhash,
                    domain=web_research_service.domain_from_url(item.url),
                    source_name=(item.source or "")[:255] or None,
                    snippet=(item.snippet or "")[:2000] or None,
                    published_at=item.published_at,
                    fetched_at=fetched_at,
                    rank=len(evidence_rows),
                    provider=search_provider.provider_name,
                    related_fields=[],
                )
            )

        for row in evidence_rows:
            db.add(row)
        run.result_count = len(evidence_rows)
        db.flush()

        if run.result_count == 0:
            run.status = WebResearchRunStatus.READY.value
            run.research_summary = None
            run.completed_at = utcnow()
            run.failure_phase = None
            run.failure_code = None
            run.failure_message = None
            session = db.execute(
                select(IdeaAiSession).where(IdeaAiSession.id == session_id).with_for_update()
            ).scalar_one_or_none()
            if session is not None and session.status == IdeaAiSessionStatus.READY_FOR_REVIEW.value:
                session.research_recommended = False
            job.status = AiJobStatus.SUCCEEDED.value
            job.finished_at = utcnow()
            job.locked_at = None
            job.lease_until = None
            db.commit()
            return

    # Refinement phase
    run.status = WebResearchRunStatus.REFINING.value
    db.commit()

    evidence_db = list(
        db.scalars(
            select(WebEvidence)
            .where(WebEvidence.research_run_id == run_id)
            .order_by(WebEvidence.rank.asc())
        )
    )

    from app.llm.research_schemas import EvidenceRefinementRequest

    refine_request: EvidenceRefinementRequest | None = None
    refine_error: LlmError | None = None
    refine_result = None
    try:
        refine_request, budget = web_research_service.prepare_refinement_request(
            input_text=session.input_text,
            base_draft=base_draft,
            base_provenance=base_provenance,
            user_edited_fields=user_edited,
            evidence_rows=evidence_db,
            settings=cfg,
        )
        logger.info(
            "research_refine_prompt_budget run_id=%s system_chars=%s user_prompt_chars=%s "
            "total_prompt_chars=%s evidence_total_count=%s evidence_candidate_count=%s "
            "evidence_used_count=%s evidence_used_chars=%s output_max_tokens=%s",
            run_id,
            budget.system_chars,
            budget.user_prompt_chars,
            budget.total_prompt_chars,
            budget.evidence_total_count,
            budget.evidence_candidate_count,
            budget.evidence_used_count,
            budget.evidence_used_chars,
            budget.output_max_tokens,
        )
    except LlmResearchRefineInputTooLargeError as exc:
        refine_error = exc

    if refine_error is None and refine_request is not None:
        try:
            raw_result = provider.refine_idea_with_evidence(refine_request)
            filtered_result, ignored_count = filter_user_edited_refinement_fields(
                raw_result,
                user_edited,
            )
            if ignored_count:
                logger.warning(
                    "research_refine_user_edit_fields_ignored run_id=%s ignored_count=%s",
                    run_id,
                    ignored_count,
                )
            valid_ids = {str(ev.evidence_id) for ev in refine_request.evidence}
            refine_result = validate_refinement_result(
                filtered_result,
                base_draft=base_draft,
                user_edited_fields=user_edited,
                valid_evidence_ids=valid_ids,
            )
        except LlmError as exc:
            refine_error = exc
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "unexpected_research_refine_error job_id=%s run_id=%s category=%s",
                job_id,
                run_id,
                type(exc).__name__,
            )
            refine_error = LlmUnavailableError()

    now = utcnow()
    job = db.execute(select(AiJob).where(AiJob.id == job_id).with_for_update()).scalar_one_or_none()
    if job is None or not _job_owned_by_worker(job, worker_id=worker_id, now=now):
        db.rollback()
        return

    run = db.execute(
        select(WebResearchRun).where(WebResearchRun.id == run_id).with_for_update()
    ).scalar_one_or_none()
    session = db.execute(
        select(IdeaAiSession).where(IdeaAiSession.id == session_id).with_for_update()
    ).scalar_one_or_none()

    if run is None or session is None or session.status != IdeaAiSessionStatus.READY_FOR_REVIEW.value:
        job.status = AiJobStatus.FAILED.value
        job.finished_at = utcnow()
        job.locked_at = None
        job.lease_until = None
        job.last_error_code = "AI_SESSION_INVALID_STATE"
        job.last_error_message = "Session state changed during research."
        db.commit()
        return

    if refine_error is not None:
        _apply_web_research_failure(
            db,
            job=job,
            run=run,
            error=refine_error,
            settings=cfg,
            failure_phase="REFINE",
        )
        db.commit()
        return

    assert refine_result is not None
    merged_draft = dict(base_draft)
    for field in RESEARCH_REFINABLE_FIELDS:
        if field in refine_result.draft:
            merged_draft[field] = refine_result.draft[field]

    merged_provenance = merge_refinement_provenance(
        base_provenance=base_provenance,
        base_draft=base_draft,
        refined_draft=merged_draft,
        evidence_links=refine_result.evidence_links,
        user_edited_fields=user_edited,
    )
    web_research_service.update_evidence_related_fields(
        db, run_id=run.id, evidence_links=refine_result.evidence_links
    )

    session.draft_payload = merged_draft
    session.field_provenance = merged_provenance
    session.research_recommended = False

    run.status = WebResearchRunStatus.READY.value
    run.research_summary = refine_result.research_summary
    run.llm_provider = getattr(provider, "provider_name", "openai_compatible")
    run.llm_model = getattr(provider, "model_name", None)
    run.prompt_version = IDEA_RESEARCH_REFINE_PROMPT_VERSION
    run.completed_at = utcnow()
    run.failure_phase = None
    run.failure_code = None
    run.failure_message = None

    job.status = AiJobStatus.SUCCEEDED.value
    job.finished_at = utcnow()
    job.locked_at = None
    job.lease_until = None
    job.last_error_code = None
    job.last_error_message = None
    db.commit()
    logger.info(
        "web_research_job_succeeded job_id=%s run_id=%s result_count=%s",
        job.id,
        run.id,
        run.result_count,
    )


def process_refine_idea_job(
    db: Session,
    *,
    job_id: UUID,
    worker_id: str,
    provider: LlmProvider,
    settings: Settings | None = None,
) -> None:
    """Refine a registered Idea (Step 17). Source snapshot is the only LLM input."""
    cfg = settings or get_settings()
    job = db.get(AiJob, job_id)
    if job is None or job.status != AiJobStatus.RUNNING.value or job.worker_id != worker_id:
        return

    session = db.get(IdeaAiSession, job.session_id)
    if session is None:
        job.status = AiJobStatus.FAILED.value
        job.finished_at = utcnow()
        job.last_error_code = "AI_SESSION_NOT_FOUND"
        job.last_error_message = "Session missing for job."
        db.commit()
        return

    if (
        session.status != IdeaAiSessionStatus.PROCESSING.value
        or session.purpose != IdeaAiSessionPurpose.REFINE.value
    ):
        job.status = AiJobStatus.FAILED.value
        job.finished_at = utcnow()
        job.last_error_code = "AI_SESSION_INVALID_STATE"
        job.last_error_message = "Session is not a PROCESSING REFINE session."
        db.commit()
        return

    session_id = session.id
    source_snapshot = dict(session.source_idea_snapshot or {})
    direction = session.refine_direction

    if not source_snapshot or not direction or session.source_idea_id is None:
        job.status = AiJobStatus.FAILED.value
        job.finished_at = utcnow()
        job.locked_at = None
        job.lease_until = None
        job.last_error_code = "AI_SESSION_INVALID_STATE"
        job.last_error_message = "REFINE session is missing source idea data."
        session.status = IdeaAiSessionStatus.FAILED.value
        session.failure_code = "AI_SESSION_INVALID_STATE"
        session.failure_message = "AI 처리 중 오류가 발생했습니다."
        db.commit()
        return

    request: IdeaRefinementRequest | None = None
    llm_error: LlmError | None = None
    try:
        request, budget = prepare_refine_prompt_request(
            direction=direction,
            source_snapshot=source_snapshot,
            clarifying_questions=session.clarifying_questions,
            clarification_answers=session.clarification_answers,
            max_prompt_chars=cfg.ai_refine_max_prompt_chars,
        )
        # Metadata only — never log source / answers / prompt body.
        logger.info(
            "ai_refine_prompt_budget session_id=%s direction=%s system_chars=%s "
            "user_prompt_chars=%s total_prompt_chars=%s context_fields=%s "
            "truncated_field_count=%s output_max_tokens=%s",
            session_id,
            direction,
            budget["system_chars"],
            budget["user_prompt_chars"],
            budget["total_prompt_chars"],
            budget["context_fields"],
            len(budget["truncated_fields"]),
            cfg.ai_refine_max_tokens,
        )
    except LlmRefineInputTooLargeError as exc:
        llm_error = exc

    # Detach before LLM call — do not hold DB transaction open.
    db.commit()

    result: IdeaRefinementResult | None = None
    if llm_error is None and request is not None:
        try:
            candidate = provider.refine_idea(request)
            validate_refinement_against_source(candidate, source_snapshot=source_snapshot)
            result = candidate
        except LlmError as exc:
            llm_error = exc
        except ValueError:
            llm_error = LlmResponseValidationError("Refinement patch failed source validation")
        except Exception as exc:  # noqa: BLE001
            # Do not log exception message / traceback locals (may contain prompts).
            logger.error(
                "unexpected_llm_error job_id=%s session_id=%s category=%s",
                job_id,
                session_id,
                type(exc).__name__,
            )
            llm_error = LlmUnavailableError()

    now = utcnow()
    job = db.execute(
        select(AiJob).where(AiJob.id == job_id).with_for_update()
    ).scalar_one_or_none()
    if job is None:
        return
    if not _job_owned_by_worker(job, worker_id=worker_id, now=now):
        logger.info("ai_job_lease_lost job_id=%s", job_id)
        db.rollback()
        return

    session = db.execute(
        select(IdeaAiSession).where(IdeaAiSession.id == session_id).with_for_update()
    ).scalar_one_or_none()
    if session is None or session.status != IdeaAiSessionStatus.PROCESSING.value:
        job.status = AiJobStatus.FAILED.value
        job.finished_at = utcnow()
        job.locked_at = None
        job.lease_until = None
        job.last_error_code = "AI_SESSION_INVALID_STATE"
        job.last_error_message = "Session state changed during LLM call."
        db.commit()
        return

    if llm_error is not None:
        _apply_failure(db, job=job, session=session, error=llm_error, settings=cfg)
        db.commit()
        logger.info(
            "ai_refine_job_failed job_id=%s session_id=%s code=%s attempts=%s",
            job.id,
            session.id,
            llm_error.code,
            job.attempts,
        )
        return

    assert result is not None
    try:
        _apply_refine_success(
            db,
            job=job,
            session=session,
            result=result,
            provider=provider,
            source_snapshot=source_snapshot,
        )
    except LlmResponseValidationError as exc:
        _apply_failure(db, job=job, session=session, error=exc, settings=cfg)
        db.commit()
        logger.info(
            "ai_refine_job_failed job_id=%s session_id=%s code=%s attempts=%s",
            job.id,
            session.id,
            exc.code,
            job.attempts,
        )
        return
    db.commit()
    logger.info(
        "ai_refine_job_succeeded job_id=%s session_id=%s decision=%s",
        job.id,
        session.id,
        result.decision.value,
    )


def process_claimed_job(
    db: Session,
    *,
    job_id: UUID,
    worker_id: str,
    provider: LlmProvider,
    search_provider: WebSearchProvider | None = None,
    settings: Settings | None = None,
) -> None:
    """Run LLM / Web Search outside prior claim txn; persist only if lease holds."""
    cfg = settings or get_settings()
    job = db.get(AiJob, job_id)
    if job is None or job.status != AiJobStatus.RUNNING.value:
        return
    if job.worker_id != worker_id:
        return

    if job.job_type == AiJobType.WEB_RESEARCH.value:
        search = search_provider or get_web_search_provider(cfg)
        process_web_research_job(
            db,
            job_id=job_id,
            worker_id=worker_id,
            provider=provider,
            search_provider=search,
            settings=cfg,
        )
        return

    if job.job_type == AiJobType.REFINE_IDEA.value:
        process_refine_idea_job(
            db,
            job_id=job_id,
            worker_id=worker_id,
            provider=provider,
            settings=cfg,
        )
        return

    session = db.get(IdeaAiSession, job.session_id)
    if session is None:
        job.status = AiJobStatus.FAILED.value
        job.finished_at = utcnow()
        job.last_error_code = "AI_SESSION_NOT_FOUND"
        job.last_error_message = "Session missing for job."
        db.commit()
        return

    if session.status != IdeaAiSessionStatus.PROCESSING.value:
        job.status = AiJobStatus.FAILED.value
        job.finished_at = utcnow()
        job.last_error_code = "AI_SESSION_INVALID_STATE"
        job.last_error_message = "Session not PROCESSING; abandoning job."
        db.commit()
        return

    categories = _load_categories(db, session.workspace_id)
    request = IdeaStructuringRequest(
        input_text=session.input_text,
        categories=categories_from_rows(categories),
        prior_draft=session.draft_payload,
        clarifying_questions=session.clarifying_questions,
        clarification_answers=session.clarification_answers,
    )

    # Detach before LLM call — do not hold DB transaction open.
    session_id = session.id
    db.commit()

    try:
        result = provider.structure_idea(request)
        llm_error: LlmError | None = None
    except LlmError as exc:
        result = None
        llm_error = exc
    except Exception as exc:  # noqa: BLE001
        # Do not log exception message / traceback locals (may contain prompts).
        logger.error(
            "unexpected_llm_error job_id=%s session_id=%s category=%s",
            job_id,
            session_id,
            type(exc).__name__,
        )
        result = None
        llm_error = LlmUnavailableError()

    # Fresh transaction: fence on AiJob ownership before touching the session.
    now = utcnow()
    job = db.execute(
        select(AiJob).where(AiJob.id == job_id).with_for_update()
    ).scalar_one_or_none()
    if job is None:
        return
    if not _job_owned_by_worker(job, worker_id=worker_id, now=now):
        logger.info("ai_job_lease_lost job_id=%s", job_id)
        db.rollback()
        return

    session = db.execute(
        select(IdeaAiSession).where(IdeaAiSession.id == session_id).with_for_update()
    ).scalar_one_or_none()
    if session is None or session.status != IdeaAiSessionStatus.PROCESSING.value:
        # Ownership held but session moved — fail the job without applying LLM draft.
        job.status = AiJobStatus.FAILED.value
        job.finished_at = utcnow()
        job.locked_at = None
        job.lease_until = None
        job.last_error_code = "AI_SESSION_INVALID_STATE"
        job.last_error_message = "Session state changed during LLM call."
        db.commit()
        return

    if llm_error is not None:
        _apply_failure(db, job=job, session=session, error=llm_error, settings=cfg)
        db.commit()
        logger.info(
            "ai_job_failed job_id=%s session_id=%s code=%s attempts=%s",
            job.id,
            session.id,
            llm_error.code,
            job.attempts,
        )
        return

    assert result is not None
    _apply_success(db, job=job, session=session, result=result, provider=provider)
    db.commit()
    logger.info(
        "ai_job_succeeded job_id=%s session_id=%s decision=%s",
        job.id,
        session.id,
        result.decision.value,
    )


def run_once(
    *,
    session_factory: sessionmaker[Session] | None = None,
    provider: LlmProvider | None = None,
    search_provider: WebSearchProvider | None = None,
    settings: Settings | None = None,
    worker_id: str | None = None,
    recover: bool = True,
) -> bool:
    """Recover stale jobs, claim one job, process it. Returns True if work done."""
    cfg = settings or get_settings()
    factory = session_factory or get_session_factory()
    wid = worker_id or make_worker_id()
    owns_provider = provider is None
    owns_search = search_provider is None
    llm = provider or get_llm_provider(cfg)
    search: WebSearchProvider | None = search_provider
    if search is None and cfg.web_search_api_url.strip():
        try:
            search = get_web_search_provider(cfg)
            owns_search = True
        except Exception:  # noqa: BLE001
            search = None

    try:
        db = factory()
        try:
            if recover:
                recover_stale_jobs(db, settings=cfg)
            job = claim_next_job(db, worker_id=wid, settings=cfg)
            if job is None:
                return False
            job_id = job.id
            job_type = job.job_type
        finally:
            db.close()

        if job_type == AiJobType.WEB_RESEARCH.value and search is None:
            db_fail = factory()
            try:
                job_row = db_fail.execute(
                    select(AiJob).where(AiJob.id == job_id).with_for_update()
                ).scalar_one_or_none()
                run_row = (
                    db_fail.get(WebResearchRun, job_row.research_run_id)
                    if job_row and job_row.research_run_id
                    else None
                )
                if job_row is not None:
                    from app.web_search.exceptions import WebSearchConfigurationError

                    err = WebSearchConfigurationError()
                    if run_row is not None:
                        _apply_web_research_failure(
                            db_fail,
                            job=job_row,
                            run=run_row,
                            error=err,
                            settings=cfg,
                            failure_phase="SEARCH",
                        )
                    else:
                        job_row.status = AiJobStatus.FAILED.value
                        job_row.finished_at = utcnow()
                        job_row.last_error_code = err.code
                        job_row.last_error_message = err.safe_message
                    db_fail.commit()
            finally:
                db_fail.close()
            return True

        db2 = factory()
        try:
            process_claimed_job(
                db2,
                job_id=job_id,
                worker_id=wid,
                provider=llm,
                search_provider=search,
                settings=cfg,
            )
            return True
        finally:
            db2.close()
    finally:
        if owns_provider:
            close = getattr(llm, "close", None)
            if callable(close):
                close()
        if owns_search and search is not None:
            close_search = getattr(search, "close", None)
            if callable(close_search):
                close_search()


class AiWorker:
    """Daemon thread polling the DB job queue."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        session_factory: sessionmaker[Session] | None = None,
        provider_factory: Callable[[], LlmProvider] | None = None,
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        if provider_factory is not None:
            self._provider_factory = provider_factory
        else:
            self._provider_factory = lambda: get_llm_provider(self._settings or get_settings())
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.worker_id = make_worker_id()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="ideaflow-ai-worker",
            daemon=True,
        )
        self._thread.start()
        logger.info("ai_worker_started worker_id=%s", self.worker_id)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        logger.info("ai_worker_stopped worker_id=%s", self.worker_id)

    def _loop(self) -> None:
        cfg = self._settings or get_settings()
        provider = self._provider_factory()
        search_provider: WebSearchProvider | None = None
        if cfg.web_search_api_url.strip():
            try:
                search_provider = get_web_search_provider(cfg)
            except Exception:  # noqa: BLE001
                search_provider = None
        try:
            while not self._stop.is_set():
                try:
                    did_work = run_once(
                        session_factory=self._session_factory,
                        provider=provider,
                        search_provider=search_provider,
                        settings=cfg,
                        worker_id=self.worker_id,
                        recover=True,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "ai_worker_loop_error worker_id=%s category=%s",
                        self.worker_id,
                        type(exc).__name__,
                    )
                    did_work = False
                interval = cfg.ai_job_poll_interval_seconds
                self._stop.wait(0 if did_work else interval)
        finally:
            close = getattr(provider, "close", None)
            if callable(close):
                close()
            if search_provider is not None:
                close_search = getattr(search_provider, "close", None)
                if callable(close_search):
                    close_search()
