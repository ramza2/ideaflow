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

    def __init__(
        self,
        results: list[IdeaRefinementResult | Exception] | None = None,
        *,
        evidence_results: list[Any] | None = None,
    ) -> None:
        self._results = list(results or [])
        self._evidence_results = list(evidence_results or [])
        self.requests: list[IdeaRefinementRequest] = []
        self.evidence_requests: list[Any] = []

    def structure_idea(self, request):
        raise AssertionError("REFINE job must not call structure_idea")

    def refine_idea_with_evidence(self, request):
        self.evidence_requests.append(request)
        if not self._evidence_results:
            raise RuntimeError("FakeRefineProvider evidence results exhausted")
        item = self._evidence_results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def refine_idea(self, request: IdeaRefinementRequest) -> IdeaRefinementResult:
        self.requests.append(request)
        if not self._results:
            raise RuntimeError("FakeRefineProvider exhausted")
        item = self._results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeSearchProvider:
    provider_name = "fake_search"
    calls = 0
    last_bodies: list[dict[str, Any]] = []

    def __init__(self, *, url: str = "https://example.com/refine-evidence") -> None:
        self._url = url

    def search(self, *, query: str, max_results: int):
        from app.web_search.base import WebSearchResult

        type(self).calls += 1
        type(self).last_bodies.append({"query": query, "max_results": max_results})
        return [
            WebSearchResult(
                title="Refine Evidence",
                url=self._url,
                snippet="Helpful refine snippet",
                source="Example",
            )
        ]

    def close(self) -> None:
        pass


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
        conn.execute(text("DELETE FROM web_evidence"))
        conn.execute(text("DELETE FROM web_research_runs"))
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


def _share_edit(
    client: TestClient,
    ws: Workspace,
    idea_id: str,
    editor_id: str,
) -> None:
    r = client.patch(
        f"/api/v1/workspaces/{ws.id}/ideas/{idea_id}",
        json={"visibility": "SELECTED_USERS"},
        headers=_headers(client),
    )
    assert r.status_code == 200, r.text
    r = client.put(
        f"/api/v1/workspaces/{ws.id}/ideas/{idea_id}/shares",
        json={"shares": [{"user_id": editor_id, "permission": "EDIT"}]},
        headers=_headers(client),
    )
    assert r.status_code == 200, r.text


def _revoke_shares(
    client: TestClient,
    ws: Workspace,
    idea_id: str,
) -> None:
    r = client.patch(
        f"/api/v1/workspaces/{ws.id}/ideas/{idea_id}",
        json={"visibility": "PRIVATE"},
        headers=_headers(client),
    )
    assert r.status_code == 200, r.text


def _make_research_job_available(db: Session, run_id: uuid.UUID) -> AiJob:
    job = db.scalars(
        select(AiJob).where(
            AiJob.research_run_id == run_id,
            AiJob.job_type == AiJobType.WEB_RESEARCH.value,
        )
    ).one()
    from datetime import datetime, timedelta, timezone

    if job.available_at > datetime.now(timezone.utc):
        job.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    return job


def _preview_approve_research(
    client: TestClient,
    ws: Workspace,
    session_id: str,
    *,
    queries: list[str],
    draft: dict[str, Any],
    user_edited_fields: list[str] | None = None,
) -> uuid.UUID:
    preview = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/research-runs/preview",
        json={
            "queries": queries,
            "current_draft": draft,
            "user_edited_fields": user_edited_fields or [],
        },
        headers=_headers(client),
    )
    assert preview.status_code == 201, preview.text
    run_id = uuid.UUID(preview.json()["id"])
    approve = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/research-runs/{run_id}/approve",
        headers=_headers(client),
    )
    assert approve.status_code == 200, approve.text
    return run_id


def test_apply_refinement_rejects_confirmed_create_session(
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
    confirm = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/confirm",
        json={
            "title": "Confirmed Create",
            "priority": "MEDIUM",
            "feasibility": "UNKNOWN",
            "visibility": "PRIVATE",
            "tags": [],
        },
        headers=_headers(client),
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["created"] is True

    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/apply-refinement",
        json=_apply_body(title="Confirmed Create"),
        headers=_headers(client),
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "AI_SESSION_INVALID_STATE"


def test_edit_share_user_can_start_and_apply_refine(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw_owner = _user(db)
    editor, pw_editor = _user(db)
    ws = _team(db, owner)
    _add_member(db, ws, editor, role=WorkspaceRole.MEMBER.value)

    _login(client, owner.email, pw_owner)
    idea = _create_idea(client, ws, visibility="PRIVATE")
    _share_edit(client, ws, idea["id"], str(editor.id))

    _login(client, editor.email, pw_editor)
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
    assert r.json()["updated"] is True
    assert r.json()["idea"]["id"] == idea["id"]


def test_apply_denied_when_edit_revoked_before_apply(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw_owner = _user(db)
    editor, pw_editor = _user(db)
    ws = _team(db, owner)
    _add_member(db, ws, editor, role=WorkspaceRole.MEMBER.value)

    _login(client, owner.email, pw_owner)
    idea = _create_idea(client, ws, visibility="PRIVATE")
    _share_edit(client, ws, idea["id"], str(editor.id))

    _login(client, editor.email, pw_editor)
    session_id = _start_refine(client, ws, idea["id"])["id"]
    ai_worker.run_once(
        session_factory=session_factory,
        provider=FakeRefineProvider([_ready_patch()]),
    )

    _login(client, owner.email, pw_owner)
    _revoke_shares(client, ws, idea["id"])

    _login(client, editor.email, pw_editor)
    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/apply-refinement",
        json=_apply_body(),
        headers=_headers(client),
    )
    assert r.status_code in {403, 404}
    db.expire_all()
    idea_row = db.get(Idea, uuid.UUID(idea["id"]))
    assert idea_row.core_concept == "초기 핵심 개념"


def test_idempotent_apply_denied_after_edit_revoked(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw_owner = _user(db)
    editor, pw_editor = _user(db)
    ws = _team(db, owner)
    _add_member(db, ws, editor, role=WorkspaceRole.MEMBER.value)

    _login(client, owner.email, pw_owner)
    idea = _create_idea(client, ws, visibility="PRIVATE")
    _share_edit(client, ws, idea["id"], str(editor.id))

    _login(client, editor.email, pw_editor)
    session_id = _start_refine(client, ws, idea["id"])["id"]
    ai_worker.run_once(
        session_factory=session_factory,
        provider=FakeRefineProvider([_ready_patch()]),
    )
    first = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/apply-refinement",
        json=_apply_body(),
        headers=_headers(client),
    )
    assert first.status_code == 200
    assert first.json()["updated"] is True

    _login(client, owner.email, pw_owner)
    _revoke_shares(client, ws, idea["id"])

    _login(client, editor.email, pw_editor)
    again = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/apply-refinement",
        json=_apply_body(),
        headers=_headers(client),
    )
    assert again.status_code in {403, 404}
    assert again.json().get("error") is not None


def test_tags_only_patch_bumps_idea_updated_at(client: TestClient, db: Session) -> None:
    import time

    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    idea = _create_idea(client, ws, tags=["A"])
    before = client.get(
        f"/api/v1/workspaces/{ws.id}/ideas/{idea['id']}",
        headers=_headers(client),
    ).json()["updated_at"]
    time.sleep(0.05)
    patched = client.patch(
        f"/api/v1/workspaces/{ws.id}/ideas/{idea['id']}",
        json={"tags": ["B"]},
        headers=_headers(client),
    )
    assert patched.status_code == 200, patched.text
    after = patched.json()["updated_at"]
    assert after > before
    assert [t["name"] for t in patched.json()["tags"]] == ["B"]


def test_tags_only_change_blocks_refine_apply_and_regenerate(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    import time

    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    idea = _create_idea(client, ws, tags=["A"])
    session_id = _start_refine(client, ws, idea["id"])["id"]
    ai_worker.run_once(
        session_factory=session_factory,
        provider=FakeRefineProvider([_ready_patch()]),
    )

    time.sleep(0.05)
    patched = client.patch(
        f"/api/v1/workspaces/{ws.id}/ideas/{idea['id']}",
        json={"tags": ["B"]},
        headers=_headers(client),
    )
    assert patched.status_code == 200
    assert [t["name"] for t in patched.json()["tags"]] == ["B"]

    apply = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/apply-refinement",
        json=_apply_body(tags=["A"]),
        headers=_headers(client),
    )
    assert apply.status_code == 409
    assert apply.json()["error"]["code"] == "AI_REFINE_SOURCE_CHANGED"
    detail = client.get(
        f"/api/v1/workspaces/{ws.id}/ideas/{idea['id']}",
        headers=_headers(client),
    ).json()
    assert sorted(t["name"] for t in detail["tags"]) == ["B"]

    regen = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/regenerate",
        headers=_headers(client),
    )
    assert regen.status_code == 409
    assert regen.json()["error"]["code"] == "AI_REFINE_SOURCE_CHANGED"


def test_refine_temp_save_preserves_user_edit_without_touching_idea(
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

    save = client.put(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/review-draft",
        json={
            "draft": {
                "title": "원본 아이디어",
                "one_line_definition": "한 줄 정의",
                "problem": "해결할 문제",
                "core_concept": "사용자가 직접 고친 개념",
                "major_features": "기능 A / 기능 B",
                "priority": "MEDIUM",
                "feasibility": "UNKNOWN",
                "tags": ["AI"],
            },
            "review_state": {
                "edited_fields": ["core_concept"],
            },
        },
        headers=_headers(client),
    )
    assert save.status_code == 200, save.text

    reloaded = client.get(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}",
        headers=_headers(client),
    )
    assert reloaded.status_code == 200
    body = reloaded.json()
    assert body["draft"]["core_concept"] == "사용자가 직접 고친 개념"
    assert body["field_provenance"]["core_concept"]["final_source"] == "USER_EDIT"

    detail = client.get(
        f"/api/v1/workspaces/{ws.id}/ideas/{idea['id']}",
        headers=_headers(client),
    ).json()
    assert detail["core_concept"] == "초기 핵심 개념"


def test_invalid_category_only_patch_does_not_become_ready(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    idea = _create_idea(client, ws)
    session_id = uuid.UUID(_start_refine(client, ws, idea["id"])["id"])

    provider = FakeRefineProvider(
        [
            _ready_patch({"category_slug": "totally_invalid_slug_xyz"}),
            _ready_patch({"category_slug": "totally_invalid_slug_xyz"}),
            _ready_patch({"category_slug": "totally_invalid_slug_xyz"}),
        ]
    )
    from datetime import datetime, timedelta, timezone

    for _ in range(5):
        job = db.scalars(select(AiJob).where(AiJob.session_id == session_id)).first()
        if job is None:
            break
        if job.status == AiJobStatus.QUEUED.value and job.available_at > datetime.now(timezone.utc):
            job.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
        if not ai_worker.run_once(session_factory=session_factory, provider=provider):
            break

    db.expire_all()
    session = db.get(IdeaAiSession, session_id)
    assert session.status in {
        IdeaAiSessionStatus.PROCESSING.value,
        IdeaAiSessionStatus.FAILED.value,
    }
    assert session.status != IdeaAiSessionStatus.READY_FOR_REVIEW.value
    assert session.draft_payload is None or session.draft_payload.get("category_slug") != (
        "totally_invalid_slug_xyz"
    )


def test_create_and_refine_evidence_aggregated_on_idea(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    from app.llm.research_schemas import EvidenceRefinementResult
    from tests.test_ai_session_integration import FakeProvider, _ready_result

    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)

    # CREATE + web research evidence A
    created = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions",
        json={"input_text": "회의록 AI 도우미"},
        headers=_headers(client),
    )
    create_session_id = created.json()["id"]
    ai_worker.run_once(
        session_factory=session_factory,
        provider=FakeProvider([_ready_result("Create Draft")]),
    )

    FakeSearchProvider.calls = 0
    create_run = _preview_approve_research(
        client,
        ws,
        create_session_id,
        queries=["meeting notes ai"],
        draft={"title": "Create Draft", "background": "A"},
    )

    class CreateEvidenceRefine(FakeProvider):
        def refine_idea_with_evidence(self, request):
            ev_id = str(request.evidence[0].evidence_id)
            return EvidenceRefinementResult(
                draft={"title": "Create Draft", "background": "CREATE evidence A"},
                evidence_links={"background": [ev_id]},
                research_summary="create evidence",
            )

    search_a = FakeSearchProvider(url="https://example.com/create-evidence-a")
    _make_research_job_available(db, create_run)
    assert ai_worker.run_once(
        session_factory=session_factory,
        provider=CreateEvidenceRefine(),
        search_provider=search_a,
    )

    confirm = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{create_session_id}/confirm",
        json={
            "title": "Create Draft",
            "background": "CREATE evidence A",
            "priority": "MEDIUM",
            "feasibility": "UNKNOWN",
            "visibility": "WORKSPACE",
            "tags": ["AI"],
        },
        headers=_headers(client),
    )
    assert confirm.status_code == 200, confirm.text
    idea_id = confirm.json()["idea"]["id"]

    evidence1 = client.get(
        f"/api/v1/workspaces/{ws.id}/ideas/{idea_id}/evidence",
        headers=_headers(client),
    )
    assert evidence1.status_code == 200
    urls1 = {item["url"] for item in evidence1.json()["items"]}
    assert "https://example.com/create-evidence-a" in urls1

    # REFINE + web research evidence B + apply
    refine_session_id = _start_refine(client, ws, idea_id)["id"]
    ai_worker.run_once(
        session_factory=session_factory,
        provider=FakeRefineProvider([_ready_patch()]),
    )
    get_session = client.get(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{refine_session_id}",
        headers=_headers(client),
    ).json()
    draft = get_session["draft"]

    # Protect a USER_EDIT field during research
    save = client.put(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{refine_session_id}/review-draft",
        json={
            "draft": {**draft, "problem": "사용자가 지킨 문제 서술"},
            "review_state": {"edited_fields": ["problem"]},
        },
        headers=_headers(client),
    )
    assert save.status_code == 200, save.text

    refine_run = _preview_approve_research(
        client,
        ws,
        refine_session_id,
        queries=["technical meeting pipeline"],
        draft={**draft, "problem": "사용자가 지킨 문제 서술"},
        user_edited_fields=["problem"],
    )

    class RefineEvidenceLlm(FakeRefineProvider):
        def __init__(self) -> None:
            super().__init__(results=[], evidence_results=[])

        def refine_idea_with_evidence(self, request):
            assert "problem" not in (request.user_edited_fields or []) or True
            # USER_EDIT fields must be listed so research refine skips them.
            assert "problem" in request.user_edited_fields
            ev_id = str(request.evidence[0].evidence_id)
            return EvidenceRefinementResult(
                draft={
                    "title": draft["title"],
                    "core_concept": "REFINE evidence B concept",
                    "problem": "should be ignored",
                },
                evidence_links={"core_concept": [ev_id]},
                research_summary="refine evidence",
            )

    search_b = FakeSearchProvider(url="https://example.com/refine-evidence-b")
    _make_research_job_available(db, refine_run)
    assert ai_worker.run_once(
        session_factory=session_factory,
        provider=RefineEvidenceLlm(),
        search_provider=search_b,
    )

    after_research = client.get(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{refine_session_id}",
        headers=_headers(client),
    ).json()
    assert after_research["draft"]["problem"] == "사용자가 지킨 문제 서술"
    assert after_research["draft"]["core_concept"] == "REFINE evidence B concept"

    apply = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{refine_session_id}/apply-refinement",
        json=_apply_body(
            title=after_research["draft"]["title"],
            core_concept=after_research["draft"]["core_concept"],
            major_features=after_research["draft"].get("major_features") or "기능 A / 기능 B",
            problem="사용자가 지킨 문제 서술",
            one_line_definition=after_research["draft"].get("one_line_definition") or "한 줄 정의",
            tags=after_research["draft"].get("tags") or ["AI"],
            priority=after_research["draft"].get("priority") or "MEDIUM",
            feasibility=after_research["draft"].get("feasibility") or "UNKNOWN",
        ),
        headers=_headers(client),
    )
    assert apply.status_code == 200, apply.text
    assert apply.json()["idea"]["id"] == idea_id

    evidence2 = client.get(
        f"/api/v1/workspaces/{ws.id}/ideas/{idea_id}/evidence",
        headers=_headers(client),
    )
    assert evidence2.status_code == 200
    urls2 = {item["url"] for item in evidence2.json()["items"]}
    assert "https://example.com/create-evidence-a" in urls2
    assert "https://example.com/refine-evidence-b" in urls2
    assert len(evidence2.json()["items"]) >= 2

    # Second REFINE apply still aggregates without MultipleResultsFound
    refine2 = _start_refine(client, ws, idea_id, direction="RISK_ANALYSIS")["id"]
    ai_worker.run_once(
        session_factory=session_factory,
        provider=FakeRefineProvider([_ready_patch({"challenges": "새 리스크"})]),
    )
    apply2 = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{refine2}/apply-refinement",
        json=_apply_body(
            core_concept="REFINE evidence B concept",
            major_features="기능 A / 기능 B",
            challenges="새 리스크",
            problem="사용자가 지킨 문제 서술",
        ),
        headers=_headers(client),
    )
    assert apply2.status_code == 200, apply2.text
    evidence3 = client.get(
        f"/api/v1/workspaces/{ws.id}/ideas/{idea_id}/evidence",
        headers=_headers(client),
    )
    assert evidence3.status_code == 200
    assert len(evidence3.json()["items"]) >= 2


def test_manual_idea_refine_evidence_visible(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    from app.llm.research_schemas import EvidenceRefinementResult

    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    idea = _create_idea(client, ws)
    session_id = _start_refine(client, ws, idea["id"])["id"]
    ai_worker.run_once(
        session_factory=session_factory,
        provider=FakeRefineProvider([_ready_patch()]),
    )
    draft = client.get(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}",
        headers=_headers(client),
    ).json()["draft"]

    run_id = _preview_approve_research(
        client,
        ws,
        session_id,
        queries=["manual idea research"],
        draft=draft,
    )

    class Ev(FakeRefineProvider):
        def refine_idea_with_evidence(self, request):
            ev_id = str(request.evidence[0].evidence_id)
            return EvidenceRefinementResult(
                draft={**draft, "expected_effect": "근거 기반 기대효과"},
                evidence_links={"expected_effect": [ev_id]},
                research_summary="manual",
            )

    _make_research_job_available(db, run_id)
    assert ai_worker.run_once(
        session_factory=session_factory,
        provider=Ev(),
        search_provider=FakeSearchProvider(url="https://example.com/manual-refine"),
    )
    after = client.get(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}",
        headers=_headers(client),
    ).json()
    apply = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/apply-refinement",
        json=_apply_body(
            expected_effect="근거 기반 기대효과",
            core_concept=after["draft"]["core_concept"],
            major_features=after["draft"].get("major_features") or "기능 A / 기능 B",
        ),
        headers=_headers(client),
    )
    assert apply.status_code == 200, apply.text
    evidence = client.get(
        f"/api/v1/workspaces/{ws.id}/ideas/{idea['id']}/evidence",
        headers=_headers(client),
    )
    assert evidence.status_code == 200
    assert any(
        item["url"] == "https://example.com/manual-refine" for item in evidence.json()["items"]
    )
