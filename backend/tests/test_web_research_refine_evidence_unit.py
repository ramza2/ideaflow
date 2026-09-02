"""Unit tests for Web Research LLM refinement evidence budgeting."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.core.config import Settings
from app.llm.exceptions import LlmResearchRefineInputTooLargeError, LlmResponseValidationError
from app.llm.research_prompts import build_research_user_prompt, research_prompt_char_counts
from app.llm.research_schemas import EvidenceInput, EvidenceRefinementRequest, EvidenceRefinementResult, validate_refinement_result
from app.models.research import WebEvidence
from app.services.web_research import (
    build_refinement_evidence_inputs,
    prepare_refinement_request,
    refinement_evidence_serialized_chars,
)


def make_settings(**overrides) -> Settings:
    base = dict(
        app_env="test",
        database_url="",
        llm_api_url="https://llm.example.test",
        llm_model_name="Qwen3-14B",
        llm_timeout_seconds=30.0,
        llm_connect_timeout_seconds=5.0,
        ai_job_lease_seconds=300,
        web_research_refine_max_evidence_items=6,
        web_research_refine_max_snippet_chars=600,
        web_research_refine_max_evidence_chars=4000,
        web_research_refine_max_prompt_chars=6000,
        web_research_refine_max_tokens=1200,
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)


def _evidence_row(*, rank: int, title: str, snippet: str | None = None) -> WebEvidence:
    row_id = uuid.uuid4()
    return WebEvidence(
        id=row_id,
        research_run_id=uuid.uuid4(),
        query="q",
        title=title,
        url=f"https://example.com/{rank}",
        url_hash=f"hash-{rank}",
        domain="example.com",
        source_name="Example",
        snippet=snippet,
        published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        rank=rank,
        provider="tavily",
        related_fields=[],
    )


def test_limits_evidence_item_count() -> None:
    rows = [_evidence_row(rank=i, title=f"Title {i}", snippet="short") for i in range(12)]
    inputs = build_refinement_evidence_inputs(rows, make_settings())
    assert len(inputs) <= 6


def test_snippet_per_item_limit() -> None:
    long_snippet = "x" * 5000
    rows = [_evidence_row(rank=0, title="T", snippet=long_snippet)]
    inputs = build_refinement_evidence_inputs(rows, make_settings())
    assert len(inputs) == 1
    assert inputs[0].snippet is not None
    assert len(inputs[0].snippet) <= 600


def test_total_serialized_char_budget() -> None:
    rows = [
        _evidence_row(rank=i, title=f"Title {i}", snippet="y" * 800)
        for i in range(6)
    ]
    settings = make_settings(web_research_refine_max_evidence_chars=1200)
    inputs = build_refinement_evidence_inputs(rows, settings)
    assert refinement_evidence_serialized_chars(inputs) <= 1200


def test_selects_lower_rank_first() -> None:
    rows = [
        _evidence_row(rank=5, title="Late"),
        _evidence_row(rank=0, title="First"),
        _evidence_row(rank=2, title="Middle"),
    ]
    inputs = build_refinement_evidence_inputs(rows, make_settings(web_research_refine_max_evidence_items=2))
    assert [ev.title for ev in inputs] == ["First", "Middle"]


def test_db_evidence_rows_not_mutated() -> None:
    original_snippet = "z" * 3000
    row = _evidence_row(rank=0, title="Keep DB", snippet=original_snippet)
    build_refinement_evidence_inputs([row], make_settings())
    assert row.snippet == original_snippet
    assert len(row.snippet) == 3000


def test_validate_refinement_rejects_evidence_not_sent_to_llm() -> None:
    sent_id = str(uuid.uuid4())
    omitted_id = str(uuid.uuid4())
    result = EvidenceRefinementResult(
        draft={"title": "T", "background": "Changed"},
        evidence_links={"background": [omitted_id]},
        research_summary="s",
    )
    with pytest.raises(LlmResponseValidationError):
        validate_refinement_result(
            result,
            base_draft={"title": "T", "background": "Old"},
            user_edited_fields=[],
            valid_evidence_ids={sent_id},
        )


def test_validate_refinement_accepts_sent_evidence_id() -> None:
    sent_id = str(uuid.uuid4())
    result = EvidenceRefinementResult(
        draft={"title": "T", "background": "Changed"},
        evidence_links={"background": [sent_id]},
        research_summary="s",
    )
    validated = validate_refinement_result(
        result,
        base_draft={"title": "T", "background": "Old"},
        user_edited_fields=[],
        valid_evidence_ids={sent_id},
    )
    assert validated.evidence_links["background"] == [sent_id]


def test_last_item_snippet_trimmed_to_fit_budget() -> None:
    rows = [
        _evidence_row(rank=0, title="A", snippet="a" * 500),
        _evidence_row(rank=1, title="B", snippet="b" * 500),
    ]
    settings = make_settings(
        web_research_refine_max_evidence_items=2,
        web_research_refine_max_snippet_chars=500,
        web_research_refine_max_evidence_chars=500,
    )
    inputs = build_refinement_evidence_inputs(rows, settings)
    assert len(inputs) >= 1
    assert refinement_evidence_serialized_chars(inputs) <= 500


def test_empty_snippet_keeps_title_metadata() -> None:
    row = _evidence_row(rank=0, title="Only Title", snippet=None)
    inputs = build_refinement_evidence_inputs([row], make_settings())
    assert len(inputs) == 1
    assert inputs[0].title == "Only Title"
    assert inputs[0].snippet is None


def test_update_evidence_related_fields_flushes() -> None:
    from unittest.mock import MagicMock

    from app.services import web_research as web_research_service

    ev_id = uuid.uuid4()
    run_id = uuid.uuid4()
    row = WebEvidence(
        id=ev_id,
        research_run_id=run_id,
        query="q",
        title="T",
        url="https://example.com/1",
        url_hash="hash",
        domain="example.com",
        source_name=None,
        snippet=None,
        published_at=None,
        fetched_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        rank=0,
        provider="tavily",
        related_fields=[],
    )
    db = MagicMock()
    db.scalars.return_value = [row]

    web_research_service.update_evidence_related_fields(
        db,
        run_id=run_id,
        evidence_links={"background": [str(ev_id)]},
    )

    assert row.related_fields == ["background"]
    db.flush.assert_called_once()


def test_research_prompt_excludes_raw_input_text() -> None:
    secret = "SECRET_INPUT_MARKER_" + ("x" * 5000)
    request = EvidenceRefinementRequest(
        input_text=secret,
        base_draft={"title": "T", "background": "A"},
        user_edited_fields=["title"],
        evidence=[],
    )
    prompt = build_research_user_prompt(request)
    assert secret not in prompt
    assert "SECRET_INPUT_MARKER_" not in prompt


def test_prepare_refinement_request_respects_total_prompt_budget() -> None:
    rows = [_evidence_row(rank=i, title=f"T{i}", snippet="y" * 500) for i in range(20)]
    settings = make_settings(
        web_research_refine_max_prompt_chars=2500,
        web_research_refine_max_evidence_chars=4000,
    )
    request, budget = prepare_refinement_request(
        input_text="ignored raw input " + ("z" * 10000),
        base_draft={"title": "T", "background": "A"},
        base_provenance={},
        user_edited_fields=[],
        evidence_rows=rows,
        settings=settings,
    )
    assert budget.total_prompt_chars <= settings.web_research_refine_max_prompt_chars
    assert budget.evidence_total_count == 20
    assert budget.evidence_used_count <= budget.evidence_candidate_count
    assert len(request.evidence) == budget.evidence_used_count


def test_dynamic_evidence_budget_can_be_smaller_than_candidate_count() -> None:
    rows = [_evidence_row(rank=i, title=f"T{i}", snippet="s" * 400) for i in range(6)]
    settings = make_settings(
        web_research_refine_max_prompt_chars=1800,
        web_research_refine_max_evidence_chars=4000,
        web_research_refine_max_evidence_items=6,
    )
    request, budget = prepare_refinement_request(
        input_text="long input",
        base_draft={"title": "T", "background": "A" * 200},
        base_provenance={},
        user_edited_fields=[],
        evidence_rows=rows,
        settings=settings,
    )
    assert budget.evidence_candidate_count == 6
    assert budget.evidence_used_count < 6
    assert len(request.evidence) == budget.evidence_used_count


def test_valid_evidence_ids_match_llm_subset() -> None:
    rows = [_evidence_row(rank=i, title=f"T{i}", snippet="s" * 300) for i in range(8)]
    request, _budget = prepare_refinement_request(
        input_text="input",
        base_draft={"title": "T"},
        base_provenance={},
        user_edited_fields=[],
        evidence_rows=rows,
        settings=make_settings(web_research_refine_max_prompt_chars=3500),
    )
    valid_ids = {str(ev.evidence_id) for ev in request.evidence}
    assert len(valid_ids) == len(request.evidence)
    sent_id = str(request.evidence[0].evidence_id)
    result = EvidenceRefinementResult(
        draft={"background": "Changed"},
        evidence_links={"background": [sent_id]},
        research_summary="s",
    )
    validate_refinement_result(
        result,
        base_draft={"title": "T", "background": "Old"},
        user_edited_fields=[],
        valid_evidence_ids=valid_ids,
    )


def test_prepare_refinement_raises_when_fixed_prompt_too_large() -> None:
    huge = "x" * 8000
    with pytest.raises(LlmResearchRefineInputTooLargeError):
        prepare_refinement_request(
            input_text="input",
            base_draft={field: huge for field in (
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
            )},
            base_provenance={},
            user_edited_fields=[],
            evidence_rows=[],
            settings=make_settings(web_research_refine_max_prompt_chars=6000),
        )


def test_partial_draft_patch_validates_and_merges() -> None:
    sent_id = str(uuid.uuid4())
    result = EvidenceRefinementResult(
        draft={"background": "Refined only"},
        evidence_links={"background": [sent_id]},
        research_summary="summary",
    )
    validated = validate_refinement_result(
        result,
        base_draft={"title": "T", "background": "Old", "problem": "P"},
        user_edited_fields=[],
        valid_evidence_ids={sent_id},
    )
    assert validated.draft == {"background": "Refined only"}


def test_repeated_user_edited_field_protection_regression() -> None:
    sent_id = str(uuid.uuid4())
    result = EvidenceRefinementResult(
        draft={"title": "Changed title", "background": "Changed"},
        evidence_links={"background": [sent_id], "title": [sent_id]},
        research_summary="s",
    )
    with pytest.raises(LlmResponseValidationError):
        validate_refinement_result(
            result,
            base_draft={"title": "T", "background": "Old"},
            user_edited_fields=["title"],
            valid_evidence_ids={sent_id},
        )


def test_refinement_uses_compact_json_without_indent() -> None:
    request = EvidenceRefinementRequest(
        input_text="ignored",
        base_draft={"title": "T", "background": "A"},
        user_edited_fields=["title"],
        evidence=[],
    )
    prompt = build_research_user_prompt(request)
    assert "\n  " not in prompt.split("## Evidence")[0]
    system_chars, user_chars, total = research_prompt_char_counts(request)
    assert total == system_chars + user_chars
    assert user_chars == len(build_research_user_prompt(request))
