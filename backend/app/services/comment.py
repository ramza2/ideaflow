"""Idea comment service (Step 10)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.collaboration import IdeaComment, IdeaCommentMention
from app.models.enums import NotificationType, UserStatus
from app.models.idea import Idea
from app.models.user import User
from app.schemas.collaboration import (
    CommentCreateRequest,
    CommentListResponse,
    CommentMentionPublic,
    CommentPublic,
    CommentUpdateRequest,
    EligibleReviewerList,
    UserRef,
)
from app.services import idea as idea_service
from app.services import idea_access
from app.services import notification as notification_service

_MAX_MENTIONS = 20


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _user_ref(user: User) -> UserRef:
    return UserRef(id=user.id, name=user.name, email=user.email)


def list_mention_candidates(
    db: Session,
    *,
    workspace_id: UUID,
    idea_id: UUID,
    user_id: UUID,
) -> EligibleReviewerList:
    idea, _ = idea_service.get_readable_idea(
        db, workspace_id=workspace_id, idea_id=idea_id, user_id=user_id
    )
    users = idea_access.list_readable_member_users(
        db, workspace_id=workspace_id, idea=idea
    )
    return EligibleReviewerList(items=[_user_ref(u) for u in users])


def _validate_mentions(
    db: Session,
    *,
    workspace_id: UUID,
    idea: Idea,
    mention_user_ids: list[UUID],
    author_id: UUID,
) -> list[UUID]:
    unique: list[UUID] = []
    seen: set[UUID] = set()
    for uid in mention_user_ids:
        if uid in seen:
            continue
        seen.add(uid)
        unique.append(uid)
    if len(unique) > _MAX_MENTIONS:
        raise AppError(
            "Too many mentions in one comment.",
            code="COMMENT_MENTION_NOT_ELIGIBLE",
            status_code=400,
        )

    eligible_ids = {u.id for u in idea_access.list_readable_member_users(db, workspace_id=workspace_id, idea=idea)}
    for uid in unique:
        user = db.get(User, uid)
        if user is None or user.status != UserStatus.ACTIVE.value or uid not in eligible_ids:
            raise AppError(
                "Mention target is not eligible.",
                code="COMMENT_MENTION_NOT_ELIGIBLE",
                status_code=400,
            )
    return unique


def _load_mentions(db: Session, comment_id: UUID) -> list[CommentMentionPublic]:
    rows = db.scalars(
        select(IdeaCommentMention).where(IdeaCommentMention.comment_id == comment_id)
    ).all()
    out: list[CommentMentionPublic] = []
    for row in rows:
        user = db.get(User, row.user_id)
        if user is not None:
            out.append(CommentMentionPublic(id=user.id, name=user.name))
    return out


def _to_public(
    db: Session,
    comment: IdeaComment,
    *,
    current_user_id: UUID,
) -> CommentPublic:
    author = db.get(User, comment.author_id)
    assert author is not None
    edited = comment.updated_at > comment.created_at
    can_edit = comment.author_id == current_user_id and comment.deleted_at is None
    can_delete = can_edit
    return CommentPublic(
        id=comment.id,
        body=comment.body,
        author=_user_ref(author),
        mentions=_load_mentions(db, comment.id),
        created_at=comment.created_at,
        updated_at=comment.updated_at,
        edited=edited,
        can_edit=can_edit,
        can_delete=can_delete,
    )


def list_comments(
    db: Session,
    *,
    workspace_id: UUID,
    idea_id: UUID,
    user_id: UUID,
    limit: int = 50,
    offset: int = 0,
) -> CommentListResponse:
    idea_service.get_readable_idea(
        db, workspace_id=workspace_id, idea_id=idea_id, user_id=user_id
    )
    limit = min(max(limit, 1), 100)
    base = select(IdeaComment).where(
        IdeaComment.workspace_id == workspace_id,
        IdeaComment.idea_id == idea_id,
        IdeaComment.deleted_at.is_(None),
    )
    total = db.scalar(
        select(func.count())
        .select_from(IdeaComment)
        .where(
            IdeaComment.workspace_id == workspace_id,
            IdeaComment.idea_id == idea_id,
            IdeaComment.deleted_at.is_(None),
        )
    ) or 0
    rows = db.scalars(
        base.order_by(IdeaComment.created_at.asc()).offset(offset).limit(limit)
    ).all()
    return CommentListResponse(
        items=[_to_public(db, row, current_user_id=user_id) for row in rows],
        total=total,
    )


def _replace_mentions(db: Session, comment_id: UUID, user_ids: list[UUID]) -> None:
    existing = db.scalars(
        select(IdeaCommentMention).where(IdeaCommentMention.comment_id == comment_id)
    ).all()
    for row in existing:
        db.delete(row)
    db.flush()
    for uid in user_ids:
        db.add(IdeaCommentMention(comment_id=comment_id, user_id=uid))


def _emit_comment_notifications(
    db: Session,
    *,
    workspace_id: UUID,
    idea: Idea,
    comment: IdeaComment,
    author_id: UUID,
    mention_user_ids: list[UUID],
    notify_author: bool,
) -> None:
    mention_set = set(mention_user_ids)
    for uid in mention_user_ids:
        if uid == author_id:
            continue
        notification_service.emit_notification(
            db,
            workspace_id=workspace_id,
            recipient_id=uid,
            actor_id=author_id,
            notification_type=NotificationType.MENTION,
            idea_id=idea.id,
            comment_id=comment.id,
            dedupe_key=f"comment:{comment.id}:mention:{uid}",
        )

    if notify_author and idea.author_id != author_id and idea.author_id not in mention_set:
        notification_service.emit_notification(
            db,
            workspace_id=workspace_id,
            recipient_id=idea.author_id,
            actor_id=author_id,
            notification_type=NotificationType.COMMENT_ADDED,
            idea_id=idea.id,
            comment_id=comment.id,
            dedupe_key=f"comment:{comment.id}:added",
        )


def create_comment(
    db: Session,
    *,
    workspace_id: UUID,
    idea_id: UUID,
    user_id: UUID,
    payload: CommentCreateRequest,
) -> CommentPublic:
    idea, _ = idea_service.get_readable_idea(
        db, workspace_id=workspace_id, idea_id=idea_id, user_id=user_id
    )
    mention_ids = _validate_mentions(
        db,
        workspace_id=workspace_id,
        idea=idea,
        mention_user_ids=payload.mention_user_ids,
        author_id=user_id,
    )
    comment = IdeaComment(
        workspace_id=workspace_id,
        idea_id=idea.id,
        author_id=user_id,
        body=payload.body,
    )
    db.add(comment)
    db.flush()
    _replace_mentions(db, comment.id, mention_ids)
    _emit_comment_notifications(
        db,
        workspace_id=workspace_id,
        idea=idea,
        comment=comment,
        author_id=user_id,
        mention_user_ids=mention_ids,
        notify_author=True,
    )
    return _to_public(db, comment, current_user_id=user_id)


def _get_comment(
    db: Session,
    *,
    workspace_id: UUID,
    idea_id: UUID,
    comment_id: UUID,
    for_update: bool = False,
) -> IdeaComment:
    stmt = select(IdeaComment).where(
        IdeaComment.id == comment_id,
        IdeaComment.workspace_id == workspace_id,
        IdeaComment.idea_id == idea_id,
        IdeaComment.deleted_at.is_(None),
    )
    if for_update:
        stmt = stmt.with_for_update()
    comment = db.scalar(stmt)
    if comment is None:
        raise AppError("Comment not found.", code="COMMENT_NOT_FOUND", status_code=404)
    return comment


def update_comment(
    db: Session,
    *,
    workspace_id: UUID,
    idea_id: UUID,
    comment_id: UUID,
    user_id: UUID,
    payload: CommentUpdateRequest,
) -> CommentPublic:
    idea, _ = idea_service.get_readable_idea(
        db, workspace_id=workspace_id, idea_id=idea_id, user_id=user_id
    )
    comment = _get_comment(
        db,
        workspace_id=workspace_id,
        idea_id=idea_id,
        comment_id=comment_id,
        for_update=True,
    )
    if comment.author_id != user_id:
        raise AppError(
            "Comment edit is forbidden.",
            code="COMMENT_EDIT_FORBIDDEN",
            status_code=403,
        )

    existing_mentions = {
        row.user_id
        for row in db.scalars(
            select(IdeaCommentMention).where(IdeaCommentMention.comment_id == comment.id)
        ).all()
    }
    new_mention_ids = _validate_mentions(
        db,
        workspace_id=workspace_id,
        idea=idea,
        mention_user_ids=payload.mention_user_ids,
        author_id=user_id,
    )
    comment.body = payload.body
    _replace_mentions(db, comment.id, new_mention_ids)

    added = [uid for uid in new_mention_ids if uid not in existing_mentions]
    _emit_comment_notifications(
        db,
        workspace_id=workspace_id,
        idea=idea,
        comment=comment,
        author_id=user_id,
        mention_user_ids=added,
        notify_author=False,
    )
    db.flush()
    return _to_public(db, comment, current_user_id=user_id)


def delete_comment(
    db: Session,
    *,
    workspace_id: UUID,
    idea_id: UUID,
    comment_id: UUID,
    user_id: UUID,
) -> None:
    idea_service.get_readable_idea(
        db, workspace_id=workspace_id, idea_id=idea_id, user_id=user_id
    )
    comment = _get_comment(
        db,
        workspace_id=workspace_id,
        idea_id=idea_id,
        comment_id=comment_id,
        for_update=True,
    )
    if comment.author_id != user_id:
        raise AppError(
            "Comment delete is forbidden.",
            code="COMMENT_DELETE_FORBIDDEN",
            status_code=403,
        )
    comment.deleted_at = utcnow()
    db.flush()
