"""Workspace / member / stage / category API schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.enums import WorkspaceRole


class TeamWorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    allow_llm: bool | None = None
    allow_web_search: bool | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must not be empty")
        return stripped


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    allow_llm: bool | None = None
    allow_web_search: bool | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must not be empty")
        return stripped


class WorkspacePublic(BaseModel):
    id: UUID
    name: str
    type: str
    owner_id: UUID
    allow_llm: bool
    allow_web_search: bool
    effective_allow_llm: bool
    effective_allow_web_search: bool
    current_user_role: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MemberAddRequest(BaseModel):
    email: EmailStr
    role: WorkspaceRole = WorkspaceRole.MEMBER


class MemberRoleUpdate(BaseModel):
    role: WorkspaceRole


class MemberPublic(BaseModel):
    user_id: UUID
    email: str
    name: str
    role: str
    status: str
    created_at: datetime
    updated_at: datetime


class StagePublic(BaseModel):
    id: UUID
    slug: str
    label: str
    sort_order: int
    is_default: bool
    is_terminal: bool

    model_config = {"from_attributes": True}


class CategoryPublic(BaseModel):
    id: UUID
    slug: str
    name: str
    sort_order: int

    model_config = {"from_attributes": True}
