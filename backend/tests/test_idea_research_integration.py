"""PostgreSQL Step 18 registered Idea RESEARCH (re-research) integration tests."""

from __future__ import annotations

import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import reset_engine
from app.llm.research_schemas import EvidenceRefinementResult
from app.main import app
from app.models.ai import AiJob, IdeaAiSession
from app.models.embedding import IdeaEmbedding, IdeaEmbeddingJob
from app.models.enums import (
    AiJobStatus,
    AiJobType,
    IdeaAiSessionPurpose,
    IdeaAiSessionStatus,
    SystemRole,
    UserStatus,
    WebResearchRunStatus,
    WorkspaceMemberStatus,
    WorkspaceRole,
    WorkspaceType,
)
from app.models.idea import Idea
from app.models.research import WebEvidence, WebResearchRun
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.services import ai_worker
from app.services.workspace import seed_workspace_defaults
from app.web_search.base import WebSearchResult

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — skipping idea research integration tests",
)


class FakeSearchProvider:
    provider_name = "fake_search"
    calls = 0
    results: list[WebSearchResult] | None = None
    fail: Exception | None = None

    def __init__(
        self,
        *,
        url: str = "https://example.com/research-a",
        results: list[WebSearchResult] | None = None,
        fail: Exception | None = None,
        second_url: str | None = None,
    ) -> None:
        self._url = url
        self._second_url = second_url or f"{url.rstrip('/')}-2"
        self._results = results
        self._fail = fail

    def search(self, *, query: str, max_results: int) -> list[WebSearchResult]:
        type(self).calls += 1
        if self._fail is not None:
            raise self._fail
        if self._results is not None:
            return list(self._results)[:max_results]
        return [
            WebSearchResult(
                title="Research Evidence",
                url=self._url,
                snippet="Helpful research snippet",
                source="Example",
            ),
            WebSearchResult(
                title="Research Evidence 2",
                url=self._second_url,
                snippet="Second snippet",
                source="Example",
            ),
        ]

    def close(self) -> None:
        pass


class FakeLlmProvider:
    provider_name = "fake_llm"
    model_name = "fake-model"

    def __init__(self, evidence_results: list[Any] | None = None) -> None:
        self._evidence_results = list(evidence_results or [])
        self.calls = 0

    def structure_idea(self, request):
        raise AssertionError("RESEARCH must not call structure_idea")

    def refine_idea(self, request):
        raise AssertionError("RESEARCH must not call refine_idea")

    def refine_idea_with_evidence(self, request):
        self.calls += 1
        if not self._evidence_results:
            raise RuntimeError("FakeLlmProvider exhausted")
        item = self._evidence_results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def close(self) -> None:
        pass


@pytest.fixture(autouse=True)
def _clean_tables(engine):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM web_evidence"))
        conn.execute(text("DELETE FROM web_research_runs"))
        conn.execute(text("DELETE FROM ai_jobs"))
        conn.execute(text("DELETE FROM idea_ai_sessions"))
        conn.execute(text("DELETE FROM idea_embedding_jobs"))
        conn.execute(text("DELETE FROM idea_embeddings"))
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
    email = f"research-{uuid.uuid4().hex[:10]}@example.com"
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


def _team(
    db: Session,
    owner: User,
    *,
    allow_llm: bool = True,
    allow_web_search: bool = True,
) -> Workspace:
    ws = Workspace(
        name=f"Research Team {uuid.uuid4().hex[:6]}",
        type=WorkspaceType.TEAM.value,
        owner_id=owner.id,
        allow_llm=allow_llm,
        allow_web_search=allow_web_search,
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
        "title": "등록된 조사 아이디어",
        "one_line_definition": "한 줄 정의",
        "background": "OLD_BACKGROUND",
        "problem": "해결할 문제",
        "core_concept": "초기 핵심 개념",
        "expected_effect": "OLD_EFFECT",
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


def _start_research(client: TestClient, ws: Workspace, idea_id: str) -> dict[str, Any]:
    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ideas/{idea_id}/research-sessions",
        headers=_headers(client),
    )
    assert r.status_code == 201, r.text
    return r.json()


def _share(
    client: TestClient,
    ws: Workspace,
    idea_id: str,
    user_id: str,
    *,
    permission: str,
) -> None:
    r = client.patch(
        f"/api/v1/workspaces/{ws.id}/ideas/{idea_id}",
        json={"visibility": "SELECTED_USERS"},
        headers=_headers(client),
    )
    assert r.status_code == 200, r.text
    r = client.put(
        f"/api/v1/workspaces/{ws.id}/ideas/{idea_id}/shares",
        json={"shares": [{"user_id": user_id, "permission": permission}]},
        headers=_headers(client),
    )
    assert r.status_code == 200, r.text


def _make_research_job_available(db: Session, run_id: uuid.UUID) -> AiJob:
    job = (
        db.scalars(
            select(AiJob)
            .where(
                AiJob.research_run_id == run_id,
                AiJob.job_type == AiJobType.WEB_RESEARCH.value,
            )
            .order_by(AiJob.created_at.desc())
        ).first()
    )
    assert job is not None
    if job.available_at > datetime.now(timezone.utc):
        job.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    return job


def _preview(
    client: TestClient,
    ws: Workspace,
    session_id: str,
    *,
    queries: list[str],
    draft: dict[str, Any] | None = None,
) -> dict[str, Any]:
    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/research-runs/preview",
        json={
            "queries": queries,
            "current_draft": draft or {},
            "user_edited_fields": [],
        },
        headers=_headers(client),
    )
    assert r.status_code == 201, r.text
    return r.json()


def _approve(client: TestClient, ws: Workspace, session_id: str, run_id: str) -> dict[str, Any]:
    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/research-runs/{run_id}/approve",
        headers=_headers(client),
    )
    return r.json() if r.status_code < 500 else {"_status": r.status_code, "_text": r.text}


def test_owner_and_edit_can_create_research_session_read_forbidden(
    client: TestClient,
    db: Session,
) -> None:
    owner, pw = _user(db)
    editor, editor_pw = _user(db)
    reader, reader_pw = _user(db)
    stranger, stranger_pw = _user(db)
    ws = _team(db, owner)
    _add_member(db, ws, editor, role=WorkspaceRole.MEMBER.value)
    _add_member(db, ws, reader, role=WorkspaceRole.MEMBER.value)
    _add_member(db, ws, stranger, role=WorkspaceRole.MEMBER.value)

    _login(client, owner.email, pw)
    idea = _create_idea(client, ws, visibility="PRIVATE")
    _share(client, ws, idea["id"], str(editor.id), permission="EDIT")
    # Add READ share alongside EDIT
    r = client.put(
        f"/api/v1/workspaces/{ws.id}/ideas/{idea['id']}/shares",
        json={
            "shares": [
                {"user_id": str(editor.id), "permission": "EDIT"},
                {"user_id": str(reader.id), "permission": "READ"},
            ]
        },
        headers=_headers(client),
    )
    assert r.status_code == 200, r.text

    body = _start_research(client, ws, idea["id"])
    assert body["purpose"] == "RESEARCH"
    assert body["status"] == "READY_FOR_REVIEW"
    assert body["source_idea_id"] == idea["id"]
    assert body["result_idea_id"] == idea["id"]
    assert body["source_idea_snapshot"]["title"] == "등록된 조사 아이디어"
    assert body["draft"]["background"] == "OLD_BACKGROUND"
    assert body["research_recommended"] is False
    assert body["refine_direction"] is None
    assert body["ready_at"] is not None

    session = db.get(IdeaAiSession, uuid.UUID(body["id"]))
    assert session is not None
    jobs = list(db.scalars(select(AiJob).where(AiJob.session_id == session.id)))
    assert jobs == []

    _login(client, editor.email, editor_pw)
    edit_body = _start_research(client, ws, idea["id"])
    assert edit_body["purpose"] == "RESEARCH"

    _login(client, reader.email, reader_pw)
    forbidden = client.post(
        f"/api/v1/workspaces/{ws.id}/ideas/{idea['id']}/research-sessions",
        headers=_headers(client),
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "IDEA_EDIT_FORBIDDEN"

    _login(client, stranger.email, stranger_pw)
    missing = client.post(
        f"/api/v1/workspaces/{ws.id}/ideas/{idea['id']}/research-sessions",
        headers=_headers(client),
    )
    assert missing.status_code in {403, 404}


def test_research_query_defaults_priority(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    idea = _create_idea(client, ws, title="Fallback Title")

    # C) no prior → [title]
    body = _start_research(client, ws, idea["id"])
    assert body["research_topics"] == ["Fallback Title"]

    # Seed a READY run with queries via RESEARCH flow
    session_id = body["id"]
    preview = _preview(
        client,
        ws,
        session_id,
        queries=["q1 prior", "q2 prior"],
        draft=body["draft"],
    )
    approve = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/research-runs/{preview['id']}/approve",
        headers=_headers(client),
    )
    assert approve.status_code == 200, approve.text
    run_id = uuid.UUID(preview["id"])
    _make_research_job_available(db, run_id)
    FakeSearchProvider.calls = 0

    class PriorLlm(FakeLlmProvider):
        def refine_idea_with_evidence(self, request):
            self.calls += 1
            ev_id = str(request.evidence[0].evidence_id)
            return EvidenceRefinementResult(
                draft={"background": "SHOULD_NOT_APPLY"},
                evidence_links={"background": [ev_id]},
                research_summary="summary",
            )

    assert ai_worker.run_once(
        session_factory=session_factory,
        provider=PriorLlm(),
        search_provider=FakeSearchProvider(url="https://example.com/prior"),
    )
    db.expire_all()
    assert (
        db.scalars(
            select(WebResearchRun).where(
                WebResearchRun.status == WebResearchRunStatus.READY.value
            )
        ).first()
        is not None
    )

    # A) previous READY run queries reused
    again = _start_research(client, ws, idea["id"])
    assert again["research_topics"] == ["q1 prior", "q2 prior"]


def test_explicit_approval_no_external_call_until_approve(
    client: TestClient,
    db: Session,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    idea = _create_idea(client, ws)
    FakeSearchProvider.calls = 0

    body = _start_research(client, ws, idea["id"])
    session_id = uuid.UUID(body["id"])
    assert FakeSearchProvider.calls == 0
    assert (
        db.scalar(
            select(func.count())
            .select_from(AiJob)
            .where(
                AiJob.session_id == session_id,
                AiJob.job_type == AiJobType.WEB_RESEARCH.value,
            )
        )
        == 0
    )

    preview = _preview(client, ws, body["id"], queries=["승인 전 검색어"], draft=body["draft"])
    assert FakeSearchProvider.calls == 0
    assert (
        db.scalar(
            select(func.count())
            .select_from(AiJob)
            .where(AiJob.research_run_id == uuid.UUID(preview["id"]))
        )
        == 0
    )

    approve = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{body['id']}/research-runs/{preview['id']}/approve",
        headers=_headers(client),
    )
    assert approve.status_code == 200, approve.text
    jobs = list(
        db.scalars(
            select(AiJob).where(
                AiJob.research_run_id == uuid.UUID(preview["id"]),
                AiJob.job_type == AiJobType.WEB_RESEARCH.value,
            )
        )
    )
    assert len(jobs) == 1
    assert jobs[0].status == AiJobStatus.QUEUED.value
    assert FakeSearchProvider.calls == 0  # worker not run yet


def test_research_worker_preserves_idea_and_embeddings(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    idea = _create_idea(client, ws)
    idea_id = uuid.UUID(idea["id"])

    # Snapshot embedding desired state: no job / no row.
    emb_before = db.get(IdeaEmbedding, idea_id)
    job_before = db.get(IdeaEmbeddingJob, idea_id)
    idea_row = db.get(Idea, idea_id)
    assert idea_row is not None
    updated_before = idea_row.updated_at
    bg_before = idea_row.background
    effect_before = idea_row.expected_effect

    body = _start_research(client, ws, idea["id"])
    preview = _preview(client, ws, body["id"], queries=["immutability"], draft=body["draft"])
    approve = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{body['id']}/research-runs/{preview['id']}/approve",
        headers=_headers(client),
    )
    assert approve.status_code == 200
    run_id = uuid.UUID(preview["id"])
    _make_research_job_available(db, run_id)

    FakeSearchProvider.calls = 0
    search = FakeSearchProvider(url="https://example.com/immutability-a")

    class LinkingLlm(FakeLlmProvider):
        def refine_idea_with_evidence(self, request):
            self.calls += 1
            ev0 = str(request.evidence[0].evidence_id)
            ev1 = str(request.evidence[1].evidence_id) if len(request.evidence) > 1 else ev0
            return EvidenceRefinementResult(
                draft={
                    "background": "LLM_RESEARCH_CHANGED",
                    "expected_effect": "CHANGED",
                },
                evidence_links={
                    "background": [ev0],
                    "expected_effect": [ev1],
                },
                research_summary="조사 요약",
            )

    llm = LinkingLlm()
    assert ai_worker.run_once(
        session_factory=session_factory,
        provider=llm,
        search_provider=search,
    )
    assert FakeSearchProvider.calls >= 1
    assert llm.calls >= 1

    db.expire_all()
    idea_after = db.get(Idea, idea_id)
    assert idea_after is not None
    assert idea_after.background == bg_before == "OLD_BACKGROUND"
    assert idea_after.expected_effect == effect_before == "OLD_EFFECT"
    assert idea_after.updated_at == updated_before
    assert db.get(IdeaEmbedding, idea_id) == emb_before
    assert db.get(IdeaEmbeddingJob, idea_id) == job_before

    session = db.get(IdeaAiSession, uuid.UUID(body["id"]))
    assert session is not None
    assert session.status == IdeaAiSessionStatus.CONFIRMED.value
    assert session.result_idea_id == idea_id
    assert session.draft_payload["background"] == "OLD_BACKGROUND"

    run = db.get(WebResearchRun, run_id)
    assert run is not None
    assert run.status == WebResearchRunStatus.READY.value
    assert run.research_summary == "조사 요약"
    assert run.result_count == 2

    evidence = list(db.scalars(select(WebEvidence).where(WebEvidence.research_run_id == run_id)))
    assert len(evidence) == 2
    assert any(ev.related_fields for ev in evidence)

    items = client.get(
        f"/api/v1/workspaces/{ws.id}/ideas/{idea['id']}/evidence",
        headers=_headers(client),
    )
    assert items.status_code == 200
    assert len(items.json()["items"]) == 2


def test_zero_results_confirms_without_changing_idea(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    idea = _create_idea(client, ws)
    idea_id = uuid.UUID(idea["id"])
    idea_row = db.get(Idea, idea_id)
    assert idea_row is not None
    updated_before = idea_row.updated_at
    evidence_before = db.scalar(select(func.count()).select_from(WebEvidence)) or 0

    body = _start_research(client, ws, idea["id"])
    preview = _preview(client, ws, body["id"], queries=["empty"], draft=body["draft"])
    assert (
        client.post(
            f"/api/v1/workspaces/{ws.id}/ai-sessions/{body['id']}/research-runs/{preview['id']}/approve",
            headers=_headers(client),
        ).status_code
        == 200
    )
    run_id = uuid.UUID(preview["id"])
    _make_research_job_available(db, run_id)

    class EmptySearch(FakeSearchProvider):
        def search(self, *, query: str, max_results: int):
            FakeSearchProvider.calls += 1
            return []

    assert ai_worker.run_once(
        session_factory=session_factory,
        provider=FakeLlmProvider([]),
        search_provider=EmptySearch(),
    )

    db.expire_all()
    run = db.get(WebResearchRun, run_id)
    session = db.get(IdeaAiSession, uuid.UUID(body["id"]))
    assert run is not None and run.status == WebResearchRunStatus.READY.value
    assert run.result_count == 0
    assert session is not None and session.status == IdeaAiSessionStatus.CONFIRMED.value
    idea_after = db.get(Idea, idea_id)
    assert idea_after is not None
    assert idea_after.updated_at == updated_before
    evidence_after = db.scalar(select(func.count()).select_from(WebEvidence)) or 0
    assert evidence_after == evidence_before
    job = db.scalars(select(AiJob).where(AiJob.research_run_id == run_id)).one()
    assert job.status == AiJobStatus.SUCCEEDED.value


def test_failure_keeps_session_ready_and_retry_succeeds(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    from app.web_search.exceptions import WebSearchTimeoutError

    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    idea = _create_idea(client, ws)
    body = _start_research(client, ws, idea["id"])
    preview = _preview(client, ws, body["id"], queries=["fail-then-retry"], draft=body["draft"])
    assert (
        client.post(
            f"/api/v1/workspaces/{ws.id}/ai-sessions/{body['id']}/research-runs/{preview['id']}/approve",
            headers=_headers(client),
        ).status_code
        == 200
    )
    run_id = uuid.UUID(preview["id"])
    _make_research_job_available(db, run_id)

    class FailingSearch(FakeSearchProvider):
        def search(self, *, query: str, max_results: int):
            FakeSearchProvider.calls += 1
            raise WebSearchTimeoutError("timeout")

    # Exhaust retries so the run ends FAILED (timeout is retryable).
    for _ in range(5):
        _make_research_job_available(db, run_id)
        ai_worker.run_once(
            session_factory=session_factory,
            provider=FakeLlmProvider([]),
            search_provider=FailingSearch(),
        )
        db.expire_all()
        run = db.get(WebResearchRun, run_id)
        if run is not None and run.status == WebResearchRunStatus.FAILED.value:
            break

    db.expire_all()
    run = db.get(WebResearchRun, run_id)
    session = db.get(IdeaAiSession, uuid.UUID(body["id"]))
    assert run is not None and run.status == WebResearchRunStatus.FAILED.value
    assert session is not None and session.status == IdeaAiSessionStatus.READY_FOR_REVIEW.value

    retry = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{body['id']}/research-runs/{preview['id']}/retry",
        headers=_headers(client),
    )
    assert retry.status_code == 200, retry.text
    _make_research_job_available(db, run_id)

    class RetryLlm(FakeLlmProvider):
        def refine_idea_with_evidence(self, request):
            self.calls += 1
            ev_id = str(request.evidence[0].evidence_id)
            return EvidenceRefinementResult(
                draft={"background": "ignored"},
                evidence_links={"background": [ev_id]},
                research_summary="ok",
            )

    assert ai_worker.run_once(
        session_factory=session_factory,
        provider=RetryLlm(),
        search_provider=FakeSearchProvider(url="https://example.com/retry-ok"),
    )
    db.expire_all()
    run = db.get(WebResearchRun, run_id)
    session = db.get(IdeaAiSession, uuid.UUID(body["id"]))
    assert run is not None and run.status == WebResearchRunStatus.READY.value
    assert session is not None and session.status == IdeaAiSessionStatus.CONFIRMED.value


def test_active_research_concurrency_blocks_second_approve(
    client: TestClient,
    db: Session,
) -> None:
    owner, pw = _user(db)
    other, other_pw = _user(db)
    ws = _team(db, owner)
    _add_member(db, ws, other, role=WorkspaceRole.MEMBER.value)
    _login(client, owner.email, pw)
    idea = _create_idea(client, ws, visibility="WORKSPACE")

    s1 = _start_research(client, ws, idea["id"])
    p1 = _preview(client, ws, s1["id"], queries=["first"], draft=s1["draft"])
    a1 = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{s1['id']}/research-runs/{p1['id']}/approve",
        headers=_headers(client),
    )
    assert a1.status_code == 200, a1.text

    _login(client, other.email, other_pw)
    # other needs EDIT — share EDIT
    _login(client, owner.email, pw)
    _share(client, ws, idea["id"], str(other.id), permission="EDIT")
    _login(client, other.email, other_pw)
    s2 = _start_research(client, ws, idea["id"])
    p2 = _preview(client, ws, s2["id"], queries=["second"], draft=s2["draft"])
    a2 = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{s2['id']}/research-runs/{p2['id']}/approve",
        headers=_headers(client),
    )
    assert a2.status_code == 409, a2.text
    assert a2.json()["error"]["code"] == "IDEA_RESEARCH_ALREADY_ACTIVE"


def test_concurrent_approve_race_only_one_queued(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    idea = _create_idea(client, ws)

    s1 = _start_research(client, ws, idea["id"])
    p1 = _preview(client, ws, s1["id"], queries=["race-a"], draft=s1["draft"])
    s2 = _start_research(client, ws, idea["id"])
    # first session abandoned/cancelled by second create — recreate both previews carefully
    # After second create, s1 should be CANCELLED. Start two fresh sessions via direct DB.
    from app.services import ai_session as ai_session_service
    from app.services import web_research as web_research_service
    from app.schemas.research import WebResearchPreviewRequest

    with session_factory() as sess:
        idea_row = sess.get(Idea, uuid.UUID(idea["id"]))
        assert idea_row is not None
        # Cancel any leftover
        for old in sess.scalars(
            select(IdeaAiSession).where(
                IdeaAiSession.source_idea_id == idea_row.id,
                IdeaAiSession.purpose == IdeaAiSessionPurpose.RESEARCH.value,
            )
        ):
            old.status = IdeaAiSessionStatus.CANCELLED.value
        sess.commit()

    results: list[int] = []

    def _prepare_session() -> tuple[str, str]:
        with session_factory() as sess:
            ws_row = sess.get(Workspace, ws.id)
            user_row = sess.get(User, owner.id)
            assert ws_row and user_row
            created = ai_session_service.create_research_ai_session(
                sess, workspace=ws_row, requester=user_row, idea_id=uuid.UUID(idea["id"])
            )
            # Do not cancel siblings for this race — manually avoid cleanup conflict
            run = web_research_service.preview_research_run(
                sess,
                workspace=ws_row,
                user=user_row,
                session_id=created.id,
                payload=WebResearchPreviewRequest(
                    queries=["race"],
                    current_draft=dict(created.draft_payload or {}),
                    user_edited_fields=[],
                ),
            )
            sess.commit()
            return str(created.id), str(run.id)

    # Bypass abandoned cleanup by creating two sessions with separate requesters... 
    # Simpler: create two AWAITING runs under two sessions without cleanup canceling:
    # Temporarily create session2 without calling create_research which cancels.
    sid_a, rid_a = _prepare_session()
    # Second prepare will cancel first if READY without executing — so create second
    # without going through create_research cleanup by cloning via ORM.
    with session_factory() as sess:
        first = sess.get(IdeaAiSession, uuid.UUID(sid_a))
        assert first is not None
        first.status = IdeaAiSessionStatus.READY_FOR_REVIEW.value  # ensure stays
        clone = IdeaAiSession(
            workspace_id=first.workspace_id,
            requester_id=first.requester_id,
            purpose=IdeaAiSessionPurpose.RESEARCH.value,
            status=IdeaAiSessionStatus.READY_FOR_REVIEW.value,
            input_text=first.input_text,
            source_idea_id=first.source_idea_id,
            source_idea_updated_at=first.source_idea_updated_at,
            source_idea_snapshot=first.source_idea_snapshot,
            result_idea_id=first.result_idea_id,
            draft_payload=first.draft_payload,
            research_recommended=False,
            research_topics=first.research_topics,
            ready_at=datetime.now(timezone.utc),
        )
        sess.add(clone)
        sess.flush()
        run_b = WebResearchRun(
            session_id=clone.id,
            requester_id=owner.id,
            status=WebResearchRunStatus.AWAITING_APPROVAL.value,
            queries_to_send=["race-b"],
            sanitization_notes=[],
            base_draft_payload=dict(first.draft_payload or {}),
            base_field_provenance={},
            user_edited_fields=[],
            provider="fake",
        )
        sess.add(run_b)
        sess.commit()
        sid_b, rid_b = str(clone.id), str(run_b.id)

    barrier = threading.Barrier(2)

    def approve_one(session_id: str, run_id: str) -> None:
        barrier.wait(timeout=5)
        with session_factory() as sess:
            ws_row = sess.get(Workspace, ws.id)
            user_row = sess.get(User, owner.id)
            assert ws_row and user_row
            try:
                web_research_service.approve_research_run(
                    sess,
                    workspace=ws_row,
                    user=user_row,
                    session_id=uuid.UUID(session_id),
                    run_id=uuid.UUID(run_id),
                )
                sess.commit()
                results.append(200)
            except Exception as exc:  # noqa: BLE001
                sess.rollback()
                code = getattr(exc, "code", None)
                results.append(409 if code == "IDEA_RESEARCH_ALREADY_ACTIVE" else -1)

    t1 = threading.Thread(target=approve_one, args=(sid_a, rid_a))
    t2 = threading.Thread(target=approve_one, args=(sid_b, rid_b))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert sorted(results) == [200, 409]
    queued = list(
        db.scalars(
            select(AiJob).where(
                AiJob.job_type == AiJobType.WEB_RESEARCH.value,
                AiJob.status.in_({AiJobStatus.QUEUED.value, AiJobStatus.RUNNING.value}),
            )
        )
    )
    assert len(queued) == 1


def test_requester_only_controls_but_evidence_readable(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    reader, reader_pw = _user(db)
    ws = _team(db, owner)
    _add_member(db, ws, reader, role=WorkspaceRole.MEMBER.value)
    _login(client, owner.email, pw)
    idea = _create_idea(client, ws, visibility="WORKSPACE")

    body = _start_research(client, ws, idea["id"])
    preview = _preview(client, ws, body["id"], queries=["privacy"], draft=body["draft"])

    _login(client, reader.email, reader_pw)
    get_session = client.get(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{body['id']}",
        headers=_headers(client),
    )
    assert get_session.status_code == 404
    approve = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{body['id']}/research-runs/{preview['id']}/approve",
        headers=_headers(client),
    )
    assert approve.status_code == 404

    _login(client, owner.email, pw)
    assert (
        client.post(
            f"/api/v1/workspaces/{ws.id}/ai-sessions/{body['id']}/research-runs/{preview['id']}/approve",
            headers=_headers(client),
        ).status_code
        == 200
    )
    run_id = uuid.UUID(preview["id"])
    _make_research_job_available(db, run_id)
    class DoneLlm(FakeLlmProvider):
        def refine_idea_with_evidence(self, request):
            self.calls += 1
            return EvidenceRefinementResult(
                draft={},
                evidence_links={},
                research_summary="done",
            )

    assert ai_worker.run_once(
        session_factory=session_factory,
        provider=DoneLlm(),
        search_provider=FakeSearchProvider(url="https://example.com/readable"),
    )

    _login(client, reader.email, reader_pw)
    evidence = client.get(
        f"/api/v1/workspaces/{ws.id}/ideas/{idea['id']}/evidence",
        headers=_headers(client),
    )
    assert evidence.status_code == 200
    assert any(i["url"] == "https://example.com/readable" for i in evidence.json()["items"])


def test_evidence_dedupe_newest_first(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    idea = _create_idea(client, ws)

    def _run_once(url: str, query: str) -> None:
        body = _start_research(client, ws, idea["id"])
        preview = _preview(client, ws, body["id"], queries=[query], draft=body["draft"])
        assert (
            client.post(
                f"/api/v1/workspaces/{ws.id}/ai-sessions/{body['id']}/research-runs/{preview['id']}/approve",
                headers=_headers(client),
            ).status_code
            == 200
        )
        run_id = uuid.UUID(preview["id"])
        _make_research_job_available(db, run_id)

        class OneResult(FakeSearchProvider):
            def search(self, *, query: str, max_results: int):
                FakeSearchProvider.calls += 1
                return [
                    WebSearchResult(
                        title=f"T {query}",
                        url=url,
                        snippet="s",
                        source="Example",
                    )
                ]

        class SummaryLlm(FakeLlmProvider):
            def refine_idea_with_evidence(self, request):
                self.calls += 1
                return EvidenceRefinementResult(
                    draft={},
                    evidence_links={},
                    research_summary=query,
                )

        assert ai_worker.run_once(
            session_factory=session_factory,
            provider=SummaryLlm(),
            search_provider=OneResult(),
        )

    _run_once("https://example.com/same", "first")
    # Ensure distinct fetched_at
    with session_factory() as sess:
        for ev in sess.scalars(select(WebEvidence)):
            ev.fetched_at = datetime.now(timezone.utc) - timedelta(hours=1)
        sess.commit()
    _run_once("https://example.com/same", "second")
    _run_once("https://example.com/other", "third")

    items = client.get(
        f"/api/v1/workspaces/{ws.id}/ideas/{idea['id']}/evidence",
        headers=_headers(client),
    ).json()["items"]
    urls = [i["url"] for i in items]
    assert urls.count("https://example.com/same") == 1
    assert "https://example.com/other" in urls
    # newest first: other or same(new) before same(old)
    assert items[0]["url"] in {"https://example.com/other", "https://example.com/same"}
    same = next(i for i in items if i["url"] == "https://example.com/same")
    # Prefer the newer research title from second run
    assert "second" in same["title"]


def test_latest_recovery_endpoint_requester_only(
    client: TestClient,
    db: Session,
) -> None:
    owner, pw = _user(db)
    other, other_pw = _user(db)
    ws = _team(db, owner)
    _add_member(db, ws, other, role=WorkspaceRole.MEMBER.value)
    _login(client, owner.email, pw)
    idea = _create_idea(client, ws, visibility="WORKSPACE")

    # Confirmed old session should not hide active recovery
    old = _start_research(client, ws, idea["id"])
    session = db.get(IdeaAiSession, uuid.UUID(old["id"]))
    assert session is not None
    session.status = IdeaAiSessionStatus.CONFIRMED.value
    session.confirmed_at = datetime.now(timezone.utc)
    db.commit()

    active = _start_research(client, ws, idea["id"])
    preview = _preview(client, ws, active["id"], queries=["recover"], draft=active["draft"])

    latest = client.get(
        f"/api/v1/workspaces/{ws.id}/ideas/{idea['id']}/research-sessions/latest",
        headers=_headers(client),
    )
    assert latest.status_code == 200
    assert latest.json()["session"]["id"] == active["id"]

    _login(client, other.email, other_pw)
    other_latest = client.get(
        f"/api/v1/workspaces/{ws.id}/ideas/{idea['id']}/research-sessions/latest",
        headers=_headers(client),
    )
    assert other_latest.status_code == 200
    assert other_latest.json()["session"] is None
    assert preview["status"] == "AWAITING_APPROVAL"


def test_regenerate_confirm_apply_rejected_for_research(
    client: TestClient,
    db: Session,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    idea = _create_idea(client, ws)
    body = _start_research(client, ws, idea["id"])

    regen = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{body['id']}/regenerate",
        headers=_headers(client),
    )
    assert regen.status_code == 409
    assert regen.json()["error"]["code"] == "AI_SESSION_INVALID_STATE"

    confirm = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{body['id']}/confirm",
        json={
            "title": "x",
            "priority": "MEDIUM",
            "feasibility": "UNKNOWN",
            "visibility": "WORKSPACE",
            "tags": [],
        },
        headers=_headers(client),
    )
    assert confirm.status_code == 400
    assert confirm.json()["error"]["code"] == "AI_SESSION_INVALID_STATE"

    apply = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{body['id']}/apply-refinement",
        json={
            "title": idea["title"],
            "one_line_definition": idea["one_line_definition"],
            "problem": idea["problem"],
            "core_concept": "changed",
            "priority": "MEDIUM",
            "feasibility": "UNKNOWN",
            "tags": ["AI"],
        },
        headers=_headers(client),
    )
    assert apply.status_code == 400
    assert apply.json()["error"]["code"] == "AI_SESSION_INVALID_STATE"


def test_web_search_disabled_blocks_create(
    client: TestClient,
    db: Session,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner, allow_web_search=False)
    _login(client, owner.email, pw)
    idea = _create_idea(client, ws)
    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ideas/{idea['id']}/research-sessions",
        headers=_headers(client),
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "WORKSPACE_WEB_SEARCH_DISABLED"
