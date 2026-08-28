"""Review request service (Step 10)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.collaboration import IdeaComment, IdeaCommentMention, IdeaReviewRequest
from app.models.enums import NotificationType, ReviewKind, ReviewStatus, UserStatus
from app.models.idea import Idea
from app.models.user import User
from app.models.workspace import WorkspaceStage
from app.schemas.collaboration import (
    EligibleReviewerList,
    IdeaInboxRef,
    ReviewCompleteRequest,
    ReviewCreateRequest,
    ReviewInboxCommentRef,
    ReviewInboxCounts,
    ReviewInboxItem,
    ReviewInboxResponse,
    ReviewInboxReviewRef,
    ReviewRequestPublic,
    StageRef,
    UserRef,
)
from app.services import idea as idea_service
from app.services import idea_access
from app.services import notification as notification_service


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _user_ref(user: User) -> UserRef:
    return UserRef(id=user.id, name=user.name, email=user.email)


def _idea_inbox_ref(db: Session, idea: Idea) -> IdeaInboxRef:
    stage = db.get(WorkspaceStage, idea.stage_id) if idea.stage_id else None
    author = db.get(User, idea.author_id)
    return IdeaInboxRef(
        id=idea.id,
        idea_code=idea.idea_code,
        title=idea.title,
        one_line_definition=idea.one_line_definition,
        stage=StageRef(id=stage.id, label=stage.label) if stage else None,
        author=_user_ref(author) if author else None,
    )


def _to_review_public(db: Session, review: IdeaReviewRequest) -> ReviewRequestPublic:
    requested_by = db.get(User, review.requested_by)
    reviewer = db.get(User, review.reviewer_id)
    assert requested_by is not None and reviewer is not None
    return ReviewRequestPublic(
        id=review.id,
        idea_id=review.idea_id,
        kind=review.kind,
        status=review.status,
        message=review.message,
        due_date=review.due_date,
        result=review.result,
        completion_note=review.completion_note,
        suggested_next_review_date=review.suggested_next_review_date,
        requested_by=_user_ref(requested_by),
        reviewer=_user_ref(reviewer),
        completed_at=review.completed_at,
        cancelled_at=review.cancelled_at,
        created_at=review.created_at,
        updated_at=review.updated_at,
    )


def _validate_reviewer_eligible(
    db: Session,
    *,
    workspace_id: UUID,
    idea: Idea,
    reviewer_id: UUID,
    requester_id: UUID,
) -> User:
    if reviewer_id == requester_id:
        raise AppError(
            "Reviewer must differ from requester.",
            code="REVIEW_REVIEWER_NOT_ELIGIBLE",
            status_code=400,
        )
    reviewer = db.get(User, reviewer_id)
    if reviewer is None or reviewer.status != UserStatus.ACTIVE.value:
        raise AppError(
            "Reviewer is not eligible.",
            code="REVIEW_REVIEWER_NOT_ELIGIBLE",
            status_code=400,
        )
    eligible_ids = {
        u.id
        for u in idea_access.list_readable_member_users(
            db,
            workspace_id=workspace_id,
            idea=idea,
            exclude_user_id=requester_id,
        )
    }
    if reviewer_id not in eligible_ids:
        raise AppError(
            "Reviewer does not have read access to this idea.",
            code="REVIEW_REVIEWER_NOT_ELIGIBLE",
            status_code=400,
        )
    return reviewer


def list_eligible_reviewers(
    db: Session,
    *,
    workspace_id: UUID,
    idea_id: UUID,
    user_id: UUID,
) -> EligibleReviewerList:
    idea_service.require_idea_edit(
        db, workspace_id=workspace_id, idea_id=idea_id, user_id=user_id
    )
    idea, _ = idea_service.get_readable_idea(
        db, workspace_id=workspace_id, idea_id=idea_id, user_id=user_id
    )
    users = idea_access.list_readable_member_users(
        db,
        workspace_id=workspace_id,
        idea=idea,
        exclude_user_id=user_id,
    )
    return EligibleReviewerList(items=[_user_ref(u) for u in users])


def create_review_request(
    db: Session,
    *,
    workspace_id: UUID,
    idea_id: UUID,
    user_id: UUID,
    payload: ReviewCreateRequest,
) -> ReviewRequestPublic:
    idea, _share, _access = idea_service.require_idea_edit(
        db, workspace_id=workspace_id, idea_id=idea_id, user_id=user_id
    )
    reviewer = _validate_reviewer_eligible(
        db,
        workspace_id=workspace_id,
        idea=idea,
        reviewer_id=payload.reviewer_id,
        requester_id=user_id,
    )

    review = IdeaReviewRequest(
        workspace_id=workspace_id,
        idea_id=idea.id,
        requested_by=user_id,
        reviewer_id=reviewer.id,
        kind=payload.kind.value,
        status=ReviewStatus.OPEN.value,
        message=payload.message,
        due_date=payload.due_date,
    )
    db.add(review)
    try:
        db.flush()
    except IntegrityError as exc:
        raise AppError(
            "An open review already exists for this reviewer.",
            code="REVIEW_ALREADY_OPEN",
            status_code=409,
        ) from exc

    notification_service.emit_notification(
        db,
        workspace_id=workspace_id,
        recipient_id=reviewer.id,
        actor_id=user_id,
        notification_type=NotificationType.REVIEW_REQUESTED,
        idea_id=idea.id,
        review_request_id=review.id,
        dedupe_key=f"review:{review.id}:requested",
    )
    return _to_review_public(db, review)


def list_idea_reviews(
    db: Session,
    *,
    workspace_id: UUID,
    idea_id: UUID,
    user_id: UUID,
) -> list[ReviewRequestPublic]:
    idea_service.get_readable_idea(
        db, workspace_id=workspace_id, idea_id=idea_id, user_id=user_id
    )
    rows = db.scalars(
        select(IdeaReviewRequest)
        .where(
            IdeaReviewRequest.workspace_id == workspace_id,
            IdeaReviewRequest.idea_id == idea_id,
        )
        .order_by(IdeaReviewRequest.created_at.desc())
    ).all()
    return [_to_review_public(db, row) for row in rows]


def _get_review_for_workspace(
    db: Session,
    *,
    workspace_id: UUID,
    review_id: UUID,
    for_update: bool = False,
) -> IdeaReviewRequest:
    stmt = select(IdeaReviewRequest).where(
        IdeaReviewRequest.id == review_id,
        IdeaReviewRequest.workspace_id == workspace_id,
    )
    if for_update:
        stmt = stmt.with_for_update()
    review = db.scalar(stmt)
    if review is None:
        raise AppError("Review not found.", code="REVIEW_NOT_FOUND", status_code=404)
    return review


def complete_review(
    db: Session,
    *,
    workspace_id: UUID,
    review_id: UUID,
    user_id: UUID,
    payload: ReviewCompleteRequest,
) -> ReviewRequestPublic:
    review = _get_review_for_workspace(
        db, workspace_id=workspace_id, review_id=review_id, for_update=True
    )
    if review.reviewer_id != user_id:
        raise AppError(
            "Only the assigned reviewer can complete this review.",
            code="REVIEW_COMPLETE_FORBIDDEN",
            status_code=403,
        )
    if review.status == ReviewStatus.COMPLETED.value:
        raise AppError(
            "Review is already completed.",
            code="REVIEW_ALREADY_COMPLETED",
            status_code=409,
        )
    if review.status != ReviewStatus.OPEN.value:
        raise AppError(
            "Review is not open.",
            code="REVIEW_INVALID_STATE",
            status_code=409,
        )

    idea, _ = idea_service.get_readable_idea(
        db,
        workspace_id=workspace_id,
        idea_id=review.idea_id,
        user_id=user_id,
    )
    stage_id_before = idea.stage_id
    next_review_before = idea.next_review_date

    review.status = ReviewStatus.COMPLETED.value
    review.result = payload.result.value
    review.completion_note = payload.completion_note
    review.suggested_next_review_date = payload.suggested_next_review_date
    review.completed_at = utcnow()
    db.flush()

    db.refresh(idea)
    assert idea.stage_id == stage_id_before
    assert idea.next_review_date == next_review_before

    requester_share = idea_access.get_idea_share(db, idea.id, review.requested_by)
    if idea_access.can_read_idea(idea, review.requested_by, requester_share):
        notification_service.emit_notification(
            db,
            workspace_id=workspace_id,
            recipient_id=review.requested_by,
            actor_id=user_id,
            notification_type=NotificationType.REVIEW_COMPLETED,
            idea_id=idea.id,
            review_request_id=review.id,
            dedupe_key=f"review:{review.id}:completed",
        )

    return _to_review_public(db, review)


def cancel_review(
    db: Session,
    *,
    workspace_id: UUID,
    review_id: UUID,
    user_id: UUID,
) -> ReviewRequestPublic:
    review = _get_review_for_workspace(
        db, workspace_id=workspace_id, review_id=review_id, for_update=True
    )
    if review.status != ReviewStatus.OPEN.value:
        raise AppError(
            "Review is not open.",
            code="REVIEW_INVALID_STATE",
            status_code=409,
        )
    idea, share = idea_service.get_readable_idea(
        db,
        workspace_id=workspace_id,
        idea_id=review.idea_id,
        user_id=user_id,
    )
    if review.requested_by != user_id and not idea_access.is_owner(idea, user_id):
        raise AppError(
            "Review cancel is forbidden.",
            code="REVIEW_CANCEL_FORBIDDEN",
            status_code=403,
        )

    review.status = ReviewStatus.CANCELLED.value
    review.cancelled_at = utcnow()
    db.flush()
    return _to_review_public(db, review)


def _today() -> date:
    return utcnow().date()


def _readable_idea_ids_subquery(user_id: UUID):
    return (
        select(Idea.id)
        .where(
            Idea.deleted_at.is_(None),
            idea_access.readable_idea_predicate(user_id),
        )
        .scalar_subquery()
    )


def _open_reviews_for_user_base(workspace_id: UUID, user_id: UUID):
    readable = _readable_idea_ids_subquery(user_id)
    return select(IdeaReviewRequest).where(
        IdeaReviewRequest.workspace_id == workspace_id,
        IdeaReviewRequest.reviewer_id == user_id,
        IdeaReviewRequest.status == ReviewStatus.OPEN.value,
        IdeaReviewRequest.idea_id.in_(readable),
    )


def review_inbox_counts(db: Session, *, workspace_id: UUID, user_id: UUID) -> ReviewInboxCounts:
    today = _today()
    base = _open_reviews_for_user_base(workspace_id, user_id)
    open_rows = list(db.scalars(base).all())

    scheduled = 0
    overdue = 0
    needs_info = 0
    next_stage = 0
    for row in open_rows:
        if row.due_date is None or row.due_date >= today:
            scheduled += 1
        if row.due_date is not None and row.due_date < today:
            overdue += 1
        if row.kind == ReviewKind.NEEDS_INFO.value:
            needs_info += 1
        if row.kind == ReviewKind.NEXT_STAGE.value:
            next_stage += 1

    readable = _readable_idea_ids_subquery(user_id)
    assigned = db.scalar(
        select(func.count())
        .select_from(Idea)
        .where(
            Idea.workspace_id == workspace_id,
            Idea.deleted_at.is_(None),
            Idea.assignee_id == user_id,
            Idea.id.in_(readable),
        )
    ) or 0

    mentioned = db.scalar(
        select(func.count(func.distinct(IdeaComment.id)))
        .select_from(IdeaCommentMention)
        .join(IdeaComment, IdeaComment.id == IdeaCommentMention.comment_id)
        .join(Idea, Idea.id == IdeaComment.idea_id)
        .where(
            IdeaCommentMention.user_id == user_id,
            IdeaComment.deleted_at.is_(None),
            Idea.deleted_at.is_(None),
            Idea.workspace_id == workspace_id,
            Idea.id.in_(readable),
        )
    ) or 0

    return ReviewInboxCounts(
        scheduled=scheduled,
        overdue=overdue,
        needs_info=needs_info,
        next_stage=next_stage,
        assigned=assigned,
        mentioned=mentioned,
        pending_total=len(open_rows),
    )


def _build_review_inbox_item(
    db: Session,
    *,
    reason: str,
    idea: Idea,
    review: IdeaReviewRequest | None = None,
    comment: IdeaComment | None = None,
    created_at: datetime,
) -> ReviewInboxItem:
    review_ref = None
    if review is not None:
        requested_by = db.get(User, review.requested_by)
        assert requested_by is not None
        review_ref = ReviewInboxReviewRef(
            id=review.id,
            kind=review.kind,
            due_date=review.due_date,
            requested_by=_user_ref(requested_by),
        )
    comment_ref = None
    if comment is not None:
        author = db.get(User, comment.author_id)
        assert author is not None
        comment_ref = ReviewInboxCommentRef(
            id=comment.id,
            body=comment.body,
            author=_user_ref(author),
            created_at=comment.created_at,
        )
    return ReviewInboxItem(
        source="REVIEW_REQUEST" if review is not None else ("COMMENT" if comment else "IDEA"),
        reason=reason,
        idea=_idea_inbox_ref(db, idea),
        review_request=review_ref,
        comment=comment_ref,
        created_at=created_at,
    )


def list_review_inbox(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    tab: str,
    limit: int = 50,
    offset: int = 0,
) -> ReviewInboxResponse:
    limit = min(max(limit, 1), 100)
    today = _today()
    readable = _readable_idea_ids_subquery(user_id)
    items: list[ReviewInboxItem] = []

    if tab == "scheduled":
        rows = db.scalars(
            _open_reviews_for_user_base(workspace_id, user_id)
            .where(
                (IdeaReviewRequest.due_date.is_(None))
                | (IdeaReviewRequest.due_date >= today)
            )
            .order_by(IdeaReviewRequest.due_date.asc().nulls_last(), IdeaReviewRequest.created_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        for review in rows:
            idea = db.get(Idea, review.idea_id)
            if idea is None:
                continue
            items.append(
                _build_review_inbox_item(
                    db,
                    reason="scheduled",
                    idea=idea,
                    review=review,
                    created_at=review.created_at,
                )
            )
    elif tab == "overdue":
        rows = db.scalars(
            _open_reviews_for_user_base(workspace_id, user_id)
            .where(
                IdeaReviewRequest.due_date.is_not(None),
                IdeaReviewRequest.due_date < today,
            )
            .order_by(IdeaReviewRequest.due_date.asc(), IdeaReviewRequest.created_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        for review in rows:
            idea = db.get(Idea, review.idea_id)
            if idea is None:
                continue
            items.append(
                _build_review_inbox_item(
                    db,
                    reason="overdue",
                    idea=idea,
                    review=review,
                    created_at=review.created_at,
                )
            )
    elif tab == "needs_info":
        rows = db.scalars(
            _open_reviews_for_user_base(workspace_id, user_id)
            .where(IdeaReviewRequest.kind == ReviewKind.NEEDS_INFO.value)
            .order_by(IdeaReviewRequest.created_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        for review in rows:
            idea = db.get(Idea, review.idea_id)
            if idea is None:
                continue
            items.append(
                _build_review_inbox_item(
                    db,
                    reason="needs_info",
                    idea=idea,
                    review=review,
                    created_at=review.created_at,
                )
            )
    elif tab == "next_stage":
        rows = db.scalars(
            _open_reviews_for_user_base(workspace_id, user_id)
            .where(IdeaReviewRequest.kind == ReviewKind.NEXT_STAGE.value)
            .order_by(IdeaReviewRequest.created_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        for review in rows:
            idea = db.get(Idea, review.idea_id)
            if idea is None:
                continue
            items.append(
                _build_review_inbox_item(
                    db,
                    reason="next_stage",
                    idea=idea,
                    review=review,
                    created_at=review.created_at,
                )
            )
    elif tab == "assigned":
        ideas = db.scalars(
            select(Idea)
            .where(
                Idea.workspace_id == workspace_id,
                Idea.deleted_at.is_(None),
                Idea.assignee_id == user_id,
                Idea.id.in_(readable),
            )
            .order_by(Idea.updated_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        for idea in ideas:
            items.append(
                _build_review_inbox_item(
                    db,
                    reason="assigned",
                    idea=idea,
                    created_at=idea.updated_at,
                )
            )
    elif tab == "mentioned":
        rows = db.execute(
            select(IdeaComment, Idea)
            .join(Idea, Idea.id == IdeaComment.idea_id)
            .join(IdeaCommentMention, IdeaCommentMention.comment_id == IdeaComment.id)
            .where(
                IdeaCommentMention.user_id == user_id,
                IdeaComment.deleted_at.is_(None),
                Idea.deleted_at.is_(None),
                Idea.workspace_id == workspace_id,
                Idea.id.in_(readable),
            )
            .order_by(IdeaComment.created_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        for comment, idea in rows:
            items.append(
                _build_review_inbox_item(
                    db,
                    reason="mentioned",
                    idea=idea,
                    comment=comment,
                    created_at=comment.created_at,
                )
            )
    else:
        raise AppError("Invalid review inbox tab.", code="REVIEW_INBOX_INVALID_TAB", status_code=400)

    return ReviewInboxResponse(items=items, total=len(items))
