"""Schemas for workspace-scoped AI task aggregation (Step 19)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

AiTaskType = Literal["CREATE", "REFINE", "RESEARCH"]


class AiTaskPublic(BaseModel):
    """Frontend-facing aggregate of CREATE/REFINE sessions and Research runs."""

    id: str = Field(description="Stable task id, e.g. session:<uuid> or research:<uuid>")
    type: AiTaskType
    status: str
    is_active: bool
    session_id: UUID
    idea_id: UUID | None = None
    idea_title: str | None = None
    failure_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime


class AiTaskListResponse(BaseModel):
    items: list[AiTaskPublic]
    active_count: int
