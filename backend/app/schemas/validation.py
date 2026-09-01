"""Idea Validation API schemas (Step 14)."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.enums import IdeaValidationOutcome, IdeaValidationStatus


class UserRef(BaseModel):
    id: UUID
    name: str
    email: str


class StageRef(BaseModel):
    id: UUID
    label: str
    slug: str | None = None


class IdeaValidationPublic(BaseModel):
    id: UUID
    idea_id: UUID
    title: str
    hypothesis: str
    method: str
    success_criteria: str
    planned_evidence: str | None = None
    status: IdeaValidationStatus
    outcome: IdeaValidationOutcome | None = None
    result_summary: str | None = None
    evidence_summary: str | None = None
    due_date: date | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_by: UserRef
    created_at: datetime
    updated_at: datetime


class IdeaValidationListResponse(BaseModel):
    items: list[IdeaValidationPublic]
    total: int


class IdeaValidationCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    hypothesis: str = Field(min_length=1, max_length=10000)
    method: str = Field(min_length=1, max_length=10000)
    success_criteria: str = Field(min_length=1, max_length=10000)
    planned_evidence: str | None = Field(default=None, max_length=10000)
    due_date: date | None = None

    @field_validator("title", "hypothesis", "method", "success_criteria", mode="before")
    @classmethod
    def strip_required(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("planned_evidence", mode="before")
    @classmethod
    def strip_optional(cls, value: object) -> object:
        if isinstance(value, str):
            text = value.strip()
            return text or None
        return value


class IdeaValidationUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    hypothesis: str | None = Field(default=None, min_length=1, max_length=10000)
    method: str | None = Field(default=None, min_length=1, max_length=10000)
    success_criteria: str | None = Field(default=None, min_length=1, max_length=10000)
    planned_evidence: str | None = Field(default=None, max_length=10000)
    due_date: date | None = None

    @field_validator("title", "hypothesis", "method", "success_criteria", mode="before")
    @classmethod
    def strip_required_optional(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("planned_evidence", mode="before")
    @classmethod
    def strip_optional(cls, value: object) -> object:
        if isinstance(value, str):
            text = value.strip()
            return text or None
        return value


class IdeaValidationCompleteRequest(BaseModel):
    outcome: IdeaValidationOutcome
    result_summary: str = Field(min_length=1, max_length=10000)
    evidence_summary: str | None = Field(default=None, max_length=10000)

    @field_validator("result_summary", mode="before")
    @classmethod
    def strip_required(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("evidence_summary", mode="before")
    @classmethod
    def strip_optional(cls, value: object) -> object:
        if isinstance(value, str):
            text = value.strip()
            return text or None
        return value


class IdeaValidationStartResponse(BaseModel):
    validation: IdeaValidationPublic
    idea_stage: StageRef
