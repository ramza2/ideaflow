"""Idea Validation domain service (Step 14)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.enums import IdeaValidationOutcome, IdeaValidationStatus
from app.models.idea import Idea
from app.models.user import User
from app.models.validation import IdeaValidation
from app.models.workspace import WorkspaceStage
from app.schemas.validation import (
    IdeaValidationCompleteRequest,
    IdeaValidationCreateRequest,
    IdeaValidationListResponse,
    IdeaValidationPublic,
    IdeaValidationStartResponse,
    IdeaValidationUpdateRequest,
    StageRef,
    UserRef,
)
from app.services import idea as idea_service
from app.services import idea_access

_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    IdeaValidationStatus.DRAFT.value: frozenset(
        {IdeaValidationStatus.READY.value, IdeaValidationStatus.CANCELLED.value}
    ),
    IdeaValidationStatus.READY.value: frozenset(
        {
            IdeaValidationStatus.DRAFT.value,
            IdeaValidationStatus.RUNNING.value,
            IdeaValidationStatus.CANCELLED.value,
        }
    ),
    IdeaValidationStatus.RUNNING.value: frozenset(
        {IdeaValidationStatus.COMPLETED.value, IdeaValidationStatus.CANCELLED.value}
    ),
    IdeaValidationStatus.COMPLETED.value: frozenset(),
    IdeaValidationStatus.CANCELLED.value: frozenset(),
}

_PLAN_FIELDS = frozenset(
    {"title", "hypothesis", "method", "success_criteria", "planned_evidence", "due_date"}
)
_RUNNING_EDITABLE_FIELDS = frozenset({"planned_evidence", "due_date"})


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _require_non_empty(value: str, *, field: str) -> str:
    text = value.strip()
    if not text:
        raise AppError(
            f"{field} is required.",
            code="VALIDATION_INVALID",
            status_code=400,
        )
    return text


def _to_public(db: Session, row: IdeaValidation) -> IdeaValidationPublic:
    creator = db.get(User, row.created_by)
    if creator is None:
        raise AppError("Validation creator not found.", code="USER_NOT_FOUND", status_code=500)
    return IdeaValidationPublic(
        id=row.id,
        idea_id=row.idea_id,
        title=row.title,
        hypothesis=row.hypothesis,
        method=row.method,
        success_criteria=row.success_criteria,
        planned_evidence=row.planned_evidence,
        status=IdeaValidationStatus(row.status),
        outcome=IdeaValidationOutcome(row.outcome) if row.outcome else None,
        result_summary=row.result_summary,
        evidence_summary=row.evidence_summary,
        due_date=row.due_date,
        started_at=row.started_at,
        completed_at=row.completed_at,
        created_by=UserRef(id=creator.id, name=creator.name, email=creator.email),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _get_readable_idea(
    db: Session,
    *,
    workspace_id: UUID,
    idea_id: UUID,
    user_id: UUID,
) -> tuple[Idea, str]:
    idea, share = idea_service.get_readable_idea(
        db,
        workspace_id=workspace_id,
        idea_id=idea_id,
        user_id=user_id,
    )
    access = idea_access.compute_access(idea, user_id, share)
    return idea, access


def _require_mutate_access(access: str) -> None:
    if access not in {idea_access.ACCESS_OWNER, idea_access.ACCESS_EDIT}:
        raise AppError(
            "Idea edit is forbidden.",
            code="IDEA_EDIT_FORBIDDEN",
            status_code=403,
        )


def _lock_idea_for_update(
    db: Session,
    *,
    workspace_id: UUID,
    idea_id: UUID,
) -> Idea:
    """Lock parent Idea and refresh ORM state from DB (identity-map safe)."""
    idea = db.execute(
        select(Idea)
        .where(
            Idea.id == idea_id,
            Idea.workspace_id == workspace_id,
            Idea.deleted_at.is_(None),
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one_or_none()
    if idea is None:
        raise AppError("Validation not found.", code="VALIDATION_NOT_FOUND", status_code=404)
    return idea


def _lock_validation_row(
    db: Session,
    *,
    idea_id: UUID,
    validation_id: UUID,
) -> IdeaValidation:
    row = db.execute(
        select(IdeaValidation)
        .where(IdeaValidation.id == validation_id)
        .with_for_update()
    ).scalar_one_or_none()
    if row is None or row.idea_id != idea_id:
        raise AppError("Validation not found.", code="VALIDATION_NOT_FOUND", status_code=404)
    return row


def _lock_validation(
    db: Session,
    *,
    workspace_id: UUID,
    idea_id: UUID,
    validation_id: UUID,
) -> IdeaValidation:
    row = _lock_validation_row(db, idea_id=idea_id, validation_id=validation_id)
    idea = db.get(Idea, idea_id)
    if idea is None or idea.workspace_id != workspace_id or idea.deleted_at is not None:
        raise AppError("Validation not found.", code="VALIDATION_NOT_FOUND", status_code=404)
    return row


def _stage_ref_for_idea(db: Session, idea: Idea) -> StageRef:
    stage = db.get(WorkspaceStage, idea.stage_id)
    if stage is None or stage.deleted_at is not None:
        raise AppError("Idea stage not found.", code="INVALID_IDEA_REFERENCE", status_code=500)
    return StageRef(id=stage.id, label=stage.label, slug=stage.slug)


def _assert_transition(current: str, target: str) -> None:
    allowed = _ALLOWED_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise AppError(
            f"Cannot transition validation from {current} to {target}.",
            code="INVALID_VALIDATION_TRANSITION",
            status_code=409,
        )


def list_validations(
    db: Session,
    *,
    workspace_id: UUID,
    idea_id: UUID,
    user_id: UUID,
) -> IdeaValidationListResponse:
    _get_readable_idea(db, workspace_id=workspace_id, idea_id=idea_id, user_id=user_id)
    stmt = (
        select(IdeaValidation)
        .where(IdeaValidation.idea_id == idea_id)
        .order_by(IdeaValidation.created_at.desc(), IdeaValidation.id.desc())
    )
    rows = list(db.scalars(stmt))
    return IdeaValidationListResponse(
        items=[_to_public(db, row) for row in rows],
        total=len(rows),
    )


def get_validation(
    db: Session,
    *,
    workspace_id: UUID,
    idea_id: UUID,
    validation_id: UUID,
    user_id: UUID,
) -> IdeaValidationPublic:
    _get_readable_idea(db, workspace_id=workspace_id, idea_id=idea_id, user_id=user_id)
    row = db.get(IdeaValidation, validation_id)
    if row is None or row.idea_id != idea_id:
        raise AppError("Validation not found.", code="VALIDATION_NOT_FOUND", status_code=404)
    idea = db.get(Idea, idea_id)
    if idea is None or idea.workspace_id != workspace_id or idea.deleted_at is not None:
        raise AppError("Validation not found.", code="VALIDATION_NOT_FOUND", status_code=404)
    return _to_public(db, row)


def create_validation(
    db: Session,
    *,
    workspace_id: UUID,
    idea_id: UUID,
    user_id: UUID,
    payload: IdeaValidationCreateRequest,
) -> IdeaValidationPublic:
    _idea, access = _get_readable_idea(
        db, workspace_id=workspace_id, idea_id=idea_id, user_id=user_id
    )
    _require_mutate_access(access)

    row = IdeaValidation(
        idea_id=idea_id,
        created_by=user_id,
        title=_require_non_empty(payload.title, field="title"),
        hypothesis=_require_non_empty(payload.hypothesis, field="hypothesis"),
        method=_require_non_empty(payload.method, field="method"),
        success_criteria=_require_non_empty(payload.success_criteria, field="success_criteria"),
        planned_evidence=payload.planned_evidence,
        due_date=payload.due_date,
        status=IdeaValidationStatus.DRAFT.value,
    )
    db.add(row)
    db.flush()
    return _to_public(db, row)


def update_validation(
    db: Session,
    *,
    workspace_id: UUID,
    idea_id: UUID,
    validation_id: UUID,
    user_id: UUID,
    payload: IdeaValidationUpdateRequest,
) -> IdeaValidationPublic:
    _idea, access = _get_readable_idea(
        db, workspace_id=workspace_id, idea_id=idea_id, user_id=user_id
    )
    _require_mutate_access(access)

    row = _lock_validation(
        db, workspace_id=workspace_id, idea_id=idea_id, validation_id=validation_id
    )
    fields_set = payload.model_fields_set
    if not fields_set:
        return _to_public(db, row)

    if row.status in {
        IdeaValidationStatus.COMPLETED.value,
        IdeaValidationStatus.CANCELLED.value,
    }:
        raise AppError(
            "Validation is not editable in the current status.",
            code="VALIDATION_NOT_EDITABLE",
            status_code=409,
        )

    if row.status == IdeaValidationStatus.RUNNING.value:
        forbidden = fields_set - _RUNNING_EDITABLE_FIELDS
        if forbidden:
            raise AppError(
                "Only planned_evidence and due_date can be edited while RUNNING.",
                code="VALIDATION_NOT_EDITABLE",
                status_code=409,
            )

    unknown = fields_set - _PLAN_FIELDS
    if unknown:
        raise AppError(
            "Unsupported validation fields.",
            code="VALIDATION_INVALID",
            status_code=400,
        )

    if "title" in fields_set and payload.title is not None:
        row.title = _require_non_empty(payload.title, field="title")
    if "hypothesis" in fields_set and payload.hypothesis is not None:
        row.hypothesis = _require_non_empty(payload.hypothesis, field="hypothesis")
    if "method" in fields_set and payload.method is not None:
        row.method = _require_non_empty(payload.method, field="method")
    if "success_criteria" in fields_set and payload.success_criteria is not None:
        row.success_criteria = _require_non_empty(
            payload.success_criteria, field="success_criteria"
        )
    if "planned_evidence" in fields_set:
        row.planned_evidence = payload.planned_evidence
    if "due_date" in fields_set:
        row.due_date = payload.due_date

    db.flush()
    return _to_public(db, row)


def mark_ready(
    db: Session,
    *,
    workspace_id: UUID,
    idea_id: UUID,
    validation_id: UUID,
    user_id: UUID,
) -> IdeaValidationPublic:
    _idea, access = _get_readable_idea(
        db, workspace_id=workspace_id, idea_id=idea_id, user_id=user_id
    )
    _require_mutate_access(access)
    row = _lock_validation(
        db, workspace_id=workspace_id, idea_id=idea_id, validation_id=validation_id
    )

    if row.status == IdeaValidationStatus.READY.value:
        return _to_public(db, row)

    _assert_transition(row.status, IdeaValidationStatus.READY.value)
    _require_non_empty(row.title, field="title")
    _require_non_empty(row.hypothesis, field="hypothesis")
    _require_non_empty(row.method, field="method")
    _require_non_empty(row.success_criteria, field="success_criteria")

    row.status = IdeaValidationStatus.READY.value
    db.flush()
    return _to_public(db, row)


def _stage_by_slug(db: Session, *, workspace_id: UUID, slug: str) -> WorkspaceStage:
    stage = db.scalar(
        select(WorkspaceStage).where(
            WorkspaceStage.workspace_id == workspace_id,
            WorkspaceStage.slug == slug,
            WorkspaceStage.deleted_at.is_(None),
        )
    )
    if stage is None:
        raise AppError(
            f"Workspace stage '{slug}' is not configured.",
            code="WORKSPACE_STAGE_CONFIGURATION_INVALID",
            status_code=500,
        )
    return stage


def start_validation(
    db: Session,
    *,
    workspace_id: UUID,
    idea_id: UUID,
    validation_id: UUID,
    user_id: UUID,
) -> IdeaValidationStartResponse:
    _idea, access = _get_readable_idea(
        db, workspace_id=workspace_id, idea_id=idea_id, user_id=user_id
    )
    _require_mutate_access(access)

    # Lock parent Idea before Validation so stage checks use fresh DB state.
    idea = _lock_idea_for_update(db, workspace_id=workspace_id, idea_id=idea_id)
    row = _lock_validation_row(db, idea_id=idea_id, validation_id=validation_id)

    if row.status == IdeaValidationStatus.RUNNING.value:
        return IdeaValidationStartResponse(
            validation=_to_public(db, row),
            idea_stage=_stage_ref_for_idea(db, idea),
        )

    _assert_transition(row.status, IdeaValidationStatus.RUNNING.value)

    current_stage = db.get(WorkspaceStage, idea.stage_id)
    if current_stage is None or current_stage.deleted_at is not None:
        raise AppError("Idea stage not found.", code="INVALID_IDEA_REFERENCE", status_code=500)

    if current_stage.slug not in {"validation_candidate", "validating"}:
        raise AppError(
            "Idea stage must be validation_candidate or validating to start validation.",
            code="IDEA_NOT_READY_FOR_VALIDATION",
            status_code=409,
        )

    if current_stage.slug == "validation_candidate":
        validating = _stage_by_slug(db, workspace_id=workspace_id, slug="validating")
        idea.stage_id = validating.id
        current_stage = validating

    row.status = IdeaValidationStatus.RUNNING.value
    row.started_at = utcnow()
    db.flush()
    return IdeaValidationStartResponse(
        validation=_to_public(db, row),
        idea_stage=StageRef(
            id=current_stage.id, label=current_stage.label, slug=current_stage.slug
        ),
    )


def complete_validation(
    db: Session,
    *,
    workspace_id: UUID,
    idea_id: UUID,
    validation_id: UUID,
    user_id: UUID,
    payload: IdeaValidationCompleteRequest,
) -> IdeaValidationPublic:
    _idea, access = _get_readable_idea(
        db, workspace_id=workspace_id, idea_id=idea_id, user_id=user_id
    )
    _require_mutate_access(access)
    row = _lock_validation(
        db, workspace_id=workspace_id, idea_id=idea_id, validation_id=validation_id
    )

    _assert_transition(row.status, IdeaValidationStatus.COMPLETED.value)
    result_summary = _require_non_empty(payload.result_summary, field="result_summary")

    row.status = IdeaValidationStatus.COMPLETED.value
    row.outcome = payload.outcome.value
    row.result_summary = result_summary
    row.evidence_summary = payload.evidence_summary
    row.completed_at = utcnow()
    db.flush()
    return _to_public(db, row)


def cancel_validation(
    db: Session,
    *,
    workspace_id: UUID,
    idea_id: UUID,
    validation_id: UUID,
    user_id: UUID,
) -> IdeaValidationPublic:
    _idea, access = _get_readable_idea(
        db, workspace_id=workspace_id, idea_id=idea_id, user_id=user_id
    )
    _require_mutate_access(access)
    row = _lock_validation(
        db, workspace_id=workspace_id, idea_id=idea_id, validation_id=validation_id
    )

    if row.status == IdeaValidationStatus.CANCELLED.value:
        return _to_public(db, row)

    _assert_transition(row.status, IdeaValidationStatus.CANCELLED.value)
    row.status = IdeaValidationStatus.CANCELLED.value
    row.outcome = None
    row.completed_at = None
    db.flush()
    return _to_public(db, row)


def revert_to_draft(
    db: Session,
    *,
    workspace_id: UUID,
    idea_id: UUID,
    validation_id: UUID,
    user_id: UUID,
) -> IdeaValidationPublic:
    """Optional READY → DRAFT transition (edit after ready)."""
    _idea, access = _get_readable_idea(
        db, workspace_id=workspace_id, idea_id=idea_id, user_id=user_id
    )
    _require_mutate_access(access)
    row = _lock_validation(
        db, workspace_id=workspace_id, idea_id=idea_id, validation_id=validation_id
    )
    _assert_transition(row.status, IdeaValidationStatus.DRAFT.value)
    row.status = IdeaValidationStatus.DRAFT.value
    db.flush()
    return _to_public(db, row)


def count_validations(db: Session, *, idea_id: UUID) -> int:
    return int(
        db.scalar(
            select(func.count()).select_from(IdeaValidation).where(IdeaValidation.idea_id == idea_id)
        )
        or 0
    )
