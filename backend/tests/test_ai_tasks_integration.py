"""Step 19 AI task aggregation API integration tests."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import reset_engine
from app.main import app
from app.models.ai import IdeaAiSession
from app.models.enums import (
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
from app.models.research import WebResearchRun
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.services.workspace import seed_workspace_defaults

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — skipping AI tasks integration tests",
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
def client(engine, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv("AI_WORKER_ENABLED", "false")
    get_settings.cache_clear()
    reset_engine()
    with TestClient(app) as c:
        yield c
    reset_engine()
    get_settings.cache_clear()


def _user(db: Session, *, password: str = "password-ok-1") -> tuple[User, str]:
    email = f"aitasks-{uuid.uuid4().hex[:10]}@example.com"
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


def _team(db: Session, owner: User) -> Workspace:
    ws = Workspace(
        name=f"AI Tasks {uuid.uuid4().hex[:6]}",
        type=WorkspaceType.TEAM.value,
        owner_id=owner.id,
        allow_llm=True,
        allow_web_search=True,
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


def _add_member(db: Session, workspace: Workspace, user: User) -> None:
    db.add(
        WorkspaceMember(
            workspace_id=workspace.id,
            user_id=user.id,
            role=WorkspaceRole.MEMBER.value,
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
        "title": "고객 VOC 분석",
        "one_line_definition": "한 줄 정의",
        "background": "배경",
        "problem": "문제",
        "core_concept": "개념",
        "expected_effect": "효과",
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


def test_list_ai_tasks_empty(client: TestClient, db: Session) -> None:
    user, password = _user(db)
    ws = _team(db, user)
    _login(client, user.email, password)

    r = client.get(f"/api/v1/workspaces/{ws.id}/ai-tasks")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["items"] == []
    assert body["active_count"] == 0


def test_list_ai_tasks_aggregates_create_refine_research(
    client: TestClient, db: Session
) -> None:
    user, password = _user(db)
    other, other_pw = _user(db)
    ws = _team(db, user)
    _add_member(db, ws, other)
    _login(client, user.email, password)
    idea = _create_idea(client, ws)

    now = datetime.now(timezone.utc)

    create_session = IdeaAiSession(
        workspace_id=ws.id,
        requester_id=user.id,
        purpose=IdeaAiSessionPurpose.CREATE.value,
        status=IdeaAiSessionStatus.PROCESSING.value,
        input_text="신규 아이디어 초안을 만들어 주세요",
        draft_payload={"title": "회의록 자동화"},
    )
    refine_session = IdeaAiSession(
        workspace_id=ws.id,
        requester_id=user.id,
        purpose=IdeaAiSessionPurpose.REFINE.value,
        status=IdeaAiSessionStatus.READY_FOR_REVIEW.value,
        input_text="보완",
        source_idea_id=uuid.UUID(idea["id"]),
        source_idea_updated_at=now,
        source_idea_snapshot={"title": idea["title"]},
        draft_payload={"title": idea["title"]},
        ready_at=now,
    )
    research_session = IdeaAiSession(
        workspace_id=ws.id,
        requester_id=user.id,
        purpose=IdeaAiSessionPurpose.RESEARCH.value,
        status=IdeaAiSessionStatus.READY_FOR_REVIEW.value,
        input_text="다시 조사",
        source_idea_id=uuid.UUID(idea["id"]),
        source_idea_updated_at=now,
        source_idea_snapshot={"title": idea["title"]},
    )
    # Other user's active session must not leak.
    foreign_session = IdeaAiSession(
        workspace_id=ws.id,
        requester_id=other.id,
        purpose=IdeaAiSessionPurpose.CREATE.value,
        status=IdeaAiSessionStatus.PROCESSING.value,
        input_text="다른 사용자 작업",
    )
    # Stale finished CREATE should be excluded.
    stale_session = IdeaAiSession(
        workspace_id=ws.id,
        requester_id=user.id,
        purpose=IdeaAiSessionPurpose.CREATE.value,
        status=IdeaAiSessionStatus.READY_FOR_REVIEW.value,
        input_text="오래된 완료",
        ready_at=now - timedelta(hours=2),
    )
    db.add_all(
        [create_session, refine_session, research_session, foreign_session, stale_session]
    )
    db.flush()

    active_run = WebResearchRun(
        session_id=research_session.id,
        requester_id=user.id,
        status=WebResearchRunStatus.SEARCHING.value,
        queries_to_send=["VOC 분석"],
        approved_at=now,
        started_at=now,
    )
    ready_run = WebResearchRun(
        session_id=research_session.id,
        requester_id=user.id,
        status=WebResearchRunStatus.READY.value,
        queries_to_send=["이전 조사"],
        approved_at=now - timedelta(minutes=5),
        started_at=now - timedelta(minutes=5),
        completed_at=now - timedelta(minutes=1),
        result_count=2,
    )
    awaiting_run = WebResearchRun(
        session_id=research_session.id,
        requester_id=user.id,
        status=WebResearchRunStatus.AWAITING_APPROVAL.value,
        queries_to_send=["승인 대기"],
    )
    db.add_all([active_run, ready_run, awaiting_run])
    db.commit()

    # Bypass ORM onupdate so this finished session falls outside the recent window.
    db.execute(
        text(
            "UPDATE idea_ai_sessions SET updated_at = :ts, ready_at = :ts WHERE id = :id"
        ),
        {"ts": now - timedelta(hours=2), "id": stale_session.id},
    )
    db.commit()

    r = client.get(f"/api/v1/workspaces/{ws.id}/ai-tasks")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["active_count"] == 2

    by_id = {item["id"]: item for item in body["items"]}
    assert f"session:{create_session.id}" in by_id
    assert f"session:{refine_session.id}" in by_id
    assert f"research:{active_run.id}" in by_id
    assert f"research:{ready_run.id}" in by_id
    assert f"session:{stale_session.id}" not in by_id
    assert f"session:{foreign_session.id}" not in by_id
    assert f"research:{awaiting_run.id}" not in by_id

    create_item = by_id[f"session:{create_session.id}"]
    assert create_item["type"] == "CREATE"
    assert create_item["status"] == "PROCESSING"
    assert create_item["is_active"] is True
    assert create_item["idea_title"] == "회의록 자동화"

    refine_item = by_id[f"session:{refine_session.id}"]
    assert refine_item["type"] == "REFINE"
    assert refine_item["is_active"] is False
    assert refine_item["idea_id"] == idea["id"]
    assert refine_item["idea_title"] == "고객 VOC 분석"

    searching = by_id[f"research:{active_run.id}"]
    assert searching["type"] == "RESEARCH"
    assert searching["status"] == "SEARCHING"
    assert searching["is_active"] is True
    assert searching["idea_title"] == "고객 VOC 분석"

    # Isolation: other user sees only their own task.
    _login(client, other.email, other_pw)
    r2 = client.get(f"/api/v1/workspaces/{ws.id}/ai-tasks")
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2["active_count"] == 1
    assert body2["items"][0]["id"] == f"session:{foreign_session.id}"


def test_list_ai_tasks_failed_includes_safe_message(
    client: TestClient, db: Session
) -> None:
    user, password = _user(db)
    ws = _team(db, user)
    _login(client, user.email, password)

    session = IdeaAiSession(
        workspace_id=ws.id,
        requester_id=user.id,
        purpose=IdeaAiSessionPurpose.CREATE.value,
        status=IdeaAiSessionStatus.FAILED.value,
        input_text="실패 케이스",
        failure_code="LLM_TIMEOUT",
        failure_message="요청 시간이 초과되었습니다.",
    )
    db.add(session)
    db.commit()

    r = client.get(f"/api/v1/workspaces/{ws.id}/ai-tasks")
    assert r.status_code == 200, r.text
    item = r.json()["items"][0]
    assert item["status"] == "FAILED"
    assert item["is_active"] is False
    assert item["failure_message"] == "요청 시간이 초과되었습니다."
