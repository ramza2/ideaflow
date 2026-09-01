"""Idea Validation workflow integration tests (Step 14)."""

from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import reset_engine
from app.main import app
from app.models.embedding import IdeaEmbeddingJob
from app.models.enums import (
    IdeaSharePermission,
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
from app.models.validation import IdeaValidation
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceStage
from app.schemas.idea import IdeaCreate
from app.services.idea import create_idea
from app.services.workspace import seed_workspace_defaults

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — skipping validation integration tests",
)


@pytest.fixture(scope="module")
def engine():
    reset_engine()
    get_settings.cache_clear()
    eng = create_engine(DATABASE_URL, pool_pre_ping=True)
    from sqlalchemy import text

    with eng.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS idea_validations (
                    id UUID PRIMARY KEY,
                    idea_id UUID NOT NULL REFERENCES ideas(id) ON DELETE CASCADE,
                    created_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
                    title VARCHAR(200) NOT NULL,
                    hypothesis TEXT NOT NULL,
                    method TEXT NOT NULL,
                    success_criteria TEXT NOT NULL,
                    planned_evidence TEXT,
                    status VARCHAR(32) NOT NULL DEFAULT 'DRAFT',
                    outcome VARCHAR(32),
                    result_summary TEXT,
                    evidence_summary TEXT,
                    due_date DATE,
                    started_at TIMESTAMPTZ,
                    completed_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    CONSTRAINT idea_validation_status CHECK (
                        status IN ('DRAFT', 'READY', 'RUNNING', 'COMPLETED', 'CANCELLED')
                    ),
                    CONSTRAINT idea_validation_outcome CHECK (
                        outcome IS NULL OR outcome IN ('PASS', 'PARTIAL', 'FAIL', 'INCONCLUSIVE')
                    ),
                    CONSTRAINT idea_validation_completed_invariant CHECK (
                        (status = 'COMPLETED' AND outcome IS NOT NULL AND result_summary IS NOT NULL AND completed_at IS NOT NULL)
                        OR (status <> 'COMPLETED' AND outcome IS NULL)
                    ),
                    CONSTRAINT idea_validation_timing_invariant CHECK (
                        (status = 'RUNNING' AND started_at IS NOT NULL)
                        OR (status IN ('DRAFT', 'READY') AND started_at IS NULL AND completed_at IS NULL)
                        OR (status IN ('COMPLETED', 'CANCELLED'))
                    )
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_idea_validations_idea_id ON idea_validations (idea_id)"))
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_idea_validations_created_by ON idea_validations (created_by)")
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_idea_validations_status ON idea_validations (status)"))
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_idea_validations_idea_created "
                "ON idea_validations (idea_id, created_at)"
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
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client(engine, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("AI_WORKER_ENABLED", "false")
    monkeypatch.setenv("EMBEDDING_WORKER_ENABLED", "false")
    monkeypatch.setenv("EMBEDDING_ENABLED", "false")
    get_settings.cache_clear()
    reset_engine()
    with TestClient(app) as c:
        yield c
    reset_engine()
    get_settings.cache_clear()


def _user(db: Session, *, email: str | None = None, password: str = "password-ok-1") -> tuple[User, str]:
    email = email or f"val-{uuid.uuid4().hex[:10]}@example.com"
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
    ws = Workspace(name=f"ValTeam-{uuid.uuid4().hex[:6]}", type=WorkspaceType.TEAM.value, owner_id=owner.id)
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


def _stage(db: Session, ws: Workspace, slug: str) -> WorkspaceStage:
    return db.scalar(
        select(WorkspaceStage).where(
            WorkspaceStage.workspace_id == ws.id,
            WorkspaceStage.slug == slug,
            WorkspaceStage.deleted_at.is_(None),
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
    assert token
    return {"X-CSRF-Token": token}


def _create_idea(
    db: Session,
    ws: Workspace,
    author: User,
    *,
    stage_slug: str = "validation_candidate",
    visibility=IdeaVisibility.WORKSPACE,
    title: str = "Validation idea",
) -> Idea:
    stage = _stage(db, ws, stage_slug)
    idea = create_idea(
        db,
        workspace_id=ws.id,
        author=author,
        payload=IdeaCreate(
            title=title,
            problem="p",
            core_concept="c",
            stage_id=stage.id,
            visibility=visibility,
            tags=[],
        ),
    )
    db.commit()
    db.refresh(idea)
    return idea


def _url(ws_id, idea_id, suffix: str = "") -> str:
    return f"/api/v1/workspaces/{ws_id}/ideas/{idea_id}/validations{suffix}"


def _create_via_api(client, headers, ws, idea) -> dict:
    r = client.post(
        _url(ws.id, idea.id),
        headers=headers,
        json={
            "title": "MVP 가설 검증",
            "hypothesis": "사용자가 클릭한다",
            "method": "랜딩 페이지 A/B",
            "success_criteria": "전환율 5%+",
            "planned_evidence": "이벤트 로그",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_create_list_get_edit(client: TestClient, db: Session) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    idea = _create_idea(db, ws, owner)
    headers = _login(client, owner.email, pw)

    created = _create_via_api(client, headers, ws, idea)
    assert created["status"] == "DRAFT"
    assert created["outcome"] is None

    listed = client.get(_url(ws.id, idea.id), headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    got = client.get(_url(ws.id, idea.id, f"/{created['id']}"), headers=headers)
    assert got.status_code == 200
    assert got.json()["title"] == "MVP 가설 검증"

    patched = client.patch(
        _url(ws.id, idea.id, f"/{created['id']}"),
        headers=headers,
        json={"title": "수정된 제목"},
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "수정된 제목"


def test_state_machine_happy_path(client: TestClient, db: Session) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    idea = _create_idea(db, ws, owner, stage_slug="validation_candidate")
    headers = _login(client, owner.email, pw)
    created = _create_via_api(client, headers, ws, idea)
    vid = created["id"]

    ready = client.post(_url(ws.id, idea.id, f"/{vid}/ready"), headers=headers)
    assert ready.status_code == 200
    assert ready.json()["status"] == "READY"

    start = client.post(_url(ws.id, idea.id, f"/{vid}/start"), headers=headers)
    assert start.status_code == 200, start.text
    assert start.json()["validation"]["status"] == "RUNNING"
    assert start.json()["idea_stage"]["slug"] == "validating"

    db.expire_all()
    refreshed = db.get(Idea, idea.id)
    stage = db.get(WorkspaceStage, refreshed.stage_id)
    assert stage.slug == "validating"

    complete = client.post(
        _url(ws.id, idea.id, f"/{vid}/complete"),
        headers=headers,
        json={"outcome": "PASS", "result_summary": "전환율 7%"},
    )
    assert complete.status_code == 200
    assert complete.json()["status"] == "COMPLETED"
    assert complete.json()["outcome"] == "PASS"

    db.expire_all()
    stage_after = db.get(WorkspaceStage, db.get(Idea, idea.id).stage_id)
    assert stage_after.slug == "validating"  # no auto execution_candidate


def test_start_wrong_stage_rejected(client: TestClient, db: Session) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    idea = _create_idea(db, ws, owner, stage_slug="memo")
    headers = _login(client, owner.email, pw)
    created = _create_via_api(client, headers, ws, idea)
    client.post(_url(ws.id, idea.id, f"/{created['id']}/ready"), headers=headers)
    start = client.post(_url(ws.id, idea.id, f"/{created['id']}/start"), headers=headers)
    assert start.status_code == 409
    assert start.json()["error"]["code"] == "IDEA_NOT_READY_FOR_VALIDATION"


def test_complete_requires_outcome_and_summary(client: TestClient, db: Session) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    idea = _create_idea(db, ws, owner)
    headers = _login(client, owner.email, pw)
    created = _create_via_api(client, headers, ws, idea)
    vid = created["id"]
    client.post(_url(ws.id, idea.id, f"/{vid}/ready"), headers=headers)
    client.post(_url(ws.id, idea.id, f"/{vid}/start"), headers=headers)

    bad = client.post(
        _url(ws.id, idea.id, f"/{vid}/complete"),
        headers=headers,
        json={"outcome": "PASS", "result_summary": ""},
    )
    assert bad.status_code == 422 or bad.status_code == 400


def test_invalid_transition(client: TestClient, db: Session) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    idea = _create_idea(db, ws, owner)
    headers = _login(client, owner.email, pw)
    created = _create_via_api(client, headers, ws, idea)
    start = client.post(_url(ws.id, idea.id, f"/{created['id']}/start"), headers=headers)
    assert start.status_code == 409
    assert start.json()["error"]["code"] == "INVALID_VALIDATION_TRANSITION"


def test_cancel_paths(client: TestClient, db: Session) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    idea = _create_idea(db, ws, owner)
    headers = _login(client, owner.email, pw)
    created = _create_via_api(client, headers, ws, idea)
    cancel = client.post(_url(ws.id, idea.id, f"/{created['id']}/cancel"), headers=headers)
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "CANCELLED"
    edit = client.patch(
        _url(ws.id, idea.id, f"/{created['id']}"),
        headers=headers,
        json={"title": "nope"},
    )
    assert edit.status_code == 409
    assert edit.json()["error"]["code"] == "VALIDATION_NOT_EDITABLE"


def test_private_acl(client: TestClient, db: Session) -> None:
    owner, pw = _user(db)
    other, other_pw = _user(db)
    ws = _team(db, owner)
    _member(db, ws, other)
    idea = _create_idea(db, ws, owner, visibility=IdeaVisibility.PRIVATE)
    owner_h = _login(client, owner.email, pw)
    created = _create_via_api(client, owner_h, ws, idea)

    other_h = _login(client, other.email, other_pw)
    denied = client.get(_url(ws.id, idea.id), headers=other_h)
    assert denied.status_code == 404
    mutate = client.post(
        _url(ws.id, idea.id),
        headers=other_h,
        json={
            "title": "x",
            "hypothesis": "h",
            "method": "m",
            "success_criteria": "s",
        },
    )
    assert mutate.status_code == 404
    owner_h = _login(client, owner.email, pw)
    assert client.get(_url(ws.id, idea.id, f"/{created['id']}"), headers=owner_h).status_code == 200


def test_selected_users_share_edit(client: TestClient, db: Session) -> None:
    owner, pw = _user(db)
    editor, editor_pw = _user(db)
    reader, reader_pw = _user(db)
    ws = _team(db, owner)
    _member(db, ws, editor)
    _member(db, ws, reader)
    idea = _create_idea(db, ws, owner, visibility=IdeaVisibility.SELECTED_USERS)
    db.add(IdeaShare(idea_id=idea.id, user_id=editor.id, permission=IdeaSharePermission.EDIT.value))
    db.add(IdeaShare(idea_id=idea.id, user_id=reader.id, permission=IdeaSharePermission.READ.value))
    db.commit()

    owner_h = _login(client, owner.email, pw)
    created = _create_via_api(client, owner_h, ws, idea)

    editor_h = _login(client, editor.email, editor_pw)
    assert client.get(_url(ws.id, idea.id), headers=editor_h).status_code == 200
    ok = client.patch(
        _url(ws.id, idea.id, f"/{created['id']}"),
        headers=editor_h,
        json={"title": "에디터 수정"},
    )
    assert ok.status_code == 200

    reader_h = _login(client, reader.email, reader_pw)
    assert client.get(_url(ws.id, idea.id), headers=reader_h).status_code == 200
    denied = client.patch(
        _url(ws.id, idea.id, f"/{created['id']}"),
        headers=reader_h,
        json={"title": "리더 수정"},
    )
    assert denied.status_code == 403


def test_workspace_isolation(client: TestClient, db: Session) -> None:
    owner_a, pw_a = _user(db)
    owner_b, pw_b = _user(db)
    ws_a = _team(db, owner_a)
    ws_b = _team(db, owner_b)
    idea_a = _create_idea(db, ws_a, owner_a)
    idea_b = _create_idea(db, ws_b, owner_b)
    h_a = _login(client, owner_a.email, pw_a)
    created = _create_via_api(client, h_a, ws_a, idea_a)

    h_b = _login(client, owner_b.email, pw_b)
    leak = client.get(_url(ws_b.id, idea_a.id, f"/{created['id']}"), headers=h_b)
    assert leak.status_code == 404
    h_a = _login(client, owner_a.email, pw_a)
    mismatch = client.get(_url(ws_a.id, idea_b.id, f"/{created['id']}"), headers=h_a)
    assert mismatch.status_code == 404


def test_validation_does_not_enqueue_embedding(client: TestClient, db: Session, monkeypatch) -> None:
    from sqlalchemy import inspect as sa_inspect

    calls: list[str] = []

    def _spy_enqueue(*args, **kwargs):
        calls.append("enqueue")
        raise AssertionError("validation must not enqueue embedding jobs")

    def _spy_invalidate(*args, **kwargs):
        calls.append("invalidate")
        raise AssertionError("validation must not invalidate embeddings")

    monkeypatch.setattr("app.services.embedding_service.enqueue_embedding_if_needed", _spy_enqueue)
    monkeypatch.setattr("app.services.embedding_service.invalidate_embedding", _spy_invalidate)

    owner, pw = _user(db)
    ws = _team(db, owner)
    idea = _create_idea(db, ws, owner, stage_slug="validation_candidate")

    headers = _login(client, owner.email, pw)
    created = _create_via_api(client, headers, ws, idea)
    assert client.post(_url(ws.id, idea.id, f"/{created['id']}/ready"), headers=headers).status_code == 200
    assert client.post(_url(ws.id, idea.id, f"/{created['id']}/start"), headers=headers).status_code == 200
    assert (
        client.post(
            _url(ws.id, idea.id, f"/{created['id']}/complete"),
            headers=headers,
            json={"outcome": "FAIL", "result_summary": "기준 미달"},
        ).status_code
        == 200
    )
    assert calls == []

    # When Step 13 embedding tables exist, also assert no jobs were written.
    if sa_inspect(db.get_bind()).has_table("idea_embedding_jobs"):
        db.expire_all()
        jobs = list(db.scalars(select(IdeaEmbeddingJob).where(IdeaEmbeddingJob.idea_id == idea.id)))
        assert jobs == []


def test_start_race_two_sessions(engine, db: Session) -> None:
    from app.schemas.validation import IdeaValidationCreateRequest
    from app.services import validation as validation_service

    owner, _ = _user(db)
    ws = _team(db, owner)
    idea = _create_idea(db, ws, owner)
    row = validation_service.create_validation(
        db,
        workspace_id=ws.id,
        idea_id=idea.id,
        user_id=owner.id,
        payload=IdeaValidationCreateRequest(
            title="race",
            hypothesis="h",
            method="m",
            success_criteria="s",
        ),
    )
    validation_service.mark_ready(
        db,
        workspace_id=ws.id,
        idea_id=idea.id,
        validation_id=row.id,
        user_id=owner.id,
    )
    db.commit()

    SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)
    results: list[str] = []

    def worker() -> None:
        session = SessionFactory()
        try:
            out = validation_service.start_validation(
                session,
                workspace_id=ws.id,
                idea_id=idea.id,
                validation_id=row.id,
                user_id=owner.id,
            )
            session.commit()
            results.append(out.validation.status.value)
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            results.append(type(exc).__name__)
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: worker(), range(2)))

    assert results.count("RUNNING") >= 1
    assert "RUNNING" in results
    assert set(results) <= {"RUNNING", "AppError"}
    verify = SessionFactory()
    try:
        final = verify.get(IdeaValidation, row.id)
        assert getattr(final.status, "value", final.status) == "RUNNING"
        assert final.started_at is not None
    finally:
        verify.close()


def test_complete_vs_cancel_race(engine, db: Session) -> None:
    from app.schemas.validation import IdeaValidationCompleteRequest, IdeaValidationCreateRequest
    from app.services import validation as validation_service

    owner, _ = _user(db)
    ws = _team(db, owner)
    idea = _create_idea(db, ws, owner)
    row = validation_service.create_validation(
        db,
        workspace_id=ws.id,
        idea_id=idea.id,
        user_id=owner.id,
        payload=IdeaValidationCreateRequest(
            title="race2",
            hypothesis="h",
            method="m",
            success_criteria="s",
        ),
    )
    validation_service.mark_ready(
        db, workspace_id=ws.id, idea_id=idea.id, validation_id=row.id, user_id=owner.id
    )
    validation_service.start_validation(
        db, workspace_id=ws.id, idea_id=idea.id, validation_id=row.id, user_id=owner.id
    )
    db.commit()

    SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)
    results: list[str] = []

    def complete_worker() -> None:
        session = SessionFactory()
        try:
            out = validation_service.complete_validation(
                session,
                workspace_id=ws.id,
                idea_id=idea.id,
                validation_id=row.id,
                user_id=owner.id,
                payload=IdeaValidationCompleteRequest(
                    outcome="PASS",
                    result_summary="ok",
                ),
            )
            session.commit()
            results.append(getattr(out.status, "value", out.status))
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            results.append(type(exc).__name__)
        finally:
            session.close()

    def cancel_worker() -> None:
        session = SessionFactory()
        try:
            out = validation_service.cancel_validation(
                session,
                workspace_id=ws.id,
                idea_id=idea.id,
                validation_id=row.id,
                user_id=owner.id,
            )
            session.commit()
            results.append(getattr(out.status, "value", out.status))
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            results.append(type(exc).__name__)
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(complete_worker)
        f2 = pool.submit(cancel_worker)
        f1.result()
        f2.result()

    assert set(results) <= {"COMPLETED", "CANCELLED", "AppError"}
    assert results.count("COMPLETED") + results.count("CANCELLED") == 1
    verify = SessionFactory()
    try:
        final = verify.get(IdeaValidation, row.id)
        status = getattr(final.status, "value", final.status)
        assert status in {"COMPLETED", "CANCELLED"}
        if status == "COMPLETED":
            assert final.outcome is not None
            assert final.result_summary is not None
            assert final.completed_at is not None
        else:
            assert final.outcome is None
            assert final.completed_at is None
    finally:
        verify.close()
