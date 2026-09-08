"""Idea embedding enqueue, invalidation, and backfill helpers."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.embeddings.canonical import (
    build_idea_embedding_text,
    compute_content_hash,
    is_embedding_current,
)
from app.models.embedding import IdeaEmbedding, IdeaEmbeddingJob
from app.models.enums import IdeaEmbeddingJobStatus
from app.models.idea import Idea
from app.models.relations import IdeaTag
from app.models.workspace import Tag

logger = logging.getLogger(__name__)

_ACTIVE_JOB_STATUSES = {
    IdeaEmbeddingJobStatus.QUEUED.value,
    IdeaEmbeddingJobStatus.RUNNING.value,
}

_EMBEDDING_STORAGE_READY: bool | None = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def embedding_storage_ready(db: Session) -> bool:
    """Return whether pgvector embedding tables are available in this database."""
    global _EMBEDDING_STORAGE_READY
    if _EMBEDDING_STORAGE_READY is True:
        return True
    try:
        bind = db.get_bind()
        with bind.connect() as conn:
            conn.execute(text("SELECT 1 FROM idea_embeddings LIMIT 1"))
    except Exception:
        return False
    _EMBEDDING_STORAGE_READY = True
    return True


def load_idea_tag_names(db: Session, idea_id: UUID) -> list[str]:
    rows = db.execute(
        select(Tag.name)
        .join(IdeaTag, IdeaTag.tag_id == Tag.id)
        .where(IdeaTag.idea_id == idea_id)
        .order_by(Tag.name)
    ).all()
    return [name for (name,) in rows]


def compute_idea_content_hash(db: Session, idea: Idea) -> str:
    tag_names = load_idea_tag_names(db, idea.id)
    text = build_idea_embedding_text(idea, tag_names)
    return compute_content_hash(text)


def invalidate_embedding(db: Session, idea_id: UUID) -> None:
    row = db.get(IdeaEmbedding, idea_id)
    if row is not None:
        db.delete(row)
        db.flush()


def _reset_job_for_hash(
    job: IdeaEmbeddingJob,
    *,
    content_hash: str,
    max_attempts: int,
) -> None:
    job.content_hash = content_hash
    job.status = IdeaEmbeddingJobStatus.QUEUED.value
    job.available_at = utcnow()
    job.attempts = 0
    job.max_attempts = max_attempts
    job.locked_at = None
    job.lease_until = None
    job.worker_id = None
    job.last_error_code = None
    job.last_error_message = None


def _is_current_embedding(
    *,
    existing: IdeaEmbedding | None,
    content_hash: str,
    settings: Settings,
    force: bool,
) -> bool:
    return (
        not force
        and existing is not None
        and is_embedding_current(
            stored_hash=existing.content_hash,
            stored_model=existing.model_name,
            stored_dimension=existing.dimension,
            current_hash=content_hash,
            settings=settings,
        )
    )


def _should_enqueue_or_reset_job(
    *,
    force: bool,
    content_hash: str,
    had_embedding: bool,
    job: IdeaEmbeddingJob | None,
    embedding_enabled: bool,
) -> bool:
    """Mirror ``sync_embedding_desired_state`` enqueue/reset decision (no DB writes).

    Call only after the current-embedding short-circuit has been ruled out.
    """
    if job is not None:
        if (
            not force
            and not had_embedding
            and job.content_hash == content_hash
            and job.status in _ACTIVE_JOB_STATUSES
        ):
            return False
        return True
    if embedding_enabled:
        return True
    return had_embedding


def sync_embedding_desired_state(
    db: Session,
    idea: Idea,
    *,
    settings: Settings | None = None,
    force: bool = False,
) -> bool:
    """Invalidate stale vectors and sync the desired job hash.

    Always removes outdated ``IdeaEmbedding`` rows when content is not current,
    regardless of ``EMBEDDING_ENABLED``. Enqueue/API work only happens when
    embeddings are enabled (or an existing job row must be updated).
    """
    cfg = settings or get_settings()
    if not embedding_storage_ready(db):
        return False

    content_hash = compute_idea_content_hash(db, idea)
    existing = db.get(IdeaEmbedding, idea.id)

    if _is_current_embedding(
        existing=existing,
        content_hash=content_hash,
        settings=cfg,
        force=force,
    ):
        return False

    had_embedding = existing is not None
    invalidate_embedding(db, idea.id)

    job = db.get(IdeaEmbeddingJob, idea.id)
    if not _should_enqueue_or_reset_job(
        force=force,
        content_hash=content_hash,
        had_embedding=had_embedding,
        job=job,
        embedding_enabled=cfg.embedding_enabled,
    ):
        return False

    if job is not None:
        _reset_job_for_hash(job, content_hash=content_hash, max_attempts=cfg.embedding_job_max_attempts)
        db.add(job)
        db.flush()
        return True

    if cfg.embedding_enabled:
        db.add(
            IdeaEmbeddingJob(
                idea_id=idea.id,
                content_hash=content_hash,
                status=IdeaEmbeddingJobStatus.QUEUED.value,
                max_attempts=cfg.embedding_job_max_attempts,
            )
        )
        db.flush()
        return True

    return had_embedding


def invalidate_stale_on_config_failure(db: Session, idea: Idea) -> None:
    """Invalidate vector + refresh job hash without calling external APIs.

    Used when Runtime embedding resolve fails so Idea CRUD still succeeds and
    stale vectors are not left behind.
    """
    if not embedding_storage_ready(db):
        return
    invalidate_embedding(db, idea.id)
    content_hash = compute_idea_content_hash(db, idea)
    job = db.get(IdeaEmbeddingJob, idea.id)
    if job is not None:
        from app.core.config import get_settings

        cfg = get_settings()
        _reset_job_for_hash(
            job,
            content_hash=content_hash,
            max_attempts=cfg.embedding_job_max_attempts,
        )
        db.add(job)
        db.flush()


def on_idea_embedding_content_changed(db: Session, idea: Idea) -> None:
    from app.services.integration_runtime_config import resolve_embedding_settings

    try:
        cfg = resolve_embedding_settings(db)
    except Exception as exc:  # noqa: BLE001 — never block Idea CRUD on config errors
        logger.info(
            "embedding_sync_config_failed idea_id=%s category=%s",
            idea.id,
            type(exc).__name__,
        )
        invalidate_stale_on_config_failure(db, idea)
        return
    sync_embedding_desired_state(db, idea, settings=cfg)


def enqueue_embedding_if_needed(
    db: Session,
    idea: Idea,
    *,
    settings: Settings | None = None,
    force: bool = False,
) -> bool:
    """Enqueue or refresh an embedding job (requires embeddings enabled)."""
    from app.services.integration_runtime_config import resolve_embedding_settings

    if settings is None:
        try:
            cfg = resolve_embedding_settings(db)
        except Exception:  # noqa: BLE001
            return False
    else:
        cfg = settings
    if not cfg.embedding_enabled:
        return False
    return sync_embedding_desired_state(db, idea, settings=cfg, force=force)


def embedding_coverage_counts(
    db: Session,
    *,
    workspace_id: UUID | None = None,
) -> dict[str, int]:
    """Return active Idea embedding coverage counters."""
    idea_filter = [Idea.deleted_at.is_(None)]
    if workspace_id is not None:
        idea_filter.append(Idea.workspace_id == workspace_id)

    total = int(db.scalar(select(func.count()).select_from(Idea).where(*idea_filter)) or 0)
    with_embedding_stmt = (
        select(func.count())
        .select_from(Idea)
        .join(IdeaEmbedding, IdeaEmbedding.idea_id == Idea.id)
        .where(*idea_filter)
    )
    with_embedding = int(db.scalar(with_embedding_stmt) or 0)
    job_counts = embedding_job_counts(db) if workspace_id is None else _workspace_job_counts(db, workspace_id)
    return {
        "total": total,
        "with_embedding": with_embedding,
        "without_embedding": max(0, total - with_embedding),
        "jobs_queued": job_counts.get(IdeaEmbeddingJobStatus.QUEUED.value, 0),
        "jobs_running": job_counts.get(IdeaEmbeddingJobStatus.RUNNING.value, 0),
        "jobs_succeeded": job_counts.get(IdeaEmbeddingJobStatus.SUCCEEDED.value, 0),
        "jobs_failed": job_counts.get(IdeaEmbeddingJobStatus.FAILED.value, 0),
    }


def _workspace_job_counts(db: Session, workspace_id: UUID) -> dict[str, int]:
    rows = db.execute(
        select(IdeaEmbeddingJob.status, func.count())
        .join(Idea, Idea.id == IdeaEmbeddingJob.idea_id)
        .where(Idea.workspace_id == workspace_id, Idea.deleted_at.is_(None))
        .group_by(IdeaEmbeddingJob.status)
    ).all()
    return {status: int(count) for status, count in rows}


def scan_ideas_for_enqueue(
    db: Session,
    *,
    workspace_id: UUID | None = None,
    force: bool = False,
    settings: Settings | None = None,
    limit: int | None = None,
    dry_run: bool = False,
) -> tuple[int, int, int]:
    """Return (scanned, already_current, queued).

    When ``dry_run`` is true, count ideas that would be queued without writing.
    ``limit`` caps how many non-deleted ideas are considered (stable by id).
    """
    from app.services.integration_runtime_config import resolve_embedding_settings

    if settings is None:
        try:
            cfg = resolve_embedding_settings(db)
        except Exception:  # noqa: BLE001
            return 0, 0, 0
    else:
        cfg = settings
    if not cfg.embedding_enabled:
        return 0, 0, 0

    stmt = select(Idea).where(Idea.deleted_at.is_(None)).order_by(Idea.id)
    if workspace_id is not None:
        stmt = stmt.where(Idea.workspace_id == workspace_id)
    if limit is not None:
        if limit < 1:
            return 0, 0, 0
        stmt = stmt.limit(limit)
    ideas = list(db.scalars(stmt))
    scanned = len(ideas)
    already_current = 0
    queued = 0
    for idea in ideas:
        content_hash = compute_idea_content_hash(db, idea)
        existing = db.get(IdeaEmbedding, idea.id)
        if _is_current_embedding(
            existing=existing,
            content_hash=content_hash,
            settings=cfg,
            force=force,
        ):
            already_current += 1
            continue
        if dry_run:
            job = db.get(IdeaEmbeddingJob, idea.id)
            if _should_enqueue_or_reset_job(
                force=force,
                content_hash=content_hash,
                had_embedding=existing is not None,
                job=job,
                embedding_enabled=cfg.embedding_enabled,
            ):
                queued += 1
            continue
        if sync_embedding_desired_state(db, idea, settings=cfg, force=force):
            queued += 1
    return scanned, already_current, queued


def embedding_job_counts(db: Session) -> dict[str, int]:
    counts = {status.value: 0 for status in IdeaEmbeddingJobStatus}
    rows = db.execute(
        select(IdeaEmbeddingJob.status, func.count()).group_by(IdeaEmbeddingJob.status)
    ).all()
    for status, count in rows:
        counts[status] = int(count)
    return counts
