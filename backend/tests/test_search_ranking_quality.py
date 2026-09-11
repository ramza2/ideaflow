"""Regression tests for search ranking quality (Step 25)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import reset_engine
from app.embeddings.canonical import build_idea_embedding_text, compute_content_hash
from app.models.embedding import IdeaEmbedding, IdeaEmbeddingJob
from app.models.enums import (
    IdeaVisibility,
    SystemRole,
    UserStatus,
    WorkspaceMemberStatus,
    WorkspaceRole,
    WorkspaceType,
)
from app.models.idea import Idea
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceStage
from app.schemas.idea import IdeaCreate
from app.services import idea as idea_service
from app.services import idea_search
from app.services.workspace import seed_workspace_defaults
from tests.db_test_safety import TEST_DATABASE_URL, assert_test_database_safe, requires_test_database
from tests.pgvector_helpers import requires_pgvector, wipe_embedding_tables
from tests.search_quality.topic_embedding import TopicAwareEvalEmbeddingProvider

pytestmark = [requires_test_database, requires_pgvector]


@pytest.fixture(scope="module")
def engine():
    reset_engine()
    get_settings.cache_clear()
    eng = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    assert_test_database_safe(eng)
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text

    with eng.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(cfg, "head")
    with eng.begin() as conn:
        wipe_embedding_tables(conn)
    yield eng
    eng.dispose()
    reset_engine()
    get_settings.cache_clear()


@pytest.fixture
def db(engine) -> Session:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        wipe_embedding_tables(session)
        session.commit()
        yield session
    finally:
        session.rollback()
        session.close()


def _enable_embedding(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("EMBEDDING_ENABLED", "true")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "fake")
    monkeypatch.setenv("EMBEDDING_API_URL", "http://embed.test")
    monkeypatch.setenv("EMBEDDING_MODEL_NAME", "BAAI/bge-m3")
    monkeypatch.setenv("APP_ENV", "development")
    get_settings.cache_clear()
    reset_engine()


def _seed_mini_corpus(db: Session, settings) -> tuple[Workspace, User, dict[str, Idea]]:
    owner = User(
        email=f"rank-{uuid4().hex[:8]}@example.com",
        name="rank-eval",
        password_hash=hash_password("password-ok-1"),
        status=UserStatus.ACTIVE.value,
        system_role=SystemRole.USER.value,
    )
    db.add(owner)
    db.flush()
    ws = Workspace(
        name=f"rank-{uuid4().hex[:6]}",
        type=WorkspaceType.TEAM.value,
        owner_id=owner.id,
    )
    db.add(ws)
    db.flush()
    seed_workspace_defaults(db, ws.id)
    db.add(
        WorkspaceMember(
            workspace_id=ws.id,
            user_id=owner.id,
            role=WorkspaceRole.ADMIN.value,
            status=WorkspaceMemberStatus.ACTIVE.value,
        )
    )
    stage = db.scalar(
        select(WorkspaceStage).where(
            WorkspaceStage.workspace_id == ws.id,
            WorkspaceStage.is_default.is_(True),
        )
    )
    provider = TopicAwareEvalEmbeddingProvider(settings)
    specs = [
        {
            "code": "SR-MEET-01",
            "title": "[SR-MEET-01] 회의록 자동 정리",
            "one_line_definition": "회의 음성과 노트를 구조화된 회의록으로 자동 정리",
            "problem": "회의록 작성이 반복된다",
            "core_concept": "회의 내용 자동 정리",
            "tags": ["회의록", "자동화"],
        },
        {
            "code": "SR-MED-WRITE-01",
            "title": "[SR-MED-WRITE-01] 진료 기록 자동 작성 보조",
            "one_line_definition": "의사가 반복해서 작성하는 진료 기록·의료 문서를 AI로 초안 작성",
            "problem": "병원 기록 작성 부담",
            "core_concept": "의료 문서 작성 보조",
            "tags": ["병원", "진료", "자동화"],
        },
        {
            "code": "SR-INV-01",
            "title": "[SR-INV-01] 재고 부족 사전 알림",
            "one_line_definition": "재고가 떨어지기 전에 알려주는 시스템",
            "problem": "재고 소진 결품",
            "core_concept": "재고 알림",
            "tags": ["재고", "알림"],
        },
        {
            "code": "SR-CRM-01",
            "title": "[SR-CRM-01] 영업 파이프라인 CRM",
            "one_line_definition": "리드부터 성사까지 고객 관리 CRM",
            "problem": "영업 기회 분산",
            "core_concept": "CRM 파이프라인",
            "tags": ["CRM", "영업"],
        },
        {
            "code": "SR-GEN-01",
            "title": "[SR-GEN-01] 만능 업무 플랫폼",
            "one_line_definition": "범용 업무 플랫폼",
            "problem": "도구가 많다",
            "core_concept": "통합 플랫폼",
            "tags": ["플랫폼"],
        },
    ]
    by_code: dict[str, Idea] = {}
    for spec in specs:
        idea = idea_service.create_idea(
            db,
            workspace_id=ws.id,
            author=owner,
            payload=IdeaCreate(
                title=spec["title"],
                one_line_definition=spec["one_line_definition"],
                problem=spec["problem"],
                core_concept=spec["core_concept"],
                tags=spec["tags"],
                visibility=IdeaVisibility.WORKSPACE,
                stage_id=stage.id,
            ),
        )
        db.flush()
        job = db.get(IdeaEmbeddingJob, idea.id)
        if job is not None:
            db.delete(job)
        text = build_idea_embedding_text(idea, spec["tags"])
        db.add(
            IdeaEmbedding(
                idea_id=idea.id,
                workspace_id=ws.id,
                embedding=provider.embed_text(text),
                content_hash=compute_content_hash(text),
                model_name=settings.embedding_model_name,
                dimension=settings.embedding_dimension,
            )
        )
        by_code[spec["code"]] = idea
    base = datetime.now(timezone.utc)
    for i, code in enumerate(["SR-MEET-01", "SR-MED-WRITE-01", "SR-INV-01", "SR-CRM-01"]):
        by_code[code].updated_at = base + timedelta(seconds=10 - i)
    db.commit()
    return ws, owner, by_code


def test_rrf_merge_uses_one_based_ranks_and_injectable_k() -> None:
    class _Idea:
        def __init__(self, idea_id, updated_at):
            self.id = idea_id
            self.updated_at = updated_at

    a, b, c = uuid4(), uuid4(), uuid4()
    now = datetime.now(timezone.utc)
    ideas = {
        a: _Idea(a, now),
        b: _Idea(b, now - timedelta(seconds=1)),
        c: _Idea(c, now - timedelta(seconds=2)),
    }
    merged = idea_search._rrf_merge([a, b, c], [a, c, b], ideas_by_id=ideas, rrf_k=60)
    assert [x.id for x in merged][0] == a
    with pytest.raises(ValueError):
        idea_search._rrf_merge([a], [a], ideas_by_id=ideas, rrf_k=0)


def test_exact_meeting_minutes_in_hybrid_top3(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_embedding(monkeypatch)
    settings = get_settings()
    ws, owner, by_code = _seed_mini_corpus(db, settings)
    ideas, _, _meta = idea_search.list_hybrid_ideas(
        db,
        workspace_id=ws.id,
        user_id=owner.id,
        q="회의록",
        limit=5,
        settings=settings,
        provider_factory=lambda s: TopicAwareEvalEmbeddingProvider(s),
    )
    assert by_code["SR-MEET-01"].id in {i.id for i in ideas[:3]}


def test_medical_paraphrase_in_hybrid_top3(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_embedding(monkeypatch)
    settings = get_settings()
    ws, owner, by_code = _seed_mini_corpus(db, settings)
    ideas, _, _meta = idea_search.list_hybrid_ideas(
        db,
        workspace_id=ws.id,
        user_id=owner.id,
        q="의료 문서 작성 보조",
        limit=5,
        settings=settings,
        provider_factory=lambda s: TopicAwareEvalEmbeddingProvider(s),
    )
    assert by_code["SR-MED-WRITE-01"].id in {i.id for i in ideas[:3]}


def test_inventory_natural_language_in_hybrid_top3(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_embedding(monkeypatch)
    settings = get_settings()
    ws, owner, by_code = _seed_mini_corpus(db, settings)
    ideas, _, _meta = idea_search.list_hybrid_ideas(
        db,
        workspace_id=ws.id,
        user_id=owner.id,
        q="재고가 떨어지기 전에 알려주는 시스템",
        limit=5,
        settings=settings,
        provider_factory=lambda s: TopicAwareEvalEmbeddingProvider(s),
    )
    assert by_code["SR-INV-01"].id in {i.id for i in ideas[:3]}


def test_hybrid_rrf_k_override_does_not_break_acl(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _enable_embedding(monkeypatch)
    settings = get_settings()
    ws, owner, by_code = _seed_mini_corpus(db, settings)
    # Mark meeting idea PRIVATE so non-members / non-authors cannot read it.
    meet = by_code["SR-MEET-01"]
    meet.visibility = IdeaVisibility.PRIVATE.value
    outsider = User(
        email=f"out-{uuid4().hex[:8]}@example.com",
        name="outsider",
        password_hash=hash_password("password-ok-1"),
        status=UserStatus.ACTIVE.value,
        system_role=SystemRole.USER.value,
    )
    db.add(outsider)
    db.commit()
    ideas, total, _meta = idea_search.list_hybrid_ideas(
        db,
        workspace_id=ws.id,
        user_id=outsider.id,
        q="회의록",
        limit=5,
        settings=settings,
        provider_factory=lambda s: TopicAwareEvalEmbeddingProvider(s),
        rrf_k=20,
        candidate_limit=50,
    )
    assert meet.id not in {i.id for i in ideas}
    assert all(i.visibility != IdeaVisibility.PRIVATE.value for i in ideas)
