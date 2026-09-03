"""PostgreSQL Web Research integration tests (Step 9)."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import reset_engine
from app.llm.exceptions import LlmTimeoutError
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
from app.web_search.exceptions import WebSearchTimeoutError
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
    prompt_version = "v2"

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
    for _ in range(5):
        job = db.scalars(
            select(AiJob).where(
                AiJob.session_id == session_id,
                AiJob.job_type == AiJobType.STRUCTURE_IDEA.value,
            )
        ).first()
        if job is not None and job.available_at > datetime.now(timezone.utc):
            job.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
        if ai_worker.run_once(session_factory=session_factory, provider=provider):
            db.expire_all()
            session = db.get(IdeaAiSession, session_id)
            if session.status == IdeaAiSessionStatus.READY_FOR_REVIEW.value:
                return session_id
    db.expire_all()
    session = db.get(IdeaAiSession, session_id)
    pytest.fail(
        f"session not ready after retries (status={session.status if session else 'missing'})"
    )


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
    assert _run_research_worker_once(
        db,
        session_factory,
        uuid.UUID(run_id),
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
    assert _run_research_worker_once(
        db, session_factory, run_id, provider=llm, search_provider=search
    )

    db.expire_all()
    run = db.get(WebResearchRun, run_id)
    session = db.get(IdeaAiSession, session_id)
    assert run.status == WebResearchRunStatus.READY.value
    assert run.prompt_version == "v2"
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


def _make_research_job_available(db: Session, run_id: uuid.UUID) -> AiJob:
    job = db.scalars(
        select(AiJob)
        .where(
            AiJob.research_run_id == run_id,
            AiJob.job_type == AiJobType.WEB_RESEARCH.value,
            AiJob.status == AiJobStatus.QUEUED.value,
        )
        .order_by(AiJob.created_at.desc())
    ).first()
    if job is None:
        job = db.scalars(
            select(AiJob)
            .where(
                AiJob.research_run_id == run_id,
                AiJob.job_type == AiJobType.WEB_RESEARCH.value,
            )
            .order_by(AiJob.created_at.desc())
        ).first()
    assert job is not None, f"no WEB_RESEARCH job for run {run_id}"
    job.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    for other in db.scalars(
        select(AiJob).where(
            AiJob.status == AiJobStatus.QUEUED.value,
            AiJob.id != job.id,
        )
    ).all():
        other.available_at = datetime.now(timezone.utc) + timedelta(hours=1)
    db.commit()
    return job


def _run_research_worker_once(
    db: Session,
    session_factory: sessionmaker,
    run_id: uuid.UUID,
    *,
    provider,
    search_provider,
) -> bool:
    _make_research_job_available(db, run_id)
    claimed = ai_worker.run_once(
        session_factory=session_factory,
        provider=provider,
        search_provider=search_provider,
    )
    db.expire_all()
    return claimed


def _preview_and_approve(
    client: TestClient,
    ws: Workspace,
    session_id: uuid.UUID,
    *,
    queries: list[str] | None = None,
    draft: dict | None = None,
) -> uuid.UUID:
    queries = queries or ["saas examples"]
    draft = draft or {"title": "AI Draft", "background": "A"}
    preview = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/research-runs/preview",
        json={"queries": queries, "current_draft": draft, "user_edited_fields": []},
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


def test_refine_auto_retry_skips_search(
    client: TestClient,
    db: Session,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_JOB_MAX_ATTEMPTS", "3")
    get_settings.cache_clear()

    FakeSearchProvider.calls = 0
    owner, pw = _user(db)
    ws = _team(db, owner)
    session_id = _ready_session(client, db, session_factory, ws, owner, pw)
    _login(client, owner.email, pw)
    run_id = _preview_and_approve(client, ws, session_id)

    class FlakyRefineProvider(FakeProvider):
        refine_calls = 0

        def refine_idea_with_evidence(self, request):
            type(self).refine_calls += 1
            if type(self).refine_calls == 1:
                raise LlmTimeoutError()
            ev_id = str(request.evidence[0].evidence_id)
            return _refine_result(ev_id)

    search = FakeSearchProvider()
    llm = FlakyRefineProvider()
    assert _run_research_worker_once(
        db, session_factory, run_id, provider=llm, search_provider=search
    )

    db.expire_all()
    run = db.get(WebResearchRun, run_id)
    assert run.status == WebResearchRunStatus.QUEUED.value
    assert run.failure_phase == "REFINE"
    assert FakeSearchProvider.calls == 1
    assert (
        db.scalar(
            select(func.count()).select_from(WebEvidence).where(WebEvidence.research_run_id == run_id)
        )
        == 1
    )

    assert _run_research_worker_once(
        db, session_factory, run_id, provider=llm, search_provider=search
    )
    assert FakeSearchProvider.calls == 1

    db.expire_all()
    run = db.get(WebResearchRun, run_id)
    assert run.status == WebResearchRunStatus.READY.value
    assert run.failure_phase is None


def test_refine_manual_retry_skips_search(
    client: TestClient,
    db: Session,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeSearchProvider.calls = 0
    owner, pw = _user(db)
    ws = _team(db, owner)
    session_id = _ready_session(client, db, session_factory, ws, owner, pw)
    _login(client, owner.email, pw)
    run_id = _preview_and_approve(client, ws, session_id)

    monkeypatch.setenv("AI_JOB_MAX_ATTEMPTS", "1")
    get_settings.cache_clear()
    research_job = db.scalars(
        select(AiJob).where(
            AiJob.research_run_id == run_id,
            AiJob.job_type == AiJobType.WEB_RESEARCH.value,
        )
    ).one()
    research_job.max_attempts = 1
    db.commit()

    class AlwaysFailRefine(FakeProvider):
        def refine_idea_with_evidence(self, request):
            raise LlmTimeoutError()

    search = FakeSearchProvider()
    llm = AlwaysFailRefine()
    assert _run_research_worker_once(
        db, session_factory, run_id, provider=llm, search_provider=search
    )

    db.expire_all()
    run = db.get(WebResearchRun, run_id)
    assert run.status == WebResearchRunStatus.FAILED.value
    assert run.failure_phase == "REFINE"
    assert FakeSearchProvider.calls == 1

    retry = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/research-runs/{run_id}/retry",
        headers=_headers(client),
    )
    assert retry.status_code == 200
    assert retry.json()["status"] == "QUEUED"

    db.expire_all()
    run = db.get(WebResearchRun, run_id)
    assert run.failure_phase == "REFINE"

    class RefineFromEvidence(FakeProvider):
        def refine_idea_with_evidence(self, request):
            ev_id = str(request.evidence[0].evidence_id)
            return _refine_result(ev_id)

    FakeSearchProvider.calls = 0
    assert _run_research_worker_once(
        db,
        session_factory,
        run_id,
        provider=RefineFromEvidence(),
        search_provider=search,
    )
    assert FakeSearchProvider.calls == 0


def test_search_retry_researches(
    client: TestClient,
    db: Session,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_JOB_MAX_ATTEMPTS", "3")
    get_settings.cache_clear()

    class FlakySearchProvider:
        provider_name = "flaky_search"
        calls = 0

        def search(self, *, query: str, max_results: int) -> list[WebSearchResult]:
            type(self).calls += 1
            if type(self).calls == 1:
                raise WebSearchTimeoutError()
            return [
                WebSearchResult(
                    title="Evidence Title",
                    url="https://example.com/article",
                    snippet="snippet",
                    source="Example",
                )
            ]

        def close(self) -> None:
            pass

    FlakySearchProvider.calls = 0
    owner, pw = _user(db)
    ws = _team(db, owner)
    session_id = _ready_session(client, db, session_factory, ws, owner, pw)
    _login(client, owner.email, pw)
    run_id = _preview_and_approve(client, ws, session_id)

    class RefineFromEvidence(FakeProvider):
        def refine_idea_with_evidence(self, request):
            ev_id = str(request.evidence[0].evidence_id)
            return _refine_result(ev_id)

    search = FlakySearchProvider()
    llm = RefineFromEvidence()
    assert _run_research_worker_once(
        db, session_factory, run_id, provider=llm, search_provider=search
    )

    db.expire_all()
    run = db.get(WebResearchRun, run_id)
    assert run.status == WebResearchRunStatus.QUEUED.value
    assert run.failure_phase == "SEARCH"
    assert FlakySearchProvider.calls == 1

    assert _run_research_worker_once(
        db, session_factory, run_id, provider=llm, search_provider=search
    )
    assert FlakySearchProvider.calls == 2

    db.expire_all()
    run = db.get(WebResearchRun, run_id)
    assert run.status == WebResearchRunStatus.READY.value


def test_stale_lease_failure_phase_search(db: Session) -> None:

    owner, _ = _user(db)
    ws = _team(db, owner)
    session = IdeaAiSession(
        workspace_id=ws.id,
        requester_id=owner.id,
        purpose="CREATE",
        status=IdeaAiSessionStatus.READY_FOR_REVIEW.value,
        input_text="idea",
        research_recommended=False,
    )
    db.add(session)
    db.flush()
    run = WebResearchRun(
        session_id=session.id,
        requester_id=owner.id,
        status=WebResearchRunStatus.SEARCHING.value,
        queries_to_send=["query"],
        base_draft_payload={"title": "t"},
    )
    db.add(run)
    db.flush()
    now = datetime.now(timezone.utc)
    job = AiJob(
        session_id=session.id,
        research_run_id=run.id,
        job_type=AiJobType.WEB_RESEARCH.value,
        status=AiJobStatus.RUNNING.value,
        attempts=3,
        max_attempts=3,
        available_at=now,
        lease_until=now - timedelta(seconds=30),
        worker_id="stale-worker",
    )
    db.add(job)
    db.commit()

    ai_worker.recover_stale_jobs(db, settings=get_settings())
    db.expire_all()
    run = db.get(WebResearchRun, run.id)
    assert run.status == WebResearchRunStatus.FAILED.value
    assert run.failure_phase == "SEARCH"


def test_stale_lease_failure_phase_refine(db: Session) -> None:
    from datetime import datetime, timedelta, timezone

    owner, _ = _user(db)
    ws = _team(db, owner)
    session = IdeaAiSession(
        workspace_id=ws.id,
        requester_id=owner.id,
        purpose="CREATE",
        status=IdeaAiSessionStatus.READY_FOR_REVIEW.value,
        input_text="idea",
        research_recommended=False,
    )
    db.add(session)
    db.flush()
    run = WebResearchRun(
        session_id=session.id,
        requester_id=owner.id,
        status=WebResearchRunStatus.REFINING.value,
        queries_to_send=["query"],
        base_draft_payload={"title": "t"},
    )
    db.add(run)
    db.flush()
    now = datetime.now(timezone.utc)
    job = AiJob(
        session_id=session.id,
        research_run_id=run.id,
        job_type=AiJobType.WEB_RESEARCH.value,
        status=AiJobStatus.RUNNING.value,
        attempts=3,
        max_attempts=3,
        available_at=now,
        lease_until=now - timedelta(seconds=30),
        worker_id="stale-worker",
    )
    db.add(job)
    db.commit()

    ai_worker.recover_stale_jobs(db, settings=get_settings())
    db.expire_all()
    run = db.get(WebResearchRun, run.id)
    assert run.status == WebResearchRunStatus.FAILED.value
    assert run.failure_phase == "REFINE"


def test_stale_refine_requeue_reuses_evidence(
    db: Session,
    session_factory,
) -> None:
    from app.services import web_research as web_research_service

    owner, _ = _user(db)
    ws = _team(db, owner)
    session = IdeaAiSession(
        workspace_id=ws.id,
        requester_id=owner.id,
        purpose="CREATE",
        status=IdeaAiSessionStatus.READY_FOR_REVIEW.value,
        input_text="idea",
        research_recommended=False,
        draft_payload={"title": "AI Draft", "background": "A"},
    )
    db.add(session)
    db.flush()
    run = WebResearchRun(
        session_id=session.id,
        requester_id=owner.id,
        status=WebResearchRunStatus.REFINING.value,
        queries_to_send=["query"],
        base_draft_payload={"title": "AI Draft", "background": "A"},
    )
    db.add(run)
    db.flush()
    evidence = WebEvidence(
        research_run_id=run.id,
        query="query",
        title="Evidence Title",
        url="https://example.com/article",
        url_hash=web_research_service.url_hash("https://example.com/article"),
        snippet="snippet",
        rank=0,
        provider="fake_search",
    )
    db.add(evidence)
    now = datetime.now(timezone.utc)
    job = AiJob(
        session_id=session.id,
        research_run_id=run.id,
        job_type=AiJobType.WEB_RESEARCH.value,
        status=AiJobStatus.RUNNING.value,
        attempts=1,
        max_attempts=3,
        available_at=now,
        lease_until=now - timedelta(seconds=30),
        worker_id="stale-worker",
    )
    db.add(job)
    db.commit()

    ai_worker.recover_stale_jobs(db, settings=get_settings())
    db.expire_all()
    job = db.get(AiJob, job.id)
    run = db.get(WebResearchRun, run.id)
    assert job.status == AiJobStatus.QUEUED.value
    assert run.status == WebResearchRunStatus.QUEUED.value
    assert run.failure_phase == "REFINE"
    assert (
        db.scalar(
            select(func.count()).select_from(WebEvidence).where(WebEvidence.research_run_id == run.id)
        )
        == 1
    )

    FakeSearchProvider.calls = 0

    class RefineFromEvidence(FakeProvider):
        refine_calls = 0

        def refine_idea_with_evidence(self, request):
            type(self).refine_calls += 1
            ev_id = str(request.evidence[0].evidence_id)
            return _refine_result(ev_id)

    llm = RefineFromEvidence()
    search = FakeSearchProvider()
    assert _run_research_worker_once(
        db, session_factory, run.id, provider=llm, search_provider=search
    )
    assert FakeSearchProvider.calls == 0
    assert RefineFromEvidence.refine_calls == 1

    db.expire_all()
    run = db.get(WebResearchRun, run.id)
    assert run.status == WebResearchRunStatus.READY.value
    assert run.failure_phase is None


def test_stale_search_requeue_researches(
    db: Session,
    session_factory,
) -> None:
    owner, _ = _user(db)
    ws = _team(db, owner)
    session = IdeaAiSession(
        workspace_id=ws.id,
        requester_id=owner.id,
        purpose="CREATE",
        status=IdeaAiSessionStatus.READY_FOR_REVIEW.value,
        input_text="idea",
        research_recommended=False,
    )
    db.add(session)
    db.flush()
    run = WebResearchRun(
        session_id=session.id,
        requester_id=owner.id,
        status=WebResearchRunStatus.SEARCHING.value,
        queries_to_send=["query"],
        base_draft_payload={"title": "AI Draft", "background": "A"},
    )
    db.add(run)
    db.flush()
    now = datetime.now(timezone.utc)
    job = AiJob(
        session_id=session.id,
        research_run_id=run.id,
        job_type=AiJobType.WEB_RESEARCH.value,
        status=AiJobStatus.RUNNING.value,
        attempts=1,
        max_attempts=3,
        available_at=now,
        lease_until=now - timedelta(seconds=30),
        worker_id="stale-worker",
    )
    db.add(job)
    db.commit()

    ai_worker.recover_stale_jobs(db, settings=get_settings())
    db.expire_all()
    job = db.get(AiJob, job.id)
    run = db.get(WebResearchRun, run.id)
    assert job.status == AiJobStatus.QUEUED.value
    assert run.status == WebResearchRunStatus.QUEUED.value
    assert run.failure_phase == "SEARCH"

    FakeSearchProvider.calls = 0

    class RefineFromEvidence(FakeProvider):
        def refine_idea_with_evidence(self, request):
            ev_id = str(request.evidence[0].evidence_id)
            return _refine_result(ev_id)

    search = FakeSearchProvider()
    llm = RefineFromEvidence()
    assert _run_research_worker_once(
        db, session_factory, run.id, provider=llm, search_provider=search
    )
    assert FakeSearchProvider.calls == 1

    db.expire_all()
    run = db.get(WebResearchRun, run.id)
    assert run.status == WebResearchRunStatus.READY.value


def test_zero_result_ready_clears_failure_metadata(
    db: Session,
    session_factory,
) -> None:
    owner, _ = _user(db)
    ws = _team(db, owner)
    session = IdeaAiSession(
        workspace_id=ws.id,
        requester_id=owner.id,
        purpose="CREATE",
        status=IdeaAiSessionStatus.READY_FOR_REVIEW.value,
        input_text="idea",
        research_recommended=True,
        draft_payload={"title": "AI Draft"},
    )
    db.add(session)
    db.flush()
    run = WebResearchRun(
        session_id=session.id,
        requester_id=owner.id,
        status=WebResearchRunStatus.QUEUED.value,
        queries_to_send=["query"],
        base_draft_payload={"title": "AI Draft"},
        failure_phase="SEARCH",
        failure_code="WEB_SEARCH_TIMEOUT",
        failure_message="search timed out",
    )
    db.add(run)
    db.flush()
    now = datetime.now(timezone.utc)
    job = AiJob(
        session_id=session.id,
        research_run_id=run.id,
        job_type=AiJobType.WEB_RESEARCH.value,
        status=AiJobStatus.QUEUED.value,
        attempts=0,
        max_attempts=3,
        available_at=now,
    )
    db.add(job)
    db.commit()

    class EmptySearchProvider:
        provider_name = "empty_search"
        calls = 0

        def search(self, *, query: str, max_results: int) -> list[WebSearchResult]:
            type(self).calls += 1
            return []

        def close(self) -> None:
            pass

    EmptySearchProvider.calls = 0
    assert _run_research_worker_once(
        db,
        session_factory,
        run.id,
        provider=FakeProvider(),
        search_provider=EmptySearchProvider(),
    )
    assert EmptySearchProvider.calls == 1

    db.expire_all()
    run = db.get(WebResearchRun, run.id)
    assert run.status == WebResearchRunStatus.READY.value
    assert run.result_count == 0
    assert run.failure_phase is None
    assert run.failure_code is None
    assert run.failure_message is None


def test_preview_edit_cancel_new_preview(
    client: TestClient,
    db: Session,
    session_factory,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    session_id = _ready_session(client, db, session_factory, ws, owner, pw)
    _login(client, owner.email, pw)

    preview_a = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/research-runs/preview",
        json={"queries": ["query A"], "current_draft": {"title": "AI Draft"}},
        headers=_headers(client),
    )
    assert preview_a.status_code == 201
    run_a_id = preview_a.json()["id"]

    cancel = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/research-runs/{run_a_id}/cancel",
        headers=_headers(client),
    )
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "CANCELLED"

    preview_b = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/research-runs/preview",
        json={"queries": ["query B"], "current_draft": {"title": "AI Draft"}},
        headers=_headers(client),
    )
    assert preview_b.status_code == 201, preview_b.text
    body = preview_b.json()
    assert body["status"] == "AWAITING_APPROVAL"
    assert body["queries_to_send"] == ["query B"]
    assert body["id"] != run_a_id


def test_preview_draft_sanitizes_unknown_keys(
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
        json={
            "queries": ["query"],
            "current_draft": {
                "title": "AI Draft",
                "background": "A",
                "evil_field": "drop me",
                "workspace_id": "secret",
            },
            "user_edited_fields": ["title", "not_a_field"],
        },
        headers=_headers(client),
    )
    assert preview.status_code == 201
    run_id = uuid.UUID(preview.json()["id"])
    run = db.get(WebResearchRun, run_id)
    assert run.base_draft_payload == {"title": "AI Draft", "background": "A"}
    assert run.user_edited_fields == ["title"]


def test_refine_passes_budgeted_evidence_to_llm(
    client: TestClient,
    db: Session,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WEB_SEARCH_MAX_TOTAL_RESULTS", "10")
    monkeypatch.setenv("WEB_SEARCH_MAX_RESULTS_PER_QUERY", "10")
    monkeypatch.setenv("WEB_RESEARCH_REFINE_MAX_EVIDENCE_ITEMS", "4")
    monkeypatch.setenv("WEB_RESEARCH_REFINE_MAX_SNIPPET_CHARS", "200")
    monkeypatch.setenv("WEB_RESEARCH_REFINE_MAX_EVIDENCE_CHARS", "1500")
    get_settings.cache_clear()

    class ManyResultSearchProvider:
        provider_name = "many_fake"

        def search(self, *, query: str, max_results: int) -> list[WebSearchResult]:
            return [
                WebSearchResult(
                    title=f"Title {i}",
                    url=f"https://example.com/{i}",
                    snippet="snippet-" + ("x" * 300),
                    source="Example",
                )
                for i in range(max_results)
            ]

        def close(self) -> None:
            pass

    captured: dict[str, Any] = {}

    class CaptureRefine(FakeProvider):
        def refine_idea_with_evidence(self, request):
            captured["evidence_count"] = len(request.evidence)
            captured["max_snippet_len"] = max(len(ev.snippet or "") for ev in request.evidence)
            ev_id = str(request.evidence[0].evidence_id)
            return _refine_result(ev_id)

    owner, pw = _user(db)
    ws = _team(db, owner)
    session_id = _ready_session(client, db, session_factory, ws, owner, pw)
    _login(client, owner.email, pw)
    run_id = _preview_and_approve(client, ws, session_id)

    search = ManyResultSearchProvider()
    llm = CaptureRefine()
    assert _run_research_worker_once(
        db, session_factory, run_id, provider=llm, search_provider=search
    )

    db.expire_all()
    stored_count = db.scalar(
        select(func.count()).select_from(WebEvidence).where(WebEvidence.research_run_id == run_id)
    )
    run = db.get(WebResearchRun, run_id)
    assert stored_count == 10
    assert run.result_count == 10
    assert captured["evidence_count"] <= 4
    assert captured["max_snippet_len"] <= 200


def test_refine_prompt_excludes_long_input_text(
    client: TestClient,
    db: Session,
    session_factory,
) -> None:
    from app.llm.research_prompts import build_research_user_prompt

    captured: dict[str, Any] = {}
    secret = "PRODUCTION_LONG_INPUT_" + ("z" * 8000)

    class CapturePrompt(FakeProvider):
        def refine_idea_with_evidence(self, request):
            captured["prompt"] = build_research_user_prompt(request)
            ev_id = str(request.evidence[0].evidence_id)
            return _refine_result(ev_id)

    owner, pw = _user(db)
    ws = _team(db, owner)
    session_id = _ready_session(client, db, session_factory, ws, owner, pw)
    session = db.get(IdeaAiSession, session_id)
    session.input_text = secret
    db.commit()

    _login(client, owner.email, pw)
    run_id = _preview_and_approve(client, ws, session_id)

    assert _run_research_worker_once(
        db,
        session_factory,
        run_id,
        provider=CapturePrompt(),
        search_provider=FakeSearchProvider(),
    )
    assert secret not in captured["prompt"]


def test_refine_input_too_large_fails_without_llm_call(
    client: TestClient,
    db: Session,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WEB_RESEARCH_REFINE_MAX_PROMPT_CHARS", "800")
    get_settings.cache_clear()

    class ShouldNotCall(FakeProvider):
        refine_calls = 0

        def refine_idea_with_evidence(self, request):
            type(self).refine_calls += 1
            return _refine_result(str(request.evidence[0].evidence_id))

    owner, pw = _user(db)
    ws = _team(db, owner)
    session_id = _ready_session(client, db, session_factory, ws, owner, pw)
    _login(client, owner.email, pw)
    huge_draft = {field: "x" * 500 for field in (
        "title",
        "one_line_definition",
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
    )}
    run_id = _preview_and_approve(client, ws, session_id, draft=huge_draft)

    provider = ShouldNotCall()
    assert _run_research_worker_once(
        db,
        session_factory,
        run_id,
        provider=provider,
        search_provider=FakeSearchProvider(),
    )
    assert provider.refine_calls == 0
    run = db.get(WebResearchRun, run_id)
    assert run.status == WebResearchRunStatus.FAILED.value
    assert run.failure_phase == "REFINE"
    assert run.failure_code == "AI_RESEARCH_REFINE_INPUT_TOO_LARGE"


def test_refine_retry_skips_search_provider(
    db: Session,
    session_factory,
) -> None:
    from app.services import web_research as web_research_service

    owner, _ = _user(db)
    ws = _team(db, owner)
    session = IdeaAiSession(
        workspace_id=ws.id,
        requester_id=owner.id,
        purpose="CREATE",
        status=IdeaAiSessionStatus.READY_FOR_REVIEW.value,
        input_text="idea",
        research_recommended=False,
        draft_payload={"title": "AI Draft", "background": "A"},
    )
    db.add(session)
    db.flush()
    run = WebResearchRun(
        session_id=session.id,
        requester_id=owner.id,
        status=WebResearchRunStatus.REFINING.value,
        queries_to_send=["query"],
        base_draft_payload={"title": "AI Draft", "background": "A"},
        failure_phase="REFINE",
    )
    db.add(run)
    db.flush()
    db.add(
        WebEvidence(
            research_run_id=run.id,
            query="query",
            title="Evidence Title",
            url="https://example.com/article",
            url_hash=web_research_service.url_hash("https://example.com/article"),
            snippet="snippet",
            rank=0,
            provider="fake_search",
        )
    )
    now = datetime.now(timezone.utc)
    db.add(
        AiJob(
            session_id=session.id,
            research_run_id=run.id,
            job_type=AiJobType.WEB_RESEARCH.value,
            status=AiJobStatus.RUNNING.value,
            attempts=1,
            max_attempts=3,
            available_at=now,
            lease_until=now + timedelta(seconds=300),
            worker_id="worker-1",
        )
    )
    db.commit()

    FakeSearchProvider.calls = 0

    class RefineOk(FakeProvider):
        def refine_idea_with_evidence(self, request):
            ev_id = str(request.evidence[0].evidence_id)
            return _refine_result(ev_id)

    job = db.scalars(select(AiJob).where(AiJob.research_run_id == run.id)).first()
    ai_worker.process_web_research_job(
        db,
        job_id=job.id,
        worker_id="worker-1",
        provider=RefineOk(),
        search_provider=FakeSearchProvider(),
    )
    assert FakeSearchProvider.calls == 0
    db.expire_all()
    run = db.get(WebResearchRun, run.id)
    assert run.status == WebResearchRunStatus.READY.value


def test_refine_ignores_user_edited_fields_in_llm_response(
    client: TestClient,
    db: Session,
    session_factory,
) -> None:
    from app.llm.research_schemas import EvidenceRefinementResult
    from app.models.enums import FieldProvenanceSource

    owner, pw = _user(db)
    ws = _team(db, owner)
    session_id = _ready_session(client, db, session_factory, ws, owner, pw)
    session = db.get(IdeaAiSession, session_id)
    session.draft_payload = {
        "title": "AI Draft",
        "background": "배경은 유지 테스트",
        "challenges": "기존 내용",
    }
    session.field_provenance = {
        "background": {
            "source": FieldProvenanceSource.USER_EDIT.value,
            "final_source": FieldProvenanceSource.USER_EDIT.value,
            "original_source": FieldProvenanceSource.LLM_SUMMARY.value,
        }
    }
    db.commit()

    _login(client, owner.email, pw)
    run_id = _preview_and_approve(
        client,
        ws,
        session_id,
        draft=session.draft_payload,
    )
    run = db.get(WebResearchRun, run_id)
    run.user_edited_fields = ["background"]
    db.commit()

    class MixedRefine(FakeProvider):
        def refine_idea_with_evidence(self, request):
            bg_id = str(uuid.uuid4())
            ch_id = str(request.evidence[0].evidence_id)
            return EvidenceRefinementResult(
                draft={
                    "background": "LLM이 바꾸려고 한 내용",
                    "challenges": "Evidence 기반 보완",
                },
                evidence_links={"background": [bg_id], "challenges": [ch_id]},
                research_summary="검색 요약",
            )

    assert _run_research_worker_once(
        db,
        session_factory,
        run_id,
        provider=MixedRefine(),
        search_provider=FakeSearchProvider(),
    )

    db.expire_all()
    run = db.get(WebResearchRun, run_id)
    session = db.get(IdeaAiSession, session_id)
    assert run.status == WebResearchRunStatus.READY.value
    assert session.draft_payload["background"] == "배경은 유지 테스트"
    assert session.draft_payload["challenges"] == "Evidence 기반 보완"
    assert session.field_provenance["background"]["source"] == FieldProvenanceSource.USER_EDIT.value
    assert session.field_provenance["challenges"]["source"] == FieldProvenanceSource.WEB_EVIDENCE.value

    evidence = db.scalars(
        select(WebEvidence).where(WebEvidence.research_run_id == run_id)
    ).all()
    assert len(evidence) >= 1
    for row in evidence:
        assert "background" not in (row.related_fields or [])


def test_refine_only_user_edited_fields_returns_ready_without_draft_change(
    client: TestClient,
    db: Session,
    session_factory,
) -> None:
    from app.llm.research_schemas import EvidenceRefinementResult

    owner, pw = _user(db)
    ws = _team(db, owner)
    session_id = _ready_session(client, db, session_factory, ws, owner, pw)
    session = db.get(IdeaAiSession, session_id)
    original_draft = dict(session.draft_payload or {"title": "AI Draft", "background": "A"})
    original_prov = dict(session.field_provenance or {})
    db.commit()

    _login(client, owner.email, pw)
    run_id = _preview_and_approve(
        client,
        ws,
        session_id,
        draft=original_draft,
    )
    run = db.get(WebResearchRun, run_id)
    run.user_edited_fields = ["background"]
    db.commit()

    class OnlyProtected(FakeProvider):
        def refine_idea_with_evidence(self, request):
            ev_id = str(request.evidence[0].evidence_id)
            return EvidenceRefinementResult(
                draft={"background": "LLM only"},
                evidence_links={"background": [ev_id]},
                research_summary="요약만 있음",
            )

    assert _run_research_worker_once(
        db,
        session_factory,
        run_id,
        provider=OnlyProtected(),
        search_provider=FakeSearchProvider(),
    )

    db.expire_all()
    run = db.get(WebResearchRun, run_id)
    session = db.get(IdeaAiSession, session_id)
    assert run.status == WebResearchRunStatus.READY.value
    assert run.research_summary == "요약만 있음"
    assert session.draft_payload == original_draft
    assert session.field_provenance == original_prov
    stored_after = db.scalar(
        select(func.count()).select_from(WebEvidence).where(WebEvidence.research_run_id == run_id)
    )
    assert stored_after >= 1
