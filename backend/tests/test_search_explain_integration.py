"""Search explainability integration tests (Step 27).

Ranking order must stay identical; explanations are additive metadata only.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import reset_engine
from app.embeddings.canonical import compute_content_hash
from app.embeddings.fake import _text_to_vector
from app.main import app
from app.models.embedding import IdeaEmbedding
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
from app.services.embedding_service import load_idea_tag_names
from app.services.workspace import seed_workspace_defaults
from tests.db_test_safety import assert_test_database_safe
from tests.pgvector_helpers import (
    DATABASE_URL,
    requires_database,
    requires_pgvector,
    wipe_embedding_tables,
)

pytestmark = [requires_database, requires_pgvector]


@pytest.fixture(scope="module")
def engine():
    reset_engine()
    get_settings.cache_clear()
    eng = create_engine(DATABASE_URL, pool_pre_ping=True)
    assert_test_database_safe(eng)
    with eng.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
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


@pytest.fixture
def client(engine, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("AI_WORKER_ENABLED", "false")
    monkeypatch.setenv("EMBEDDING_WORKER_ENABLED", "false")
    monkeypatch.setenv("EMBEDDING_ENABLED", "true")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "fake")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("EMBEDDING_API_URL", "http://embed.test")
    monkeypatch.setenv("EMBEDDING_MODEL_NAME", "BAAI/bge-m3")
    get_settings.cache_clear()
    reset_engine()
    with TestClient(app) as c:
        yield c
    reset_engine()
    get_settings.cache_clear()


def _user(db: Session, *, email: str | None = None, password: str = "password-ok-1") -> tuple[User, str]:
    email = email or f"explain-{uuid.uuid4().hex[:10]}@example.com"
    user = User(
        email=email.lower(),
        name=email.split("@")[0],
        password_hash=hash_password(password),
        status=UserStatus.ACTIVE.value,
        system_role=SystemRole.USER.value,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, password


def _team(db: Session, owner: User) -> Workspace:
    ws = Workspace(name=f"Explain-{uuid.uuid4().hex[:6]}", type=WorkspaceType.TEAM.value, owner_id=owner.id)
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
    db.commit()
    db.refresh(ws)
    return ws


def _member(db: Session, ws: Workspace, user: User) -> None:
    db.add(
        WorkspaceMember(
            workspace_id=ws.id,
            user_id=user.id,
            role=WorkspaceRole.MEMBER.value,
            status=WorkspaceMemberStatus.ACTIVE.value,
        )
    )
    db.commit()


def _stage(db: Session, ws: Workspace) -> WorkspaceStage:
    return db.scalar(
        select(WorkspaceStage).where(
            WorkspaceStage.workspace_id == ws.id,
            WorkspaceStage.is_default.is_(True),
        )
    )


def _csrf(client: TestClient) -> str:
    return client.get("/api/v1/auth/csrf").json()["csrf_token"]


def _login(client: TestClient, email: str, password: str) -> dict[str, str]:
    client.cookies.clear()
    r = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers={"X-CSRF-Token": _csrf(client)},
    )
    assert r.status_code == 200, r.text
    token = client.cookies.get(get_settings().auth_csrf_cookie_name)
    return {"X-CSRF-Token": token or ""}


def _create_idea(db: Session, ws: Workspace, author: User, **kwargs) -> Idea:
    payload = IdeaCreate(
        title=kwargs.get("title", "Explain idea"),
        one_line_definition=kwargs.get("one_line_definition"),
        problem=kwargs.get("problem", "default problem"),
        core_concept=kwargs.get("core_concept", "default concept"),
        tags=kwargs.get("tags", []),
        visibility=kwargs.get("visibility", IdeaVisibility.WORKSPACE),
    )
    idea = idea_service.create_idea(db, workspace_id=ws.id, author=author, payload=payload)
    db.commit()
    db.refresh(idea)
    return idea


def _store_embedding(db: Session, idea: Idea, *, text: str) -> None:
    settings = get_settings()
    vector = _text_to_vector(text, dimension=settings.embedding_dimension)
    content_hash = compute_content_hash(text)
    row = db.get(IdeaEmbedding, idea.id)
    if row is None:
        db.add(
            IdeaEmbedding(
                idea_id=idea.id,
                workspace_id=idea.workspace_id,
                embedding=vector,
                content_hash=content_hash,
                model_name=settings.embedding_model_name,
                dimension=settings.embedding_dimension,
            )
        )
    else:
        row.embedding = vector
        row.content_hash = content_hash
    db.commit()


def test_keyword_explain_matched_fields_and_no_query(client: TestClient, db: Session) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    idea = _create_idea(
        db,
        ws,
        owner,
        title="회의록 자동 정리",
        one_line_definition="음성을 요약",
        problem="수동 정리 부담",
    )
    headers = _login(client, owner.email, pw)

    with_q = client.get(
        f"/api/v1/workspaces/{ws.id}/ideas",
        params={"q": "회의록", "search_mode": "keyword"},
        headers=headers,
    )
    assert with_q.status_code == 200
    hit = next(i for i in with_q.json()["items"] if i["id"] == str(idea.id))
    exp = hit["search_explanation"]
    assert exp is not None
    assert exp["mode"] == "keyword"
    assert "title" in exp["keyword"]["matched_fields"]
    assert exp["keyword"]["fts_match"] is False
    assert exp["keyword"]["rank"] >= 1

    no_q = client.get(
        f"/api/v1/workspaces/{ws.id}/ideas",
        params={"search_mode": "keyword"},
        headers=headers,
    )
    assert no_q.status_code == 200
    for item in no_q.json()["items"]:
        assert item.get("search_explanation") in (None, {})


def test_keyword_explain_core_concept_field(client: TestClient, db: Session) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    idea = _create_idea(
        db,
        ws,
        owner,
        title="일반 제목",
        core_concept="workflow automation platform",
    )
    headers = _login(client, owner.email, pw)
    r = client.get(
        f"/api/v1/workspaces/{ws.id}/ideas",
        params={"q": "automation", "search_mode": "keyword"},
        headers=headers,
    )
    hit = next(i for i in r.json()["items"] if i["id"] == str(idea.id))
    assert "core_concept" in hit["search_explanation"]["keyword"]["matched_fields"]


def test_semantic_explain_reuses_distance(client: TestClient, db: Session) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    idea = _create_idea(db, ws, owner, title="Semantic explain", problem="clinical triage assistant")
    from app.embeddings.canonical import build_idea_embedding_text

    text = build_idea_embedding_text(idea, load_idea_tag_names(db, idea.id))
    _store_embedding(db, idea, text=text)

    headers = _login(client, owner.email, pw)
    r = client.get(
        f"/api/v1/workspaces/{ws.id}/ideas",
        params={"q": "clinical triage", "search_mode": "semantic"},
        headers=headers,
    )
    assert r.status_code == 200
    hit = next(i for i in r.json()["items"] if i["id"] == str(idea.id))
    exp = hit["search_explanation"]
    assert exp["mode"] == "semantic"
    assert exp["semantic"]["distance"] is not None
    assert exp["semantic"]["similarity"] is not None
    assert abs(exp["semantic"]["similarity"] - (1.0 - exp["semantic"]["distance"])) < 1e-5
    assert exp["semantic"]["rank"] >= 1


def test_hybrid_explain_ranks_and_one_sided(client: TestClient, db: Session) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    kw_only = _create_idea(db, ws, owner, title="exact-keyword-token-xyz", problem="unrelated body")
    sem_only = _create_idea(db, ws, owner, title="Other title", problem="clinical triage assistant")
    from app.embeddings.canonical import build_idea_embedding_text

    sem_text = build_idea_embedding_text(sem_only, load_idea_tag_names(db, sem_only.id))
    _store_embedding(db, sem_only, text=sem_text)

    headers = _login(client, owner.email, pw)
    r = client.get(
        f"/api/v1/workspaces/{ws.id}/ideas",
        params={"q": "clinical triage", "search_mode": "hybrid"},
        headers=headers,
    )
    assert r.status_code == 200
    by_id = {i["id"]: i for i in r.json()["items"]}

    assert str(sem_only.id) in by_id
    sem_exp = by_id[str(sem_only.id)]["search_explanation"]
    assert sem_exp["mode"] == "hybrid"
    assert sem_exp["hybrid"]["semantic_rank"] is not None
    assert sem_exp["hybrid"]["rrf_score"] is not None
    if str(kw_only.id) in by_id:
        kw_exp = by_id[str(kw_only.id)]["search_explanation"]
        assert kw_exp["hybrid"]["keyword_rank"] is not None


def test_hybrid_acl_private_explanation_not_leaked(client: TestClient, db: Session) -> None:
    owner, pw = _user(db)
    other, other_pw = _user(db)
    ws = _team(db, owner)
    _member(db, ws, other)
    private = _create_idea(
        db,
        ws,
        owner,
        title="비밀 회의록",
        problem="private explain semantic",
        visibility=IdeaVisibility.PRIVATE,
    )
    from app.embeddings.canonical import build_idea_embedding_text

    text = build_idea_embedding_text(private, load_idea_tag_names(db, private.id))
    _store_embedding(db, private, text=text)

    headers = _login(client, other.email, other_pw)
    r = client.get(
        f"/api/v1/workspaces/{ws.id}/ideas",
        params={"q": "회의록", "search_mode": "hybrid"},
        headers=headers,
    )
    assert r.status_code == 200
    ids = {i["id"] for i in r.json()["items"]}
    assert str(private.id) not in ids


def test_hybrid_pagination_uses_candidate_ranks_not_page_index(
    client: TestClient, db: Session
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    for i in range(5):
        idea = _create_idea(
            db,
            ws,
            owner,
            title=f"page-rank-token-{i}",
            problem=f"page rank semantic content {i}",
        )
        from app.embeddings.canonical import build_idea_embedding_text

        text = build_idea_embedding_text(idea, load_idea_tag_names(db, idea.id))
        _store_embedding(db, idea, text=text)

    headers = _login(client, owner.email, pw)
    full = client.get(
        f"/api/v1/workspaces/{ws.id}/ideas",
        params={"q": "page-rank-token", "search_mode": "hybrid", "limit": 10, "offset": 0},
        headers=headers,
    ).json()
    page1 = client.get(
        f"/api/v1/workspaces/{ws.id}/ideas",
        params={"q": "page-rank-token", "search_mode": "hybrid", "limit": 2, "offset": 2},
        headers=headers,
    ).json()
    assert full["total"] >= 4
    assert len(page1["items"]) >= 1
    full_by_id = {i["id"]: i for i in full["items"]}
    for item in page1["items"]:
        # Explanations must be stable across pages (candidate ranks, not page-local).
        assert item["search_explanation"] == full_by_id[item["id"]]["search_explanation"]
    first = page1["items"][0]
    hybrid_pos = [i["id"] for i in full["items"]].index(first["id"]) + 1
    assert hybrid_pos >= 3
    # Page-local index would be 1; candidate ranks must not be rewritten to 1.
    page_local = 1
    kw_rank = first["search_explanation"]["hybrid"].get("keyword_rank")
    sem_rank = first["search_explanation"]["hybrid"].get("semantic_rank")
    if kw_rank is not None and sem_rank is not None:
        assert not (kw_rank == page_local and sem_rank == page_local and hybrid_pos > 1)


def test_rrf_merge_with_scores_preserves_ranking_order() -> None:
    now = datetime.now(timezone.utc)
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    ideas = {
        a: SimpleNamespace(id=a, updated_at=now),
        b: SimpleNamespace(id=b, updated_at=now),
        c: SimpleNamespace(id=c, updated_at=now),
    }
    merged = idea_search._rrf_merge([a, b, c], [a, c, b], ideas_by_id=ideas, rrf_k=60)
    with_scores, scores = idea_search._rrf_merge_with_scores(
        [a, b, c], [a, c, b], ideas_by_id=ideas, rrf_k=60
    )
    assert [i.id for i in merged] == [i.id for i in with_scores]
    assert set(scores.keys()) == {a, b, c}
