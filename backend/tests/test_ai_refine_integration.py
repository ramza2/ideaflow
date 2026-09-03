"""PostgreSQL Step 17 REFINE (registered Idea AI evolution) integration tests."""

from __future__ import annotations

import os
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import reset_engine
from app.llm.exceptions import LlmAuthenticationError
from app.llm.refine_schemas import IdeaRefinementRequest, IdeaRefinementResult
from app.llm.schemas import FieldProvenanceEntry
from app.main import app
from app.models.ai import AiJob, IdeaAiSession
from app.models.enums import (
    AiJobStatus,
    AiJobType,
    AiLlmDecision,
    FieldProvenanceSource,
    IdeaAiSessionPurpose,
    IdeaAiSessionStatus,
    SystemRole,
    UserStatus,
    WorkspaceMemberStatus,
    WorkspaceRole,
    WorkspaceType,
)
from app.models.idea import Idea
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.services import ai_worker
from app.services.workspace import seed_workspace_defaults

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — skipping AI refine integration tests",
)


class FakeRefineProvider:
    provider_name = "fake_refine"
    model_name = "fake-refine-model"
    prompt_version = "v2"
    refine_prompt_version = "v1"

    def __init__(self, results: list[IdeaRefinementResult | Exception] | None = None) -> None:
        self._results = list(results or [])
        self.requests: list[IdeaRefinementRequest] = []

    def structure_idea(self, request):
        raise AssertionError("REFINE job must not call structure_idea")

    def refine_idea_with_evidence(self, request):
        raise AssertionError("REFINE job must not call refine_idea_with_evidence")

    def refine_idea(self, request: IdeaRefinementRequest) -> IdeaRefinementResult:
        self.requests.append(request)
        if not self._results:
            raise RuntimeError("FakeRefineProvider exhausted")
        item = self._results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _ready_patch(patch: dict[str, Any] | None = None) -> IdeaRefinementResult:
    return IdeaRefinementResult(
        decision=AiLlmDecision.READY_FOR_REVIEW,
        draft_patch=patch
        or {
            "core_concept": "구체화된 핵심 개념",
            "major_features": "기능 A / 기능 B",
        },
        field_provenance={
            "core_concept": FieldProvenanceEntry(
                source=FieldProvenanceSource.LLM_SUMMARY,
                note="요약",
            )
        },
        research_recommended=False,
        research_topics=[],
    )


def _clarify_result() -> IdeaRefinementResult:
    return IdeaRefinementResult(
        decision=AiLlmDecision.NEEDS_CLARIFICATION,
        draft_patch={},
        clarifying_questions=[{"field": "target_users", "question": "주요 사용자는 누구인가요?"}],
        research_recommended=False,
        research_topics=[],
    )


@pytest.fixture(autouse=True)
def _clean_ai_tables(engine):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM ai_jobs"))
        conn.execute(text("DELETE FROM idea_ai_sessions"))
    yield


@pytest.fixture(scope="module")
def engine():
    reset_engine()
    get_settings.cache_clear()
    eng = create_engine(DATABASE_URL, pool_pre_ping=True)
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
def session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def client(engine, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("AI_WORKER_ENABLED", "false")
    monkeypatch.setenv("AI_JOB_LEASE_SECONDS", "300")
    get_settings.cache_clear()
    reset_engine()
    with TestClient(app) as c:
        yield c
    reset_engine()
    get_settings.cache_clear()


def _user(db: Session, *, password: str = "password-ok-1") -> tuple[User, str]:
    email = f"refine-{uuid.uuid4().hex[:10]}@example.com"
    user = User(
        email=email,
        name=email.split("@")[0],
        password_hash=hash_password(password),
        status=UserStatus.ACTIVE.value,
        system_role=SystemRole.USER.value,
        must_change_password=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, password


def _team(db: Session, owner: User, *, allow_llm: bool = True) -> Workspace:
    ws = Workspace(
        name=f"Refine Team {uuid.uuid4().hex[:6]}",
        type=WorkspaceType.TEAM.value,
        owner_id=owner.id,
        allow_llm=allow_llm,
    )
    db.add(ws)
    db.flush()
    db.add(
        WorkspaceMember(
            workspace_id=ws.id,
            user_id=owner.id,
            role=WorkspaceRole.ADMIN.value,
            status=WorkspaceMemberStatus.ACTIVE.value,
        )
    )
    seed_workspace_defaults(db, ws.id)
    db.commit()
    db.refresh(ws)
    return ws


def _add_member(db: Session, workspace: Workspace, user: User, *, role: str) -> None:
    db.add(
        WorkspaceMember(
            workspace_id=workspace.id,
            user_id=user.id,
            role=role,
            status=WorkspaceMemberStatus.ACTIVE.value,
        )
    )
    db.commit()


def _csrf(client: TestClient) -> str:
    return client.get("/api/v1/auth/csrf").json()["csrf_token"]


def _login(client: TestClient, email: str, password: str) -> None:
    client.cookies.clear()
    r = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers={"X-CSRF-Token": _csrf(client)},
    )
    assert r.status_code == 200, r.text


def _headers(client: TestClient) -> dict[str, str]:
    token = client.cookies.get(get_settings().auth_csrf_cookie_name)
    assert token
    return {"X-CSRF-Token": token}


def _create_idea(client: TestClient, ws: Workspace, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "title": "원본 아이디어",
        "one_line_definition": "한 줄 정의",
        "problem": "해결할 문제",
        "core_concept": "초기 핵심 개념",
        "priority": "MEDIUM",
        "feasibility": "UNKNOWN",
        "visibility": "WORKSPACE",
        "tags": ["AI"],
    }
    body.update(overrides)
    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ideas",
        json=body,
        headers=_headers(client),
    )
    assert r.status_code == 201, r.text
    return r.json()


def _start_refine(
    client: TestClient,
    ws: Workspace,
    idea_id: str,
    *,
    direction: str = "EXPAND_DETAIL",
) -> dict[str, Any]:
    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ideas/{idea_id}/ai-refine-sessions",
        json={"direction": direction},
        headers=_headers(client),
    )
    assert r.status_code == 202, r.text
    return r.json()


def _apply_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "title": "원본 아이디어",
        "one_line_definition": "한 줄 정의",
        "problem": "해결할 문제",
        "core_concept": "구체화된 핵심 개념",
        "major_features": "기능 A / 기능 B",
        "priority": "MEDIUM",
        "feasibility": "UNKNOWN",
        "tags": ["AI"],
    }
    body.update(overrides)
    return body


def test_create_refine_session_snapshots_source_and_enqueues_refine_job(
    client: TestClient,
    db: Session,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    idea = _create_idea(client, ws)

    body = _start_refine(client, ws, idea["id"], direction="TECHNICAL_IMPLEMENTATION")
    assert body["purpose"] == "REFINE"
    assert body["status"] == "PROCESSING"
    assert body["refine_direction"] == "TECHNICAL_IMPLEMENTATION"
    assert body["source_idea_id"] == idea["id"]
    assert body["source_idea_snapshot"]["title"] == "원본 아이디어"
    assert body["source_idea_snapshot"]["tags"] == ["AI"]
    assert body["result_idea_id"] is None
    assert body["llm"]["prompt_version"] == "v1"

    session = db.get(IdeaAiSession, uuid.UUID(body["id"]))
    assert session.purpose == IdeaAiSessionPurpose.REFINE.value
    assert session.source_idea_updated_at is not None
    jobs = list(db.scalars(select(AiJob).where(AiJob.session_id == session.id)))
    assert len(jobs) == 1
    assert jobs[0].job_type == AiJobType.REFINE_IDEA.value


def test_refine_requires_edit_permission(client: TestClient, db: Session) -> None:
    owner, pw_owner = _user(db)
    reader, pw_reader = _user(db)
    ws = _team(db, owner)
    _add_member(db, ws, reader, role=WorkspaceRole.MEMBER.value)

    _login(client, owner.email, pw_owner)
    idea = _create_idea(client, ws)

    _login(client, reader.email, pw_reader)
    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ideas/{idea['id']}/ai-refine-sessions",
        json={"direction": "EXPAND_DETAIL"},
        headers=_headers(client),
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "IDEA_EDIT_FORBIDDEN"


def test_refine_blocked_when_workspace_llm_disabled(client: TestClient, db: Session) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner, allow_llm=False)
    _login(client, owner.email, pw)

    ws.allow_llm = True
    db.commit()
    idea = _create_idea(client, ws)
    ws.allow_llm = False
    db.commit()

    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ideas/{idea['id']}/ai-refine-sessions",
        json={"direction": "EXPAND_DETAIL"},
        headers=_headers(client),
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "WORKSPACE_LLM_DISABLED"


def test_refine_worker_merges_patch_onto_source_snapshot(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    idea = _create_idea(client, ws)
    session_id = uuid.UUID(_start_refine(client, ws, idea["id"])["id"])

    provider = FakeRefineProvider([_ready_patch()])
    assert ai_worker.run_once(session_factory=session_factory, provider=provider)

    assert len(provider.requests) == 1
    request = provider.requests[0]
    assert request.direction.value == "EXPAND_DETAIL"
    assert request.source_context["title"] == "원본 아이디어"

    db.expire_all()
    session = db.get(IdeaAiSession, session_id)
    assert session.status == IdeaAiSessionStatus.READY_FOR_REVIEW.value
    # Unpatched fields keep their source values; patched fields are replaced.
    assert session.draft_payload["title"] == "원본 아이디어"
    assert session.draft_payload["problem"] == "해결할 문제"
    assert session.draft_payload["core_concept"] == "구체화된 핵심 개념"
    assert session.draft_payload["major_features"] == "기능 A / 기능 B"
    assert session.draft_payload["tags"] == ["AI"]
    # Provenance is recorded only for patched fields.
    assert session.field_provenance["core_concept"]["source"] == "LLM_SUMMARY"
    assert session.field_provenance["major_features"]["source"] == "LLM_INFERENCE"
    assert "problem" not in session.field_provenance
    assert session.prompt_version == "v1"
    assert session.llm_provider == "fake_refine"

    job = db.scalars(select(AiJob).where(AiJob.session_id == session_id)).one()
    assert job.status == AiJobStatus.SUCCEEDED.value


def test_refine_worker_rejects_noop_ready_patch(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    idea = _create_idea(client, ws)
    session_id = uuid.UUID(_start_refine(client, ws, idea["id"])["id"])

    job = db.scalars(select(AiJob).where(AiJob.session_id == session_id)).one()
    job.max_attempts = 1
    db.commit()

    # Patch repeats the source value verbatim — not a real refinement.
    provider = FakeRefineProvider([_ready_patch({"core_concept": "초기 핵심 개념"})])
    ai_worker.run_once(session_factory=session_factory, provider=provider)

    db.expire_all()
    session = db.get(IdeaAiSession, session_id)
    assert session.status == IdeaAiSessionStatus.FAILED.value
    assert session.failure_code == "LLM_RESPONSE_INVALID"
    assert session.draft_payload is None


def test_refine_clarification_enqueues_refine_job(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    idea = _create_idea(client, ws)
    session_id = uuid.UUID(_start_refine(client, ws, idea["id"])["id"])

    ai_worker.run_once(
        session_factory=session_factory,
        provider=FakeRefineProvider([_clarify_result()]),
    )

    g = client.get(f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}")
    assert g.json()["status"] == "NEEDS_CLARIFICATION"
    question_id = g.json()["clarifying_questions"][0]["id"]

    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/clarifications",
        json={"answers": [{"question_id": question_id, "answer": "연구개발 담당자"}]},
        headers=_headers(client),
    )
    assert r.status_code == 200
    jobs = list(db.scalars(select(AiJob).where(AiJob.session_id == session_id)))
    assert len(jobs) == 2
    assert {j.job_type for j in jobs} == {AiJobType.REFINE_IDEA.value}

    provider = FakeRefineProvider([_ready_patch()])
    ai_worker.run_once(session_factory=session_factory, provider=provider)
    db.expire_all()
    session = db.get(IdeaAiSession, session_id)
    assert session.status == IdeaAiSessionStatus.READY_FOR_REVIEW.value
    assert provider.requests[0].clarification_answers[0]["answer"] == "연구개발 담당자"


def test_refine_retry_enqueues_refine_job(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    idea = _create_idea(client, ws)
    session_id = uuid.UUID(_start_refine(client, ws, idea["id"])["id"])

    ai_worker.run_once(
        session_factory=session_factory,
        provider=FakeRefineProvider([LlmAuthenticationError()]),
    )
    db.expire_all()
    assert db.get(IdeaAiSession, session_id).status == IdeaAiSessionStatus.FAILED.value

    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/retry",
        headers=_headers(client),
    )
    assert r.status_code == 200
    jobs = list(db.scalars(select(AiJob).where(AiJob.session_id == session_id)))
    assert {j.job_type for j in jobs} == {AiJobType.REFINE_IDEA.value}


def test_refine_regenerate_creates_new_refine_session(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    idea = _create_idea(client, ws)
    first = _start_refine(client, ws, idea["id"], direction="RISK_ANALYSIS")
    ai_worker.run_once(
        session_factory=session_factory,
        provider=FakeRefineProvider([_ready_patch()]),
    )

    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{first['id']}/regenerate",
        headers=_headers(client),
    )
    assert r.status_code == 200, r.text
    new_session = r.json()["session"]
    assert new_session["id"] != first["id"]
    assert new_session["purpose"] == "REFINE"
    assert new_session["refine_direction"] == "RISK_ANALYSIS"
    assert new_session["source_idea_id"] == idea["id"]
    assert new_session["draft"] is None
    assert not new_session["clarifying_questions"]

    jobs = list(
        db.scalars(select(AiJob).where(AiJob.session_id == uuid.UUID(new_session["id"])))
    )
    assert [j.job_type for j in jobs] == [AiJobType.REFINE_IDEA.value]


def test_refine_regenerate_rejects_changed_source(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    idea = _create_idea(client, ws)
    first = _start_refine(client, ws, idea["id"])
    ai_worker.run_once(
        session_factory=session_factory,
        provider=FakeRefineProvider([_ready_patch()]),
    )

    patched = client.patch(
        f"/api/v1/workspaces/{ws.id}/ideas/{idea['id']}",
        json={"problem": "직접 수정한 문제"},
        headers=_headers(client),
    )
    assert patched.status_code == 200

    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{first['id']}/regenerate",
        headers=_headers(client),
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "AI_REFINE_SOURCE_CHANGED"


def test_apply_refinement_updates_source_idea_and_is_idempotent(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    idea = _create_idea(client, ws)
    session_id = _start_refine(client, ws, idea["id"])["id"]
    ai_worker.run_once(
        session_factory=session_factory,
        provider=FakeRefineProvider([_ready_patch()]),
    )

    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/apply-refinement",
        json=_apply_body(),
        headers=_headers(client),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["updated"] is True
    assert body["idea"]["id"] == idea["id"]
    assert body["idea"]["core_concept"] == "구체화된 핵심 개념"
    assert body["idea"]["major_features"] == "기능 A / 기능 B"
    # A refinement never creates a second Idea.
    assert db.scalar(select(Idea.id).where(Idea.workspace_id == ws.id)) == uuid.UUID(idea["id"])

    db.expire_all()
    session = db.get(IdeaAiSession, uuid.UUID(session_id))
    assert session.status == IdeaAiSessionStatus.CONFIRMED.value
    assert session.result_idea_id == uuid.UUID(idea["id"])
    assert session.confirmed_at is not None

    # Replaying the same apply is a no-op that returns the current idea.
    again = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/apply-refinement",
        json=_apply_body(),
        headers=_headers(client),
    )
    assert again.status_code == 200, again.text
    assert again.json()["updated"] is False
    assert again.json()["idea"]["core_concept"] == "구체화된 핵심 개념"


def test_apply_refinement_preserves_workflow_fields(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    idea = _create_idea(client, ws, visibility="PRIVATE", next_review_date="2030-01-01")
    session_id = _start_refine(client, ws, idea["id"])["id"]
    ai_worker.run_once(
        session_factory=session_factory,
        provider=FakeRefineProvider([_ready_patch()]),
    )

    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/apply-refinement",
        json=_apply_body(),
        headers=_headers(client),
    )
    assert r.status_code == 200, r.text
    updated = r.json()["idea"]
    assert updated["visibility"] == "PRIVATE"
    assert updated["next_review_date"] == "2030-01-01"
    assert updated["stage"]["id"] == idea["stage"]["id"]
    assert updated["original_text"] == idea["original_text"]


def test_apply_refinement_rejects_changed_source(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    idea = _create_idea(client, ws)
    session_id = _start_refine(client, ws, idea["id"])["id"]
    ai_worker.run_once(
        session_factory=session_factory,
        provider=FakeRefineProvider([_ready_patch()]),
    )

    patched = client.patch(
        f"/api/v1/workspaces/{ws.id}/ideas/{idea['id']}",
        json={"problem": "그 사이 직접 수정"},
        headers=_headers(client),
    )
    assert patched.status_code == 200

    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/apply-refinement",
        json=_apply_body(),
        headers=_headers(client),
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "AI_REFINE_SOURCE_CHANGED"

    db.expire_all()
    session = db.get(IdeaAiSession, uuid.UUID(session_id))
    assert session.status == IdeaAiSessionStatus.READY_FOR_REVIEW.value
    assert db.get(Idea, uuid.UUID(idea["id"])).problem == "그 사이 직접 수정"


def test_apply_refinement_rejects_no_changes(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    idea = _create_idea(client, ws)
    session_id = _start_refine(client, ws, idea["id"])["id"]
    ai_worker.run_once(
        session_factory=session_factory,
        provider=FakeRefineProvider([_ready_patch()]),
    )

    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/apply-refinement",
        json=_apply_body(core_concept="초기 핵심 개념", major_features=None),
        headers=_headers(client),
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "AI_REFINE_NO_CHANGES"

    db.expire_all()
    session = db.get(IdeaAiSession, uuid.UUID(session_id))
    assert session.status == IdeaAiSessionStatus.READY_FOR_REVIEW.value
    assert session.result_idea_id is None


def test_apply_refinement_requester_only(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw_owner = _user(db)
    other, pw_other = _user(db)
    ws = _team(db, owner)
    _add_member(db, ws, other, role=WorkspaceRole.ADMIN.value)

    _login(client, owner.email, pw_owner)
    idea = _create_idea(client, ws)
    session_id = _start_refine(client, ws, idea["id"])["id"]
    ai_worker.run_once(
        session_factory=session_factory,
        provider=FakeRefineProvider([_ready_patch()]),
    )

    _login(client, other.email, pw_other)
    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/apply-refinement",
        json=_apply_body(),
        headers=_headers(client),
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "AI_SESSION_NOT_FOUND"


def test_apply_refinement_rejects_create_session(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    from tests.test_ai_session_integration import FakeProvider, _ready_result

    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    created = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions",
        json={"input_text": "새 아이디어 입력 텍스트"},
        headers=_headers(client),
    )
    session_id = created.json()["id"]
    ai_worker.run_once(
        session_factory=session_factory,
        provider=FakeProvider([_ready_result()]),
    )

    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/apply-refinement",
        json=_apply_body(),
        headers=_headers(client),
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "AI_SESSION_INVALID_STATE"


def test_refine_input_too_large_fails_without_retry(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    idea = _create_idea(client, ws, one_line_definition=None)
    session_id = uuid.UUID(_start_refine(client, ws, idea["id"])["id"])

    monkeypatch.setenv("AI_REFINE_MAX_PROMPT_CHARS", "100")
    get_settings.cache_clear()
    settings = get_settings()

    provider = FakeRefineProvider([_ready_patch()])
    ai_worker.run_once(
        session_factory=session_factory,
        provider=provider,
        settings=settings,
    )

    assert provider.requests == []
    db.expire_all()
    session = db.get(IdeaAiSession, session_id)
    assert session.status == IdeaAiSessionStatus.FAILED.value
    assert session.failure_code == "AI_REFINE_INPUT_TOO_LARGE"
    job = db.scalars(select(AiJob).where(AiJob.session_id == session_id)).one()
    assert job.status == AiJobStatus.FAILED.value
    assert job.attempts == 1
