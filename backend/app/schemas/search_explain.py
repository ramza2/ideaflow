"""Search explainability schemas (Step 27).

Additive metadata for search results only — ranking is unchanged.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class KeywordSearchExplanation(BaseModel):
    """Direct ILIKE field hits and/or FTS-only match."""

    matched_fields: list[str] = Field(default_factory=list)
    fts_match: bool = False
    rank: int | None = None


class SemanticSearchExplanation(BaseModel):
    """Cosine distance from SQL + optional 1-based rank."""

    distance: float | None = None
    similarity: float | None = None
    rank: int | None = None


class HybridSearchExplanation(BaseModel):
    """RRF fusion metadata (candidate ranks, not page-local index)."""

    keyword_rank: int | None = None
    semantic_rank: int | None = None
    rrf_score: float | None = None


class SearchExplanation(BaseModel):
    mode: Literal["keyword", "semantic", "hybrid"]
    keyword: KeywordSearchExplanation | None = None
    semantic: SemanticSearchExplanation | None = None
    hybrid: HybridSearchExplanation | None = None
