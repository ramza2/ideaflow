"""Semantic and hybrid Idea search (Step 13)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.embeddings.base import EmbeddingProvider
from app.embeddings.factory import get_embedding_provider
from app.models.embedding import IdeaEmbedding
from app.models.enums import SearchMode
from app.models.idea import Idea
from app.services import idea_access
from app.services.idea import (
    _apply_list_filters,
    _build_keyword_query,
    _finalize_list_response,
    _normalize_list_pagination,
)

RRF_K = 60
HYBRID_MAX_RESULT_WINDOW = 300
HYBRID_CANDIDATE_MIN = 50
HYBRID_CANDIDATE_MULTIPLIER = 3
HYBRID_CANDIDATE_MAX = HYBRID_MAX_RESULT_WINDOW


def _validate_hybrid_result_window(offset: int, limit: int) -> None:
    if offset + limit > HYBRID_MAX_RESULT_WINDOW:
        raise AppError(
            f"Hybrid search supports offset + limit up to {HYBRID_MAX_RESULT_WINDOW}.",
            code="HYBRID_RESULT_WINDOW_EXCEEDED",
            status_code=400,
        )


def _require_semantic_enabled(settings: Settings | None = None) -> Settings:
    cfg = settings or get_settings()
    if not cfg.embedding_enabled:
        raise AppError(
            "Semantic search is unavailable because embeddings are disabled.",
            code="SEMANTIC_SEARCH_UNAVAILABLE",
            status_code=503,
        )
    return cfg


def _embedding_current_filters(settings: Settings):
    return (
        IdeaEmbedding.model_name == settings.embedding_model_name,
        IdeaEmbedding.dimension == settings.embedding_dimension,
    )


def _candidate_limit(limit: int, offset: int) -> int:
    return min(max(HYBRID_CANDIDATE_MIN, (limit + offset) * HYBRID_CANDIDATE_MULTIPLIER), HYBRID_CANDIDATE_MAX)


def _embed_query(
    q: str,
    *,
    settings: Settings,
    provider_factory,
) -> list[float]:
    try:
        provider: EmbeddingProvider = provider_factory(settings)
    except Exception as exc:
        raise AppError(
            "Semantic search is unavailable.",
            code="SEMANTIC_SEARCH_UNAVAILABLE",
            status_code=503,
        ) from exc
    try:
        return provider.embed_text(q)
    except Exception as exc:
        raise AppError(
            "Semantic search is unavailable.",
            code="SEMANTIC_SEARCH_UNAVAILABLE",
            status_code=503,
        ) from exc
    finally:
        provider.close()


def list_semantic_ideas(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    q: str,
    stage_id: UUID | None = None,
    category_id: UUID | None = None,
    priority: str | None = None,
    feasibility: str | None = None,
    visibility: str | None = None,
    author_id: UUID | None = None,
    assignee_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
    settings: Settings | None = None,
    provider_factory=None,
) -> tuple[list[Idea], int]:
    cfg = _require_semantic_enabled(settings)
    factory = provider_factory or get_embedding_provider
    query_vector = _embed_query(q, settings=cfg, provider_factory=factory)
    limit, offset = _normalize_list_pagination(limit, offset)

    distance = IdeaEmbedding.embedding.cosine_distance(query_vector)
    base = (
        select(Idea, distance.label("distance"))
        .join(IdeaEmbedding, IdeaEmbedding.idea_id == Idea.id)
        .where(Idea.workspace_id == workspace_id)
    )
    base = idea_access.apply_readable_filter(base, user_id)
    base = base.where(*_embedding_current_filters(cfg))
    base = _apply_list_filters(
        base,
        stage_id=stage_id,
        category_id=category_id,
        priority=priority,
        feasibility=feasibility,
        visibility=visibility,
        author_id=author_id,
        assignee_id=assignee_id,
    )

    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = list(
        db.execute(base.order_by(distance.asc(), Idea.updated_at.desc(), Idea.id.desc()).offset(offset).limit(limit))
    )
    ideas = [row[0] for row in rows]
    return ideas, int(total)


def _keyword_ranked_ids(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    q: str,
    stage_id: UUID | None,
    category_id: UUID | None,
    priority: str | None,
    feasibility: str | None,
    visibility: str | None,
    author_id: UUID | None,
    assignee_id: UUID | None,
    candidate_limit: int,
) -> list[UUID]:
    base = _build_keyword_query(
        db,
        workspace_id=workspace_id,
        user_id=user_id,
        q=q,
        stage_id=stage_id,
        category_id=category_id,
        priority=priority,
        feasibility=feasibility,
        visibility=visibility,
        author_id=author_id,
        assignee_id=assignee_id,
    )
    rows = list(
        db.scalars(
            base.order_by(Idea.updated_at.desc(), Idea.id.desc()).limit(candidate_limit)
        )
    )
    return [idea.id for idea in rows]


def _semantic_ranked_ids(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    q: str,
    query_vector: list[float],
    stage_id: UUID | None,
    category_id: UUID | None,
    priority: str | None,
    feasibility: str | None,
    visibility: str | None,
    author_id: UUID | None,
    assignee_id: UUID | None,
    candidate_limit: int,
    settings: Settings,
) -> list[UUID]:
    distance = IdeaEmbedding.embedding.cosine_distance(query_vector)
    base = (
        select(Idea.id, distance.label("distance"))
        .join(IdeaEmbedding, IdeaEmbedding.idea_id == Idea.id)
        .where(Idea.workspace_id == workspace_id)
    )
    base = idea_access.apply_readable_filter(base, user_id)
    base = base.where(*_embedding_current_filters(settings))
    base = _apply_list_filters(
        base,
        stage_id=stage_id,
        category_id=category_id,
        priority=priority,
        feasibility=feasibility,
        visibility=visibility,
        author_id=author_id,
        assignee_id=assignee_id,
    )
    rows = list(db.execute(base.order_by(distance.asc(), Idea.id.asc()).limit(candidate_limit)))
    return [row[0] for row in rows]


def _rrf_merge(
    keyword_ids: list[UUID],
    semantic_ids: list[UUID],
    *,
    ideas_by_id: dict[UUID, Idea],
) -> list[Idea]:
    scores: dict[UUID, float] = {}
    for rank, idea_id in enumerate(keyword_ids, start=1):
        if idea_id not in ideas_by_id:
            continue
        scores[idea_id] = scores.get(idea_id, 0.0) + 1.0 / (RRF_K + rank)
    for rank, idea_id in enumerate(semantic_ids, start=1):
        if idea_id not in ideas_by_id:
            continue
        scores[idea_id] = scores.get(idea_id, 0.0) + 1.0 / (RRF_K + rank)

    ranked = sorted(
        scores.keys(),
        key=lambda iid: (
            -scores[iid],
            -(ideas_by_id[iid].updated_at.timestamp() if ideas_by_id[iid].updated_at else 0),
            str(iid),
        ),
    )
    return [ideas_by_id[iid] for iid in ranked]


def list_hybrid_ideas(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    q: str,
    stage_id: UUID | None = None,
    category_id: UUID | None = None,
    priority: str | None = None,
    feasibility: str | None = None,
    visibility: str | None = None,
    author_id: UUID | None = None,
    assignee_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
    settings: Settings | None = None,
    provider_factory=None,
) -> tuple[list[Idea], int]:
    cfg = _require_semantic_enabled(settings)
    limit, offset = _normalize_list_pagination(limit, offset)
    _validate_hybrid_result_window(offset, limit)
    factory = provider_factory or get_embedding_provider
    query_vector = _embed_query(q, settings=cfg, provider_factory=factory)
    pool = HYBRID_MAX_RESULT_WINDOW

    keyword_ids = _keyword_ranked_ids(
        db,
        workspace_id=workspace_id,
        user_id=user_id,
        q=q,
        stage_id=stage_id,
        category_id=category_id,
        priority=priority,
        feasibility=feasibility,
        visibility=visibility,
        author_id=author_id,
        assignee_id=assignee_id,
        candidate_limit=pool,
    )
    semantic_ids = _semantic_ranked_ids(
        db,
        workspace_id=workspace_id,
        user_id=user_id,
        q=q,
        query_vector=query_vector,
        stage_id=stage_id,
        category_id=category_id,
        priority=priority,
        feasibility=feasibility,
        visibility=visibility,
        author_id=author_id,
        assignee_id=assignee_id,
        candidate_limit=pool,
        settings=cfg,
    )

    all_ids = list(dict.fromkeys(keyword_ids + semantic_ids))
    if not all_ids:
        return [], 0

    final_stmt = select(Idea).where(
        Idea.id.in_(all_ids),
        Idea.workspace_id == workspace_id,
    )
    final_stmt = idea_access.apply_readable_filter(final_stmt, user_id)
    final_stmt = _apply_list_filters(
        final_stmt,
        stage_id=stage_id,
        category_id=category_id,
        priority=priority,
        feasibility=feasibility,
        visibility=visibility,
        author_id=author_id,
        assignee_id=assignee_id,
    )
    ideas = list(db.scalars(final_stmt))
    ideas_by_id = {idea.id: idea for idea in ideas}
    valid_ids = set(ideas_by_id)
    keyword_ids = [idea_id for idea_id in keyword_ids if idea_id in valid_ids]
    semantic_ids = [idea_id for idea_id in semantic_ids if idea_id in valid_ids]
    merged = _rrf_merge(keyword_ids, semantic_ids, ideas_by_id=ideas_by_id)
    total = len(merged)
    page = merged[offset : offset + limit]
    return page, total


def list_ideas_with_search_mode(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    q: str | None = None,
    search_mode: str = SearchMode.KEYWORD.value,
    stage_id: UUID | None = None,
    category_id: UUID | None = None,
    priority: str | None = None,
    feasibility: str | None = None,
    visibility: str | None = None,
    author_id: UUID | None = None,
    assignee_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
    settings: Settings | None = None,
    provider_factory=None,
):
    from app.schemas.idea import IdeaListResponse
    from app.services.idea import list_ideas

    query = q.strip() if q and q.strip() else None
    mode = (search_mode or SearchMode.KEYWORD.value).lower()

    if mode not in {m.value for m in SearchMode}:
        raise AppError(
            "Invalid search_mode. Allowed: keyword, semantic, hybrid.",
            code="INVALID_SEARCH_MODE",
            status_code=400,
        )

    if query is None or mode == SearchMode.KEYWORD.value:
        return list_ideas(
            db,
            workspace_id=workspace_id,
            user_id=user_id,
            q=q,
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

    if mode == SearchMode.SEMANTIC.value:
        rows, total = list_semantic_ideas(
            db,
            workspace_id=workspace_id,
            user_id=user_id,
            q=query,
            stage_id=stage_id,
            category_id=category_id,
            priority=priority,
            feasibility=feasibility,
            visibility=visibility,
            author_id=author_id,
            assignee_id=assignee_id,
            limit=limit,
            offset=offset,
            settings=settings,
            provider_factory=provider_factory,
        )
        return _finalize_list_response(db, rows, user_id=user_id, total=total, limit=limit, offset=offset)

    rows, total = list_hybrid_ideas(
        db,
        workspace_id=workspace_id,
        user_id=user_id,
        q=query,
        stage_id=stage_id,
        category_id=category_id,
        priority=priority,
        feasibility=feasibility,
        visibility=visibility,
        author_id=author_id,
        assignee_id=assignee_id,
        limit=limit,
        offset=offset,
        settings=settings,
        provider_factory=provider_factory,
    )
    return _finalize_list_response(db, rows, user_id=user_id, total=total, limit=limit, offset=offset)
