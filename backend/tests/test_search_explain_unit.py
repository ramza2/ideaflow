"""Unit tests for search explainability helpers (Step 27)."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.services.search_explain import (
    KEYWORD_MATCH_FIELDS,
    build_keyword_explanation,
    explain_hybrid_page,
    matched_keyword_fields,
    similarity_from_distance,
)


def test_matched_keyword_fields_case_insensitive_substring() -> None:
    idea = SimpleNamespace(
        title="회의록 자동 정리",
        one_line_definition="회의 음성을 요약합니다",
        original_text=None,
        background=None,
        problem="수동 정리 부담",
        core_concept=None,
        expected_effect=None,
    )
    assert matched_keyword_fields(idea, "회의록") == ["title"]
    assert "problem" in matched_keyword_fields(idea, "수동")
    assert matched_keyword_fields(idea, "없는단어") == []


def test_keyword_explanation_marks_fts_when_no_ilike() -> None:
    idea = SimpleNamespace(**{f: None for f in KEYWORD_MATCH_FIELDS})
    idea.title = "완전히 다른 제목"
    exp = build_keyword_explanation(idea, "회의록", rank=2, in_keyword_result=True)
    assert exp.matched_fields == []
    assert exp.fts_match is True
    assert exp.rank == 2


def test_similarity_from_distance() -> None:
    assert similarity_from_distance(0.13) == 0.87
    assert similarity_from_distance(None) is None


def test_hybrid_explanation_one_sided_and_candidate_ranks() -> None:
    id_a, id_b, id_c = uuid4(), uuid4(), uuid4()
    ideas = [
        SimpleNamespace(
            id=id_a,
            title="키워드만",
            one_line_definition=None,
            original_text=None,
            background=None,
            problem=None,
            core_concept=None,
            expected_effect=None,
        ),
        SimpleNamespace(
            id=id_b,
            title="의미만",
            one_line_definition=None,
            original_text=None,
            background=None,
            problem=None,
            core_concept=None,
            expected_effect=None,
        ),
        SimpleNamespace(
            id=id_c,
            title="둘 다 회의록",
            one_line_definition=None,
            original_text=None,
            background=None,
            problem=None,
            core_concept=None,
            expected_effect=None,
        ),
    ]
    out = explain_hybrid_page(
        ideas,  # type: ignore[arg-type]
        "회의록",
        keyword_ids=[id_c, id_a],
        semantic_ids=[id_b, id_c],
        distance_by_id={id_b: 0.2, id_c: 0.1},
        rrf_score_by_id={id_a: 0.01, id_b: 0.02, id_c: 0.03},
    )
    assert out[id_a].hybrid is not None
    assert out[id_a].hybrid.keyword_rank == 2
    assert out[id_a].hybrid.semantic_rank is None
    assert out[id_a].keyword is not None
    assert out[id_a].semantic is None

    assert out[id_b].hybrid is not None
    assert out[id_b].hybrid.keyword_rank is None
    assert out[id_b].hybrid.semantic_rank == 1
    assert out[id_b].keyword is None
    assert out[id_b].semantic is not None
    assert out[id_b].semantic.similarity == 0.8

    assert out[id_c].hybrid is not None
    assert out[id_c].hybrid.keyword_rank == 1
    assert out[id_c].hybrid.semantic_rank == 2
    assert out[id_c].keyword is not None
    assert "title" in out[id_c].keyword.matched_fields
