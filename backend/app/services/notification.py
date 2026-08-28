"""In-app notification service (Step 10)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.collaboration import IdeaComment, Notification
from app.models.enums import NotificationType
from app.models.idea import Idea
from app.models.user import User
from app.models.workspace import WorkspaceStage
from app.schemas.collaboration import IdeaInboxRef, NotificationListResponse, NotificationPublic, StageRef, UserRef
from app.services import idea_access


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def emit_notification(
    db: Session,
    *,
    workspace_id: UUID,
    recipient_id: UUID,
    actor_id: UUID | None,
    notification_type: NotificationType | str,
    dedupe_key: str,
    idea_id: UUID | None = None,
    comment_id: UUID | None = None,
    review_request_id: UUID | None = None,
) -> Notification | None:
    if actor_id is not None and recipient_id == actor_id:
        return None

    exists = db.scalar(
        select(Notification.id).where(
            Notification.recipient_id == recipient_id,
            Notification.dedupe_key == dedupe_key,
        )
    )
    if exists is not None:
        return None

    row = Notification(
        workspace_id=workspace_id,
        recipient_id=recipient_id,
        actor_id=actor_id,
        type=str(notification_type),
        idea_id=idea_id,
        comment_id=comment_id,
        review_request_id=review_request_id,
        dedupe_key=dedupe_key,
    )
    db.add(row)
    db.flush()
    return row


def _idea_readable(db: Session, idea_id: UUID, user_id: UUID) -> bool:
    idea = db.get(Idea, idea_id)
    if idea is None:
        return False
    share = idea_access.get_idea_share(db, idea_id, user_id)
    return idea_access.can_read_idea(idea, user_id, share)


def _build_idea_ref(db: Session, idea: Idea) -> IdeaInboxRef:
    stage = db.get(WorkspaceStage, idea.stage_id) if idea.stage_id else None
    author = db.get(User, idea.author_id)
    return IdeaInboxRef(
        id=idea.id,
        idea_code=idea.idea_code,
        title=idea.title,
        one_line_definition=idea.one_line_definition,
        stage=StageRef(id=stage.id, label=stage.label) if stage else None,
        author=UserRef(id=author.id, name=author.name, email=author.email) if author else None,
    )


def _build_actor(db: Session, actor_id: UUID | None) -> UserRef | None:
    if actor_id is None:
        return None
    user = db.get(User, actor_id)
    if user is None:
        return None
    return UserRef(id=user.id, name=user.name, email=user.email)


def _to_public(db: Session, row: Notification, *, user_id: UUID) -> NotificationPublic | None:
    if row.idea_id is not None:
        idea = db.get(Idea, row.idea_id)
        if idea is None or idea.deleted_at is not None:
            return None
        if not _idea_readable(db, row.idea_id, user_id):
            return None

    if row.comment_id is not None:
        comment = db.get(IdeaComment, row.comment_id)
        if comment is None:
            return None

    idea_ref = None
    if row.idea_id is not None:
        idea = db.get(Idea, row.idea_id)
        if idea is None or idea.deleted_at is not None:
            return None
        idea_ref = _build_idea_ref(db, idea)

    return NotificationPublic(
        id=row.id,
        type=row.type,
        read=row.read_at is not None,
        created_at=row.created_at,
        actor=_build_actor(db, row.actor_id),
        idea=idea_ref,
        comment_id=row.comment_id,
        review_request_id=row.review_request_id,
    )


def list_notifications(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    limit: int = 20,
    offset: int = 0,
    unread_only: bool = False,
) -> NotificationListResponse:
    limit = min(max(limit, 1), 50)
    base = select(Notification).where(
        Notification.workspace_id == workspace_id,
        Notification.recipient_id == user_id,
    )
    if unread_only:
        base = base.where(Notification.read_at.is_(None))

    rows = list(db.scalars(base.order_by(Notification.created_at.desc())))

    visible: list[NotificationPublic] = []
    for row in rows:
        public = _to_public(db, row, user_id=user_id)
        if public is not None:
            visible.append(public)

    total = len(visible)
    items = visible[offset : offset + limit]
    return NotificationListResponse(items=items, total=total)


def unread_count(db: Session, *, workspace_id: UUID, user_id: UUID) -> int:
    rows = db.scalars(
        select(Notification).where(
            Notification.workspace_id == workspace_id,
            Notification.recipient_id == user_id,
            Notification.read_at.is_(None),
        )
    ).all()
    count = 0
    for row in rows:
        if _to_public(db, row, user_id=user_id) is not None:
            count += 1
    return count


def mark_read(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    notification_id: UUID,
) -> NotificationPublic:
    row = db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.workspace_id == workspace_id,
            Notification.recipient_id == user_id,
        )
    )
    if row is None:
        raise AppError("Notification not found.", code="NOTIFICATION_NOT_FOUND", status_code=404)
    public = _to_public(db, row, user_id=user_id)
    if public is None:
        raise AppError("Notification not found.", code="NOTIFICATION_NOT_FOUND", status_code=404)
    if row.read_at is None:
        row.read_at = utcnow()
        db.flush()
    public.read = True
    return public


def mark_all_read(db: Session, *, workspace_id: UUID, user_id: UUID) -> int:
    rows = list(
        db.scalars(
            select(Notification).where(
                Notification.workspace_id == workspace_id,
                Notification.recipient_id == user_id,
                Notification.read_at.is_(None),
            )
        )
    )
    now = utcnow()
    updated = 0
    for row in rows:
        if _to_public(db, row, user_id=user_id) is None:
            continue
        row.read_at = now
        updated += 1
    db.flush()
    return updated


def emit_assigned(
    db: Session,
    *,
    workspace_id: UUID,
    idea: Idea,
    assignee_id: UUID,
    actor_id: UUID,
) -> None:
    share = idea_access.get_idea_share(db, idea.id, assignee_id)
    if not idea_access.can_read_idea(idea, assignee_id, share):
        return
    dedupe_key = f"idea:{idea.id}:assigned:{assignee_id}:{utcnow().isoformat()}"
    emit_notification(
        db,
        workspace_id=workspace_id,
        recipient_id=assignee_id,
        actor_id=actor_id,
        notification_type=NotificationType.ASSIGNED,
        idea_id=idea.id,
        dedupe_key=dedupe_key,
    )
