"""Unit tests for LLM structuring schemas / JSON parsing (no DB)."""

from __future__ import annotations

import pytest

from app.llm.exceptions import LlmResponseValidationError
from app.llm.schemas import (
    MAX_CLARIFYING_QUESTIONS,
    MAX_RESEARCH_TOPICS,
    IdeaStructuringResult,
    parse_structuring_result,
    strip_json_fence,
)
from app.models.enums import AiLlmDecision, FieldProvenanceSource


def _ready_payload(**overrides):
    base = {
        "decision": "READY_FOR_REVIEW",
        "draft": {
            "title": "회의 정리 도구",
            "one_line_definition": "회의록을 아이디어로 저장",
            "background": None,
            "problem": "회의 내용이 흩어짐",
            "core_concept": "자동 구조화",
            "major_features": None,
            "expected_effect": None,
            "target_users": None,
            "scenarios": None,
            "challenges": None,
            "minimum_validation": None,
            "related_project": None,
            "category_slug": "technology_rd",
            "priority": "MEDIUM",
            "feasibility": "UNKNOWN",
            "tags": ["AI"],
        },
        "field_provenance": {
            "title": {"source": "LLM_SUMMARY", "note": "짧은 제목"},
            "problem": {"source": "USER_INPUT", "note": None},
        },
        "clarifying_questions": [],
        "research_recommended": False,
        "research_topics": [],
    }
    base.update(overrides)
    return base


def test_valid_ready_result() -> None:
    result = IdeaStructuringResult.model_validate(_ready_payload())
    assert result.decision == AiLlmDecision.READY_FOR_REVIEW
    assert result.draft.title == "회의 정리 도구"
    assert result.field_provenance["title"].source == FieldProvenanceSource.LLM_SUMMARY


def test_needs_clarification() -> None:
    payload = _ready_payload(
        decision="NEEDS_CLARIFICATION",
        clarifying_questions=[{"field": "target_users", "question": "누가 쓰나요?"}],
    )
    result = IdeaStructuringResult.model_validate(payload)
    assert result.decision == AiLlmDecision.NEEDS_CLARIFICATION
    assert len(result.clarifying_questions) == 1


def test_invalid_priority_enum() -> None:
    payload = _ready_payload()
    payload["draft"]["priority"] = "URGENT"
    with pytest.raises(Exception):
        IdeaStructuringResult.model_validate(payload)


def test_invalid_json() -> None:
    with pytest.raises(LlmResponseValidationError):
        parse_structuring_result("{not json")


def test_fenced_json() -> None:
    raw = "```json\n" + __import__("json").dumps(_ready_payload()) + "\n```"
    assert strip_json_fence(raw).startswith("{")
    result = parse_structuring_result(raw)
    assert result.decision == AiLlmDecision.READY_FOR_REVIEW


def test_max_clarification_count() -> None:
    qs = [{"field": f"f{i}", "question": f"q{i}?"} for i in range(MAX_CLARIFYING_QUESTIONS + 1)]
    payload = _ready_payload(decision="NEEDS_CLARIFICATION", clarifying_questions=qs)
    with pytest.raises(Exception):
        IdeaStructuringResult.model_validate(payload)


def test_research_topics_truncated() -> None:
    topics = [f"t{i}" for i in range(MAX_RESEARCH_TOPICS + 3)]
    result = IdeaStructuringResult.model_validate(
        _ready_payload(research_recommended=True, research_topics=topics)
    )
    assert len(result.research_topics) == MAX_RESEARCH_TOPICS


def test_web_evidence_provenance_rejected() -> None:
    payload = _ready_payload()
    payload["field_provenance"]["title"] = {"source": "WEB_EVIDENCE", "note": None}
    with pytest.raises(Exception):
        IdeaStructuringResult.model_validate(payload)


def test_ready_with_extra_questions_normalized() -> None:
    payload = _ready_payload(
        clarifying_questions=[{"field": "x", "question": "why?"}],
    )
    result = IdeaStructuringResult.model_validate(payload)
    assert result.decision == AiLlmDecision.READY_FOR_REVIEW
    assert result.clarifying_questions == []


def test_needs_clarification_requires_questions() -> None:
    payload = _ready_payload(decision="NEEDS_CLARIFICATION", clarifying_questions=[])
    with pytest.raises(Exception):
        IdeaStructuringResult.model_validate(payload)


def _insufficient_ready_payload(**overrides) -> dict:
    base = _ready_payload()
    base["draft"] = {
        "title": None,
        "one_line_definition": None,
        "background": None,
        "problem": None,
        "core_concept": None,
        "major_features": None,
        "expected_effect": None,
        "target_users": None,
        "scenarios": None,
        "challenges": None,
        "minimum_validation": None,
        "related_project": None,
        "category_slug": "technology_rd",
        "priority": None,
        "feasibility": None,
        "tags": [],
    }
    base.update(overrides)
    return base


def test_ready_rejects_title_null_with_only_category_slug() -> None:
    with pytest.raises(LlmResponseValidationError):
        parse_structuring_result(__import__("json").dumps(_insufficient_ready_payload()))


def test_ready_rejects_empty_title() -> None:
    payload = _insufficient_ready_payload()
    payload["draft"]["title"] = ""
    with pytest.raises(LlmResponseValidationError):
        parse_structuring_result(__import__("json").dumps(payload))


def test_ready_rejects_whitespace_title() -> None:
    payload = _insufficient_ready_payload()
    payload["draft"]["title"] = "   "
    with pytest.raises(LlmResponseValidationError):
        parse_structuring_result(__import__("json").dumps(payload))


def test_ready_accepts_title_and_one_line_definition() -> None:
    payload = _insufficient_ready_payload()
    payload["draft"]["title"] = "테스트 아이디어"
    payload["draft"]["one_line_definition"] = "한 줄 요약"
    result = parse_structuring_result(__import__("json").dumps(payload))
    assert result.draft.title == "테스트 아이디어"
    assert result.draft.one_line_definition == "한 줄 요약"


def test_ready_accepts_title_and_problem_only() -> None:
    payload = _insufficient_ready_payload()
    payload["draft"]["title"] = "테스트 아이디어"
    payload["draft"]["problem"] = "문제"
    result = parse_structuring_result(__import__("json").dumps(payload))
    assert result.draft.title == "테스트 아이디어"
    assert result.draft.problem == "문제"


def test_ready_rejects_metadata_only_draft() -> None:
    payload = _insufficient_ready_payload()
    payload["draft"]["title"] = "제목만 있음"
    payload["draft"]["priority"] = "HIGH"
    payload["draft"]["tags"] = ["AI", "SaaS"]
    with pytest.raises(LlmResponseValidationError):
        parse_structuring_result(__import__("json").dumps(payload))


def test_needs_clarification_validation_unchanged() -> None:
    payload = _ready_payload(
        decision="NEEDS_CLARIFICATION",
        clarifying_questions=[{"field": "target_users", "question": "누가 쓰나요?"}],
    )
    payload["draft"]["title"] = None
    result = IdeaStructuringResult.model_validate(payload)
    assert result.decision == AiLlmDecision.NEEDS_CLARIFICATION
    assert len(result.clarifying_questions) == 1
