"""PostgreSQL AI Session review draft save & regenerate integration tests (Step 16)."""

from __future__ import annotations

import os
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
from app.models.idea import Idea
from app.models.research import WebEvidence, WebResearchRun
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.services import ai_worker, web_research as web_research_service
from app.services.workspace import seed_workspace_defaults

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — skipping AI review draft integration tests",
)


class FakeProvider:
    provider_name = "fake"
    model_name = "fake-model"
    prompt_version = "v1"

    def __init__(self, results: list[IdeaStructuringResult] | None = None) -> None:
        self._results = list(results or [])
        self.calls = 0

    def structure_idea(self, request):
        self.calls += 1
        if not self._results:
            raise RuntimeError("FakeProvider exhausted")
        return self._results.pop(0)

    def refine_idea_with_evidence(self, request):
        raise NotImplementedError


def _ready_result(title: str = "AI Draft Title") -> IdeaStructuringResult:
    return IdeaStructuringResult(
        decision=AiLlmDecision.READY_FOR_REVIEW,
        draft=IdeaDraftPayload(
            title=title,
            one_line_definition="한 줄",
            background="배경",
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
            ),
            "background": FieldProvenanceEntry(
                source=FieldProvenanceSource.LLM_SUMMARY,
                note="배경 요약",
            ),
        },
        clarifying_questions=[],
        research_recommended=True,
        research_topics=["유사 SaaS"],
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
    email = email or f"draft-{uuid.uuid4().hex[:10]}@example.com"
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
        name=f"Draft Team {uuid.uuid4().hex[:6]}",
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


def _ready_session(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
    ws: Workspace,
    owner: User,
    pw: str,
    *,
    input_text: str = "아이디어 본문입니다.",
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
    pytest.fail("session not ready")


def _draft_payload(**overrides: Any) -> dict[str, Any]:
    base = {
        "draft": {
            "title": "수정 제목",
            "one_line_definition": "한 줄",
            "background": "수정 배경",
            "problem": "문제",
            "core_concept": "개념",
            "major_features": None,
            "expected_effect": None,
            "target_users": None,
            "scenarios": None,
            "challenges": None,
            "minimum_validation": None,
            "related_project": None,
            "category_slug": None,
            "priority": "HIGH",
            "feasibility": "LOW",
            "tags": ["tag1"],
        },
        "review_state": {
            "category_id": None,
            "stage_id": None,
            "visibility": "WORKSPACE",
            "assignee_id": None,
            "next_review_date": None,
            "shares": [],
            "edited_fields": ["title", "background", "priority", "feasibility", "tags"],
        },
    }
    if overrides:
        base["draft"].update(overrides.get("draft", {}))
        base["review_state"].update(overrides.get("review_state", {}))
    return base


def _save_draft(
    client: TestClient,
    ws: Workspace,
    session_id: uuid.UUID,
    payload: dict[str, Any] | None = None,
) -> Any:
    return client.put(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/review-draft",
        json=payload or _draft_payload(),
        headers=_headers(client),
    )


def test_review_draft_save_and_reload(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    session_id = _ready_session(client, db, session_factory, ws, owner, pw)

    r = _save_draft(client, ws, session_id)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["draft"]["title"] == "수정 제목"
    assert body["draft"]["background"] == "수정 배경"
    assert body["draft"]["priority"] == "HIGH"
    assert body["review_state"]["visibility"] == "WORKSPACE"
    assert body["review_state"]["edited_fields"] == [
        "title",
        "background",
        "priority",
        "feasibility",
        "tags",
    ]
    assert body["review_saved_at"] is not None

    g = client.get(f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}")
    assert g.status_code == 200
    assert g.json()["draft"]["title"] == "수정 제목"
    assert g.json()["review_state"]["edited_fields"] == body["review_state"]["edited_fields"]


def test_review_draft_empty_title_allowed(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    session_id = _ready_session(client, db, session_factory, ws, owner, pw)

    payload = _draft_payload()
    payload["draft"]["title"] = ""
    r = _save_draft(client, ws, session_id, payload)
    assert r.status_code == 200, r.text
    assert r.json()["draft"]["title"] == ""


def test_review_draft_user_edit_provenance(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    session_id = _ready_session(client, db, session_factory, ws, owner, pw)

    r = _save_draft(client, ws, session_id)
    assert r.status_code == 200, r.text
    prov = r.json()["field_provenance"]
    assert prov["title"]["source"] == "USER_EDIT"
    assert prov["title"]["final_source"] == "USER_EDIT"
    assert prov["title"]["original_source"] == "LLM_SUMMARY"
    assert prov["priority"]["source"] == "USER_EDIT"


def test_review_draft_preserves_web_evidence_provenance(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    session_id = _ready_session(client, db, session_factory, ws, owner, pw)

    session = db.get(IdeaAiSession, session_id)
    session.field_provenance = {
        "background": {
            "source": "WEB_EVIDENCE",
            "original_source": "LLM_SUMMARY",
            "final_source": "WEB_EVIDENCE",
            "evidence_ids": [str(uuid.uuid4())],
            "note": "evidence",
        }
    }
    db.commit()

    payload = _draft_payload()
    payload["review_state"]["edited_fields"] = ["background"]
    r = _save_draft(client, ws, session_id, payload)
    assert r.status_code == 200, r.text
    prov = r.json()["field_provenance"]["background"]
    assert prov["source"] == "USER_EDIT"
    assert prov["original_source"] == "LLM_SUMMARY"
    assert prov["evidence_ids"]


def test_review_draft_repeated_user_edit_preserves_original_source(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    session_id = _ready_session(client, db, session_factory, ws, owner, pw)

    session = db.get(IdeaAiSession, session_id)
    session.field_provenance = {
        "background": {
            "source": "WEB_EVIDENCE",
            "original_source": "LLM_SUMMARY",
            "final_source": "WEB_EVIDENCE",
            "evidence_ids": [str(uuid.uuid4())],
            "note": "evidence",
        }
    }
    db.commit()

    payload = _draft_payload()
    payload["review_state"]["edited_fields"] = ["background"]
    r1 = _save_draft(client, ws, session_id, payload)
    assert r1.status_code == 200, r1.text
    prov1 = r1.json()["field_provenance"]["background"]
    assert prov1["source"] == "USER_EDIT"
    assert prov1["original_source"] == "LLM_SUMMARY"

    payload["draft"]["background"] = "다시 수정한 배경"
    r2 = _save_draft(client, ws, session_id, payload)
    assert r2.status_code == 200, r2.text
    prov2 = r2.json()["field_provenance"]["background"]
    assert prov2["source"] == "USER_EDIT"
    assert prov2["original_source"] == "LLM_SUMMARY"
    assert prov2["evidence_ids"] == prov1["evidence_ids"]


def test_review_draft_requester_only_acl(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw_a = _user(db)
    other, pw_b = _user(db)
    admin, pw_admin = _user(db, system_role=SystemRole.SYSTEM_ADMIN.value)
    ws = _team(db, owner)
    _add_member(db, ws, other, role=WorkspaceRole.MEMBER.value)
    _add_member(db, ws, admin, role=WorkspaceRole.ADMIN.value)

    session_id = _ready_session(client, db, session_factory, ws, owner, pw_a)

    _login(client, other.email, pw_b)
    r = _save_draft(client, ws, session_id)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "AI_SESSION_NOT_FOUND"

    _login(client, admin.email, pw_admin)
    r2 = _save_draft(client, ws, session_id)
    assert r2.status_code == 404


def test_review_draft_invalid_status_409(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    session_id = _ready_session(client, db, session_factory, ws, owner, pw)

    session = db.get(IdeaAiSession, session_id)
    session.status = IdeaAiSessionStatus.PROCESSING.value
    db.commit()

    r = _save_draft(client, ws, session_id)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "AI_SESSION_INVALID_STATE"


def test_review_draft_csrf_required(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    session_id = _ready_session(client, db, session_factory, ws, owner, pw)

    r = client.put(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/review-draft",
        json=_draft_payload(),
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "CSRF_INVALID"


def test_review_draft_does_not_create_idea(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    session_id = _ready_session(client, db, session_factory, ws, owner, pw)

    r = _save_draft(client, ws, session_id)
    assert r.status_code == 200

    count = db.scalar(
        select(func.count()).select_from(Idea).where(Idea.workspace_id == ws.id)
    )
    assert count == 0
    session = db.get(IdeaAiSession, session_id)
    assert session.status == IdeaAiSessionStatus.READY_FOR_REVIEW.value
    assert session.result_idea_id is None


def test_review_draft_works_when_llm_disabled(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    admin, admin_pw = _user(db, system_role=SystemRole.SYSTEM_ADMIN.value)
    owner, owner_pw = _user(db)
    ws = _team(db, owner)
    session_id = _ready_session(client, db, session_factory, ws, owner, owner_pw)

    _login(client, admin.email, admin_pw)
    client.patch(
        "/api/v1/admin/system-settings",
        json={"global_llm_enabled": False},
        headers=_headers(client),
    )

    _login(client, owner.email, owner_pw)
    r = _save_draft(client, ws, session_id)
    assert r.status_code == 200, r.text

    _login(client, admin.email, admin_pw)
    client.patch(
        "/api/v1/admin/system-settings",
        json={"global_llm_enabled": True},
        headers=_headers(client),
    )


def test_review_draft_does_not_change_web_research_rows(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    session_id = _ready_session(client, db, session_factory, ws, owner, pw)

    run = WebResearchRun(
        session_id=session_id,
        requester_id=owner.id,
        status=WebResearchRunStatus.READY.value,
        queries_to_send=["q1"],
        base_draft_payload={"title": "AI Draft Title"},
    )
    db.add(run)
    db.flush()
    db.add(
        WebEvidence(
            research_run_id=run.id,
            query="q1",
            title="Evidence",
            url="https://example.com",
            url_hash=web_research_service.url_hash("https://example.com"),
            snippet="snippet",
            rank=0,
            provider="fake_search",
        )
    )
    db.commit()

    before_runs = db.scalar(select(func.count()).select_from(WebResearchRun))
    before_evidence = db.scalar(select(func.count()).select_from(WebEvidence))

    r = _save_draft(client, ws, session_id)
    assert r.status_code == 200

    assert db.scalar(select(func.count()).select_from(WebResearchRun)) == before_runs
    assert db.scalar(select(func.count()).select_from(WebEvidence)) == before_evidence


def test_confirm_rejects_empty_title_after_temp_save(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    session_id = _ready_session(client, db, session_factory, ws, owner, pw)

    payload = _draft_payload()
    payload["draft"]["title"] = ""
    r = _save_draft(client, ws, session_id, payload)
    assert r.status_code == 200

    c = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/confirm",
        json={
            "title": "",
            "priority": "MEDIUM",
            "feasibility": "UNKNOWN",
            "visibility": "PRIVATE",
            "tags": [],
        },
        headers=_headers(client),
    )
    assert c.status_code == 422


def test_confirm_after_temp_save(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    session_id = _ready_session(client, db, session_factory, ws, owner, pw)

    r = _save_draft(client, ws, session_id)
    assert r.status_code == 200

    c = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/confirm",
        json={
            "title": "최종 등록",
            "background": "수정 배경",
            "priority": "HIGH",
            "feasibility": "LOW",
            "visibility": "WORKSPACE",
            "tags": ["tag1"],
        },
        headers=_headers(client),
    )
    assert c.status_code == 200, c.text
    assert c.json()["created"] is True
    assert c.json()["idea"]["title"] == "최종 등록"


def test_review_draft_blocked_after_confirm(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    session_id = _ready_session(client, db, session_factory, ws, owner, pw)

    client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/confirm",
        json={
            "title": "등록됨",
            "priority": "MEDIUM",
            "feasibility": "UNKNOWN",
            "visibility": "PRIVATE",
            "tags": [],
        },
        headers=_headers(client),
    )

    r = _save_draft(client, ws, session_id)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "AI_SESSION_INVALID_STATE"


def test_regenerate_creates_new_session(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    session_id = _ready_session(client, db, session_factory, ws, owner, pw)

    _save_draft(client, ws, session_id)

    old = db.get(IdeaAiSession, session_id)
    old_snapshot = {
        "status": old.status,
        "draft": dict(old.draft_payload or {}),
        "review_state": dict(old.review_state or {}),
        "review_saved_at": old.review_saved_at,
        "input_text": old.input_text,
    }

    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/regenerate",
        headers=_headers(client),
    )
    assert r.status_code == 200, r.text
    new_id = uuid.UUID(r.json()["session"]["id"])
    assert new_id != session_id
    assert r.json()["session"]["status"] == "PROCESSING"

    db.expire_all()
    old_after = db.get(IdeaAiSession, session_id)
    assert old_after.status == old_snapshot["status"]
    assert old_after.draft_payload == old_snapshot["draft"]
    assert old_after.review_state == old_snapshot["review_state"]
    assert old_after.review_saved_at == old_snapshot["review_saved_at"]
    assert old_after.input_text == old_snapshot["input_text"]

    new_session = db.get(IdeaAiSession, new_id)
    assert new_session.input_text == old_snapshot["input_text"]
    assert new_session.draft_payload is None
    assert new_session.review_state is None
    assert new_session.review_saved_at is None
    assert new_session.result_idea_id is None
    assert new_session.requester_id == owner.id

    jobs = list(
        db.scalars(
            select(AiJob).where(
                AiJob.session_id == new_id,
                AiJob.job_type == AiJobType.STRUCTURE_IDEA.value,
            )
        )
    )
    assert len(jobs) == 1
    assert jobs[0].status == AiJobStatus.QUEUED.value

    research_count = db.scalar(
        select(func.count()).select_from(WebResearchRun).where(
            WebResearchRun.session_id == new_id
        )
    )
    assert research_count == 0


def test_regenerate_copies_clarification_context(
    client: TestClient,
    db: Session,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    _login(client, owner.email, pw)

    session = IdeaAiSession(
        workspace_id=ws.id,
        requester_id=owner.id,
        purpose="CREATE",
        status=IdeaAiSessionStatus.READY_FOR_REVIEW.value,
        input_text="원문 텍스트",
        clarifying_questions=[{"id": "q1", "field": "target_users", "question": "누구?"}],
        clarification_answers=[{"question_id": "q1", "answer": "개발자"}],
        draft_payload={"title": "초안"},
        field_provenance={},
        research_recommended=False,
        research_topics=[],
    )
    db.add(session)
    db.commit()

    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session.id}/regenerate",
        headers=_headers(client),
    )
    assert r.status_code == 200, r.text
    new_session = db.get(IdeaAiSession, uuid.UUID(r.json()["session"]["id"]))
    assert new_session.clarifying_questions == session.clarifying_questions
    assert new_session.clarification_answers == session.clarification_answers


def test_regenerate_llm_disabled(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner, allow_llm=True)
    session_id = _ready_session(client, db, session_factory, ws, owner, pw)

    ws.allow_llm = False
    db.commit()

    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/regenerate",
        headers=_headers(client),
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "WORKSPACE_LLM_DISABLED"


def test_regenerate_active_research_blocked(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    session_id = _ready_session(client, db, session_factory, ws, owner, pw)

    db.add(
        WebResearchRun(
            session_id=session_id,
            requester_id=owner.id,
            status=WebResearchRunStatus.SEARCHING.value,
            queries_to_send=["q"],
            base_draft_payload={"title": "AI Draft Title"},
        )
    )
    db.commit()

    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/regenerate",
        headers=_headers(client),
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "AI_REGENERATE_RESEARCH_ACTIVE"


def test_regenerate_requester_only(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw_a = _user(db)
    other, pw_b = _user(db)
    ws = _team(db, owner)
    _add_member(db, ws, other, role=WorkspaceRole.ADMIN.value)
    session_id = _ready_session(client, db, session_factory, ws, owner, pw_a)

    _login(client, other.email, pw_b)
    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/regenerate",
        headers=_headers(client),
    )
    assert r.status_code == 404


def test_regenerate_worker_enters_ready_flow(
    client: TestClient,
    db: Session,
    session_factory: sessionmaker,
) -> None:
    owner, pw = _user(db)
    ws = _team(db, owner)
    session_id = _ready_session(client, db, session_factory, ws, owner, pw)

    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/regenerate",
        headers=_headers(client),
    )
    new_id = uuid.UUID(r.json()["session"]["id"])

    provider = FakeProvider([_ready_result("Regenerated Title")])
    assert ai_worker.run_once(session_factory=session_factory, provider=provider)

    db.expire_all()
    new_session = db.get(IdeaAiSession, new_id)
    assert new_session.status == IdeaAiSessionStatus.READY_FOR_REVIEW.value
    assert new_session.draft_payload["title"] == "Regenerated Title"
