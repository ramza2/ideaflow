"""Embedding jobs, race protection, and semantic/hybrid search integration tests."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import EMBEDDING_DIMENSION, get_settings
from app.core.security import hash_password
from app.db.session import reset_engine
from app.embeddings.canonical import compute_content_hash
from app.embeddings.fake import FakeEmbeddingProvider, _text_to_vector
from app.main import app
from app.models.embedding import IdeaEmbedding, IdeaEmbeddingJob
from app.models.enums import (
    IdeaEmbeddingJobStatus,
    IdeaVisibility,
    SystemRole,
    UserStatus,
    WorkspaceMemberStatus,
    WorkspaceRole,
    WorkspaceType,
)
from app.models.idea import Idea
from app.models.relations import IdeaShare
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceStage
from app.schemas.idea import IdeaCreate, IdeaUpdate
from app.services import idea as idea_service
from app.services import idea_search
from app.services.embedding_service import load_idea_tag_names
from app.services.embedding_worker import (
    finalize_embedding_result,
    prepare_claimed_embedding_work,
    process_claimed_embedding_job,
    run_once,
)
from app.services.workspace import seed_workspace_defaults
from tests.pgvector_helpers import DATABASE_URL, requires_database, requires_pgvector

pytestmark = [requires_database, requires_pgvector]


@pytest.fixture(scope="module")
def engine():
    reset_engine()
    get_settings.cache_clear()
    eng = create_engine(DATABASE_URL, pool_pre_ping=True)
    with eng.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(cfg, "head")
    with eng.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE idea_embedding_jobs, idea_embeddings, "
                "integration_config_audits, integration_runtime_configs CASCADE"
            )
        )
    yield eng
    eng.dispose()
    reset_engine()
    get_settings.cache_clear()


@pytest.fixture
def db(engine) -> Session:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        session.execute(
            text(
                "TRUNCATE idea_embedding_jobs, idea_embeddings, "
                "integration_config_audits, integration_runtime_configs CASCADE"
            )
        )
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
    monkeypatch.setenv("APP_ENV", "development")
    get_settings.cache_clear()
    reset_engine()
    with TestClient(app) as c:
        yield c
    reset_engine()
    get_settings.cache_clear()


def _enable_embedding_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBEDDING_ENABLED", "true")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "fake")
    monkeypatch.setenv("EMBEDDING_API_URL", "http://embed.test")
    monkeypatch.setenv("EMBEDDING_MODEL_NAME", "BAAI/bge-m3")
    monkeypatch.setenv("APP_ENV", "development")
    get_settings.cache_clear()


def _user(db: Session, *, email: str | None = None, password: str = "password-ok-1") -> tuple[User, str]:
    email = email or f"emb-{uuid.uuid4().hex[:10]}@example.com"
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
    ws = Workspace(name=f"Team-{uuid.uuid4().hex[:6]}", type=WorkspaceType.TEAM.value, owner_id=owner.id)
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


def _member(db: Session, ws: Workspace, user: User, role: str = WorkspaceRole.MEMBER.value) -> None:
    db.add(
        WorkspaceMember(
            workspace_id=ws.id,
            user_id=user.id,
            role=role,
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
    stage = _stage(db, ws)
    payload = IdeaCreate(
        title=kwargs.get("title", "Semantic idea"),
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


def test_create_idea_enqueues_job(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_embedding_env(monkeypatch)
    owner, _ = _user(db)
    ws = _team(db, owner)
    idea = _create_idea(db, ws, owner, title="Queue me")
    job = db.get(IdeaEmbeddingJob, idea.id)
    assert job is not None
    assert job.status == IdeaEmbeddingJobStatus.QUEUED.value


def test_non_content_update_does_not_enqueue(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_embedding_env(monkeypatch)
    owner, _ = _user(db)
    ws = _team(db, owner)
    idea = _create_idea(db, ws, owner)
    db.query(IdeaEmbeddingJob).filter(IdeaEmbeddingJob.idea_id == idea.id).delete()
    db.commit()
    idea_service.update_idea(
        db,
        idea=idea,
        access="OWNER",
        payload=IdeaUpdate.model_validate({"priority": "HIGH"}),
    )
    db.commit()
    assert db.get(IdeaEmbeddingJob, idea.id) is None


def test_worker_success_stores_embedding(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_embedding_env(monkeypatch)
    owner, _ = _user(db)
    ws = _team(db, owner)
    idea = _create_idea(db, ws, owner, title="Worker success")
    settings = get_settings()
    worker_id = "test-worker"
    session_factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
    processed = run_once(
        db,
        worker_id=worker_id,
        settings=settings,
        provider_factory=lambda s: FakeEmbeddingProvider(s),
        session_factory=session_factory,
    )
    assert processed
    row = db.get(IdeaEmbedding, idea.id)
    assert row is not None
    assert row.dimension == EMBEDDING_DIMENSION


def test_run_once_without_explicit_session_factory(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_embedding_env(monkeypatch)
    owner, _ = _user(db)
    ws = _team(db, owner)
    idea = _create_idea(db, ws, owner, title="Default factory path")
    settings = get_settings()
    processed = run_once(
        db,
        worker_id="default-factory-worker",
        settings=settings,
        provider_factory=lambda s: FakeEmbeddingProvider(s),
    )
    assert processed
    db.expire_all()
    row = db.get(IdeaEmbedding, idea.id)
    assert row is not None
    assert row.dimension == EMBEDDING_DIMENSION


def test_race_two_independent_sessions_not_saved(engine, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_embedding_env(monkeypatch)

    SessionFactory = sessionmaker(bind=engine, expire_on_commit=True)
    setup_session = SessionFactory()
    owner, _ = _user(setup_session)
    ws = _team(setup_session, owner)
    idea = _create_idea(setup_session, ws, owner, title="Hash A", problem="alpha content")
    job = setup_session.get(IdeaEmbeddingJob, idea.id)
    assert job is not None
    hash_a = job.content_hash
    idea_id = idea.id
    job.status = IdeaEmbeddingJobStatus.RUNNING.value
    job.worker_id = "worker-1"
    job.lease_until = datetime.now(timezone.utc) + timedelta(minutes=5)
    job.locked_at = datetime.now(timezone.utc)
    setup_session.commit()
    setup_session.close()

    settings = get_settings()

    class CrossSessionProvider(FakeEmbeddingProvider):
        def embed_text(self, text: str) -> list[float]:
            request_session = SessionFactory()
            try:
                fresh_idea = request_session.get(Idea, idea_id)
                idea_service.update_idea(
                    request_session,
                    idea=fresh_idea,
                    access="OWNER",
                    payload=IdeaUpdate.model_validate({"problem": "beta content changed"}),
                )
                request_session.commit()
            finally:
                request_session.close()
            return super().embed_text(text)

    worker_session = SessionFactory()
    try:
        worker_job = worker_session.get(IdeaEmbeddingJob, idea_id)
        work = prepare_claimed_embedding_work(
            worker_session,
            job=worker_job,
            worker_id="worker-1",
            claimed_revision=0,
        )
        assert work is not None
        assert work.content_hash == hash_a
        worker_session.commit()

        provider = CrossSessionProvider(settings)
        vector = provider.embed_text(work.embedding_text)

        finalize_session = SessionFactory()
        try:
            finalize_embedding_result(
                finalize_session,
                idea_id=work.idea_id,
                workspace_id=work.workspace_id,
                worker_id="worker-1",
                claimed_hash=work.content_hash,
                vector=vector,
                settings=settings,
            )
        finally:
            finalize_session.close()
    finally:
        worker_session.close()

    verify_session = SessionFactory()
    try:
        row = verify_session.get(IdeaEmbedding, idea_id)
        assert row is None or row.content_hash != hash_a

        refreshed_job = verify_session.get(IdeaEmbeddingJob, idea_id)
        assert refreshed_job is not None
        assert refreshed_job.content_hash != hash_a
        assert refreshed_job.status != IdeaEmbeddingJobStatus.SUCCEEDED.value

        worker_session2 = SessionFactory()
        try:
            processed = run_once(
                worker_session2,
                worker_id="worker-2",
                settings=settings,
                provider_factory=lambda s: FakeEmbeddingProvider(s),
                session_factory=SessionFactory,
            )
            assert processed
        finally:
            worker_session2.close()

        final_row = verify_session.get(IdeaEmbedding, idea_id)
        assert final_row is not None
        assert final_row.content_hash == refreshed_job.content_hash
    finally:
        verify_session.close()


def test_disabled_content_update_invalidates_embedding(
    client: TestClient,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_embedding_env(monkeypatch)

    owner, pw = _user(db)
    ws = _team(db, owner)
    idea = _create_idea(db, ws, owner, title="Stale guard", problem="alpha semantic content")
    from app.embeddings.canonical import build_idea_embedding_text

    text_a = build_idea_embedding_text(idea, load_idea_tag_names(db, idea.id))
    _store_embedding(db, idea, text=text_a)
    assert db.get(IdeaEmbedding, idea.id) is not None

    monkeypatch.setenv("EMBEDDING_ENABLED", "false")
    get_settings.cache_clear()

    idea = db.get(Idea, idea.id)
    idea_service.update_idea(
        db,
        idea=idea,
        access="OWNER",
        payload=IdeaUpdate.model_validate({"problem": "beta semantic content"}),
    )
    db.commit()

    assert db.get(IdeaEmbedding, idea.id) is None

    job = db.get(IdeaEmbeddingJob, idea.id)
    if job is not None:
        assert job.content_hash != compute_content_hash(text_a)

    monkeypatch.setenv("EMBEDDING_ENABLED", "true")
    get_settings.cache_clear()
    reset_engine()

    headers = _login(client, owner.email, pw)
    r = client.get(
        f"/api/v1/workspaces/{ws.id}/ideas",
        params={"q": "beta semantic content", "search_mode": "semantic"},
        headers=headers,
    )
    assert r.status_code == 200
    ids = [item["id"] for item in r.json()["items"]]
    assert str(idea.id) not in ids


def test_semantic_private_acl(client: TestClient, db: Session) -> None:
    owner, pw = _user(db)
    other, other_pw = _user(db)
    ws = _team(db, owner)
    _member(db, ws, other)
    private = _create_idea(
        db,
        ws,
        owner,
        title="비밀 임베딩",
        problem="private semantic",
        visibility=IdeaVisibility.PRIVATE,
    )
    from app.embeddings.canonical import build_idea_embedding_text
    from app.services.embedding_service import load_idea_tag_names

    text = build_idea_embedding_text(private, load_idea_tag_names(db, private.id))
    _store_embedding(db, private, text=text)

    _login(client, owner.email, pw)
    r_owner = client.get(
        f"/api/v1/workspaces/{ws.id}/ideas",
        params={"q": "private semantic", "search_mode": "semantic"},
        headers={"X-CSRF-Token": client.cookies.get(get_settings().auth_csrf_cookie_name) or ""},
    )
    assert r_owner.status_code == 200
    assert r_owner.json()["total"] >= 1

    _login(client, other.email, other_pw)
    r_other = client.get(
        f"/api/v1/workspaces/{ws.id}/ideas",
        params={"q": "private semantic", "search_mode": "semantic"},
        headers={"X-CSRF-Token": client.cookies.get(get_settings().auth_csrf_cookie_name) or ""},
    )
    assert r_other.status_code == 200
    assert r_other.json()["total"] == 0


def test_semantic_selected_users_share(client: TestClient, db: Session) -> None:
    owner, pw = _user(db)
    shared_user, shared_pw = _user(db)
    outsider, outsider_pw = _user(db)
    ws = _team(db, owner)
    _member(db, ws, shared_user)
    _member(db, ws, outsider)
    idea = _create_idea(
        db,
        ws,
        owner,
        title="Shared semantic",
        problem="selected users semantic",
        visibility=IdeaVisibility.SELECTED_USERS,
    )
    db.add(IdeaShare(idea_id=idea.id, user_id=shared_user.id, permission="READ"))
    db.commit()
    from app.embeddings.canonical import build_idea_embedding_text
    from app.services.embedding_service import load_idea_tag_names

    text = build_idea_embedding_text(idea, load_idea_tag_names(db, idea.id))
    _store_embedding(db, idea, text=text)

    _login(client, shared_user.email, shared_pw)
    assert (
        client.get(
            f"/api/v1/workspaces/{ws.id}/ideas",
            params={"q": "selected users semantic", "search_mode": "semantic"},
            headers={"X-CSRF-Token": client.cookies.get(get_settings().auth_csrf_cookie_name) or ""},
        ).json()["total"]
        == 1
    )
    _login(client, outsider.email, outsider_pw)
    assert (
        client.get(
            f"/api/v1/workspaces/{ws.id}/ideas",
            params={"q": "selected users semantic", "search_mode": "semantic"},
            headers={"X-CSRF-Token": client.cookies.get(get_settings().auth_csrf_cookie_name) or ""},
        ).json()["total"]
        == 0
    )


def test_semantic_unavailable_when_disabled(client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBEDDING_ENABLED", "false")
    get_settings.cache_clear()
    reset_engine()
    owner, pw = _user(db)
    ws = _team(db, owner)
    headers = _login(client, owner.email, pw)
    r = client.get(
        f"/api/v1/workspaces/{ws.id}/ideas",
        params={"q": "test", "search_mode": "semantic"},
        headers=headers,
    )
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "SEMANTIC_SEARCH_UNAVAILABLE"


def test_keyword_regression_unchanged(db: Session, client: TestClient) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    _create_idea(db, ws, owner, title="Keyword regression", problem="unique keyword xyz")
    headers = _login(client, owner.email, pw)
    direct = idea_service.list_ideas(
        db,
        workspace_id=ws.id,
        user_id=owner.id,
        q="unique keyword xyz",
    )
    api = client.get(
        f"/api/v1/workspaces/{ws.id}/ideas",
        params={"q": "unique keyword xyz", "search_mode": "keyword"},
        headers=headers,
    ).json()
    assert api["total"] == direct.total
    assert [i["id"] for i in api["items"]] == [str(i.id) for i in direct.items]


def test_hybrid_combines_keyword_and_semantic(client: TestClient, db: Session) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    kw = _create_idea(db, ws, owner, title="exact-keyword-token", problem="unrelated")
    sem = _create_idea(db, ws, owner, title="Other", problem="clinical triage assistant")
    from app.embeddings.canonical import build_idea_embedding_text
    from app.services.embedding_service import load_idea_tag_names

    sem_text = build_idea_embedding_text(sem, load_idea_tag_names(db, sem.id))
    _store_embedding(db, sem, text=sem_text)

    headers = _login(client, owner.email, pw)
    r = client.get(
        f"/api/v1/workspaces/{ws.id}/ideas",
        params={"q": "clinical triage", "search_mode": "hybrid"},
        headers=headers,
    )
    assert r.status_code == 200
    ids = [item["id"] for item in r.json()["items"]]
    assert str(sem.id) in ids


def test_hybrid_acl_race_revalidates_final_fetch(
    client: TestClient,
    db: Session,
    engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, owner_pw = _user(db)
    member, member_pw = _user(db)
    ws = _team(db, owner)
    _member(db, ws, member)
    idea = _create_idea(
        db,
        ws,
        owner,
        title="hybrid race keyword",
        problem="hybrid race semantic content",
        visibility=IdeaVisibility.WORKSPACE,
    )
    from app.embeddings.canonical import build_idea_embedding_text

    text = build_idea_embedding_text(idea, load_idea_tag_names(db, idea.id))
    _store_embedding(db, idea, text=text)
    idea_id = idea.id

    original_semantic = idea_search._semantic_ranked_ids
    SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)

    def semantic_then_revoke_acl(*args, **kwargs):
        ids = original_semantic(*args, **kwargs)
        revoke_session = SessionFactory()
        try:
            target = revoke_session.get(Idea, idea_id)
            target.visibility = IdeaVisibility.PRIVATE.value
            revoke_session.commit()
        finally:
            revoke_session.close()
        return ids

    monkeypatch.setattr(idea_search, "_semantic_ranked_ids", semantic_then_revoke_acl)

    headers = _login(client, member.email, member_pw)
    r = client.get(
        f"/api/v1/workspaces/{ws.id}/ideas",
        params={"q": "hybrid race", "search_mode": "hybrid"},
        headers=headers,
    )
    assert r.status_code == 200
    payload = r.json()
    ids = [item["id"] for item in payload["items"]]
    assert str(idea_id) not in ids
    assert payload["total"] == 0


def test_hybrid_result_window_within_limit(client: TestClient, db: Session) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    idea = _create_idea(db, ws, owner, title="window ok", problem="hybrid window content")
    from app.embeddings.canonical import build_idea_embedding_text

    _store_embedding(db, idea, text=build_idea_embedding_text(idea, load_idea_tag_names(db, idea.id)))

    headers = _login(client, owner.email, pw)
    r = client.get(
        f"/api/v1/workspaces/{ws.id}/ideas",
        params={"q": "hybrid window", "search_mode": "hybrid", "offset": 0, "limit": 50},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["total"] <= 300


def test_hybrid_result_window_exceeded_returns_400(client: TestClient, db: Session) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    headers = _login(client, owner.email, pw)
    r = client.get(
        f"/api/v1/workspaces/{ws.id}/ideas",
        params={"q": "anything", "search_mode": "hybrid", "offset": 300, "limit": 1},
        headers=headers,
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "HYBRID_RESULT_WINDOW_EXCEEDED"
