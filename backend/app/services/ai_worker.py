"""DB-backed in-process AI job worker (Step 7)."""

from __future__ import annotations

import logging
import os
import socket
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.db.session import get_session_factory
from app.llm.base import LlmProvider
from app.llm.exceptions import LlmError, LlmUnavailableError
from app.llm.factory import get_llm_provider
from app.llm.prompts import IDEA_STRUCTURE_PROMPT_VERSION, categories_from_rows
from app.llm.schemas import IdeaStructuringRequest
from app.models.ai import AiJob, IdeaAiSession
from app.models.enums import AiJobStatus, AiLlmDecision, IdeaAiSessionStatus
from app.models.workspace import WorkspaceCategory
from app.services import ai_session as ai_session_service

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def make_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def backoff_seconds(base: float, attempt: int) -> float:
    """Exponential backoff: base * 2^(attempt-1). attempt is 1-based after claim."""
    exp = max(attempt - 1, 0)
    return base * (2**exp)


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
        if job.attempts < job.max_attempts:
            job.status = AiJobStatus.QUEUED.value
            job.available_at = now
            job.locked_at = None
            job.lease_until = None
            job.worker_id = None
            job.started_at = None
            job.last_error_code = "LLM_LEASE_EXPIRED"
            job.last_error_message = "Worker lease expired; job requeued."
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


def _apply_failure(
    db: Session,
    *,
    job: AiJob,
    session: IdeaAiSession | None,
    error: LlmError,
    settings: Settings,
) -> None:
    now = utcnow()
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


def process_claimed_job(
    db: Session,
    *,
    job_id: UUID,
    worker_id: str,
    provider: LlmProvider,
    settings: Settings | None = None,
) -> None:
    """Run LLM outside prior claim txn; persist only if lease ownership holds."""
    cfg = settings or get_settings()
    job = db.get(AiJob, job_id)
    if job is None or job.status != AiJobStatus.RUNNING.value:
        return
    if job.worker_id != worker_id:
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
    settings: Settings | None = None,
    worker_id: str | None = None,
    recover: bool = True,
) -> bool:
    """Recover stale jobs, claim one job, process it. Returns True if work done."""
    cfg = settings or get_settings()
    factory = session_factory or get_session_factory()
    wid = worker_id or make_worker_id()
    owns_provider = provider is None
    llm = provider or get_llm_provider(cfg)

    try:
        db = factory()
        try:
            if recover:
                recover_stale_jobs(db, settings=cfg)
            job = claim_next_job(db, worker_id=wid, settings=cfg)
            if job is None:
                return False
            job_id = job.id
        finally:
            db.close()

        db2 = factory()
        try:
            process_claimed_job(
                db2,
                job_id=job_id,
                worker_id=wid,
                provider=llm,
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
        try:
            while not self._stop.is_set():
                try:
                    did_work = run_once(
                        session_factory=self._session_factory,
                        provider=provider,
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
