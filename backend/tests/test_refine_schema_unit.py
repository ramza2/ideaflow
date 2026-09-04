"""Unit tests for Step 17 REFINE schemas, typed patches, and prompt budget."""

from __future__ import annotations

import logging

import pytest

from app.llm.exceptions import LlmResponseValidationError
from app.llm.refine_schemas import (
    IdeaRefinementResult,
    LlmRefineInputTooLargeError,
    merge_refinement_patch,
    merged_draft_differs_from_source,
    parse_refinement_result,
    prepare_refine_prompt_request,
    prepare_refine_source_context,
    refine_prompt_char_counts,
    validate_refinement_against_source,
)
from app.models.enums import AiLlmDecision, IdeaRefineDirection


def test_all_refine_directions_are_valid() -> None:
    assert {d.value for d in IdeaRefineDirection} == {
        "EXPAND_DETAIL",
        "TECHNICAL_IMPLEMENTATION",
        "BUSINESS_PERSPECTIVE",
        "USER_PERSPECTIVE",
        "COUNTER_PERSPECTIVE",
        "RISK_ANALYSIS",
        "MINIMUM_VALIDATION",
        "NEXT_ACTIONS",
    }


def test_unknown_direction_rejected_by_request() -> None:
    from app.llm.refine_schemas import IdeaRefinementRequest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        IdeaRefinementRequest(direction="NOT_A_DIRECTION", source_context={"title": "t"})


def test_invalid_priority_rejected() -> None:
    with pytest.raises(LlmResponseValidationError):
        parse_refinement_result(
            '{"decision":"READY_FOR_REVIEW","draft_patch":{"priority":"SUPER_HIGH"}}'
        )


def test_invalid_feasibility_rejected() -> None:
    with pytest.raises(LlmResponseValidationError):
        parse_refinement_result(
            '{"decision":"READY_FOR_REVIEW","draft_patch":{"feasibility":"IMPOSSIBLE"}}'
        )


def test_tags_object_rejected() -> None:
    with pytest.raises(LlmResponseValidationError):
        parse_refinement_result(
            '{"decision":"READY_FOR_REVIEW","draft_patch":{"tags":{"bad":"shape"}}}'
        )


def test_overlong_title_rejected() -> None:
    with pytest.raises(LlmResponseValidationError):
        parse_refinement_result(
            '{"decision":"READY_FOR_REVIEW","draft_patch":{"title":"' + ("x" * 201) + '"}}'
        )


def test_overlong_category_slug_rejected() -> None:
    with pytest.raises(LlmResponseValidationError):
        parse_refinement_result(
            '{"decision":"READY_FOR_REVIEW","draft_patch":{"category_slug":"'
            + ("c" * 65)
            + '"}}'
        )


def test_sparse_one_field_patch_passes() -> None:
    result = parse_refinement_result(
        '{"decision":"READY_FOR_REVIEW","draft_patch":{"core_concept":"새 개념"}}'
    )
    assert result.draft_patch == {"core_concept": "새 개념"}
    validate_refinement_against_source(
        result,
        source_snapshot={"core_concept": "옛 개념", "title": "T"},
    )


def test_protected_field_rejected() -> None:
    with pytest.raises(LlmResponseValidationError):
        parse_refinement_result(
            '{"decision":"READY_FOR_REVIEW","draft_patch":{"visibility":"WORKSPACE"}}'
        )


def test_empty_patch_ready_rejected() -> None:
    with pytest.raises(LlmResponseValidationError):
        parse_refinement_result('{"decision":"READY_FOR_REVIEW","draft_patch":{}}')


def test_identical_patch_vs_source_rejected() -> None:
    result = parse_refinement_result(
        '{"decision":"READY_FOR_REVIEW","draft_patch":{"core_concept":"same"}}'
    )
    with pytest.raises(ValueError, match="actual change"):
        validate_refinement_against_source(
            result,
            source_snapshot={"core_concept": "same"},
        )


def test_clearing_nonempty_field_rejected() -> None:
    result = parse_refinement_result(
        '{"decision":"READY_FOR_REVIEW","draft_patch":{"problem":""}}'
    )
    with pytest.raises(ValueError, match="cannot clear"):
        validate_refinement_against_source(
            result,
            source_snapshot={"problem": "기존 문제"},
        )


def test_blank_string_vs_null_is_semantic_noop() -> None:
    result = parse_refinement_result(
        '{"decision":"READY_FOR_REVIEW","draft_patch":{"background":""}}'
    )
    with pytest.raises(ValueError, match="actual change"):
        validate_refinement_against_source(
            result,
            source_snapshot={"background": None, "title": "T"},
        )
    merged = merge_refinement_patch({"background": None, "title": "T"}, result.draft_patch)
    assert merged_draft_differs_from_source({"background": None, "title": "T"}, merged) is False


def test_tag_order_only_change_is_semantic_noop() -> None:
    result = parse_refinement_result(
        '{"decision":"READY_FOR_REVIEW","draft_patch":{"tags":["B","A"]}}'
    )
    with pytest.raises(ValueError, match="actual change"):
        validate_refinement_against_source(
            result,
            source_snapshot={"tags": ["A", "B"], "title": "T"},
        )


def test_tag_duplicate_only_change_is_semantic_noop() -> None:
    result = parse_refinement_result(
        '{"decision":"READY_FOR_REVIEW","draft_patch":{"tags":["A","A"]}}'
    )
    with pytest.raises(ValueError, match="actual change"):
        validate_refinement_against_source(
            result,
            source_snapshot={"tags": ["A"], "title": "T"},
        )


def test_tags_object_element_rejected() -> None:
    with pytest.raises(LlmResponseValidationError):
        parse_refinement_result(
            '{"decision":"READY_FOR_REVIEW","draft_patch":{"tags":[{"bad":1}]}}'
        )


def test_tags_number_elements_rejected() -> None:
    with pytest.raises(LlmResponseValidationError):
        parse_refinement_result(
            '{"decision":"READY_FOR_REVIEW","draft_patch":{"tags":[1,2]}}'
        )


def test_tags_string_normalization() -> None:
    result = parse_refinement_result(
        '{"decision":"READY_FOR_REVIEW","draft_patch":{"tags":[" A ","B",""]}}'
    )
    assert result.draft_patch["tags"] == ["A", "B"]
    validate_refinement_against_source(
        result,
        source_snapshot={"tags": ["X"], "title": "T"},
    )


def test_merged_draft_no_effective_change_after_category_sanitize() -> None:
    source = {
        "title": "T",
        "one_line_definition": "O",
        "category_slug": "product_service",
        "core_concept": "C",
        "tags": [],
    }
    patch = {"category_slug": "does_not_exist"}
    merged = merge_refinement_patch(source, patch)
    # Simulate sanitize restoring source category.
    merged["category_slug"] = source["category_slug"]
    assert merged_draft_differs_from_source(source, merged) is False


def test_prompt_budget_normal_source_within_max() -> None:
    snapshot = {
        "title": "회의록 도우미",
        "one_line_definition": "요약을 구조화한다",
        "core_concept": "파이프라인",
        "problem": "수동 정리",
    }
    _req, meta = prepare_refine_prompt_request(
        direction="EXPAND_DETAIL",
        source_snapshot=snapshot,
        max_prompt_chars=5500,
    )
    assert meta["total_prompt_chars"] <= 5500
    assert meta["system_chars"] + meta["user_prompt_chars"] == meta["total_prompt_chars"]


def test_prompt_budget_truncates_long_fields() -> None:
    snapshot = {
        "title": "T",
        "one_line_definition": "O",
        "core_concept": "개념 " * 2000,
        "major_features": "기능 " * 2000,
        "challenges": "난제 " * 2000,
        "scenarios": "시나리오 " * 2000,
    }
    _req, meta = prepare_refine_prompt_request(
        direction="TECHNICAL_IMPLEMENTATION",
        source_snapshot=snapshot,
        max_prompt_chars=5500,
        max_field_chars=400,
    )
    assert meta["total_prompt_chars"] <= 5500
    assert meta["truncated_fields"] or meta["context_fields"] < 6


def test_prompt_budget_includes_clarification_qa() -> None:
    snapshot = {"title": "T", "one_line_definition": "O", "core_concept": "C"}
    questions = [{"id": "q1", "field": "target_users", "question": "사용자는?"}]
    answers = [{"question_id": "q1", "answer": "프로덕트 팀"}]
    empty_total = refine_prompt_char_counts(
        direction="USER_PERSPECTIVE",
        source_context={},
        clarifying_questions=questions,
        clarification_answers=answers,
    )[2]
    with_context_total = refine_prompt_char_counts(
        direction="USER_PERSPECTIVE",
        source_context=snapshot,
        clarifying_questions=questions,
        clarification_answers=answers,
    )[2]
    assert with_context_total > empty_total

    _req, meta = prepare_refine_prompt_request(
        direction="USER_PERSPECTIVE",
        source_snapshot=snapshot,
        clarifying_questions=questions,
        clarification_answers=answers,
        max_prompt_chars=5500,
    )
    assert meta["total_prompt_chars"] <= 5500
    # Rebuild exact user prompt from request must match budgeted size.
    rebuilt = refine_prompt_char_counts(
        direction="USER_PERSPECTIVE",
        source_context=_req.source_context,
        clarifying_questions=questions,
        clarification_answers=answers,
    )
    assert rebuilt[2] == meta["total_prompt_chars"]


def test_prompt_budget_rejects_when_qa_alone_exceeds_max() -> None:
    huge_answer = "답변" * 5000
    with pytest.raises(LlmRefineInputTooLargeError):
        prepare_refine_prompt_request(
            direction="EXPAND_DETAIL",
            source_snapshot={"title": "T", "one_line_definition": "O"},
            clarifying_questions=[{"id": "q1", "question": "Q?"}],
            clarification_answers=[{"question_id": "q1", "answer": huge_answer}],
            max_prompt_chars=5500,
        )


def test_prompt_budget_logs_metadata_not_raw_content(caplog: pytest.LogCaptureFixture) -> None:
    secret = "SECRET_SOURCE_BODY_SHOULD_NOT_APPEAR"
    snapshot = {
        "title": "T",
        "one_line_definition": "O",
        "core_concept": secret,
    }
    with caplog.at_level(logging.INFO):
        _ctx, meta = prepare_refine_source_context(
            snapshot,
            direction="EXPAND_DETAIL",
            max_prompt_chars=5500,
        )
    joined = " ".join(r.message for r in caplog.records)
    assert secret not in joined
    assert "total_prompt_chars" in meta
    assert meta["total_prompt_chars"] <= 5500


def test_ready_result_rejects_unset_null_injection_for_sparse_semantics() -> None:
    result = IdeaRefinementResult.model_validate(
        {"decision": "READY_FOR_REVIEW", "draft_patch": {"major_features": "F1"}}
    )
    assert "background" not in result.draft_patch
    assert set(result.draft_patch.keys()) == {"major_features"}
