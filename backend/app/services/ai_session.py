"""IdeaAiSession domain service (Step 7)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.llm.prompts import IDEA_STRUCTURE_PROMPT_VERSION
from app.llm.refine_prompts import IDEA_REFINE_PROMPT_VERSION, direction_label_ko
from app.llm.refine_schemas import REFINE_PATCH_FIELDS, build_idea_source_snapshot
from app.models.ai import AiJob, IdeaAiSession
from app.models.enums import (
    AiJobStatus,
    AiJobType,
    FieldProvenanceSource,
    IdeaAiSessionPurpose,
    IdeaAiSessionStatus,
    IdeaRefineDirection,
    IdeaVisibility,
)
from app.models.idea import Idea
from app.models.relations import IdeaTag
from app.models.user import User
from app.models.workspace import Tag, Workspace, WorkspaceCategory
from app.schemas.ai import (
    AiRefineApplyRequest,
    AiRefineApplyResponse,
    AiSessionConfirmRequest,
    AiSessionConfirmResponse,
    AiSessionCreate,
    AiSessionFailurePublic,
    AiSessionLlmPublic,
    AiSessionPublic,
    AiSessionReviewDraftSaveRequest,
    ClarificationSubmit,
)
from app.schemas.idea import IdeaCreate, IdeaUpdate
from app.services import idea as idea_service
from app.services import idea_access
from app.services import system_setting as system_setting_service

_DRAFT_COMPARE_FIELDS = (
    "title",
    "one_line_definition",
    "background",
    "problem",
    "core_concept",
    "major_features",
    "expected_effect",
    "target_users",
    "scenarios",
    "challenges",
    "minimum_validation",
    "related_project",
    "priority",
    "feasibility",
)

REFINE_SOURCE_CHANGED_MESSAGE = (
    "원본 아이디어가 변경되어 이 발전 결과를 적용할 수 없습니다. "
    "다시 발전시켜 주세요."
)
REFINE_NO_CHANGES_MESSAGE = "변경된 내용이 없습니다. 적용할 내용을 확인해 주세요."


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _require_llm_enabled(db: Session, workspace: Workspace) -> None:
    system_setting_service.require_global_llm_enabled(db)
    if not workspace.allow_llm:
        raise AppError(
            "LLM is disabled for this workspace.",
            code="WORKSPACE_LLM_DISABLED",
            status_code=403,
        )


def get_session_for_requester(
    db: Session,
    *,
    workspace_id: UUID,
    session_id: UUID,
    user_id: UUID,
    for_update: bool = False,
) -> IdeaAiSession:
    """Requester-only access. ADMIN / SYSTEM_ADMIN do not bypass."""
    stmt = select(IdeaAiSession).where(
        IdeaAiSession.id == session_id,
        IdeaAiSession.workspace_id == workspace_id,
    )
    if for_update:
        stmt = stmt.with_for_update()
    session = db.execute(stmt).scalar_one_or_none()
    if session is None or session.requester_id != user_id:
        raise AppError(
            "AI session not found.",
            code="AI_SESSION_NOT_FOUND",
            status_code=404,
        )
    return session


def _assert_transition(current: str, target: str) -> None:
    allowed: dict[str, set[str]] = {
        IdeaAiSessionStatus.PROCESSING.value: {
            IdeaAiSessionStatus.NEEDS_CLARIFICATION.value,
            IdeaAiSessionStatus.READY_FOR_REVIEW.value,
            IdeaAiSessionStatus.FAILED.value,
            IdeaAiSessionStatus.CANCELLED.value,
        },
        IdeaAiSessionStatus.NEEDS_CLARIFICATION.value: {
            IdeaAiSessionStatus.PROCESSING.value,
            IdeaAiSessionStatus.CANCELLED.value,
        },
        IdeaAiSessionStatus.FAILED.value: {
            IdeaAiSessionStatus.PROCESSING.value,
            IdeaAiSessionStatus.CANCELLED.value,
        },
        IdeaAiSessionStatus.READY_FOR_REVIEW.value: {
            IdeaAiSessionStatus.CONFIRMED.value,
            IdeaAiSessionStatus.CANCELLED.value,
        },
        IdeaAiSessionStatus.CONFIRMED.value: set(),
        IdeaAiSessionStatus.CANCELLED.value: set(),
    }
    if target not in allowed.get(current, set()):
        raise AppError(
            f"Invalid AI session transition: {current} → {target}",
            code="AI_SESSION_INVALID_STATE",
            status_code=409,
        )


def create_ai_session(
    db: Session,
    *,
    workspace: Workspace,
    requester: User,
    payload: AiSessionCreate,
    settings: Settings | None = None,
) -> IdeaAiSession:
    _require_llm_enabled(db, workspace)
    if payload.purpose != IdeaAiSessionPurpose.CREATE:
        raise AppError(
            "Only purpose=CREATE is supported.",
            code="AI_SESSION_INVALID_STATE",
            status_code=400,
        )

    cfg = settings or get_settings()
    session = IdeaAiSession(
        workspace_id=workspace.id,
        requester_id=requester.id,
        purpose=IdeaAiSessionPurpose.CREATE.value,
        status=IdeaAiSessionStatus.PROCESSING.value,
        input_text=payload.input_text,
        research_recommended=False,
        research_topics=[],
        prompt_version=IDEA_STRUCTURE_PROMPT_VERSION,
    )
    db.add(session)
    db.flush()

    job = AiJob(
        session_id=session.id,
        job_type=AiJobType.STRUCTURE_IDEA.value,
        status=AiJobStatus.QUEUED.value,
        attempts=0,
        max_attempts=cfg.ai_job_max_attempts,
        available_at=utcnow(),
    )
    db.add(job)
    db.flush()
    return session


def _idea_tag_names(db: Session, idea_id: UUID) -> list[str]:
    return list(
        db.scalars(
            select(Tag.name)
            .join(IdeaTag, IdeaTag.tag_id == Tag.id)
            .where(IdeaTag.idea_id == idea_id)
            .order_by(Tag.name)
        )
    )


def build_source_snapshot(db: Session, idea: Idea) -> dict[str, Any]:
    """AI-facing snapshot of a registered Idea (Step 17 REFINE source)."""
    category_slug: str | None = None
    if idea.category_id is not None:
        category = db.get(WorkspaceCategory, idea.category_id)
        if category is not None and category.deleted_at is None:
            category_slug = category.slug
    snapshot = build_idea_source_snapshot(idea, category_slug=category_slug)
    snapshot["tags"] = _idea_tag_names(db, idea.id)
    return snapshot


def _job_type_for_session(session: IdeaAiSession) -> str:
    if session.purpose == IdeaAiSessionPurpose.REFINE.value:
        return AiJobType.REFINE_IDEA.value
    return AiJobType.STRUCTURE_IDEA.value


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _require_unchanged_source(idea: Idea, session: IdeaAiSession) -> None:
    if _as_utc(idea.updated_at) != _as_utc(session.source_idea_updated_at):
        raise AppError(
            REFINE_SOURCE_CHANGED_MESSAGE,
            code="AI_REFINE_SOURCE_CHANGED",
            status_code=409,
        )


def _load_refine_source_idea(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    session: IdeaAiSession,
    for_update: bool = False,
) -> tuple[Idea, str]:
    """Re-check source existence + edit permission, then compare freshness."""
    if session.source_idea_id is None:
        raise AppError(
            "AI session has no source idea.",
            code="AI_SESSION_INVALID_STATE",
            status_code=409,
        )
    if for_update:
        # populate_existing keeps the locked row authoritative for the freshness check.
        locked = db.execute(
            select(Idea)
            .where(Idea.id == session.source_idea_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if locked is None or locked.deleted_at is not None or locked.workspace_id != workspace.id:
            raise AppError("Idea not found.", code="IDEA_NOT_FOUND", status_code=404)

    idea, _share, access = idea_service.require_idea_edit(
        db,
        workspace_id=workspace.id,
        idea_id=session.source_idea_id,
        user_id=user.id,
    )
    _require_unchanged_source(idea, session)
    return idea, access


def create_refine_ai_session(
    db: Session,
    *,
    workspace: Workspace,
    requester: User,
    idea_id: UUID,
    direction: IdeaRefineDirection,
    settings: Settings | None = None,
) -> IdeaAiSession:
    """Start an AI refinement session for an already-registered Idea."""
    _require_llm_enabled(db, workspace)
    cfg = settings or get_settings()

    idea, _share, _access = idea_service.require_idea_edit(
        db,
        workspace_id=workspace.id,
        idea_id=idea_id,
        user_id=requester.id,
    )

    session = IdeaAiSession(
        workspace_id=workspace.id,
        requester_id=requester.id,
        purpose=IdeaAiSessionPurpose.REFINE.value,
        status=IdeaAiSessionStatus.PROCESSING.value,
        input_text=f"발전 방향: {direction_label_ko(direction.value)}",
        source_idea_id=idea.id,
        source_idea_updated_at=idea.updated_at,
        source_idea_snapshot=build_source_snapshot(db, idea),
        refine_direction=direction.value,
        result_idea_id=None,
        research_recommended=False,
        research_topics=[],
        prompt_version=IDEA_REFINE_PROMPT_VERSION,
    )
    db.add(session)
    db.flush()

    db.add(
        AiJob(
            session_id=session.id,
            job_type=AiJobType.REFINE_IDEA.value,
            status=AiJobStatus.QUEUED.value,
            attempts=0,
            max_attempts=cfg.ai_job_max_attempts,
            available_at=utcnow(),
        )
    )
    db.flush()
    return session


def submit_clarifications(
    db: Session,
    *,
    workspace: Workspace,
    user_id: UUID,
    session_id: UUID,
    payload: ClarificationSubmit,
    settings: Settings | None = None,
) -> IdeaAiSession:
    _require_llm_enabled(db, workspace)
    cfg = settings or get_settings()
    session = get_session_for_requester(
        db,
        workspace_id=workspace.id,
        session_id=session_id,
        user_id=user_id,
        for_update=True,
    )
    if session.status != IdeaAiSessionStatus.NEEDS_CLARIFICATION.value:
        raise AppError(
            "AI session is not awaiting clarification.",
            code="AI_SESSION_INVALID_STATE",
            status_code=409,
        )

    questions = session.clarifying_questions or []
    valid_ids = {q.get("id") for q in questions if isinstance(q, dict)}
    for answer in payload.answers:
        if answer.question_id not in valid_ids:
            raise AppError(
                "Unknown clarification question_id.",
                code="AI_CLARIFICATION_INVALID",
                status_code=400,
            )

    answers = [
        {"question_id": a.question_id, "answer": a.answer} for a in payload.answers
    ]
    existing = list(session.clarification_answers or [])
    existing.extend(answers)
    session.clarification_answers = existing

    _assert_transition(session.status, IdeaAiSessionStatus.PROCESSING.value)
    session.status = IdeaAiSessionStatus.PROCESSING.value
    session.failure_code = None
    session.failure_message = None

    db.add(
        AiJob(
            session_id=session.id,
            job_type=_job_type_for_session(session),
            status=AiJobStatus.QUEUED.value,
            attempts=0,
            max_attempts=cfg.ai_job_max_attempts,
            available_at=utcnow(),
        )
    )
    db.flush()
    return session


def retry_ai_session(
    db: Session,
    *,
    workspace: Workspace,
    user_id: UUID,
    session_id: UUID,
    settings: Settings | None = None,
) -> IdeaAiSession:
    _require_llm_enabled(db, workspace)
    cfg = settings or get_settings()
    session = get_session_for_requester(
        db,
        workspace_id=workspace.id,
        session_id=session_id,
        user_id=user_id,
        for_update=True,
    )
    if session.status != IdeaAiSessionStatus.FAILED.value:
        raise AppError(
            "Only FAILED sessions can be retried.",
            code="AI_SESSION_INVALID_STATE",
            status_code=409,
        )

    _assert_transition(session.status, IdeaAiSessionStatus.PROCESSING.value)
    session.status = IdeaAiSessionStatus.PROCESSING.value
    session.failure_code = None
    session.failure_message = None

    db.add(
        AiJob(
            session_id=session.id,
            job_type=_job_type_for_session(session),
            status=AiJobStatus.QUEUED.value,
            attempts=0,
            max_attempts=cfg.ai_job_max_attempts,
            available_at=utcnow(),
        )
    )
    db.flush()
    return session


def sanitize_draft_category(
    db: Session,
    *,
    workspace_id: UUID,
    draft: dict[str, Any],
) -> dict[str, Any]:
    """Drop invalid category_slug instead of persisting unknown values."""
    out = dict(draft)
    slug = out.get("category_slug")
    if slug is None or slug == "":
        out["category_slug"] = None
        return out
    category = db.execute(
        select(WorkspaceCategory).where(
            WorkspaceCategory.workspace_id == workspace_id,
            WorkspaceCategory.slug == slug,
            WorkspaceCategory.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
    if category is None:
        out["category_slug"] = None
    return out


def assign_question_ids(raw_questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for idx, q in enumerate(raw_questions, start=1):
        result.append(
            {
                "id": f"q{idx}",
                "field": q.get("field"),
                "question": q.get("question"),
            }
        )
    return result


def to_public(session: IdeaAiSession) -> AiSessionPublic:
    failure = None
    if session.status == IdeaAiSessionStatus.FAILED.value and session.failure_code:
        failure = AiSessionFailurePublic(
            code=session.failure_code,
            message=session.failure_message
            or "AI 처리 중 일시적인 오류가 발생했습니다.",
        )
    topics = session.research_topics
    if topics is not None and not isinstance(topics, list):
        topics = []
    return AiSessionPublic(
        id=session.id,
        workspace_id=session.workspace_id,
        purpose=IdeaAiSessionPurpose(session.purpose),
        status=IdeaAiSessionStatus(session.status),
        input_text=session.input_text,
        draft=session.draft_payload,
        field_provenance=session.field_provenance,
        clarifying_questions=session.clarifying_questions,
        clarification_answers=session.clarification_answers,
        research_recommended=bool(session.research_recommended),
        research_topics=list(topics) if topics else [],
        review_state=session.review_state,
        review_saved_at=session.review_saved_at,
        result_idea_id=session.result_idea_id,
        failure=failure,
        llm=AiSessionLlmPublic(
            provider=session.llm_provider,
            model=session.llm_model,
            prompt_version=session.prompt_version,
        ),
        source_idea_id=session.source_idea_id,
        source_idea_updated_at=session.source_idea_updated_at,
        source_idea_snapshot=session.source_idea_snapshot,
        refine_direction=(
            IdeaRefineDirection(session.refine_direction)
            if session.refine_direction
            else None
        ),
        created_at=session.created_at,
        updated_at=session.updated_at,
        ready_at=session.ready_at,
        confirmed_at=session.confirmed_at,
    )


def _confirm_payload_dict(body: AiSessionConfirmRequest) -> dict[str, Any]:
    data = body.model_dump(mode="json")
    # Normalize enum values already handled by mode=json
    return data


def _merge_user_edit_provenance(
    original: dict[str, Any] | None,
    draft: dict[str, Any] | None,
    confirm: AiSessionConfirmRequest | AiRefineApplyRequest,
) -> dict[str, Any]:
    provenance = dict(original or {})
    draft = draft or {}
    for field in _DRAFT_COMPARE_FIELDS:
        draft_val = draft.get(field)
        confirm_val = getattr(confirm, field)
        if hasattr(confirm_val, "value"):
            confirm_val = confirm_val.value
        # Normalize empty string / None
        if draft_val == "":
            draft_val = None
        if confirm_val == "":
            confirm_val = None
        if draft_val != confirm_val:
            prev = provenance.get(field) if isinstance(provenance.get(field), dict) else {}
            provenance[field] = {
                "original_source": prev.get("source") or prev.get("original_source"),
                "final_source": FieldProvenanceSource.USER_EDIT.value,
                "source": FieldProvenanceSource.USER_EDIT.value,
                "note": prev.get("note"),
            }
    # tags
    draft_tags = draft.get("tags") or []
    if list(draft_tags) != list(confirm.tags):
        prev = provenance.get("tags") if isinstance(provenance.get("tags"), dict) else {}
        provenance["tags"] = {
            "original_source": prev.get("source") or prev.get("original_source"),
            "final_source": FieldProvenanceSource.USER_EDIT.value,
            "source": FieldProvenanceSource.USER_EDIT.value,
            "note": prev.get("note"),
        }
    return provenance


def _apply_edited_fields_provenance(
    provenance: dict[str, Any] | None,
    edited_fields: list[str],
) -> dict[str, Any]:
    result = dict(provenance or {})
    for field in edited_fields:
        if field not in _DRAFT_COMPARE_FIELDS and field != "tags":
            continue
        prev = result.get(field) if isinstance(result.get(field), dict) else {}
        original_source = (
            prev.get("original_source")
            or prev.get("source")
            or prev.get("final_source")
        )
        entry: dict[str, Any] = {
            "original_source": original_source,
            "final_source": FieldProvenanceSource.USER_EDIT.value,
            "source": FieldProvenanceSource.USER_EDIT.value,
            "note": prev.get("note"),
        }
        if prev.get("evidence_ids"):
            entry["evidence_ids"] = prev.get("evidence_ids")
        result[field] = entry
    return result


def _review_state_dict(payload: AiSessionReviewDraftSaveRequest) -> dict[str, Any]:
    rs = payload.review_state
    return {
        "category_id": str(rs.category_id) if rs.category_id else None,
        "stage_id": str(rs.stage_id) if rs.stage_id else None,
        "visibility": rs.visibility.value,
        "assignee_id": str(rs.assignee_id) if rs.assignee_id else None,
        "next_review_date": rs.next_review_date.isoformat() if rs.next_review_date else None,
        "shares": [
            {"user_id": str(share.user_id), "permission": share.permission.value}
            for share in rs.shares
        ],
        "edited_fields": list(rs.edited_fields),
    }


def save_review_draft(
    db: Session,
    *,
    workspace: Workspace,
    user_id: UUID,
    session_id: UUID,
    payload: AiSessionReviewDraftSaveRequest,
) -> IdeaAiSession:
    session = get_session_for_requester(
        db,
        workspace_id=workspace.id,
        session_id=session_id,
        user_id=user_id,
        for_update=True,
    )
    if session.status != IdeaAiSessionStatus.READY_FOR_REVIEW.value:
        raise AppError(
            "AI session is not ready for review draft save.",
            code="AI_SESSION_INVALID_STATE",
            status_code=409,
        )

    draft_data = payload.draft.model_dump(mode="json")
    session.draft_payload = sanitize_draft_category(
        db,
        workspace_id=workspace.id,
        draft=draft_data,
    )
    session.field_provenance = _apply_edited_fields_provenance(
        session.field_provenance,
        payload.review_state.edited_fields,
    )
    session.review_state = _review_state_dict(payload)
    session.review_saved_at = utcnow()
    db.flush()
    return session


def regenerate_ai_session(
    db: Session,
    *,
    workspace: Workspace,
    requester: User,
    session_id: UUID,
    settings: Settings | None = None,
) -> IdeaAiSession:
    _require_llm_enabled(db, workspace)
    cfg = settings or get_settings()

    session = get_session_for_requester(
        db,
        workspace_id=workspace.id,
        session_id=session_id,
        user_id=requester.id,
        for_update=True,
    )
    if session.status != IdeaAiSessionStatus.READY_FOR_REVIEW.value:
        raise AppError(
            "Only READY_FOR_REVIEW sessions can be regenerated.",
            code="AI_SESSION_INVALID_STATE",
            status_code=409,
        )

    from app.services import web_research as web_research_service

    if web_research_service.has_blocking_research_for_regenerate(db, session.id):
        raise AppError(
            "Complete or cancel in-progress web research before regenerating.",
            code="AI_REGENERATE_RESEARCH_ACTIVE",
            status_code=409,
        )

    if session.purpose == IdeaAiSessionPurpose.REFINE.value:
        idea, _access = _load_refine_source_idea(
            db,
            workspace=workspace,
            user=requester,
            session=session,
        )
        new_session = IdeaAiSession(
            workspace_id=workspace.id,
            requester_id=requester.id,
            purpose=IdeaAiSessionPurpose.REFINE.value,
            status=IdeaAiSessionStatus.PROCESSING.value,
            input_text=session.input_text,
            source_idea_id=idea.id,
            source_idea_updated_at=session.source_idea_updated_at,
            source_idea_snapshot=session.source_idea_snapshot,
            refine_direction=session.refine_direction,
            research_recommended=False,
            research_topics=[],
            prompt_version=IDEA_REFINE_PROMPT_VERSION,
        )
        job_type = AiJobType.REFINE_IDEA.value
    else:
        new_session = IdeaAiSession(
            workspace_id=workspace.id,
            requester_id=requester.id,
            purpose=IdeaAiSessionPurpose.CREATE.value,
            status=IdeaAiSessionStatus.PROCESSING.value,
            input_text=session.input_text,
            clarifying_questions=session.clarifying_questions,
            clarification_answers=session.clarification_answers,
            research_recommended=False,
            research_topics=[],
            prompt_version=IDEA_STRUCTURE_PROMPT_VERSION,
        )
        job_type = AiJobType.STRUCTURE_IDEA.value

    db.add(new_session)
    db.flush()

    db.add(
        AiJob(
            session_id=new_session.id,
            job_type=job_type,
            status=AiJobStatus.QUEUED.value,
            attempts=0,
            max_attempts=cfg.ai_job_max_attempts,
            available_at=utcnow(),
        )
    )
    db.flush()
    return new_session


def confirm_ai_session(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    session_id: UUID,
    payload: AiSessionConfirmRequest,
) -> AiSessionConfirmResponse:
    """Confirm creates exactly one Idea (row lock + result_idea_id check)."""
    session = get_session_for_requester(
        db,
        workspace_id=workspace.id,
        session_id=session_id,
        user_id=user.id,
        for_update=True,
    )

    if session.result_idea_id is not None:
        idea = db.get(Idea, session.result_idea_id)
        if idea is None or idea.deleted_at is not None or idea.workspace_id != workspace.id:
            raise AppError(
                "Confirmed idea was deleted.",
                code="AI_SESSION_RESULT_IDEA_DELETED",
                status_code=409,
            )
        detail = idea_service.to_detail(db, idea, user_id=user.id, share=None)
        return AiSessionConfirmResponse(created=False, idea=detail)

    if session.status != IdeaAiSessionStatus.READY_FOR_REVIEW.value:
        raise AppError(
            "AI session is not ready for confirm.",
            code="AI_SESSION_INVALID_STATE",
            status_code=409,
        )

    from app.services import web_research as web_research_service

    if web_research_service.has_active_research(db, session.id):
        raise AppError(
            "Web research is in progress.",
            code="AI_RESEARCH_IN_PROGRESS",
            status_code=409,
        )

    if payload.visibility is None:
        visibility = IdeaVisibility.PRIVATE
    else:
        visibility = payload.visibility

    idea_payload = IdeaCreate(
        title=payload.title,
        one_line_definition=payload.one_line_definition,
        original_text=session.input_text,
        background=payload.background,
        problem=payload.problem,
        core_concept=payload.core_concept,
        major_features=payload.major_features,
        expected_effect=payload.expected_effect,
        target_users=payload.target_users,
        scenarios=payload.scenarios,
        challenges=payload.challenges,
        minimum_validation=payload.minimum_validation,
        related_project=payload.related_project,
        category_id=payload.category_id,
        stage_id=payload.stage_id,
        priority=payload.priority,
        feasibility=payload.feasibility,
        visibility=visibility,
        assignee_id=payload.assignee_id,
        next_review_date=payload.next_review_date,
        tags=payload.tags,
        shares=payload.shares,
    )

    try:
        idea = idea_service.create_idea(
            db,
            workspace_id=workspace.id,
            author=user,
            payload=idea_payload,
        )
    except AppError as exc:
        # Remap validation to AI confirm code when appropriate
        if exc.code in {"INVALID_IDEA_REFERENCE", "INVALID_TAG", "ASSIGNEE_NOT_ELIGIBLE"}:
            raise AppError(exc.message, code="AI_CONFIRM_INVALID", status_code=400) from exc
        raise

    session.result_idea_id = idea.id
    _assert_transition(session.status, IdeaAiSessionStatus.CONFIRMED.value)
    session.status = IdeaAiSessionStatus.CONFIRMED.value
    session.confirmed_payload = _confirm_payload_dict(payload)
    session.field_provenance = _merge_user_edit_provenance(
        session.field_provenance,
        session.draft_payload,
        payload,
    )
    session.confirmed_at = utcnow()
    db.flush()

    detail = idea_service.to_detail(db, idea, user_id=user.id, share=None)
    return AiSessionConfirmResponse(created=True, idea=detail)


def _normalize_refine_value(value: Any) -> Any:
    if hasattr(value, "value"):
        value = value.value
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, list):
        return sorted({str(v).strip() for v in value if str(v).strip()})
    return value


def _refine_payload_snapshot(
    db: Session,
    *,
    workspace_id: UUID,
    payload: AiRefineApplyRequest,
) -> dict[str, Any]:
    category_slug: str | None = None
    if payload.category_id is not None:
        category = db.get(WorkspaceCategory, payload.category_id)
        if (
            category is not None
            and category.deleted_at is None
            and category.workspace_id == workspace_id
        ):
            category_slug = category.slug
    snapshot = {field: getattr(payload, field, None) for field in REFINE_PATCH_FIELDS}
    snapshot["category_slug"] = category_slug
    return snapshot


def _refine_changes_source(
    *,
    source_snapshot: dict[str, Any],
    payload_snapshot: dict[str, Any],
) -> bool:
    for field in REFINE_PATCH_FIELDS:
        old = _normalize_refine_value(source_snapshot.get(field))
        new = _normalize_refine_value(payload_snapshot.get(field))
        if field == "tags":
            old = old or []
            new = new or []
        if old != new:
            return True
    return False


def apply_refinement(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    session_id: UUID,
    payload: AiRefineApplyRequest,
) -> AiRefineApplyResponse:
    """Apply a reviewed REFINE draft back onto its source Idea (idempotent)."""
    session = get_session_for_requester(
        db,
        workspace_id=workspace.id,
        session_id=session_id,
        user_id=user.id,
        for_update=True,
    )

    if (
        session.status == IdeaAiSessionStatus.CONFIRMED.value
        and session.result_idea_id is not None
    ):
        applied = db.get(Idea, session.result_idea_id)
        if (
            applied is None
            or applied.deleted_at is not None
            or applied.workspace_id != workspace.id
        ):
            raise AppError(
                "Refined idea was deleted.",
                code="AI_SESSION_RESULT_IDEA_DELETED",
                status_code=409,
            )
        share = idea_access.get_idea_share(db, applied.id, user.id)
        detail = idea_service.to_detail(db, applied, user_id=user.id, share=share)
        return AiRefineApplyResponse(updated=False, idea=detail)

    if session.purpose != IdeaAiSessionPurpose.REFINE.value:
        raise AppError(
            "Only purpose=REFINE sessions can be applied.",
            code="AI_SESSION_INVALID_STATE",
            status_code=400,
        )
    if session.status != IdeaAiSessionStatus.READY_FOR_REVIEW.value:
        raise AppError(
            "AI session is not ready to apply.",
            code="AI_SESSION_INVALID_STATE",
            status_code=409,
        )

    from app.services import web_research as web_research_service

    if web_research_service.has_blocking_research_for_regenerate(db, session.id):
        raise AppError(
            "Complete or cancel in-progress web research before applying.",
            code="AI_RESEARCH_IN_PROGRESS",
            status_code=409,
        )

    idea, access = _load_refine_source_idea(
        db,
        workspace=workspace,
        user=user,
        session=session,
        for_update=True,
    )

    source_snapshot = dict(session.source_idea_snapshot or {})
    payload_snapshot = _refine_payload_snapshot(
        db, workspace_id=workspace.id, payload=payload
    )
    if not _refine_changes_source(
        source_snapshot=source_snapshot,
        payload_snapshot=payload_snapshot,
    ):
        raise AppError(
            REFINE_NO_CHANGES_MESSAGE,
            code="AI_REFINE_NO_CHANGES",
            status_code=400,
        )

    idea = idea_service.update_idea(
        db,
        idea=idea,
        access=access,
        payload=IdeaUpdate(
            title=payload.title,
            one_line_definition=payload.one_line_definition,
            background=payload.background,
            problem=payload.problem,
            core_concept=payload.core_concept,
            major_features=payload.major_features,
            expected_effect=payload.expected_effect,
            target_users=payload.target_users,
            scenarios=payload.scenarios,
            challenges=payload.challenges,
            minimum_validation=payload.minimum_validation,
            related_project=payload.related_project,
            category_id=payload.category_id,
            priority=payload.priority,
            feasibility=payload.feasibility,
            tags=payload.tags,
        ),
    )

    session.result_idea_id = idea.id
    _assert_transition(session.status, IdeaAiSessionStatus.CONFIRMED.value)
    session.status = IdeaAiSessionStatus.CONFIRMED.value
    session.confirmed_payload = payload.model_dump(mode="json")
    session.field_provenance = _merge_user_edit_provenance(
        session.field_provenance,
        session.draft_payload,
        payload,
    )
    session.confirmed_at = utcnow()
    db.flush()

    share = idea_access.get_idea_share(db, idea.id, user.id)
    detail = idea_service.to_detail(db, idea, user_id=user.id, share=share)
    return AiRefineApplyResponse(updated=True, idea=detail)
