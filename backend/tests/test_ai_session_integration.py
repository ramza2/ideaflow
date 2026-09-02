"""PostgreSQL AI Session / Job / Worker / Confirm integration tests."""

from __future__ import annotations

import os
import threading
import uuid
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import reset_engine
from app.llm.exceptions import LlmAuthenticationError, LlmResponseValidationError, LlmTimeoutError
from app.llm.schemas import (
    ClarifyingQuestionRaw,
    FieldProvenanceEntry,
    IdeaDraftPayload,
    IdeaStructuringRequest,
    IdeaStructuringResult,
    parse_structuring_result,
)
from app.main import app
from app.models.ai import AiJob, IdeaAiSession
from app.models.enums import (
    AiJobStatus,
    AiLlmDecision,
    FieldProvenanceSource,
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
    reason="DATABASE_URL not set — skipping AI session integration tests",
)


class FakeProvider:
    provider_name = "fake"
    model_name = "fake-model"
    prompt_version = "v1"

    def __init__(self, results: list[IdeaStructuringResult | Exception] | None = None) -> None:
        self._results = list(results or [])
        self.calls = 0

    def structure_idea(self, request: IdeaStructuringRequest) -> IdeaStructuringResult:
        self.calls += 1
        if not self._results:
            raise RuntimeError("FakeProvider exhausted")
        item = self._results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def refine_idea_with_evidence(self, request):
        from app.llm.research_schemas import EvidenceRefinementResult

        self.calls += 1
        if not self._results:
            raise RuntimeError("FakeProvider exhausted")
        item = self._results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class ParsingFakeProvider:
    provider_name = "parsing_fake"
    model_name = "parsing-fake-model"
    prompt_version = "v1"

    def __init__(self, contents: list[str]) -> None:
        self._contents = list(contents)
        self.calls = 0

    def structure_idea(self, request: IdeaStructuringRequest) -> IdeaStructuringResult:
        self.calls += 1
        if not self._contents:
            raise RuntimeError("ParsingFakeProvider exhausted")
        return parse_structuring_result(self._contents.pop(0))

    def refine_idea_with_evidence(self, request):
        raise NotImplementedError


def _insufficient_ready_json() -> str:
    return json.dumps(
        {
            "decision": "READY_FOR_REVIEW",
            "draft": {
                "title": None,
                "one_line_definition": None,
                "background": None,
                "problem": None,
                "core_concept": None,
                "major_features": None,
                "expected_effect": None,
                "target_users": None,
                "scenarios": None,
                "challenges": None,
                "minimum_validation": None,
                "related_project": None,
                "category_slug": "technology_rd",
                "priority": None,
                "feasibility": None,
                "tags": [],
            },
            "field_provenance": {},
            "clarifying_questions": [],
            "research_recommended": False,
            "research_topics": [],
        }
    )


def _valid_ready_json(title: str = "Retry Success Title") -> str:
    return json.dumps(
        {
            "decision": "READY_FOR_REVIEW",
            "draft": {
                "title": title,
                "one_line_definition": "한 줄",
                "background": None,
                "problem": None,
                "core_concept": None,
                "major_features": None,
                "expected_effect": None,
                "target_users": None,
                "scenarios": None,
                "challenges": None,
                "minimum_validation": None,
                "related_project": None,
                "category_slug": None,
                "priority": "MEDIUM",
                "feasibility": "UNKNOWN",
                "tags": [],
            },
            "field_provenance": {},
            "clarifying_questions": [],
            "research_recommended": False,
            "research_topics": [],
        }
    )


def _ready_result(title: str = "AI Draft Title") -> IdeaStructuringResult:
    return IdeaStructuringResult(
        decision=AiLlmDecision.READY_FOR_REVIEW,
        draft=IdeaDraftPayload(
            title=title,
            one_line_definition="한 줄",
            problem="문제",
            core_concept="개념",
            priority="MEDIUM",
            feasibility="UNKNOWN",
            tags=["AI"],
            category_slug=None,
        ),
        field_provenance={
            "title": FieldProvenanceEntry(
                source=FieldProvenanceSource.LLM_SUMMARY,
                note="요약",
            )
        },
        clarifying_questions=[],
        research_recommended=True,
        research_topics=["유사 SaaS"],
    )


def _clarify_result() -> IdeaStructuringResult:
    return IdeaStructuringResult(
        decision=AiLlmDecision.NEEDS_CLARIFICATION,
        draft=IdeaDraftPayload(title="초안", tags=[]),
        field_provenance={},
        clarifying_questions=[
            ClarifyingQuestionRaw(field="target_users", question="주요 사용자는?"),
        ],
        research_recommended=False,
        research_topics=[],
    )


@pytest.fixture(autouse=True)
def _clean_ai_tables(engine):
    """Prevent leftover QUEUED jobs from earlier tests being claimed."""
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
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "120")
    get_settings.cache_clear()
    reset_engine()
    with TestClient(app) as c:
        yield c
    reset_engine()
    get_settings.cache_clear()


def _user(
    db: Session,
    *,
    email: str | None = None,
    password: str = "password-ok-1",
    system_role: str = SystemRole.USER.value,
) -> tuple[User, str]:
    email = email or f"ai-{uuid.uuid4().hex[:10]}@example.com"
    user = User(
        email=email.lower(),
        name=email.split("@")[0],
        password_hash=hash_password(password),
        status=UserStatus.ACTIVE.value,
        system_role=system_role,
        must_change_password=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, password


def _team(db: Session, owner: User, *, allow_llm: bool = True) -> Workspace:
    ws = Workspace(
        name=f"AI Team {uuid.uuid4().hex[:6]}",
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


def test_create_session_atomic(client: TestClient, db: Session) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions",
        json={"input_text": "회의 중 떠오른 아이디어"},
        headers=_headers(client),
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "PROCESSING"
    session_id = body["id"]

    session = db.get(IdeaAiSession, uuid.UUID(session_id))
    assert session is not None
    assert session.status == IdeaAiSessionStatus.PROCESSING.value
    jobs = list(db.scalars(select(AiJob).where(AiJob.session_id == session.id)))
    assert len(jobs) == 1
    # QUEUED normally; RUNNING only if an external worker claimed it between commit and assert.
    assert jobs[0].status in {AiJobStatus.QUEUED.value, AiJobStatus.RUNNING.value}


def test_allow_llm_false(client: TestClient, db: Session) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner, allow_llm=False)
    _login(client, owner.email, pw)
    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions",
        json={"input_text": "아이디어"},
        headers=_headers(client),
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "WORKSPACE_LLM_DISABLED"
    assert db.scalar(select(func.count()).select_from(AiJob)) is not None  # just query ok
    count = db.scalar(
        select(func.count()).select_from(IdeaAiSession).where(IdeaAiSession.workspace_id == ws.id)
    )
    assert count == 0


def test_session_requester_only_acl(client: TestClient, db: Session) -> None:
    owner, pw_a = _user(db)
    admin_b, pw_b = _user(db, system_role=SystemRole.SYSTEM_ADMIN.value)
    ws = _team(db, owner)
    _add_member(db, ws, admin_b, role=WorkspaceRole.ADMIN.value)

    _login(client, owner.email, pw_a)
    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions",
        json={"input_text": "비공개 세션"},
        headers=_headers(client),
    )
    assert r.status_code == 202
    session_id = r.json()["id"]

    _login(client, admin_b.email, pw_b)
    r2 = client.get(f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}")
    assert r2.status_code == 404
    assert r2.json()["error"]["code"] == "AI_SESSION_NOT_FOUND"


def test_worker_success(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions",
        json={"input_text": "구조화 가능한 아이디어입니다. 문제를 해결하고 핵심 개념이 분명합니다."},
        headers=_headers(client),
    )
    assert r.status_code == 202
    session_id = uuid.UUID(r.json()["id"])

    provider = FakeProvider([_ready_result()])
    assert ai_worker.run_once(session_factory=session_factory, provider=provider, recover=True)

    db.expire_all()
    session = db.get(IdeaAiSession, session_id)
    assert session.status == IdeaAiSessionStatus.READY_FOR_REVIEW.value
    assert session.draft_payload["title"] == "AI Draft Title"
    assert session.field_provenance["title"]["source"] == "LLM_SUMMARY"
    assert session.llm_provider == "fake"
    assert session.llm_model == "fake-model"
    assert session.prompt_version == "v1"
    job = db.scalars(select(AiJob).where(AiJob.session_id == session_id)).first()
    assert job.status == AiJobStatus.SUCCEEDED.value

    g = client.get(f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}")
    assert g.status_code == 200
    assert g.json()["status"] == "READY_FOR_REVIEW"
    assert g.json()["research_recommended"] is True


def test_clarification_flow(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions",
        json={"input_text": "아이디어"},
        headers=_headers(client),
    )
    session_id = uuid.UUID(r.json()["id"])

    provider = FakeProvider([_clarify_result()])
    ai_worker.run_once(session_factory=session_factory, provider=provider)

    g = client.get(f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}")
    assert g.json()["status"] == "NEEDS_CLARIFICATION"
    qid = g.json()["clarifying_questions"][0]["id"]

    r2 = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/clarifications",
        json={"answers": [{"question_id": qid, "answer": "연구개발 담당자"}]},
        headers=_headers(client),
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "PROCESSING"
    jobs = list(db.scalars(select(AiJob).where(AiJob.session_id == session_id)))
    assert len(jobs) == 2
    assert any(j.status == AiJobStatus.QUEUED.value for j in jobs)

    provider2 = FakeProvider([_ready_result("After Clarify")])
    ai_worker.run_once(session_factory=session_factory, provider=provider2)
    db.expire_all()
    session = db.get(IdeaAiSession, session_id)
    assert session.status == IdeaAiSessionStatus.READY_FOR_REVIEW.value


def test_retry_backoff_then_fail(
    db: Session,
    session_factory: sessionmaker,
    client: TestClient,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions",
        json={"input_text": "retry me"},
        headers=_headers(client),
    )
    session_id = uuid.UUID(r.json()["id"])

    # Force max_attempts=2 on the queued job
    job = db.scalars(select(AiJob).where(AiJob.session_id == session_id)).one()
    job.max_attempts = 2
    db.commit()

    provider = FakeProvider([LlmTimeoutError(), LlmTimeoutError()])
    settings = get_settings()

    # attempt 1 → requeue
    ai_worker.run_once(session_factory=session_factory, provider=provider, settings=settings)
    db.expire_all()
    job = db.scalars(select(AiJob).where(AiJob.session_id == session_id)).one()
    assert job.status == AiJobStatus.QUEUED.value
    assert job.attempts == 1
    assert job.available_at > datetime.now(timezone.utc)
    session = db.get(IdeaAiSession, session_id)
    assert session.status == IdeaAiSessionStatus.PROCESSING.value

    # make available now without sleep
    job.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    ai_worker.run_once(session_factory=session_factory, provider=provider, settings=settings)
    db.expire_all()
    job = db.scalars(select(AiJob).where(AiJob.session_id == session_id)).one()
    assert job.status == AiJobStatus.FAILED.value
    session = db.get(IdeaAiSession, session_id)
    assert session.status == IdeaAiSessionStatus.FAILED.value
    assert session.failure_code == "LLM_TIMEOUT"


def test_non_retryable_immediate_fail(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions",
        json={"input_text": "auth fail"},
        headers=_headers(client),
    )
    session_id = uuid.UUID(r.json()["id"])
    provider = FakeProvider([LlmAuthenticationError()])
    ai_worker.run_once(session_factory=session_factory, provider=provider)
    db.expire_all()
    job = db.scalars(select(AiJob).where(AiJob.session_id == session_id)).one()
    assert job.status == AiJobStatus.FAILED.value
    assert job.attempts == 1
    session = db.get(IdeaAiSession, session_id)
    assert session.status == IdeaAiSessionStatus.FAILED.value
    assert session.failure_code == "LLM_AUTH_ERROR"


def test_insufficient_ready_retries_then_succeeds(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions",
        json={"input_text": "insufficient then ok"},
        headers=_headers(client),
    )
    session_id = uuid.UUID(r.json()["id"])

    provider = ParsingFakeProvider(
        [_insufficient_ready_json(), _valid_ready_json("Recovered Title")]
    )
    settings = get_settings()

    ai_worker.run_once(session_factory=session_factory, provider=provider, settings=settings)
    db.expire_all()
    job = db.scalars(select(AiJob).where(AiJob.session_id == session_id)).one()
    assert job.status == AiJobStatus.QUEUED.value
    assert job.attempts == 1
    assert job.last_error_code == "LLM_RESPONSE_INVALID"
    session = db.get(IdeaAiSession, session_id)
    assert session.status == IdeaAiSessionStatus.PROCESSING.value
    assert session.draft_payload is None

    job.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    ai_worker.run_once(session_factory=session_factory, provider=provider, settings=settings)
    db.expire_all()
    job = db.scalars(select(AiJob).where(AiJob.session_id == session_id)).one()
    assert job.status == AiJobStatus.SUCCEEDED.value
    session = db.get(IdeaAiSession, session_id)
    assert session.status == IdeaAiSessionStatus.READY_FOR_REVIEW.value
    assert session.draft_payload["title"] == "Recovered Title"
    assert provider.calls == 2


def test_insufficient_ready_max_attempts_generic_message(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions",
        json={"input_text": "always insufficient"},
        headers=_headers(client),
    )
    session_id = uuid.UUID(r.json()["id"])

    job = db.scalars(select(AiJob).where(AiJob.session_id == session_id)).one()
    job.max_attempts = 2
    db.commit()

    provider = ParsingFakeProvider([_insufficient_ready_json(), _insufficient_ready_json()])
    settings = get_settings()

    ai_worker.run_once(session_factory=session_factory, provider=provider, settings=settings)
    db.expire_all()
    job = db.scalars(select(AiJob).where(AiJob.session_id == session_id)).one()
    assert job.status == AiJobStatus.QUEUED.value
    assert job.attempts == 1

    job.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    ai_worker.run_once(session_factory=session_factory, provider=provider, settings=settings)
    db.expire_all()
    job = db.scalars(select(AiJob).where(AiJob.session_id == session_id)).one()
    assert job.status == AiJobStatus.FAILED.value
    session = db.get(IdeaAiSession, session_id)
    assert session.status == IdeaAiSessionStatus.FAILED.value
    assert session.failure_code == "LLM_RESPONSE_INVALID"
    assert session.failure_message == LlmResponseValidationError.safe_message
    assert "title" not in (session.failure_message or "").lower()


def test_stale_lease_recovery(db: Session, session_factory: sessionmaker, client: TestClient) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions",
        json={"input_text": "stale"},
        headers=_headers(client),
    )
    session_id = uuid.UUID(r.json()["id"])
    job = db.scalars(select(AiJob).where(AiJob.session_id == session_id)).one()
    job.status = AiJobStatus.RUNNING.value
    job.attempts = 1
    job.max_attempts = 3
    job.lease_until = datetime.now(timezone.utc) - timedelta(seconds=10)
    job.locked_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    job.worker_id = "dead-worker"
    db.commit()

    recovered = ai_worker.recover_stale_jobs(db)
    assert recovered == 1
    db.expire_all()
    job = db.get(AiJob, job.id)
    assert job.status == AiJobStatus.QUEUED.value
    assert job.worker_id is None

    # max attempts path
    job.status = AiJobStatus.RUNNING.value
    job.attempts = 3
    job.max_attempts = 3
    job.lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    ai_worker.recover_stale_jobs(db)
    db.expire_all()
    job = db.get(AiJob, job.id)
    assert job.status == AiJobStatus.FAILED.value
    session = db.get(IdeaAiSession, session_id)
    assert session.status == IdeaAiSessionStatus.FAILED.value


def test_skip_locked_claim(db: Session, session_factory: sessionmaker, client: TestClient) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions",
        json={"input_text": "skip locked"},
        headers=_headers(client),
    )
    session_id = uuid.UUID(r.json()["id"])
    settings = get_settings()

    results: list[uuid.UUID | None] = []

    def claim() -> None:
        s = session_factory()
        try:
            job = ai_worker.claim_next_job(s, worker_id=f"w-{uuid.uuid4().hex[:6]}", settings=settings)
            results.append(job.id if job else None)
        finally:
            s.close()

    t1 = threading.Thread(target=claim)
    t2 = threading.Thread(target=claim)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    claimed = [x for x in results if x is not None]
    assert len(claimed) == 1
    assert claimed[0] == db.scalars(select(AiJob).where(AiJob.session_id == session_id)).one().id


def test_stale_worker_result_discarded_after_reclaim(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    """Worker A loses lease; Worker B reclaims; A's late persistence must not overwrite."""
    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions",
        json={"input_text": "lease fencing"},
        headers=_headers(client),
    )
    session_id = uuid.UUID(r.json()["id"])
    settings = get_settings()

    db_a = session_factory()
    job_a = ai_worker.claim_next_job(db_a, worker_id="worker-A", settings=settings)
    assert job_a is not None
    job_id = job_a.id
    db_a.close()

    # Expire lease while A is "still calling the LLM"
    job = db.get(AiJob, job_id)
    job.lease_until = datetime.now(timezone.utc) - timedelta(seconds=5)
    db.commit()

    recovered = ai_worker.recover_stale_jobs(session_factory())
    assert recovered == 1

    db_b = session_factory()
    job_b = ai_worker.claim_next_job(db_b, worker_id="worker-B", settings=settings)
    assert job_b is not None
    assert job_b.id == job_id
    assert job_b.worker_id == "worker-B"
    db_b.close()

    # Late persistence from A with a distinct draft title must be ignored.
    class DelayedProvider:
        provider_name = "fake-a"
        model_name = "a-model"
        prompt_version = "v1"

        def structure_idea(self, request: IdeaStructuringRequest) -> IdeaStructuringResult:
            return _ready_result("FromWorkerA")

    db_persist = session_factory()
    try:
        ai_worker.process_claimed_job(
            db_persist,
            job_id=job_id,
            worker_id="worker-A",
            provider=DelayedProvider(),
            settings=settings,
        )
    finally:
        db_persist.close()

    db.expire_all()
    job = db.get(AiJob, job_id)
    assert job.worker_id == "worker-B"
    assert job.status == AiJobStatus.RUNNING.value
    session = db.get(IdeaAiSession, session_id)
    assert session.status == IdeaAiSessionStatus.PROCESSING.value
    assert session.draft_payload is None

    # B can still succeed with its own result.
    db_b2 = session_factory()
    try:
        ai_worker.process_claimed_job(
            db_b2,
            job_id=job_id,
            worker_id="worker-B",
            provider=FakeProvider([_ready_result("FromWorkerB")]),
            settings=settings,
        )
    finally:
        db_b2.close()
    db.expire_all()
    job = db.get(AiJob, job_id)
    assert job.status == AiJobStatus.SUCCEEDED.value
    session = db.get(IdeaAiSession, session_id)
    assert session.status == IdeaAiSessionStatus.READY_FOR_REVIEW.value
    assert session.draft_payload["title"] == "FromWorkerB"


def test_confirm_and_idempotency(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions",
        json={"input_text": "원본 입력 텍스트입니다."},
        headers=_headers(client),
    )
    session_id = r.json()["id"]
    ai_worker.run_once(
        session_factory=session_factory,
        provider=FakeProvider([_ready_result("A")]),
    )

    confirm_body = {
        "title": "B",
        "one_line_definition": "수정된 정의",
        "problem": "문제",
        "core_concept": "개념",
        "priority": "MEDIUM",
        "feasibility": "UNKNOWN",
        "visibility": "PRIVATE",
        "tags": ["AI"],
    }
    c1 = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/confirm",
        json=confirm_body,
        headers=_headers(client),
    )
    assert c1.status_code == 200, c1.text
    assert c1.json()["created"] is True
    idea_id = c1.json()["idea"]["id"]
    assert c1.json()["idea"]["title"] == "B"
    assert c1.json()["idea"]["original_text"] == "원본 입력 텍스트입니다."
    assert c1.json()["idea"]["visibility"] == "PRIVATE"
    assert c1.json()["idea"]["idea_code"].startswith("IF-")

    db.expire_all()
    session = db.get(IdeaAiSession, uuid.UUID(session_id))
    assert session.status == IdeaAiSessionStatus.CONFIRMED.value
    assert session.draft_payload["title"] == "A"
    assert session.confirmed_payload["title"] == "B"
    assert session.field_provenance["title"]["final_source"] == "USER_EDIT"

    c2 = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/confirm",
        json={**confirm_body, "title": "C"},
        headers=_headers(client),
    )
    assert c2.status_code == 200
    assert c2.json()["created"] is False
    assert c2.json()["idea"]["id"] == idea_id
    assert c2.json()["idea"]["title"] == "B"  # not overwritten

    count = db.scalar(
        select(func.count()).select_from(Idea).where(
            Idea.workspace_id == ws.id,
            Idea.deleted_at.is_(None),
        )
    )
    assert count == 1


def test_concurrent_confirm(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
    engine,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions",
        json={"input_text": "동시 confirm"},
        headers=_headers(client),
    )
    session_id = r.json()["id"]
    ai_worker.run_once(
        session_factory=session_factory,
        provider=FakeProvider([_ready_result()]),
    )

    confirm_body = {
        "title": "Concurrent",
        "priority": "MEDIUM",
        "feasibility": "UNKNOWN",
        "visibility": "PRIVATE",
        "tags": [],
    }

    # Use separate TestClients sharing cookies is hard; call service layer with two DB sessions.
    from app.schemas.ai import AiSessionConfirmRequest
    from app.services import ai_session as ai_session_service

    results: list[Any] = []
    errors: list[Exception] = []
    barrier = threading.Barrier(2)

    def worker() -> None:
        s = session_factory()
        try:
            barrier.wait(timeout=5)
            user = s.get(User, owner.id)
            workspace = s.get(Workspace, ws.id)
            out = ai_session_service.confirm_ai_session(
                s,
                workspace=workspace,
                user=user,
                session_id=uuid.UUID(session_id),
                payload=AiSessionConfirmRequest.model_validate(confirm_body),
            )
            s.commit()
            results.append(out)
        except Exception as exc:  # noqa: BLE001
            s.rollback()
            errors.append(exc)
        finally:
            s.close()

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors, errors
    assert len(results) == 2
    ids = {r.idea.id for r in results}
    assert len(ids) == 1
    created_flags = sorted(r.created for r in results)
    assert created_flags == [False, True] or created_flags == [True, False]

    count = db.scalar(
        select(func.count()).select_from(Idea).where(
            Idea.workspace_id == ws.id,
            Idea.deleted_at.is_(None),
            Idea.title == "Concurrent",
        )
    )
    assert count == 1


def test_manual_retry_endpoint(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)
    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions",
        json={"input_text": "manual retry"},
        headers=_headers(client),
    )
    session_id = uuid.UUID(r.json()["id"])
    ai_worker.run_once(
        session_factory=session_factory,
        provider=FakeProvider([LlmAuthenticationError()]),
    )
    r2 = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/retry",
        headers=_headers(client),
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "PROCESSING"
    jobs = list(db.scalars(select(AiJob).where(AiJob.session_id == session_id)))
    assert len(jobs) == 2
    assert any(j.status == AiJobStatus.QUEUED.value for j in jobs)
