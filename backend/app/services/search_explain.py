"""Search explainability helpers (Step 27).

Compute match metadata for final page items only — no extra DB queries,
no ranking changes. Keyword field checks mirror ILIKE %q% (case-insensitive).
"""

from __future__ import annotations

from uuid import UUID

from app.models.idea import Idea
from app.schemas.search_explain import (
    HybridSearchExplanation,
    KeywordSearchExplanation,
    SearchExplanation,
    SemanticSearchExplanation,
)

# Fields included in keyword `_search_predicate` — keep in sync with idea.py.
KEYWORD_MATCH_FIELDS: tuple[str, ...] = (
    "title",
    "one_line_definition",
    "original_text",
    "background",
    "problem",
    "core_concept",
    "expected_effect",
)


def normalize_query(q: str) -> str:
    return q.strip().lower()


def matched_keyword_fields(idea: Idea, q: str) -> list[str]:
    """Return field names with case-insensitive substring match (ILIKE-equivalent)."""
    needle = normalize_query(q)
    if not needle:
        return []
    hits: list[str] = []
    for field in KEYWORD_MATCH_FIELDS:
        value = getattr(idea, field, None)
        if isinstance(value, str) and needle in value.lower():
            hits.append(field)
    return hits


def build_keyword_explanation(
    idea: Idea,
    q: str,
    *,
    rank: int | None = None,
    in_keyword_result: bool = True,
) -> KeywordSearchExplanation:
    matched = matched_keyword_fields(idea, q)
    # Idea is a keyword hit but no ILIKE field → FTS contributed.
    fts_match = in_keyword_result and len(matched) == 0
    return KeywordSearchExplanation(
        matched_fields=matched,
        fts_match=fts_match,
        rank=rank,
    )


def similarity_from_distance(distance: float | None) -> float | None:
    """pgvector cosine_distance ≈ 1 - cosine_similarity for normalized vectors."""
    if distance is None:
        return None
    return round(1.0 - float(distance), 6)


def build_semantic_explanation(
    *,
    distance: float | None,
    rank: int | None = None,
) -> SemanticSearchExplanation:
    return SemanticSearchExplanation(
        distance=None if distance is None else round(float(distance), 6),
        similarity=similarity_from_distance(distance),
        rank=rank,
    )


def build_hybrid_explanation(
    *,
    keyword_rank: int | None,
    semantic_rank: int | None,
    rrf_score: float | None,
) -> HybridSearchExplanation:
    return HybridSearchExplanation(
        keyword_rank=keyword_rank,
        semantic_rank=semantic_rank,
        rrf_score=None if rrf_score is None else round(float(rrf_score), 6),
    )


def explain_keyword_page(
    ideas: list[Idea],
    q: str,
    *,
    offset: int,
) -> dict[UUID, SearchExplanation]:
    out: dict[UUID, SearchExplanation] = {}
    for index, idea in enumerate(ideas):
        out[idea.id] = SearchExplanation(
            mode="keyword",
            keyword=build_keyword_explanation(
                idea,
                q,
                rank=offset + index + 1,
                in_keyword_result=True,
            ),
        )
    return out


def explain_semantic_page(
    ideas: list[Idea],
    *,
    distance_by_id: dict[UUID, float],
    offset: int,
) -> dict[UUID, SearchExplanation]:
    out: dict[UUID, SearchExplanation] = {}
    for index, idea in enumerate(ideas):
        out[idea.id] = SearchExplanation(
            mode="semantic",
            semantic=build_semantic_explanation(
                distance=distance_by_id.get(idea.id),
                rank=offset + index + 1,
            ),
        )
    return out


def explain_hybrid_page(
    ideas: list[Idea],
    q: str,
    *,
    keyword_ids: list[UUID],
    semantic_ids: list[UUID],
    distance_by_id: dict[UUID, float],
    rrf_score_by_id: dict[UUID, float],
) -> dict[UUID, SearchExplanation]:
    keyword_rank_by_id = {idea_id: rank for rank, idea_id in enumerate(keyword_ids, start=1)}
    semantic_rank_by_id = {idea_id: rank for rank, idea_id in enumerate(semantic_ids, start=1)}
    out: dict[UUID, SearchExplanation] = {}
    for idea in ideas:
        kw_rank = keyword_rank_by_id.get(idea.id)
        sem_rank = semantic_rank_by_id.get(idea.id)
        keyword_part = None
        if kw_rank is not None:
            keyword_part = build_keyword_explanation(
                idea,
                q,
                rank=kw_rank,
                in_keyword_result=True,
            )
        semantic_part = None
        if sem_rank is not None:
            semantic_part = build_semantic_explanation(
                distance=distance_by_id.get(idea.id),
                rank=sem_rank,
            )
        out[idea.id] = SearchExplanation(
            mode="hybrid",
            keyword=keyword_part,
            semantic=semantic_part,
            hybrid=build_hybrid_explanation(
                keyword_rank=kw_rank,
                semantic_rank=sem_rank,
                rrf_score=rrf_score_by_id.get(idea.id),
            ),
        )
    return out
