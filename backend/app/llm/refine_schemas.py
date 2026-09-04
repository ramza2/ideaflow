"""LLM request/response schemas for registered Idea refinement (Step 17)."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.llm.exceptions import LlmError, LlmResponseValidationError
from app.llm.refine_prompts import (
    DIRECTION_PRIORITY_FIELDS,
    REFINE_SYSTEM_PROMPT,
    build_refine_user_prompt,
)
from app.llm.schemas import ClarifyingQuestionRaw, FieldProvenanceEntry, MAX_CLARIFYING_QUESTIONS, MAX_RESEARCH_TOPICS
from app.models.enums import AiLlmDecision, IdeaFeasibility, IdeaPriority, IdeaRefineDirection

REFINE_PATCH_FIELDS = (
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
    "category_slug",
    "priority",
    "feasibility",
    "tags",
)

_PROTECTED_FIELDS = frozenset(
    {
        "stage_id",
        "visibility",
        "shares",
        "assignee_id",
        "next_review_date",
        "author",
        "idea_code",
        "original_text",
        "workspace_id",
    }
)

_FENCE_RE = re.compile(r"^```(?:json)?\s*([\s\S]*?)\s*```$", re.IGNORECASE)

_ALWAYS_INCLUDE = ("title", "one_line_definition")


class LlmRefineInputTooLargeError(LlmError):
    code = "AI_REFINE_INPUT_TOO_LARGE"
    retryable = False
    safe_message = (
        "현재 아이디어가 너무 길어 AI로 발전시킬 수 없습니다. "
        "내용을 일부 줄인 후 다시 시도해 주세요."
    )


class IdeaRefinementRequest(BaseModel):
    """Inputs sent to the LLM for idea refinement (never log source content)."""

    direction: IdeaRefineDirection
    source_context: dict[str, Any]
    clarifying_questions: list[dict[str, Any]] | None = None
    clarification_answers: list[dict[str, Any]] | None = None


class IdeaRefinementPatch(BaseModel):
    """Sparse patch of editable idea fields."""

    title: str | None = Field(default=None, max_length=200)
    one_line_definition: str | None = Field(default=None, max_length=500)
    background: str | None = None
    problem: str | None = None
    core_concept: str | None = None
    major_features: str | None = None
    expected_effect: str | None = None
    target_users: str | None = None
    scenarios: str | None = None
    challenges: str | None = None
    minimum_validation: str | None = None
    related_project: str | None = None
    category_slug: str | None = Field(default=None, max_length=64)
    priority: IdeaPriority | None = None
    feasibility: IdeaFeasibility | None = None
    tags: list[str] | None = None

    @field_validator("title")
    @classmethod
    def title_nonempty_when_set(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("title must be non-empty when supplied")
        return cleaned

    @field_validator("one_line_definition")
    @classmethod
    def strip_one_line(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()

    @field_validator("category_slug")
    @classmethod
    def strip_category_slug(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("tags", mode="before")
    @classmethod
    def coerce_tags(cls, value: Any) -> list[str] | None:
        if value is None:
            return None
        if not isinstance(value, list):
            raise ValueError("tags must be a list")
        # Match Idea tag rules: string elements only, trim, drop blanks, dedupe.
        # Do not stringify objects/numbers into tag names.
        seen: set[str] = set()
        normalized: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError("tags elements must be strings")
            name = item.strip()
            if not name:
                continue
            if len(name) > 64:
                raise ValueError("tag name must be at most 64 characters")
            if name in seen:
                continue
            seen.add(name)
            normalized.append(name)
        if len(normalized) > 20:
            raise ValueError("at most 20 tags are allowed")
        return normalized


def _typed_sparse_patch(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate patch values via IdeaRefinementPatch while keeping sparse keys."""
    bad = sorted(set(raw.keys()) & _PROTECTED_FIELDS)
    if bad:
        raise ValueError(f"draft_patch includes protected fields: {', '.join(bad)}")
    unknown = sorted(set(raw.keys()) - set(REFINE_PATCH_FIELDS))
    if unknown:
        raise ValueError(f"draft_patch includes unknown fields: {', '.join(unknown)}")
    patch = IdeaRefinementPatch.model_validate(raw)
    return patch.model_dump(mode="json", exclude_unset=True)


class IdeaRefinementResult(BaseModel):
    decision: AiLlmDecision
    draft_patch: dict[str, Any] = Field(default_factory=dict)
    field_provenance: dict[str, FieldProvenanceEntry] = Field(default_factory=dict)
    clarifying_questions: list[ClarifyingQuestionRaw] = Field(default_factory=list)
    research_recommended: bool = False
    research_topics: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_ready_questions(cls, value: Any) -> Any:
        if isinstance(value, dict) and value.get("decision") == AiLlmDecision.READY_FOR_REVIEW.value:
            data = dict(value)
            data["clarifying_questions"] = []
            return data
        return value

    @field_validator("research_topics", mode="before")
    @classmethod
    def coerce_topics(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("research_topics must be a list")
        topics = [str(t).strip() for t in value if str(t).strip()]
        return topics[:MAX_RESEARCH_TOPICS]

    @field_validator("draft_patch", mode="before")
    @classmethod
    def validate_typed_patch(cls, value: Any) -> Any:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("draft_patch must be an object")
        return _typed_sparse_patch(value)

    @model_validator(mode="after")
    def validate_decision_shape(self) -> IdeaRefinementResult:
        if len(self.clarifying_questions) > MAX_CLARIFYING_QUESTIONS:
            raise ValueError(f"clarifying_questions max is {MAX_CLARIFYING_QUESTIONS}")
        if self.decision == AiLlmDecision.NEEDS_CLARIFICATION:
            if not self.clarifying_questions:
                raise ValueError("NEEDS_CLARIFICATION requires at least one question")
        if self.decision == AiLlmDecision.READY_FOR_REVIEW:
            if self.clarifying_questions:
                raise ValueError("READY_FOR_REVIEW must not include clarifying_questions")
            if not self.draft_patch:
                raise ValueError("READY_FOR_REVIEW requires a non-empty draft_patch")
        return self


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _normalize_comparable(value: Any) -> Any:
    """Canonical semantic equality used by Worker and aligned with apply/FE.

    - blank/whitespace strings ≡ None
    - lists ≡ trim + drop blanks + dedupe + sort
    """
    if hasattr(value, "value"):
        value = value.value
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    if isinstance(value, list):
        return sorted({str(v).strip() for v in value if str(v).strip()})
    return value


def _field_comparable(key: str, value: Any) -> Any:
    """Per-field comparable form (tags: None ≡ [])."""
    if key == "tags" and value is None:
        value = []
    return _normalize_comparable(value)


def validate_refinement_against_source(
    result: IdeaRefinementResult,
    *,
    source_snapshot: dict[str, Any],
) -> None:
    """Reject empty/noop/destructive READY patches relative to source snapshot."""
    if result.decision != AiLlmDecision.READY_FOR_REVIEW:
        return
    if not result.draft_patch:
        raise ValueError("READY_FOR_REVIEW requires a non-empty draft_patch")

    changed = False
    for key, new_val in result.draft_patch.items():
        if key not in REFINE_PATCH_FIELDS:
            raise ValueError(f"unsupported patch field: {key}")
        old_val = source_snapshot.get(key)
        if key == "title" and not _is_nonempty_string(new_val):
            raise ValueError("title patch must be non-empty")
        # Reject clearing previously non-empty string fields.
        if key != "tags" and _is_nonempty_string(old_val):
            if new_val is None or (isinstance(new_val, str) and not new_val.strip()):
                raise ValueError(f"cannot clear non-empty field: {key}")
        if _field_comparable(key, old_val) != _field_comparable(key, new_val):
            changed = True
    if not changed:
        raise ValueError("READY_FOR_REVIEW requires at least one actual change vs source")


def merged_draft_differs_from_source(
    source_snapshot: dict[str, Any],
    merged_draft: dict[str, Any],
) -> bool:
    """True when sanitized/merged draft still differs from the source snapshot."""
    for key in REFINE_PATCH_FIELDS:
        if _field_comparable(key, source_snapshot.get(key)) != _field_comparable(
            key, merged_draft.get(key)
        ):
            return True
    return False


def merge_refinement_patch(
    source_snapshot: dict[str, Any],
    draft_patch: dict[str, Any],
) -> dict[str, Any]:
    """Merge sparse patch onto source snapshot for a full draft_payload."""
    merged = {k: source_snapshot.get(k) for k in REFINE_PATCH_FIELDS}
    # Normalize tags default
    if merged.get("tags") is None:
        merged["tags"] = []
    for key, value in draft_patch.items():
        if key not in REFINE_PATCH_FIELDS:
            continue
        if key == "priority" and hasattr(value, "value"):
            merged[key] = value.value
        elif key == "feasibility" and hasattr(value, "value"):
            merged[key] = value.value
        else:
            merged[key] = value
    if isinstance(merged.get("tags"), list):
        merged["tags"] = [str(t).strip() for t in merged["tags"] if str(t).strip()]
    else:
        merged["tags"] = []
    return merged


def strip_json_fence(text: str) -> str:
    stripped = text.strip()
    match = _FENCE_RE.match(stripped)
    if match:
        return match.group(1).strip()
    return stripped


def parse_refinement_result(content: str) -> IdeaRefinementResult:
    cleaned = strip_json_fence(content)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LlmResponseValidationError("LLM response is not valid JSON") from exc
    if not isinstance(data, dict):
        raise LlmResponseValidationError("LLM response must be a JSON object")
    try:
        return IdeaRefinementResult.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        raise LlmResponseValidationError("LLM response failed schema validation") from exc


def _field_char_len(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (dict, list)):
        return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    return len(str(value))


def refine_prompt_char_counts(
    *,
    direction: str,
    source_context: dict[str, Any],
    clarifying_questions: list[dict[str, Any]] | None = None,
    clarification_answers: list[dict[str, Any]] | None = None,
) -> tuple[int, int, int]:
    """Exact system + user prompt sizes used by the OpenAI-compatible provider."""
    system_chars = len(REFINE_SYSTEM_PROMPT)
    user_prompt_chars = len(
        build_refine_user_prompt(
            direction=direction,
            source_context=source_context,
            clarifying_questions=clarifying_questions,
            clarification_answers=clarification_answers,
        )
    )
    return system_chars, user_prompt_chars, system_chars + user_prompt_chars


def _truncate_field_value(raw: Any, *, max_field_chars: int) -> tuple[Any, bool]:
    if isinstance(raw, str) and len(raw) > max_field_chars:
        return raw[: max_field_chars - 1] + "…", True
    return raw, False


def prepare_refine_source_context(
    source_snapshot: dict[str, Any],
    *,
    direction: str,
    max_prompt_chars: int,
    max_field_chars: int = 1200,
    clarifying_questions: list[dict[str, Any]] | None = None,
    clarification_answers: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Select/truncate source fields so system + user prompt (incl. Q/A) fit budget.

    Returns (source_context, meta). Raises LlmRefineInputTooLargeError when even a
    minimal prompt exceeds max_prompt_chars.
    """
    empty_system, empty_user, empty_total = refine_prompt_char_counts(
        direction=direction,
        source_context={},
        clarifying_questions=clarifying_questions,
        clarification_answers=clarification_answers,
    )
    if empty_total > max_prompt_chars:
        raise LlmRefineInputTooLargeError()

    priority = list(DIRECTION_PRIORITY_FIELDS.get(direction, REFINE_PATCH_FIELDS))
    ordered: list[str] = []
    for key in list(_ALWAYS_INCLUDE) + priority + list(REFINE_PATCH_FIELDS):
        if key in REFINE_PATCH_FIELDS and key not in ordered:
            ordered.append(key)

    context: dict[str, Any] = {}
    truncated_fields: list[str] = []
    included: list[str] = []

    for key in ordered:
        if key not in source_snapshot:
            continue
        raw = source_snapshot.get(key)
        if raw is None:
            continue
        value, was_truncated = _truncate_field_value(raw, max_field_chars=max_field_chars)
        candidate = dict(context)
        candidate[key] = value
        _sys, _user, total = refine_prompt_char_counts(
            direction=direction,
            source_context=candidate,
            clarifying_questions=clarifying_questions,
            clarification_answers=clarification_answers,
        )
        if total > max_prompt_chars:
            if key not in _ALWAYS_INCLUDE:
                continue
            # Always-include fields: shrink further until they fit or give up.
            if isinstance(value, str):
                fitted = False
                for limit in (200, 80, 40, 16):
                    shrunk = value[: limit - 1] + "…" if len(value) > limit else value
                    trial = dict(context)
                    trial[key] = shrunk
                    _s, _u, trial_total = refine_prompt_char_counts(
                        direction=direction,
                        source_context=trial,
                        clarifying_questions=clarifying_questions,
                        clarification_answers=clarification_answers,
                    )
                    if trial_total <= max_prompt_chars:
                        context[key] = shrunk
                        included.append(key)
                        truncated_fields.append(key)
                        fitted = True
                        break
                if not fitted:
                    raise LlmRefineInputTooLargeError()
            else:
                raise LlmRefineInputTooLargeError()
            continue

        context[key] = value
        included.append(key)
        if was_truncated:
            truncated_fields.append(key)

    if len(included) < 1 or (
        "title" not in included and "one_line_definition" not in included and not context
    ):
        # Require at least one content field when the snapshot had any.
        has_source_content = any(
            source_snapshot.get(k) is not None for k in REFINE_PATCH_FIELDS
        )
        if has_source_content and not included:
            raise LlmRefineInputTooLargeError()

    system_chars, user_prompt_chars, total_prompt_chars = refine_prompt_char_counts(
        direction=direction,
        source_context=context,
        clarifying_questions=clarifying_questions,
        clarification_answers=clarification_answers,
    )
    if total_prompt_chars > max_prompt_chars:
        raise LlmRefineInputTooLargeError()

    meta = {
        "context_fields": len(included),
        "included_fields": included,
        "truncated_fields": truncated_fields,
        "system_chars": system_chars,
        "user_prompt_chars": user_prompt_chars,
        "total_prompt_chars": total_prompt_chars,
        # Backward-compatible alias — total only, never source-context-only.
        "prompt_chars_estimate": total_prompt_chars,
        "empty_prompt_chars": empty_total,
        "empty_system_chars": empty_system,
        "empty_user_chars": empty_user,
    }
    return context, meta


def prepare_refine_prompt_request(
    *,
    direction: str,
    source_snapshot: dict[str, Any],
    clarifying_questions: list[dict[str, Any]] | None = None,
    clarification_answers: list[dict[str, Any]] | None = None,
    max_prompt_chars: int,
    max_field_chars: int = 1200,
) -> tuple[IdeaRefinementRequest, dict[str, Any]]:
    """Build a budgeted IdeaRefinementRequest using exact system+user lengths."""
    source_context, meta = prepare_refine_source_context(
        source_snapshot,
        direction=direction,
        max_prompt_chars=max_prompt_chars,
        max_field_chars=max_field_chars,
        clarifying_questions=clarifying_questions,
        clarification_answers=clarification_answers,
    )
    request = IdeaRefinementRequest(
        direction=direction,
        source_context=source_context,
        clarifying_questions=clarifying_questions,
        clarification_answers=clarification_answers,
    )
    return request, meta


def build_idea_source_snapshot(idea: Any, *, category_slug: str | None) -> dict[str, Any]:
    """Build AI-facing snapshot from an Idea ORM row (no secrets)."""
    tags = []
    if getattr(idea, "tags", None):
        tags = [t.tag for t in idea.tags if getattr(t, "tag", None)]
    return {
        "title": idea.title,
        "one_line_definition": idea.one_line_definition,
        "background": idea.background,
        "problem": idea.problem,
        "core_concept": idea.core_concept,
        "major_features": idea.major_features,
        "expected_effect": idea.expected_effect,
        "target_users": idea.target_users,
        "scenarios": idea.scenarios,
        "challenges": idea.challenges,
        "minimum_validation": idea.minimum_validation,
        "related_project": idea.related_project,
        "category_slug": category_slug,
        "priority": idea.priority,
        "feasibility": idea.feasibility,
        "tags": tags,
    }
