"""Review, comment, and notification API schemas (Step 10)."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.enums import ReviewKind, ReviewResult


class UserRef(BaseModel):
    id: UUID
    name: str
    email: str


class StageRef(BaseModel):
    id: UUID
    label: str


class IdeaInboxRef(BaseModel):
    id: UUID
    idea_code: str
    title: str
    one_line_definition: str | None = None
    stage: StageRef | None = None
    author: UserRef | None = None


class ReviewRequestPublic(BaseModel):
    id: UUID
    idea_id: UUID
    kind: ReviewKind
    status: str
    message: str | None = None
    due_date: date | None = None
    result: ReviewResult | None = None
    completion_note: str | None = None
    suggested_next_review_date: date | None = None
    requested_by: UserRef
    reviewer: UserRef
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ReviewCreateRequest(BaseModel):
    reviewer_id: UUID
    kind: ReviewKind = ReviewKind.GENERAL
    message: str | None = Field(default=None, max_length=5000)
    due_date: date | None = None


class ReviewCompleteRequest(BaseModel):
    result: ReviewResult
    completion_note: str | None = Field(default=None, max_length=5000)
    suggested_next_review_date: date | None = None


class EligibleReviewerList(BaseModel):
    items: list[UserRef]


class ReviewInboxReviewRef(BaseModel):
    id: UUID
    kind: ReviewKind
    due_date: date | None = None
    requested_by: UserRef


class ReviewInboxCommentRef(BaseModel):
    id: UUID
    body: str
    author: UserRef
    created_at: datetime


class ReviewInboxItem(BaseModel):
    source: str
    reason: str
    idea: IdeaInboxRef
    review_request: ReviewInboxReviewRef | None = None
    comment: ReviewInboxCommentRef | None = None
    created_at: datetime


class ReviewInboxResponse(BaseModel):
    items: list[ReviewInboxItem]
    total: int


class ReviewInboxCounts(BaseModel):
    scheduled: int
    overdue: int
    needs_info: int
    next_stage: int
    assigned: int
    mentioned: int
    pending_total: int


class CommentMentionPublic(BaseModel):
    id: UUID
    name: str


class CommentPublic(BaseModel):
    id: UUID
    body: str
    author: UserRef
    mentions: list[CommentMentionPublic]
    created_at: datetime
    updated_at: datetime
    edited: bool
    can_edit: bool
    can_delete: bool


class CommentListResponse(BaseModel):
    items: list[CommentPublic]
    total: int


class CommentCreateRequest(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    mention_user_ids: list[UUID] = Field(default_factory=list)

    @field_validator("body")
    @classmethod
    def strip_body(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("body must not be empty")
        return stripped


class CommentUpdateRequest(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    mention_user_ids: list[UUID] = Field(default_factory=list)

    @field_validator("body")
    @classmethod
    def strip_body(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("body must not be empty")
        return stripped


class NotificationPublic(BaseModel):
    id: UUID
    type: str
    read: bool
    created_at: datetime
    actor: UserRef | None = None
    idea: IdeaInboxRef | None = None
    comment_id: UUID | None = None
    review_request_id: UUID | None = None


class NotificationListResponse(BaseModel):
    items: list[NotificationPublic]
    total: int


class NotificationUnreadCount(BaseModel):
    count: int
