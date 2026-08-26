"""Idea schemas (Pydantic v2)."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.enums import IdeaFeasibility, IdeaPriority, IdeaSharePermission, IdeaVisibility


class IdeaShareInput(BaseModel):
    user_id: UUID
    permission: IdeaSharePermission


class IdeaShareReplace(BaseModel):
    shares: list[IdeaShareInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def no_duplicate_users(self) -> IdeaShareReplace:
        ids = [s.user_id for s in self.shares]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate share user_id")
        return self


class IdeaSharePublic(BaseModel):
    user_id: UUID
    name: str
    permission: str


class IdeaUserPublic(BaseModel):
    id: UUID
    name: str

    model_config = {"from_attributes": True}


class TagPublic(BaseModel):
    id: UUID
    name: str

    model_config = {"from_attributes": True}


class StageRef(BaseModel):
    id: UUID
    slug: str
    label: str

    model_config = {"from_attributes": True}


class CategoryRef(BaseModel):
    id: UUID
    slug: str
    name: str

    model_config = {"from_attributes": True}


class IdeaCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    one_line_definition: str | None = Field(default=None, max_length=500)
    original_text: str | None = None

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
    def validate_shares(self) -> IdeaCreate:
        if self.shares is not None:
            ids = [s.user_id for s in self.shares]
            if len(ids) != len(set(ids)):
                raise ValueError("duplicate share user_id")
        return self


class IdeaUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    one_line_definition: str | None = Field(default=None, max_length=500)
    original_text: str | None = None

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

    priority: IdeaPriority | None = None
    feasibility: IdeaFeasibility | None = None
    visibility: IdeaVisibility | None = None

    assignee_id: UUID | None = None
    next_review_date: date | None = None

    tags: list[str] | None = None

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("title must not be empty")
        return stripped


class IdeaListItem(BaseModel):
    id: UUID
    idea_code: str
    title: str
    one_line_definition: str | None
    category: CategoryRef | None
    stage: StageRef
    priority: str
    feasibility: str
    visibility: str
    author: IdeaUserPublic
    assignee: IdeaUserPublic | None
    tags: list[TagPublic]
    next_review_date: date | None
    created_at: datetime
    updated_at: datetime
    current_user_access: str


class IdeaDetail(IdeaListItem):
    workspace_id: UUID
    original_text: str | None
    background: str | None
    problem: str | None
    core_concept: str | None
    major_features: str | None
    expected_effect: str | None
    target_users: str | None
    scenarios: str | None
    challenges: str | None
    minimum_validation: str | None
    related_project: str | None


class IdeaListResponse(BaseModel):
    items: list[IdeaListItem]
    total: int
    limit: int
    offset: int
