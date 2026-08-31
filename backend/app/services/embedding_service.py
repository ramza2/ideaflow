"""Idea embedding enqueue, invalidation, and backfill helpers."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
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


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


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


def enqueue_embedding_if_needed(
    db: Session,
    idea: Idea,
    *,
    settings: Settings | None = None,
    force: bool = False,
) -> bool:
    """Enqueue or refresh an embedding job. Returns True if a job was queued/updated."""
    cfg = settings or get_settings()
    if not cfg.embedding_enabled:
        return False

    content_hash = compute_idea_content_hash(db, idea)
    existing = db.get(IdeaEmbedding, idea.id)
    if (
        not force
        and existing is not None
        and is_embedding_current(
            stored_hash=existing.content_hash,
            stored_model=existing.model_name,
            stored_dimension=existing.dimension,
            current_hash=content_hash,
            settings=cfg,
        )
    ):
        return False

    job = db.get(IdeaEmbeddingJob, idea.id)
    if job is not None:
        if (
            not force
            and job.content_hash == content_hash
            and job.status in _ACTIVE_JOB_STATUSES
        ):
            return False
        if job.content_hash != content_hash:
            invalidate_embedding(db, idea.id)
        job.content_hash = content_hash
        job.status = IdeaEmbeddingJobStatus.QUEUED.value
        job.available_at = utcnow()
        job.attempts = 0
        job.max_attempts = cfg.embedding_job_max_attempts
        job.locked_at = None
        job.lease_until = None
        job.worker_id = None
        job.last_error_code = None
        job.last_error_message = None
        db.add(job)
        db.flush()
        return True

    invalidate_embedding(db, idea.id)
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


def on_idea_embedding_content_changed(db: Session, idea: Idea) -> None:
    enqueue_embedding_if_needed(db, idea)


def scan_ideas_for_enqueue(
    db: Session,
    *,
    workspace_id: UUID | None = None,
    force: bool = False,
    settings: Settings | None = None,
) -> tuple[int, int, int]:
    """Return (scanned, already_current, queued)."""
    cfg = settings or get_settings()
    stmt = select(Idea).where(Idea.deleted_at.is_(None))
    if workspace_id is not None:
        stmt = stmt.where(Idea.workspace_id == workspace_id)
    ideas = list(db.scalars(stmt))
    scanned = len(ideas)
    already_current = 0
    queued = 0
    for idea in ideas:
        content_hash = compute_idea_content_hash(db, idea)
        existing = db.get(IdeaEmbedding, idea.id)
        if (
            not force
            and existing is not None
            and is_embedding_current(
                stored_hash=existing.content_hash,
                stored_model=existing.model_name,
                stored_dimension=existing.dimension,
                current_hash=content_hash,
                settings=cfg,
            )
        ):
            already_current += 1
            continue
        if enqueue_embedding_if_needed(db, idea, settings=cfg, force=force):
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
