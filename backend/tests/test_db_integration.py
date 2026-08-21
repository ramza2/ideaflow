"""PostgreSQL integration tests — skipped unless DATABASE_URL is set."""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    Idea,
    IdeaParticipant,
    IdeaShare,
    IdeaTag,
    Tag,
    User,
    Workspace,
    WorkspaceCategory,
    WorkspaceMember,
    WorkspaceStage,
)
from app.models.enums import (
    IdeaSharePermission,
    WorkspaceMemberStatus,
    WorkspaceRole,
    WorkspaceType,
)

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — skipping PostgreSQL integration tests",
)


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(DATABASE_URL, pool_pre_ping=True)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine) -> Session:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _user(db: Session, suffix: str | None = None) -> User:
    suffix = suffix or uuid.uuid4().hex[:10]
    user = User(
        email=f"u-{suffix}@example.com",
        password_hash="not-a-real-hash",
        name=f"User {suffix}",
    )
    db.add(user)
    db.flush()
    return user


def _workspace(db: Session, owner: User, *, ws_type: str = WorkspaceType.TEAM.value) -> Workspace:
    ws = Workspace(name=f"WS-{uuid.uuid4().hex[:6]}", type=ws_type, owner_id=owner.id)
    db.add(ws)
    db.flush()
    return ws


def _stage(db: Session, ws: Workspace) -> WorkspaceStage:
    stage = WorkspaceStage(
        workspace_id=ws.id,
        slug="memo",
        label="메모",
        sort_order=10,
        is_default=True,
        is_terminal=False,
    )
    db.add(stage)
    db.flush()
    return stage


def test_database_select_one(engine) -> None:
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar_one() == 1


def test_user_email_unique(db: Session) -> None:
    email = f"dup-{uuid.uuid4().hex[:8]}@example.com"
    db.add(User(email=email, password_hash="h", name="A"))
    db.flush()
    with pytest.raises(IntegrityError):
        db.add(User(email=email, password_hash="h", name="B"))
        db.flush()


def test_one_active_personal_workspace_per_owner(db: Session) -> None:
    owner = _user(db)
    _workspace(db, owner, ws_type=WorkspaceType.PERSONAL.value)
    with pytest.raises(IntegrityError):
        _workspace(db, owner, ws_type=WorkspaceType.PERSONAL.value)


def test_workspace_member_unique(db: Session) -> None:
    owner = _user(db)
    ws = _workspace(db, owner)
    db.add(
        WorkspaceMember(
            workspace_id=ws.id,
            user_id=owner.id,
            role=WorkspaceRole.ADMIN.value,
            status=WorkspaceMemberStatus.ACTIVE.value,
        )
    )
    db.flush()
    with pytest.raises(IntegrityError):
        db.add(
            WorkspaceMember(
                workspace_id=ws.id,
                user_id=owner.id,
                role=WorkspaceRole.MEMBER.value,
                status=WorkspaceMemberStatus.ACTIVE.value,
            )
        )
        db.flush()


def test_stage_and_category_slug_unique(db: Session) -> None:
    owner = _user(db)
    ws = _workspace(db, owner)
    _stage(db, ws)
    with pytest.raises(IntegrityError):
        _stage(db, ws)

    db.rollback()
    owner = _user(db)
    ws = _workspace(db, owner)
    db.add(
        WorkspaceCategory(workspace_id=ws.id, slug="other", name="기타", sort_order=80)
    )
    db.flush()
    with pytest.raises(IntegrityError):
        db.add(
            WorkspaceCategory(workspace_id=ws.id, slug="other", name="기타2", sort_order=81)
        )
        db.flush()


def test_idea_code_unique_and_relations(db: Session) -> None:
    owner = _user(db)
    ws = _workspace(db, owner)
    stage = _stage(db, ws)
    tag = Tag(workspace_id=ws.id, name="ai", color="#4f46e5")
    db.add(tag)
    db.flush()

    idea = Idea(
        idea_code="IF-001",
        workspace_id=ws.id,
        author_id=owner.id,
        title="Core idea",
        stage_id=stage.id,
    )
    db.add(idea)
    db.flush()

    with pytest.raises(IntegrityError):
        db.add(
            Idea(
                idea_code="IF-001",
                workspace_id=ws.id,
                author_id=owner.id,
                title="Dup",
                stage_id=stage.id,
            )
        )
        db.flush()
    db.rollback()

    owner = _user(db)
    ws = _workspace(db, owner)
    stage = _stage(db, ws)
    tag = Tag(workspace_id=ws.id, name="ai")
    db.add(tag)
    db.flush()
    idea = Idea(
        idea_code="IF-100",
        workspace_id=ws.id,
        author_id=owner.id,
        title="OK",
        stage_id=stage.id,
    )
    db.add(idea)
    db.flush()
    db.add(IdeaTag(idea_id=idea.id, tag_id=tag.id))
    db.add(
        IdeaShare(
            idea_id=idea.id,
            user_id=owner.id,
            permission=IdeaSharePermission.READ.value,
        )
    )
    db.add(IdeaParticipant(idea_id=idea.id, user_id=owner.id))
    db.flush()

    with pytest.raises(IntegrityError):
        db.add(IdeaTag(idea_id=idea.id, tag_id=tag.id))
        db.flush()
    db.rollback()

    owner = _user(db)
    ws = _workspace(db, owner)
    stage = _stage(db, ws)
    idea = Idea(
        idea_code="IF-200",
        workspace_id=ws.id,
        author_id=owner.id,
        title="Share",
        stage_id=stage.id,
    )
    db.add(idea)
    db.flush()
    db.add(
        IdeaShare(
            idea_id=idea.id,
            user_id=owner.id,
            permission=IdeaSharePermission.EDIT.value,
        )
    )
    db.flush()
    with pytest.raises(IntegrityError):
        db.add(
            IdeaShare(
                idea_id=idea.id,
                user_id=owner.id,
                permission=IdeaSharePermission.READ.value,
            )
        )
        db.flush()
    db.rollback()

    owner = _user(db)
    ws = _workspace(db, owner)
    stage = _stage(db, ws)
    idea = Idea(
        idea_code="IF-300",
        workspace_id=ws.id,
        author_id=owner.id,
        title="Part",
        stage_id=stage.id,
    )
    db.add(idea)
    db.flush()
    db.add(IdeaParticipant(idea_id=idea.id, user_id=owner.id))
    db.flush()
    with pytest.raises(IntegrityError):
        db.add(IdeaParticipant(idea_id=idea.id, user_id=owner.id))
        db.flush()
