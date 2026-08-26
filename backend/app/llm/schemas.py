"""LLM request/response schemas for idea structuring (Pydantic v2)."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.llm.exceptions import LlmResponseValidationError
from app.models.enums import (
    AiLlmDecision,
    FieldProvenanceSource,
    IdeaFeasibility,
    IdeaPriority,
)

MAX_CLARIFYING_QUESTIONS = 3
MAX_RESEARCH_TOPICS = 5

_FENCE_RE = re.compile(r"^```(?:json)?\s*([\s\S]*?)\s*```$", re.IGNORECASE)


class CategoryOption(BaseModel):
    slug: str
    name: str


class IdeaStructuringRequest(BaseModel):
    """Inputs sent to the LLM provider (never log input_text)."""

    input_text: str
    categories: list[CategoryOption] = Field(default_factory=list)
    prior_draft: dict[str, Any] | None = None
    clarifying_questions: list[dict[str, Any]] | None = None
    clarification_answers: list[dict[str, Any]] | None = None


class FieldProvenanceEntry(BaseModel):
    source: FieldProvenanceSource
    note: str | None = None

    @field_validator("source", mode="before")
    @classmethod
    def reject_web_evidence_in_step7(cls, value: Any) -> Any:
        # Step 7 does not run Web Search — LLM must not claim WEB_EVIDENCE.
        if value == FieldProvenanceSource.WEB_EVIDENCE.value or value == FieldProvenanceSource.WEB_EVIDENCE:
            raise ValueError("WEB_EVIDENCE is not allowed without Web Search")
        return value


class IdeaDraftPayload(BaseModel):
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
    tags: list[str] = Field(default_factory=list)

    @field_validator("tags", mode="before")
    @classmethod
    def coerce_tags(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("tags must be a list")
        return [str(t).strip() for t in value if str(t).strip()]


class ClarifyingQuestionRaw(BaseModel):
    field: str | None = None
    question: str = Field(min_length=1, max_length=500)


class IdeaStructuringResult(BaseModel):
    decision: AiLlmDecision
    draft: IdeaDraftPayload
    field_provenance: dict[str, FieldProvenanceEntry] = Field(default_factory=dict)
    clarifying_questions: list[ClarifyingQuestionRaw] = Field(default_factory=list)
    research_recommended: bool = False
    research_topics: list[str] = Field(default_factory=list)

    @field_validator("research_topics", mode="before")
    @classmethod
    def coerce_topics(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("research_topics must be a list")
        topics = [str(t).strip() for t in value if str(t).strip()]
        return topics[:MAX_RESEARCH_TOPICS]

    @model_validator(mode="after")
    def validate_decision_shape(self) -> IdeaStructuringResult:
        if len(self.clarifying_questions) > MAX_CLARIFYING_QUESTIONS:
            raise ValueError(f"clarifying_questions max is {MAX_CLARIFYING_QUESTIONS}")
        if self.decision == AiLlmDecision.NEEDS_CLARIFICATION:
            if not self.clarifying_questions:
                raise ValueError("NEEDS_CLARIFICATION requires at least one question")
        if self.decision == AiLlmDecision.READY_FOR_REVIEW:
            # Questions may be empty; if present, ignore is not allowed — reject extras.
            if self.clarifying_questions:
                raise ValueError("READY_FOR_REVIEW must not include clarifying_questions")
        return self


def strip_json_fence(text: str) -> str:
    stripped = text.strip()
    match = _FENCE_RE.match(stripped)
    if match:
        return match.group(1).strip()
    return stripped


def parse_structuring_result(content: str) -> IdeaStructuringResult:
    """Parse LLM content into a validated structuring result.

    Allows optional Markdown ```json fences. Does not invent missing fields
    or repair broken JSON.
    """
    cleaned = strip_json_fence(content)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LlmResponseValidationError("LLM response is not valid JSON") from exc
    if not isinstance(data, dict):
        raise LlmResponseValidationError("LLM response must be a JSON object")
    try:
        return IdeaStructuringResult.model_validate(data)
    except Exception as exc:  # noqa: BLE001 — map any pydantic/validation failure
        raise LlmResponseValidationError("LLM response failed schema validation") from exc
