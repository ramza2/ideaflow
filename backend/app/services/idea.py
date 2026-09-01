"""Idea domain service — CRUD, tags, shares, search, idea_code."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.enums import (
    IdeaSharePermission,
    IdeaVisibility,
    UserStatus,
    WorkspaceMemberStatus,
)
from app.models.idea import Idea
from app.models.relations import IdeaShare, IdeaTag
from app.models.user import User
from app.models.workspace import Tag, WorkspaceCategory, WorkspaceMember, WorkspaceStage
from app.schemas.idea import (
    CategoryRef,
    IdeaCreate,
    IdeaDetail,
    IdeaListItem,
    IdeaListResponse,
    IdeaShareInput,
    IdeaSharePublic,
    IdeaUpdate,
    IdeaUserPublic,
    StageRef,
    TagPublic,
)
from app.embeddings.canonical import embedding_fields_changed
from app.services import idea_access
from app.services.embedding_service import on_idea_embedding_content_changed

_MAX_TAGS = 20
_TAG_MAX_LEN = 64
_IDEA_CODE_RE = re.compile(r"^IF-(\d+)$")

EDIT_SHARE_FORBIDDEN_FIELDS = frozenset({"visibility", "original_text"})


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _workspace_advisory_lock_key(workspace_id: UUID) -> int:
    """Deterministic signed 64-bit key for pg_advisory_xact_lock (not Python hash())."""
    digest = hashlib.sha256(f"ideaflow:idea_code:{workspace_id}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def allocate_idea_code(db: Session, workspace_id: UUID) -> str:
    """Concurrency-safe IF-N code using transaction-scoped advisory lock."""
    key = _workspace_advisory_lock_key(workspace_id)
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})

    codes = db.scalars(select(Idea.idea_code).where(Idea.workspace_id == workspace_id)).all()
    max_n = 0
    for code in codes:
        match = _IDEA_CODE_RE.match(code)
        if match:
            max_n = max(max_n, int(match.group(1)))
    return f"IF-{max_n + 1:03d}"


def _default_stage(db: Session, workspace_id: UUID) -> WorkspaceStage:
    stages = list(
        db.scalars(
            select(WorkspaceStage).where(
                WorkspaceStage.workspace_id == workspace_id,
                WorkspaceStage.is_default.is_(True),
                WorkspaceStage.deleted_at.is_(None),
            )
        )
    )
    if len(stages) != 1:
        raise AppError(
            "Workspace default stage configuration is invalid.",
            code="WORKSPACE_STAGE_CONFIGURATION_INVALID",
            status_code=500,
        )
    return stages[0]


def _validate_stage(db: Session, workspace_id: UUID, stage_id: UUID) -> WorkspaceStage:
    stage = db.get(WorkspaceStage, stage_id)
    if (
        stage is None
        or stage.deleted_at is not None
        or stage.workspace_id != workspace_id
    ):
        raise AppError(
            "Invalid stage reference for this workspace.",
            code="INVALID_IDEA_REFERENCE",
            status_code=400,
        )
    return stage


def _validate_category(
    db: Session, workspace_id: UUID, category_id: UUID | None
) -> WorkspaceCategory | None:
    if category_id is None:
        return None
    category = db.get(WorkspaceCategory, category_id)
    if (
        category is None
        or category.deleted_at is not None
        or category.workspace_id != workspace_id
    ):
        raise AppError(
            "Invalid category reference for this workspace.",
            code="INVALID_IDEA_REFERENCE",
            status_code=400,
        )
    return category


def _validate_assignee(
    db: Session, workspace_id: UUID, assignee_id: UUID | None
) -> User | None:
    if assignee_id is None:
        return None
    user = db.get(User, assignee_id)
    if user is None or user.deleted_at is not None or user.status != UserStatus.ACTIVE.value:
        raise AppError(
            "Assignee is not eligible.",
            code="ASSIGNEE_NOT_ELIGIBLE",
            status_code=400,
        )
    membership = db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == assignee_id,
            WorkspaceMember.status == WorkspaceMemberStatus.ACTIVE.value,
        )
    )
    if membership is None:
        raise AppError(
            "Assignee is not an active workspace member.",
            code="ASSIGNEE_NOT_ELIGIBLE",
            status_code=400,
        )
    return user


def normalize_tag_names(tags: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in tags:
        name = raw.strip()
        if not name:
            continue
        if len(name) > _TAG_MAX_LEN:
            raise AppError(
                f"Tag name must be 1–{_TAG_MAX_LEN} characters.",
                code="INVALID_TAG",
                status_code=400,
            )
        if name in seen:
            continue
        seen.add(name)
        result.append(name)
    if len(result) > _MAX_TAGS:
        raise AppError(
            f"At most {_MAX_TAGS} tags are allowed.",
            code="INVALID_TAG",
            status_code=400,
        )
    return result


def sync_idea_tags(db: Session, idea: Idea, tag_names: list[str]) -> list[Tag]:
    names = normalize_tag_names(tag_names)
    tags: list[Tag] = []
    for name in names:
        tag = db.scalar(
            select(Tag).where(Tag.workspace_id == idea.workspace_id, Tag.name == name)
        )
        if tag is None:
            tag = Tag(workspace_id=idea.workspace_id, name=name)
            db.add(tag)
            db.flush()
        tags.append(tag)

    existing = list(db.scalars(select(IdeaTag).where(IdeaTag.idea_id == idea.id)))
    existing_ids = {row.tag_id for row in existing}
    desired_ids = {tag.id for tag in tags}

    for row in existing:
        if row.tag_id not in desired_ids:
            db.delete(row)
    for tag in tags:
        if tag.id not in existing_ids:
            db.add(IdeaTag(idea_id=idea.id, tag_id=tag.id))
    db.flush()
    return tags


def _validate_share_target(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    author_id: UUID,
) -> User:
    if user_id == author_id:
        raise AppError(
            "Author cannot be added to shares.",
            code="SHARE_USER_NOT_ELIGIBLE",
            status_code=400,
        )
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None or user.status != UserStatus.ACTIVE.value:
        raise AppError(
            "Share target user is not eligible.",
            code="SHARE_USER_NOT_ELIGIBLE",
            status_code=400,
        )
    membership = db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.status == WorkspaceMemberStatus.ACTIVE.value,
        )
    )
    if membership is None:
        raise AppError(
            "Share target must be an active workspace member.",
            code="SHARE_USER_NOT_ELIGIBLE",
            status_code=400,
        )
    return user


def replace_shares(
    db: Session,
    *,
    idea: Idea,
    shares: list[IdeaShareInput],
) -> list[tuple[IdeaShare, User]]:
    ids = [s.user_id for s in shares]
    if len(ids) != len(set(ids)):
        raise AppError(
            "Duplicate share user_id.",
            code="SHARE_DUPLICATE_USER",
            status_code=400,
        )

    validated: list[tuple[UUID, str, User]] = []
    for item in shares:
        user = _validate_share_target(
            db,
            workspace_id=idea.workspace_id,
            user_id=item.user_id,
            author_id=idea.author_id,
        )
        validated.append((item.user_id, item.permission.value, user))

    existing = list(db.scalars(select(IdeaShare).where(IdeaShare.idea_id == idea.id)))
    by_user = {row.user_id: row for row in existing}
    desired = {user_id for user_id, _, _ in validated}

    for row in existing:
        if row.user_id not in desired:
            db.delete(row)

    result: list[tuple[IdeaShare, User]] = []
    for user_id, permission, user in validated:
        row = by_user.get(user_id)
        if row is None:
            row = IdeaShare(idea_id=idea.id, user_id=user_id, permission=permission)
            db.add(row)
        else:
            row.permission = permission
        result.append((row, user))
    db.flush()
    return result


def clear_shares(db: Session, idea_id: UUID) -> None:
    for row in db.scalars(select(IdeaShare).where(IdeaShare.idea_id == idea_id)):
        db.delete(row)
    db.flush()


def create_idea(
    db: Session,
    *,
    workspace_id: UUID,
    author: User,
    payload: IdeaCreate,
) -> Idea:
    if payload.stage_id is None:
        stage = _default_stage(db, workspace_id)
    else:
        stage = _validate_stage(db, workspace_id, payload.stage_id)

    _validate_category(db, workspace_id, payload.category_id)
    _validate_assignee(db, workspace_id, payload.assignee_id)

    if payload.shares and payload.visibility != IdeaVisibility.SELECTED_USERS:
        raise AppError(
            "Shares are only allowed when visibility is SELECTED_USERS.",
            code="INVALID_IDEA_REFERENCE",
            status_code=400,
        )

    idea_code = allocate_idea_code(db, workspace_id)
    idea = Idea(
        idea_code=idea_code,
        workspace_id=workspace_id,
        author_id=author.id,
        title=payload.title,
        one_line_definition=payload.one_line_definition,
        original_text=payload.original_text,
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
        stage_id=stage.id,
        priority=payload.priority.value,
        feasibility=payload.feasibility.value,
        visibility=payload.visibility.value,
        assignee_id=payload.assignee_id,
        next_review_date=payload.next_review_date,
    )
    db.add(idea)
    db.flush()

    sync_idea_tags(db, idea, payload.tags)

    if payload.visibility == IdeaVisibility.SELECTED_USERS and payload.shares:
        replace_shares(db, idea=idea, shares=payload.shares)

    db.flush()
    on_idea_embedding_content_changed(db, idea)
    return idea


def get_readable_idea(
    db: Session,
    *,
    workspace_id: UUID,
    idea_id: UUID,
    user_id: UUID,
) -> tuple[Idea, IdeaShare | None]:
    idea = db.get(Idea, idea_id)
    if idea is None or idea.workspace_id != workspace_id or idea.deleted_at is not None:
        raise AppError("Idea not found.", code="IDEA_NOT_FOUND", status_code=404)

    share = idea_access.get_idea_share(db, idea.id, user_id)
    if not idea_access.can_read_idea(idea, user_id, share):
        raise AppError("Idea not found.", code="IDEA_NOT_FOUND", status_code=404)
    return idea, share


def require_idea_edit(
    db: Session,
    *,
    workspace_id: UUID,
    idea_id: UUID,
    user_id: UUID,
) -> tuple[Idea, IdeaShare | None, str]:
    idea, share = get_readable_idea(
        db, workspace_id=workspace_id, idea_id=idea_id, user_id=user_id
    )
    if not idea_access.can_edit_idea(idea, user_id, share):
        raise AppError(
            "Idea edit is forbidden.",
            code="IDEA_EDIT_FORBIDDEN",
            status_code=403,
        )
    access = idea_access.compute_access(idea, user_id, share)
    return idea, share, access


def require_idea_owner(
    db: Session,
    *,
    workspace_id: UUID,
    idea_id: UUID,
    user_id: UUID,
) -> Idea:
    idea, _share = get_readable_idea(
        db, workspace_id=workspace_id, idea_id=idea_id, user_id=user_id
    )
    if not idea_access.is_owner(idea, user_id):
        raise AppError(
            "Idea owner required.",
            code="IDEA_OWNER_REQUIRED",
            status_code=403,
        )
    return idea


def update_idea(
    db: Session,
    *,
    idea: Idea,
    access: str,
    payload: IdeaUpdate,
) -> Idea:
    fields_set = payload.model_fields_set

    if access != idea_access.ACCESS_OWNER:
        forbidden = fields_set & EDIT_SHARE_FORBIDDEN_FIELDS
        if forbidden:
            raise AppError(
                "Only the idea owner can change this field.",
                code="IDEA_OWNER_REQUIRED",
                status_code=403,
            )

    if "stage_id" in fields_set and payload.stage_id is not None:
        _validate_stage(db, idea.workspace_id, payload.stage_id)
        idea.stage_id = payload.stage_id

    if "category_id" in fields_set:
        _validate_category(db, idea.workspace_id, payload.category_id)
        idea.category_id = payload.category_id

    if "assignee_id" in fields_set:
        _validate_assignee(db, idea.workspace_id, payload.assignee_id)
        idea.assignee_id = payload.assignee_id

    content_fields = (
        "title",
        "one_line_definition",
        "original_text",
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
        "next_review_date",
    )
    for name in content_fields:
        if name in fields_set:
            setattr(idea, name, getattr(payload, name))

    if "priority" in fields_set and payload.priority is not None:
        idea.priority = payload.priority.value
    if "feasibility" in fields_set and payload.feasibility is not None:
        idea.feasibility = payload.feasibility.value

    if "visibility" in fields_set and payload.visibility is not None:
        previous = idea.visibility
        idea.visibility = payload.visibility.value
        if previous == IdeaVisibility.SELECTED_USERS.value and idea.visibility in {
            IdeaVisibility.PRIVATE.value,
            IdeaVisibility.WORKSPACE.value,
        }:
            clear_shares(db, idea.id)

    if "tags" in fields_set and payload.tags is not None:
        sync_idea_tags(db, idea, payload.tags)

    db.flush()
    if embedding_fields_changed(fields_set):
        on_idea_embedding_content_changed(db, idea)
    return idea


def soft_delete_idea(db: Session, idea: Idea) -> None:
    idea.deleted_at = utcnow()
    db.flush()


def _load_related(
    db: Session, ideas: list[Idea]
) -> tuple[
    dict[UUID, User],
    dict[UUID, WorkspaceStage],
    dict[UUID, WorkspaceCategory],
    dict[UUID, list[Tag]],
]:
    if not ideas:
        return {}, {}, {}, {}

    user_ids = {i.author_id for i in ideas}
    user_ids.update(i.assignee_id for i in ideas if i.assignee_id)
    users = {
        u.id: u
        for u in db.scalars(select(User).where(User.id.in_(user_ids))).all()
    }

    stage_ids = {i.stage_id for i in ideas}
    stages = {
        s.id: s
        for s in db.scalars(select(WorkspaceStage).where(WorkspaceStage.id.in_(stage_ids))).all()
    }

    category_ids = {i.category_id for i in ideas if i.category_id}
    categories = {
        c.id: c
        for c in db.scalars(
            select(WorkspaceCategory).where(WorkspaceCategory.id.in_(category_ids))
        ).all()
    } if category_ids else {}

    idea_ids = [i.id for i in ideas]
    tag_rows = db.execute(
        select(IdeaTag.idea_id, Tag)
        .join(Tag, Tag.id == IdeaTag.tag_id)
        .where(IdeaTag.idea_id.in_(idea_ids))
        .order_by(Tag.name)
    ).all()
    tags_by_idea: dict[UUID, list[Tag]] = {iid: [] for iid in idea_ids}
    for idea_id, tag in tag_rows:
        tags_by_idea[idea_id].append(tag)

    return users, stages, categories, tags_by_idea


def _to_list_item(
    idea: Idea,
    *,
    user_id: UUID,
    share: IdeaShare | None,
    users: dict[UUID, User],
    stages: dict[UUID, WorkspaceStage],
    categories: dict[UUID, WorkspaceCategory],
    tags_by_idea: dict[UUID, list[Tag]],
) -> IdeaListItem:
    author = users[idea.author_id]
    stage = stages[idea.stage_id]
    category = categories.get(idea.category_id) if idea.category_id else None
    assignee = users.get(idea.assignee_id) if idea.assignee_id else None
    tags = tags_by_idea.get(idea.id, [])
    return IdeaListItem(
        id=idea.id,
        idea_code=idea.idea_code,
        title=idea.title,
        one_line_definition=idea.one_line_definition,
        category=CategoryRef.model_validate(category) if category else None,
        stage=StageRef.model_validate(stage),
        priority=idea.priority,
        feasibility=idea.feasibility,
        visibility=idea.visibility,
        author=IdeaUserPublic.model_validate(author),
        assignee=IdeaUserPublic.model_validate(assignee) if assignee else None,
        tags=[TagPublic.model_validate(t) for t in tags],
        next_review_date=idea.next_review_date,
        created_at=idea.created_at,
        updated_at=idea.updated_at,
        current_user_access=idea_access.compute_access(idea, user_id, share),
    )


def to_detail(
    db: Session,
    idea: Idea,
    *,
    user_id: UUID,
    share: IdeaShare | None,
) -> IdeaDetail:
    users, stages, categories, tags_by_idea = _load_related(db, [idea])
    base = _to_list_item(
        idea,
        user_id=user_id,
        share=share,
        users=users,
        stages=stages,
        categories=categories,
        tags_by_idea=tags_by_idea,
    )
    return IdeaDetail(
        **base.model_dump(),
        workspace_id=idea.workspace_id,
        original_text=idea.original_text,
        background=idea.background,
        problem=idea.problem,
        core_concept=idea.core_concept,
        major_features=idea.major_features,
        expected_effect=idea.expected_effect,
        target_users=idea.target_users,
        scenarios=idea.scenarios,
        challenges=idea.challenges,
        minimum_validation=idea.minimum_validation,
        related_project=idea.related_project,
    )


def _search_predicate(q: str):
    pattern = f"%{q}%"
    ilike_clause = or_(
        Idea.title.ilike(pattern),
        Idea.one_line_definition.ilike(pattern),
        Idea.original_text.ilike(pattern),
        Idea.background.ilike(pattern),
        Idea.problem.ilike(pattern),
        Idea.core_concept.ilike(pattern),
        Idea.expected_effect.ilike(pattern),
    )
    # FTS on concatenated fields (simple config); ILIKE remains primary for Korean.
    document = func.concat_ws(
        " ",
        Idea.title,
        func.coalesce(Idea.one_line_definition, ""),
        func.coalesce(Idea.original_text, ""),
        func.coalesce(Idea.background, ""),
        func.coalesce(Idea.problem, ""),
        func.coalesce(Idea.core_concept, ""),
        func.coalesce(Idea.expected_effect, ""),
    )
    fts_clause = func.to_tsvector("simple", document).op("@@")(
        func.plainto_tsquery("simple", q)
    )
    return or_(ilike_clause, fts_clause)


def _normalize_list_pagination(limit: int, offset: int) -> tuple[int, int]:
    return min(max(limit, 1), 100), max(offset, 0)


def _apply_list_filters(
    stmt,
    *,
    stage_id: UUID | None = None,
    category_id: UUID | None = None,
    priority: str | None = None,
    feasibility: str | None = None,
    visibility: str | None = None,
    author_id: UUID | None = None,
    assignee_id: UUID | None = None,
):
    if stage_id is not None:
        stmt = stmt.where(Idea.stage_id == stage_id)
    if category_id is not None:
        stmt = stmt.where(Idea.category_id == category_id)
    if priority is not None:
        stmt = stmt.where(Idea.priority == priority)
    if feasibility is not None:
        stmt = stmt.where(Idea.feasibility == feasibility)
    if visibility is not None:
        stmt = stmt.where(Idea.visibility == visibility)
    if author_id is not None:
        stmt = stmt.where(Idea.author_id == author_id)
    if assignee_id is not None:
        stmt = stmt.where(Idea.assignee_id == assignee_id)
    return stmt


def _build_keyword_query(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    q: str,
    stage_id: UUID | None = None,
    category_id: UUID | None = None,
    priority: str | None = None,
    feasibility: str | None = None,
    visibility: str | None = None,
    author_id: UUID | None = None,
    assignee_id: UUID | None = None,
):
    del db
    base = select(Idea).where(Idea.workspace_id == workspace_id)
    base = idea_access.apply_readable_filter(base, user_id)
    base = base.where(_search_predicate(q.strip()))
    return _apply_list_filters(
        base,
        stage_id=stage_id,
        category_id=category_id,
        priority=priority,
        feasibility=feasibility,
        visibility=visibility,
        author_id=author_id,
        assignee_id=assignee_id,
    )


def _finalize_list_response(
    db: Session,
    rows: list[Idea],
    *,
    user_id: UUID,
    total: int,
    limit: int,
    offset: int,
) -> IdeaListResponse:
    users, stages, categories, tags_by_idea = _load_related(db, rows)
    shares = {
        s.idea_id: s
        for s in db.scalars(
            select(IdeaShare).where(
                IdeaShare.idea_id.in_([i.id for i in rows]),
                IdeaShare.user_id == user_id,
            )
        ).all()
    } if rows else {}

    items = [
        _to_list_item(
            idea,
            user_id=user_id,
            share=shares.get(idea.id),
            users=users,
            stages=stages,
            categories=categories,
            tags_by_idea=tags_by_idea,
        )
        for idea in rows
    ]
    return IdeaListResponse(items=items, total=total, limit=limit, offset=offset)


def list_ideas(
    db: Session,
    *,
    workspace_id: UUID,
    user_id: UUID,
    q: str | None = None,
    stage_id: UUID | None = None,
    category_id: UUID | None = None,
    priority: str | None = None,
    feasibility: str | None = None,
    visibility: str | None = None,
    author_id: UUID | None = None,
    assignee_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> IdeaListResponse:
    limit, offset = _normalize_list_pagination(limit, offset)

    base = select(Idea).where(Idea.workspace_id == workspace_id)
    base = idea_access.apply_readable_filter(base, user_id)

    if q and q.strip():
        base = base.where(_search_predicate(q.strip()))
    base = _apply_list_filters(
        base,
        stage_id=stage_id,
        category_id=category_id,
        priority=priority,
        feasibility=feasibility,
        visibility=visibility,
        author_id=author_id,
        assignee_id=assignee_id,
    )

    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0

    rows = list(
        db.scalars(
            base.order_by(Idea.updated_at.desc(), Idea.id.desc())
            .offset(offset)
            .limit(limit)
        )
    )

    return _finalize_list_response(
        db, rows, user_id=user_id, total=total, limit=limit, offset=offset
    )


def list_shares(db: Session, idea: Idea) -> list[IdeaSharePublic]:
    rows = db.execute(
        select(IdeaShare, User)
        .join(User, User.id == IdeaShare.user_id)
        .where(IdeaShare.idea_id == idea.id)
        .order_by(User.name)
    ).all()
    return [
        IdeaSharePublic(user_id=share.user_id, name=user.name, permission=share.permission)
        for share, user in rows
    ]
