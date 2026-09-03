"""LLM request/response schemas for registered Idea refinement (Step 17)."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.llm.exceptions import LlmError, LlmResponseValidationError
from app.llm.refine_prompts import DIRECTION_PRIORITY_FIELDS
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
    category_slug: str | None = None
    priority: IdeaPriority | None = None
    feasibility: IdeaFeasibility | None = None
    tags: list[str] | None = None

    @field_validator("tags", mode="before")
    @classmethod
    def coerce_tags(cls, value: Any) -> list[str] | None:
        if value is None:
            return None
        if not isinstance(value, list):
            raise ValueError("tags must be a list")
        return [str(t).strip() for t in value if str(t).strip()]


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
    def reject_protected_fields(cls, value: Any) -> Any:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("draft_patch must be an object")
        bad = sorted(set(value.keys()) & _PROTECTED_FIELDS)
        if bad:
            raise ValueError(f"draft_patch includes protected fields: {', '.join(bad)}")
        unknown = sorted(set(value.keys()) - set(REFINE_PATCH_FIELDS))
        if unknown:
            raise ValueError(f"draft_patch includes unknown fields: {', '.join(unknown)}")
        return value

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
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if hasattr(value, "value"):
        return value.value
    return value


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
        if _normalize_comparable(old_val) != _normalize_comparable(new_val):
            changed = True
    if not changed:
        raise ValueError("READY_FOR_REVIEW requires at least one actual change vs source")


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


def prepare_refine_source_context(
    source_snapshot: dict[str, Any],
    *,
    direction: str,
    max_prompt_chars: int,
    max_field_chars: int = 1200,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Select/truncate source fields for prompt budget. Returns (context, meta)."""
    priority = list(DIRECTION_PRIORITY_FIELDS.get(direction, REFINE_PATCH_FIELDS))
    # Ensure always-include fields first, then direction priority, then remaining.
    ordered: list[str] = []
    for key in list(_ALWAYS_INCLUDE) + priority + list(REFINE_PATCH_FIELDS):
        if key in REFINE_PATCH_FIELDS and key not in ordered:
            ordered.append(key)

    context: dict[str, Any] = {"direction": direction}
    truncated_fields: list[str] = []
    included: list[str] = []

    # Reserve space for wrapper / direction guidance overhead.
    used = 400
    for key in ordered:
        if key not in source_snapshot:
            continue
        raw = source_snapshot.get(key)
        if raw is None:
            continue
        if isinstance(raw, str):
            value: Any = raw
            if len(value) > max_field_chars:
                value = value[: max_field_chars - 1] + "…"
                truncated_fields.append(key)
        elif isinstance(raw, list):
            value = raw
        else:
            value = raw
        candidate = dict(context)
        candidate[key] = value
        size = len(json.dumps(candidate, ensure_ascii=False, separators=(",", ":")))
        if used + size > max_prompt_chars and key not in _ALWAYS_INCLUDE:
            continue
        if used + size > max_prompt_chars and key in _ALWAYS_INCLUDE:
            # Still include but truncate further.
            if isinstance(value, str) and len(value) > 200:
                value = value[:199] + "…"
                truncated_fields.append(key)
                candidate[key] = value
                size = len(json.dumps(candidate, ensure_ascii=False, separators=(",", ":")))
        context[key] = value
        included.append(key)
        used = size

    if len(included) < 2:
        raise LlmRefineInputTooLargeError()

    meta = {
        "context_fields": len(included),
        "included_fields": included,
        "truncated_fields": truncated_fields,
        "prompt_chars_estimate": used,
    }
    return context, meta


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
