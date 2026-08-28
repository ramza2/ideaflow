"""Pydantic schemas for web research API (Step 9)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import WebResearchRunStatus


class WebResearchPreviewRequest(BaseModel):
    queries: list[str] = Field(min_length=1, max_length=5)
    current_draft: dict[str, Any] = Field(default_factory=dict)
    user_edited_fields: list[str] = Field(default_factory=list)


class SanitizationNotePublic(BaseModel):
    query_index: int
    changed: bool


class WebResearchFailurePublic(BaseModel):
    phase: str | None = None
    code: str | None = None
    message: str | None = None


class WebEvidencePublic(BaseModel):
    id: UUID
    query: str
    title: str
    url: str
    domain: str | None = None
    source_name: str | None = None
    snippet: str | None = None
    published_at: datetime | None = None
    fetched_at: datetime
    rank: int
    related_fields: list[str] = Field(default_factory=list)


class WebResearchRunPublic(BaseModel):
    id: UUID
    session_id: UUID
    status: WebResearchRunStatus
    queries_to_send: list[str]
    sanitization_notes: list[SanitizationNotePublic] = Field(default_factory=list)
    provider: str | None = None
    result_count: int | None = None
    research_summary: str | None = None
    failure: WebResearchFailurePublic | None = None
    evidence: list[WebEvidencePublic] = Field(default_factory=list)
    approved_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class WebResearchLatestResponse(BaseModel):
    run: WebResearchRunPublic | None = None


class IdeaEvidenceItem(BaseModel):
    id: UUID
    title: str
    url: str
    domain: str | None = None
    source_name: str | None = None
    snippet: str | None = None
    published_at: datetime | None = None
    fetched_at: datetime
    related_fields: list[str] = Field(default_factory=list)


class IdeaEvidenceResponse(BaseModel):
    items: list[IdeaEvidenceItem] = Field(default_factory=list)
