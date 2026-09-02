"""Unit tests for Web Research LLM refinement evidence budgeting."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.core.config import Settings
from app.llm.research_schemas import EvidenceInput, validate_refinement_result
from app.llm.exceptions import LlmResponseValidationError
from app.llm.research_schemas import EvidenceRefinementResult
from app.models.research import WebEvidence
from app.services.web_research import (
    build_refinement_evidence_inputs,
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
