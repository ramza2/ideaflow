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
from app.models.ai import AiJob, IdeaAiSession
from app.models.enums import (
    AiJobStatus,
    AiJobType,
    FieldProvenanceSource,
    IdeaAiSessionPurpose,
    IdeaAiSessionStatus,
    IdeaVisibility,
)
from app.models.idea import Idea
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceCategory
from app.schemas.ai import (
    AiSessionConfirmRequest,
    AiSessionConfirmResponse,
    AiSessionCreate,
    AiSessionFailurePublic,
    AiSessionLlmPublic,
    AiSessionPublic,
    ClarificationSubmit,
)
from app.schemas.idea import IdeaCreate
from app.services import idea as idea_service

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


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _require_llm_enabled(workspace: Workspace) -> None:
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
    _require_llm_enabled(workspace)
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


def submit_clarifications(
    db: Session,
    *,
    workspace: Workspace,
    user_id: UUID,
    session_id: UUID,
    payload: ClarificationSubmit,
    settings: Settings | None = None,
) -> IdeaAiSession:
    _require_llm_enabled(workspace)
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
            job_type=AiJobType.STRUCTURE_IDEA.value,
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
    _require_llm_enabled(workspace)
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
            job_type=AiJobType.STRUCTURE_IDEA.value,
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
        result_idea_id=session.result_idea_id,
        failure=failure,
        llm=AiSessionLlmPublic(
            provider=session.llm_provider,
            model=session.llm_model,
            prompt_version=session.prompt_version,
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
    confirm: AiSessionConfirmRequest,
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
