"""AI Session API schemas (Step 7)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import (
    IdeaAiSessionPurpose,
    IdeaAiSessionStatus,
    IdeaFeasibility,
    IdeaPriority,
    IdeaRefineDirection,
    IdeaSharePermission,
    IdeaVisibility,
)
from app.schemas.idea import IdeaDetail, IdeaShareInput


class AiSessionCreate(BaseModel):
    purpose: IdeaAiSessionPurpose = IdeaAiSessionPurpose.CREATE
    input_text: str = Field(min_length=1, max_length=20000)

    @field_validator("input_text")
    @classmethod
    def strip_input(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("input_text must not be empty")
        if len(stripped) > 20000:
            raise ValueError("input_text too long")
        return stripped

    @field_validator("purpose")
    @classmethod
    def create_only(cls, value: IdeaAiSessionPurpose) -> IdeaAiSessionPurpose:
        if value != IdeaAiSessionPurpose.CREATE:
            raise ValueError("Only purpose=CREATE is supported in this step")
        return value


class AiRefineSessionCreate(BaseModel):
    """Start an AI refinement session on an already-registered Idea (Step 17)."""

    direction: IdeaRefineDirection


class ClarificationAnswerInput(BaseModel):
    question_id: str = Field(min_length=1, max_length=64)
    answer: str = Field(min_length=1, max_length=5000)

    @field_validator("answer")
    @classmethod
    def strip_answer(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("answer must not be empty")
        return stripped


class ClarificationSubmit(BaseModel):
    answers: list[ClarificationAnswerInput] = Field(min_length=1)


class AiSessionReviewDraftBody(BaseModel):
    """Reviewed draft fields stored in IdeaAiSession.draft_payload."""

    title: str = Field(default="", max_length=200)
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
    priority: IdeaPriority = IdeaPriority.MEDIUM
    feasibility: IdeaFeasibility = IdeaFeasibility.UNKNOWN
    tags: list[str] = Field(default_factory=list)

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()[:200]

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for tag in value:
            cleaned = tag.strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            out.append(cleaned[:64])
        return out


class AiSessionReviewStateInput(BaseModel):
    category_id: UUID | None = None
    stage_id: UUID | None = None
    visibility: IdeaVisibility = IdeaVisibility.PRIVATE
    assignee_id: UUID | None = None
    next_review_date: date | None = None
    shares: list[IdeaShareInput] = Field(default_factory=list)
    edited_fields: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def no_duplicate_share_users(self) -> AiSessionReviewStateInput:
        ids = [s.user_id for s in self.shares]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate share user_id")
        return self

    @field_validator("edited_fields")
    @classmethod
    def normalize_edited_fields(cls, value: list[str]) -> list[str]:
        allowed = {
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
        }
        seen: set[str] = set()
        out: list[str] = []
        for item in value:
            field = item.strip()
            if not field or field not in allowed or field in seen:
                continue
            seen.add(field)
            out.append(field)
        return out


class AiSessionReviewDraftSaveRequest(BaseModel):
    draft: AiSessionReviewDraftBody
    review_state: AiSessionReviewStateInput


class AiSessionRegenerateResponse(BaseModel):
    session: "AiSessionPublic"


class AiSessionConfirmRequest(BaseModel):
    """User-reviewed idea fields. original_text is taken from the session input."""

    title: str = Field(min_length=1, max_length=200)
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

    category_id: UUID | None = None
    stage_id: UUID | None = None

    priority: IdeaPriority = IdeaPriority.MEDIUM
    feasibility: IdeaFeasibility = IdeaFeasibility.UNKNOWN
    visibility: IdeaVisibility = IdeaVisibility.PRIVATE

    assignee_id: UUID | None = None
    next_review_date: date | None = None

    tags: list[str] = Field(default_factory=list)
    shares: list[IdeaShareInput] | None = None

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("title must not be empty")
        return stripped

    @model_validator(mode="after")
    def no_duplicate_share_users(self) -> AiSessionConfirmRequest:
        if self.shares:
            ids = [s.user_id for s in self.shares]
            if len(ids) != len(set(ids)):
                raise ValueError("duplicate share user_id")
        return self


class AiRefineApplyRequest(BaseModel):
    """User-reviewed refinement applied to the source Idea.

    Excludes stage/visibility/assignee/next_review_date/shares — refinement
    never changes workflow or ACL fields of the registered Idea.
    """

    title: str = Field(min_length=1, max_length=200)
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

    category_id: UUID | None = None

    priority: IdeaPriority = IdeaPriority.MEDIUM
    feasibility: IdeaFeasibility = IdeaFeasibility.UNKNOWN

    tags: list[str] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("title must not be empty")
        return stripped


class AiSessionFailurePublic(BaseModel):
    code: str
    message: str


class AiSessionLlmPublic(BaseModel):
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None


class AiSessionPublic(BaseModel):
    id: UUID
    workspace_id: UUID
    purpose: IdeaAiSessionPurpose
    status: IdeaAiSessionStatus

    input_text: str

    draft: dict[str, Any] | None = None
    field_provenance: dict[str, Any] | None = None
    clarifying_questions: list[dict[str, Any]] | None = None
    clarification_answers: list[dict[str, Any]] | None = None

    research_recommended: bool = False
    research_topics: list[str] | None = None

    review_state: dict[str, Any] | None = None
    review_saved_at: datetime | None = None

    result_idea_id: UUID | None = None
    failure: AiSessionFailurePublic | None = None
    llm: AiSessionLlmPublic

    source_idea_id: UUID | None = None
    source_idea_updated_at: datetime | None = None
    source_idea_snapshot: dict[str, Any] | None = None
    refine_direction: IdeaRefineDirection | None = None

    created_at: datetime
    updated_at: datetime
    ready_at: datetime | None = None
    confirmed_at: datetime | None = None


class AiSessionConfirmResponse(BaseModel):
    created: bool
    idea: IdeaDetail


class AiRefineApplyResponse(BaseModel):
    updated: bool
    idea: IdeaDetail
