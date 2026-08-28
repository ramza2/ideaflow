"""PostgreSQL Web Research integration tests (Step 9)."""

from __future__ import annotations

import os
import uuid
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import reset_engine
from app.llm.research_schemas import EvidenceRefinementResult
from app.llm.schemas import (
    ClarifyingQuestionRaw,
    FieldProvenanceEntry,
    IdeaDraftPayload,
    IdeaStructuringResult,
)
from app.main import app
from app.models.ai import AiJob, IdeaAiSession
from app.models.enums import (
    AiJobStatus,
    AiJobType,
    AiLlmDecision,
    FieldProvenanceSource,
    IdeaAiSessionStatus,
    SystemRole,
    UserStatus,
    WebResearchRunStatus,
    WorkspaceMemberStatus,
    WorkspaceRole,
    WorkspaceType,
)
from app.models.research import WebEvidence, WebResearchRun
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.services import ai_worker
from app.services.workspace import seed_workspace_defaults
from app.web_search.base import WebSearchResult
from app.web_search.http_json import HttpJsonWebSearchProvider

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — skipping web research integration tests",
)

PRIVATE_MARKER = "PRIVATE_SECRET_IDEA_MARKER_987654"


class FakeSearchProvider:
    provider_name = "fake_search"
    calls = 0
    last_bodies: list[dict[str, Any]] = []

    def search(self, *, query: str, max_results: int) -> list[WebSearchResult]:
        type(self).calls += 1
        type(self).last_bodies.append({"query": query, "max_results": max_results})
        return [
            WebSearchResult(
                title="Evidence Title",
                url="https://example.com/article",
                snippet="Helpful snippet",
                source="Example",
            )
        ]

    def close(self) -> None:
        pass


class FakeProvider:
    provider_name = "fake"
    model_name = "fake-model"
    prompt_version = "v1"

    def __init__(self, results: list[Any] | None = None) -> None:
        self._results = list(results or [])
        self.calls = 0

    def structure_idea(self, request):
        self.calls += 1
        item = self._results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def refine_idea_with_evidence(self, request):
        self.calls += 1
        item = self._results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def close(self) -> None:
        pass


def _ready_result() -> IdeaStructuringResult:
    return IdeaStructuringResult(
        decision=AiLlmDecision.READY_FOR_REVIEW,
        draft=IdeaDraftPayload(
            title="AI Draft",
            background="A",
            problem="P",
            tags=[],
        ),
        field_provenance={
            "background": FieldProvenanceEntry(
                source=FieldProvenanceSource.LLM_SUMMARY,
                note="요약",
            )
        },
        research_recommended=True,
        research_topics=["idea management software"],
    )


def _refine_result(evidence_id: str) -> EvidenceRefinementResult:
    return EvidenceRefinementResult(
        draft={
            "title": "AI Draft",
            "background": "B from evidence",
        },
        evidence_links={"background": [evidence_id]},
        research_summary="보완 요약",
    )


@pytest.fixture(autouse=True)
def _clean_tables(engine):
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
    monkeypatch.setenv("WEB_SEARCH_API_URL", "https://search.example.test/query")
    get_settings.cache_clear()
    reset_engine()
    with TestClient(app) as c:
        yield c
    reset_engine()
    get_settings.cache_clear()


def _user(db: Session, *, email: str | None = None, password: str = "password-ok-1") -> tuple[User, str]:
    email = email or f"wr-{uuid.uuid4().hex[:10]}@example.com"
    user = User(
        email=email.lower(),
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


def _team(db: Session, owner: User, *, allow_web_search: bool = True, allow_llm: bool = True) -> Workspace:
    ws = Workspace(
        name=f"WR Team {uuid.uuid4().hex[:6]}",
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


def _ready_session(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
    ws: Workspace,
    owner: User,
    pw: str,
    *,
    input_text: str = "아이디어 본문",
) -> uuid.UUID:
    _login(client, owner.email, pw)
    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions",
        json={"input_text": input_text},
        headers=_headers(client),
    )
    assert r.status_code == 202
    session_id = uuid.UUID(r.json()["id"])
    provider = FakeProvider([_ready_result()])
    assert ai_worker.run_once(session_factory=session_factory, provider=provider)
    db.expire_all()
    return session_id


def test_preview_no_external_call(client: TestClient, db: Session, session_factory) -> None:
    FakeSearchProvider.calls = 0
    owner, pw = _user(db)
    ws = _team(db, owner)
    session_id = _ready_session(client, db, session_factory, ws, owner, pw)

    _login(client, owner.email, pw)
    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/research-runs/preview",
        json={
            "queries": ["idea management software"],
            "current_draft": {"title": "AI Draft", "background": "A"},
            "user_edited_fields": [],
        },
        headers=_headers(client),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "AWAITING_APPROVAL"
    assert FakeSearchProvider.calls == 0
    jobs = db.scalars(select(AiJob).where(AiJob.session_id == session_id)).all()
    assert len(jobs) == 1
    assert jobs[0].job_type == AiJobType.STRUCTURE_IDEA.value


def test_approve_creates_job_not_search(client: TestClient, db: Session, session_factory) -> None:
    FakeSearchProvider.calls = 0
    owner, pw = _user(db)
    ws = _team(db, owner)
    session_id = _ready_session(client, db, session_factory, ws, owner, pw)

    _login(client, owner.email, pw)
    preview = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/research-runs/preview",
        json={"queries": ["idea management software"], "current_draft": {"title": "AI Draft"}},
        headers=_headers(client),
    )
    run_id = preview.json()["id"]

    approve = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/research-runs/{run_id}/approve",
        headers=_headers(client),
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "QUEUED"
    assert FakeSearchProvider.calls == 0

    research_jobs = list(
        db.scalars(
            select(AiJob).where(
                AiJob.session_id == session_id,
                AiJob.job_type == AiJobType.WEB_RESEARCH.value,
            )
        )
    )
    assert len(research_jobs) == 1
    assert research_jobs[0].status == AiJobStatus.QUEUED.value


def test_allow_web_search_false(client: TestClient, db: Session, session_factory) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner, allow_web_search=False)
    session_id = _ready_session(client, db, session_factory, ws, owner, pw)

    _login(client, owner.email, pw)
    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/research-runs/preview",
        json={"queries": ["test"], "current_draft": {}},
        headers=_headers(client),
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "WORKSPACE_WEB_SEARCH_DISABLED"


def test_security_no_idea_leakage(
    client: TestClient,
    db: Session,
    session_factory,
) -> None:
    FakeSearchProvider.calls = 0
    FakeSearchProvider.last_bodies = []
    owner, pw = _user(db)
    ws = _team(db, owner)
    session_id = _ready_session(
        client,
        db,
        session_factory,
        ws,
        owner,
        pw,
        input_text=PRIVATE_MARKER,
    )

    _login(client, owner.email, pw)
    preview = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/research-runs/preview",
        json={
            "queries": ["idea management software"],
            "current_draft": {"title": PRIVATE_MARKER, "background": PRIVATE_MARKER},
        },
        headers=_headers(client),
    )
    run_id = preview.json()["id"]
    client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/research-runs/{run_id}/approve",
        headers=_headers(client),
    )

    class RefineFromEvidence(FakeProvider):
        def refine_idea_with_evidence(self, request):
            ev_id = str(request.evidence[0].evidence_id)
            return _refine_result(ev_id)

    search = FakeSearchProvider()
    llm = RefineFromEvidence()
    assert ai_worker.run_once(
        session_factory=session_factory,
        provider=llm,
        search_provider=search,
    )

    for body in FakeSearchProvider.last_bodies:
        assert PRIVATE_MARKER not in str(body)
        assert body == {"query": "idea management software", "max_results": 5}


def test_research_success_updates_session(
    client: TestClient,
    db: Session,
    session_factory,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    session_id = _ready_session(client, db, session_factory, ws, owner, pw)

    _login(client, owner.email, pw)
    preview = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/research-runs/preview",
        json={"queries": ["saas examples"], "current_draft": {"title": "AI Draft", "background": "A"}},
        headers=_headers(client),
    )
    run_id = uuid.UUID(preview.json()["id"])
    client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/research-runs/{run_id}/approve",
        headers=_headers(client),
    )

    search = FakeSearchProvider()

    class RefineFromEvidence(FakeProvider):
        def refine_idea_with_evidence(self, request):
            ev_id = str(request.evidence[0].evidence_id)
            return _refine_result(ev_id)

    llm = RefineFromEvidence()
    assert ai_worker.run_once(session_factory=session_factory, provider=llm, search_provider=search)

    db.expire_all()
    run = db.get(WebResearchRun, run_id)
    session = db.get(IdeaAiSession, session_id)
    assert run.status == WebResearchRunStatus.READY.value
    assert session.status == IdeaAiSessionStatus.READY_FOR_REVIEW.value
    assert session.draft_payload["background"] == "B from evidence"
    assert session.field_provenance["background"]["source"] == "WEB_EVIDENCE"
    assert session.research_recommended is False


def test_confirm_blocked_during_research(client: TestClient, db: Session, session_factory) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    session_id = _ready_session(client, db, session_factory, ws, owner, pw)

    _login(client, owner.email, pw)
    preview = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/research-runs/preview",
        json={"queries": ["test"], "current_draft": {"title": "AI Draft"}},
        headers=_headers(client),
    )
    run_id = preview.json()["id"]
    client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/research-runs/{run_id}/approve",
        headers=_headers(client),
    )

    db.expire_all()
    run = db.scalars(select(WebResearchRun).where(WebResearchRun.id == uuid.UUID(run_id))).first()
    run.status = WebResearchRunStatus.SEARCHING.value
    db.commit()

    confirm = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/confirm",
        json={"title": "AI Draft"},
        headers=_headers(client),
    )
    assert confirm.status_code == 409
    assert confirm.json()["error"]["code"] == "AI_RESEARCH_IN_PROGRESS"
