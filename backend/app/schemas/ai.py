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

    result_idea_id: UUID | None = None
    failure: AiSessionFailurePublic | None = None
    llm: AiSessionLlmPublic

    created_at: datetime
    updated_at: datetime
    ready_at: datetime | None = None
    confirmed_at: datetime | None = None


class AiSessionConfirmResponse(BaseModel):
    created: bool
    idea: IdeaDetail
