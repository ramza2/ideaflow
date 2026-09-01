"""DB-backed in-process embedding job worker (Step 13)."""

from __future__ import annotations

import logging
import os
import socket
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.db.session import get_session_factory
from app.embeddings.base import EmbeddingProvider
from app.embeddings.canonical import build_idea_embedding_text
from app.embeddings.exceptions import (
    EmbeddingAuthenticationError,
    EmbeddingError,
    EmbeddingResponseValidationError,
    EmbeddingServerError,
    EmbeddingTimeoutError,
    EmbeddingUnavailableError,
)
from app.embeddings.factory import get_embedding_provider
from app.models.embedding import IdeaEmbedding, IdeaEmbeddingJob
from app.models.enums import IdeaEmbeddingJobStatus
from app.models.idea import Idea
from app.services.embedding_service import compute_idea_content_hash, load_idea_tag_names

logger = logging.getLogger(__name__)

_RETRYABLE_CODES = {
    "EMBEDDING_UNAVAILABLE",
    "EMBEDDING_TIMEOUT",
    "EMBEDDING_SERVER_ERROR",
    "EMBEDDING_CONNECTION_ERROR",
}


@dataclass(frozen=True)
class PreparedEmbeddingWork:
    idea_id: UUID
    workspace_id: UUID
    content_hash: str
    embedding_text: str


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def make_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def backoff_seconds(base: float, attempt: int) -> float:
    exp = max(attempt - 1, 0)
    return base * (2**exp)


def _lease_valid(job: IdeaEmbeddingJob, now: datetime) -> bool:
    if job.lease_until is None:
        return False
    lease = job.lease_until
    if lease.tzinfo is None:
        lease = lease.replace(tzinfo=timezone.utc)
    return lease >= now


def _job_owned_by_worker(job: IdeaEmbeddingJob, *, worker_id: str, now: datetime) -> bool:
    if job.status != IdeaEmbeddingJobStatus.RUNNING.value:
        return False
    if job.worker_id != worker_id:
        return False
    return _lease_valid(job, now)


def _load_fresh_idea(db: Session, idea_id: UUID) -> Idea | None:
    db.expire_all()
    return db.execute(
        select(Idea).where(Idea.id == idea_id).execution_options(populate_existing=True)
    ).scalar_one_or_none()


def _clear_job_lease(job: IdeaEmbeddingJob) -> None:
    job.locked_at = None
    job.lease_until = None
    job.worker_id = None


def recover_stale_embedding_jobs(db: Session, *, settings: Settings | None = None) -> int:
    """Requeue or fail RUNNING jobs whose lease expired (lock-safe)."""
    del settings
    now = utcnow()
    recovered = 0
    while True:
        job = db.execute(
            select(IdeaEmbeddingJob)
            .where(
                IdeaEmbeddingJob.status == IdeaEmbeddingJobStatus.RUNNING.value,
                IdeaEmbeddingJob.lease_until.is_not(None),
                IdeaEmbeddingJob.lease_until < now,
            )
            .order_by(IdeaEmbeddingJob.lease_until.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        ).scalar_one_or_none()
        if job is None:
            break

        if job.attempts < job.max_attempts:
            job.status = IdeaEmbeddingJobStatus.QUEUED.value
            job.available_at = now
            _clear_job_lease(job)
            job.last_error_code = "EMBEDDING_LEASE_EXPIRED"
            job.last_error_message = "Worker lease expired; job requeued."
        else:
            job.status = IdeaEmbeddingJobStatus.FAILED.value
            _clear_job_lease(job)
            job.last_error_code = "EMBEDDING_LEASE_EXPIRED"
            job.last_error_message = "Worker lease expired; max attempts reached."
        recovered += 1

    if recovered:
        db.commit()
    else:
        db.rollback()
    return recovered


def claim_next_embedding_job(
    db: Session,
    *,
    worker_id: str,
    settings: Settings | None = None,
) -> IdeaEmbeddingJob | None:
    cfg = settings or get_settings()
    now = utcnow()
    job = db.execute(
        select(IdeaEmbeddingJob)
        .where(
            IdeaEmbeddingJob.status == IdeaEmbeddingJobStatus.QUEUED.value,
            IdeaEmbeddingJob.available_at <= now,
        )
        .order_by(IdeaEmbeddingJob.created_at.asc())
        .with_for_update(skip_locked=True)
        .limit(1)
    ).scalar_one_or_none()
    if job is None:
        return None

    job.status = IdeaEmbeddingJobStatus.RUNNING.value
    job.attempts = int(job.attempts) + 1
    job.locked_at = now
    job.lease_until = now + timedelta(seconds=cfg.embedding_job_lease_seconds)
    job.worker_id = worker_id
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def prepare_claimed_embedding_work(
    db: Session,
    *,
    job: IdeaEmbeddingJob,
    worker_id: str,
) -> PreparedEmbeddingWork | None:
    """Read immutable work inputs and end the claim transaction before external API calls."""
    now = utcnow()
    if not _job_owned_by_worker(job, worker_id=worker_id, now=now):
        db.rollback()
        return None

    idea = _load_fresh_idea(db, job.idea_id)
    if idea is None or idea.deleted_at is not None:
        job.status = IdeaEmbeddingJobStatus.SUCCEEDED.value
        _clear_job_lease(job)
        db.commit()
        return None

    current_hash = compute_idea_content_hash(db, idea)
    if current_hash != job.content_hash:
        job.status = IdeaEmbeddingJobStatus.QUEUED.value
        job.content_hash = current_hash
        job.available_at = now
        _clear_job_lease(job)
        db.commit()
        return None

    tag_names = load_idea_tag_names(db, idea.id)
    text = build_idea_embedding_text(idea, tag_names)
    return PreparedEmbeddingWork(
        idea_id=idea.id,
        workspace_id=idea.workspace_id,
        content_hash=job.content_hash,
        embedding_text=text,
    )


def finalize_embedding_result(
    db: Session,
    *,
    idea_id: UUID,
    workspace_id: UUID,
    worker_id: str,
    claimed_hash: str,
    vector: list[float],
    settings: Settings,
) -> None:
    """Persist embedding only when fresh DB state still matches the claimed job hash."""
    now = utcnow()
    job = db.execute(
        select(IdeaEmbeddingJob)
        .where(IdeaEmbeddingJob.idea_id == idea_id)
        .with_for_update()
    ).scalar_one_or_none()
    if job is None:
        db.rollback()
        return

    if not _job_owned_by_worker(job, worker_id=worker_id, now=now):
        db.rollback()
        return

    if job.content_hash != claimed_hash:
        db.rollback()
        return

    idea = _load_fresh_idea(db, idea_id)
    if idea is None or idea.deleted_at is not None:
        job.status = IdeaEmbeddingJobStatus.SUCCEEDED.value
        _clear_job_lease(job)
        job.last_error_code = None
        job.last_error_message = None
        db.commit()
        return

    latest_hash = compute_idea_content_hash(db, idea)
    if latest_hash != claimed_hash or latest_hash != job.content_hash:
        db.rollback()
        return

    row = db.get(IdeaEmbedding, idea_id)
    if row is None:
        row = IdeaEmbedding(
            idea_id=idea_id,
            workspace_id=workspace_id,
            embedding=vector,
            content_hash=claimed_hash,
            model_name=settings.embedding_model_name,
            dimension=settings.embedding_dimension,
        )
        db.add(row)
    else:
        row.embedding = vector
        row.content_hash = claimed_hash
        row.model_name = settings.embedding_model_name
        row.dimension = settings.embedding_dimension
        row.workspace_id = workspace_id

    job.status = IdeaEmbeddingJobStatus.SUCCEEDED.value
    _clear_job_lease(job)
    job.last_error_code = None
    job.last_error_message = None
    db.commit()


def _fail_or_retry_job_locked(
    db: Session,
    *,
    idea_id: UUID,
    worker_id: str,
    exc: EmbeddingError,
    settings: Settings,
    now: datetime | None = None,
) -> None:
    now = now or utcnow()
    job = db.execute(
        select(IdeaEmbeddingJob)
        .where(IdeaEmbeddingJob.idea_id == idea_id)
        .with_for_update()
    ).scalar_one_or_none()
    if job is None or not _job_owned_by_worker(job, worker_id=worker_id, now=now):
        db.rollback()
        return

    code = getattr(exc, "code", "EMBEDDING_ERROR")
    message = str(exc)
    retryable = code in _RETRYABLE_CODES or isinstance(
        exc, (EmbeddingTimeoutError, EmbeddingServerError, EmbeddingUnavailableError)
    )
    if isinstance(exc, EmbeddingResponseValidationError):
        retryable = False
    if isinstance(exc, EmbeddingAuthenticationError):
        retryable = False

    if retryable and job.attempts < job.max_attempts:
        delay = backoff_seconds(settings.embedding_job_retry_base_seconds, job.attempts)
        job.status = IdeaEmbeddingJobStatus.QUEUED.value
        job.available_at = now + timedelta(seconds=delay)
        _clear_job_lease(job)
        job.last_error_code = code
        job.last_error_message = message[:500]
    else:
        job.status = IdeaEmbeddingJobStatus.FAILED.value
        _clear_job_lease(job)
        job.last_error_code = code
        job.last_error_message = message[:500]
    db.commit()


def process_claimed_embedding_job(
    db: Session,
    *,
    job: IdeaEmbeddingJob,
    worker_id: str,
    provider: EmbeddingProvider,
    settings: Settings | None = None,
    session_factory: sessionmaker | None = None,
) -> None:
    """Process one claimed job: prepare, external API, finalize in a fresh session."""
    cfg = settings or get_settings()
    work = prepare_claimed_embedding_work(db, job=job, worker_id=worker_id)
    if work is None:
        return

    db.commit()

    try:
        vector = provider.embed_text(work.embedding_text)
    except EmbeddingError as exc:
        factory = session_factory or get_session_factory()
        with factory() as retry_db:
            _fail_or_retry_job_locked(
                retry_db,
                idea_id=work.idea_id,
                worker_id=worker_id,
                exc=exc,
                settings=cfg,
            )
        return

    factory = session_factory or get_session_factory()
    with factory() as finalize_db:
        finalize_embedding_result(
            finalize_db,
            idea_id=work.idea_id,
            workspace_id=work.workspace_id,
            worker_id=worker_id,
            claimed_hash=work.content_hash,
            vector=vector,
            settings=cfg,
        )


def run_once(
    db: Session,
    *,
    worker_id: str,
    settings: Settings | None = None,
    provider_factory: Callable[[Settings], EmbeddingProvider] | None = None,
    session_factory: sessionmaker | None = None,
) -> bool:
    cfg = settings or get_settings()
    if not cfg.embedding_enabled:
        return False

    factory_sf = session_factory or get_session_factory()

    recover_stale_embedding_jobs(db, settings=cfg)
    job = claim_next_embedding_job(db, worker_id=worker_id, settings=cfg)
    if job is None:
        return False

    provider_factory = provider_factory or get_embedding_provider
    provider = provider_factory(cfg)
    try:
        process_claimed_embedding_job(
            db,
            job=job,
            worker_id=worker_id,
            provider=provider,
            settings=cfg,
            session_factory=factory_sf,
        )
    finally:
        provider.close()
    return True


class EmbeddingWorker:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        session_factory: sessionmaker | None = None,
        provider_factory: Callable[[Settings], EmbeddingProvider] | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._session_factory = session_factory or get_session_factory()
        self._provider_factory = provider_factory
        self._worker_id = make_worker_id()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop, name="embedding-worker", daemon=True)
        self._thread.start()
        logger.info(
            "Embedding worker started (enabled=%s, provider=%s, model=%s, dimension=%s)",
            self._settings.embedding_enabled,
            self._settings.embedding_provider,
            self._settings.embedding_model_name,
            self._settings.embedding_dimension,
        )

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def _run_loop(self) -> None:
        interval = self._settings.embedding_job_poll_interval_seconds
        while not self._stop.is_set():
            try:
                with self._session_factory() as db:
                    run_once(
                        db,
                        worker_id=self._worker_id,
                        settings=self._settings,
                        provider_factory=self._provider_factory,
                        session_factory=self._session_factory,
                    )
            except Exception:
                logger.exception("Embedding worker loop error")
            self._stop.wait(interval)
