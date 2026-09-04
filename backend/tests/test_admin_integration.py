"""PostgreSQL Admin / System Settings integration tests (Step 11)."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import hash_password
from app.db.session import reset_engine
from app.llm.exceptions import LlmAuthenticationError, LlmTimeoutError
from app.llm.schemas import (
    CategoryOption,
    FieldProvenanceEntry,
    IdeaDraftPayload,
    IdeaStructuringRequest,
    IdeaStructuringResult,
)
from app.main import app
from app.models.auth import AuthSession
from app.models.enums import (
    AiLlmDecision,
    FieldProvenanceSource,
    SystemRole,
    SystemSettingKey,
    UserStatus,
    WorkspaceMemberStatus,
    WorkspaceRole,
    WorkspaceType,
)
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.schemas.admin import AdminUserUpdateRequest
from app.services import admin_integration as admin_integration_service
from app.services import admin_user as admin_user_service
from app.services.workspace import (
    ensure_personal_workspace_for_user,
    get_active_personal_workspace,
    seed_workspace_defaults,
)
from app.web_search.base import WebSearchResult
from app.web_search.exceptions import (
    WebSearchAuthenticationError,
    WebSearchRateLimitError,
    WebSearchTimeoutError,
)

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — skipping admin integration tests",
)


class FakeLlmProvider:
    provider_name = "fake"
    model_name = "fake-model"
    prompt_version = "v2"

    def __init__(self) -> None:
        self.calls = 0
        self.last_request: IdeaStructuringRequest | None = None

    def structure_idea(self, request: IdeaStructuringRequest) -> IdeaStructuringResult:
        self.calls += 1
        self.last_request = request
        return IdeaStructuringResult(
            decision=AiLlmDecision.READY_FOR_REVIEW,
            draft=IdeaDraftPayload(title="Probe", one_line_definition="probe", tags=[]),
            field_provenance={
                "title": FieldProvenanceEntry(
                    source=FieldProvenanceSource.LLM_SUMMARY,
                    note="probe",
                )
            },
            clarifying_questions=[],
            research_recommended=False,
            research_topics=[],
        )

    def refine_idea(self, request):
        raise NotImplementedError

    def close(self) -> None:
        pass


class FakeWebSearchProvider:
    provider_name = "fake"

    def __init__(
        self,
        results: list[WebSearchResult] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.calls: list[dict[str, object]] = []
        self._results = list(results or [])
        self._error = error

    def search(self, *, query: str, max_results: int) -> list[WebSearchResult]:
        self.calls.append({"query": query, "max_results": max_results})
        if self._error is not None:
            raise self._error
        return self._results[:max_results]

    def close(self) -> None:
        pass


@pytest.fixture(autouse=True)
def _clean_system_settings(engine):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM system_settings"))
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


def _user(
    db: Session,
    *,
    email: str | None = None,
    password: str = "password-ok-1",
    system_role: str = SystemRole.USER.value,
    status: str = UserStatus.ACTIVE.value,
    must_change_password: bool = False,
) -> tuple[User, str]:
    email = email or f"admin-test-{uuid.uuid4().hex[:10]}@example.com"
    user = User(
        email=email.lower(),
        name=email.split("@")[0],
        password_hash=hash_password(password),
        status=status,
        system_role=system_role,
        must_change_password=must_change_password,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, password


def _admin_user(
    db: Session,
    *,
    email: str | None = None,
    password: str = "password-ok-1",
    must_change_password: bool = False,
) -> tuple[User, str]:
    return _user(
        db,
        email=email,
        password=password,
        system_role=SystemRole.SYSTEM_ADMIN.value,
        must_change_password=must_change_password,
    )


def _team(db: Session, owner: User, *, allow_llm: bool = True, allow_web_search: bool = True) -> Workspace:
    ws = Workspace(
        name=f"Admin Team {uuid.uuid4().hex[:6]}",
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


def _auth_headers(client: TestClient) -> dict[str, str]:
    token = client.cookies.get(get_settings().auth_csrf_cookie_name)
    assert token
    return {"X-CSRF-Token": token}


def _active_sessions(db: Session, user_id: uuid.UUID) -> list[AuthSession]:
    now = datetime.now(timezone.utc)
    return list(
        db.scalars(
            select(AuthSession).where(
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
                AuthSession.absolute_expires_at > now,
            )
        ).all()
    )


def test_non_admin_forbidden_on_admin_endpoints(client: TestClient, db: Session) -> None:
    user, pw = _user(db)
    _login(client, user.email, pw)
    headers = _auth_headers(client)

    for method, path in (
        ("GET", "/api/v1/admin/users"),
        ("GET", "/api/v1/admin/system-settings"),
        ("GET", "/api/v1/admin/integrations"),
    ):
        r = client.request(method, path, headers=headers)
        assert r.status_code == 403, r.text
        assert r.json()["error"]["code"] == "FORBIDDEN"

    r = client.patch(
        "/api/v1/admin/system-settings",
        json={"global_llm_enabled": False},
        headers=headers,
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"

    r = client.post(
        "/api/v1/admin/users",
        json={
            "email": f"new-{uuid.uuid4().hex[:8]}@example.com",
            "name": "New User",
            "temporary_password": "temp-pass-01",
        },
        headers=headers,
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"

    r = client.post("/api/v1/admin/integrations/llm/test", headers=headers)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"

    r = client.post(
        "/api/v1/admin/integrations/web-search/test",
        json={"query": "idea management"},
        headers=headers,
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"

    r = client.post("/api/v1/admin/integrations/embedding/test", headers=headers)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"


def test_system_admin_must_change_password_blocked(client: TestClient, db: Session) -> None:
    admin, pw = _admin_user(db, must_change_password=True)
    _login(client, admin.email, pw)
    headers = _auth_headers(client)

    for method, path, body in (
        ("GET", "/api/v1/admin/users", None),
        ("GET", "/api/v1/admin/system-settings", None),
        ("PATCH", "/api/v1/admin/system-settings", {"global_llm_enabled": False}),
        (
            "POST",
            "/api/v1/admin/users",
            {
                "email": f"blocked-{uuid.uuid4().hex[:8]}@example.com",
                "name": "Blocked",
                "temporary_password": "temp-pass-02",
            },
        ),
        ("POST", "/api/v1/admin/integrations/llm/test", None),
        (
            "POST",
            "/api/v1/admin/integrations/web-search/test",
            {"query": "idea management"},
        ),
        ("POST", "/api/v1/admin/integrations/embedding/test", None),
    ):
        if body is None:
            r = client.request(method, path, headers=headers)
        else:
            r = client.request(method, path, json=body, headers=headers)
        assert r.status_code == 403, r.text
        assert r.json()["error"]["code"] == "PASSWORD_CHANGE_REQUIRED"


def test_system_settings_defaults_when_db_empty(client: TestClient, db: Session) -> None:
    admin, pw = _admin_user(db)
    _login(client, admin.email, pw)

    r = client.get("/api/v1/admin/system-settings", headers=_auth_headers(client))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["global_llm_enabled"] is True
    assert body["global_web_search_enabled"] is True
    assert body["default_team_allow_llm"] is True
    assert body["default_team_allow_web_search"] is True
    for key in (
        "GLOBAL_LLM_ENABLED",
        "GLOBAL_WEB_SEARCH_ENABLED",
        "DEFAULT_TEAM_ALLOW_LLM",
        "DEFAULT_TEAM_ALLOW_WEB_SEARCH",
    ):
        meta = body["metadata"][key]
        assert meta["source"] == "DEFAULT"
        assert meta["updated_at"] is None
        assert meta["updated_by"] is None


def test_patch_system_settings_persists_with_updated_by(
    client: TestClient, db: Session
) -> None:
    admin, pw = _admin_user(db)
    _login(client, admin.email, pw)
    headers = _auth_headers(client)

    r = client.patch(
        "/api/v1/admin/system-settings",
        json={"global_llm_enabled": False},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["global_llm_enabled"] is False
    meta = body["metadata"]["GLOBAL_LLM_ENABLED"]
    assert meta["source"] == "DATABASE"
    assert meta["updated_by"]["id"] == str(admin.id)

    row = db.get(SystemSetting, SystemSettingKey.GLOBAL_LLM_ENABLED.value)
    assert row is not None
    assert row.value_json is False
    assert row.updated_by == admin.id


def test_patch_system_settings_rejects_extra_fields(client: TestClient, db: Session) -> None:
    admin, pw = _admin_user(db)
    _login(client, admin.email, pw)

    r = client.patch(
        "/api/v1/admin/system-settings",
        json={"global_llm_enabled": False, "llm_api_key": "secret"},
        headers=_auth_headers(client),
    )
    assert r.status_code == 422


def test_admin_user_create_provisions_personal_workspace(
    client: TestClient, db: Session
) -> None:
    admin, pw = _admin_user(db)
    _login(client, admin.email, pw)
    email = f"provision-{uuid.uuid4().hex[:8]}@example.com"

    r = client.post(
        "/api/v1/admin/users",
        json={
            "email": email,
            "name": "Provisioned",
            "temporary_password": "temp-pass-03",
        },
        headers=_auth_headers(client),
    )
    assert r.status_code == 201, r.text
    created_id = uuid.UUID(r.json()["id"])

    personal = get_active_personal_workspace(db, created_id)
    assert personal is not None
    assert personal.type == WorkspaceType.PERSONAL.value


def test_admin_user_create_duplicate_email(client: TestClient, db: Session) -> None:
    admin, pw = _admin_user(db)
    existing, _ = _user(db, email=f"dup-{uuid.uuid4().hex[:8]}@example.com")
    _login(client, admin.email, pw)

    r = client.post(
        "/api/v1/admin/users",
        json={
            "email": existing.email,
            "name": "Duplicate",
            "temporary_password": "temp-pass-04",
        },
        headers=_auth_headers(client),
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "EMAIL_EXISTS"


def test_inactive_user_sessions_revoked(client: TestClient, db: Session) -> None:
    admin, admin_pw = _admin_user(db)
    target, target_pw = _user(db)
    _login(client, target.email, target_pw)
    assert len(_active_sessions(db, target.id)) == 1

    _login(client, admin.email, admin_pw)
    r = client.patch(
        f"/api/v1/admin/users/{target.id}",
        json={"status": "INACTIVE"},
        headers=_auth_headers(client),
    )
    assert r.status_code == 200, r.text
    db.expire_all()
    assert len(_active_sessions(db, target.id)) == 0


def test_unlock_login_clears_lock_counters(client: TestClient, db: Session) -> None:
    admin, admin_pw = _admin_user(db)
    target, _ = _user(db)
    target.failed_login_count = 5
    target.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
    db.commit()

    _login(client, admin.email, admin_pw)
    r = client.post(
        f"/api/v1/admin/users/{target.id}/unlock-login",
        headers=_auth_headers(client),
    )
    assert r.status_code == 200, r.text
    db.refresh(target)
    assert target.failed_login_count == 0
    assert target.locked_until is None


def test_reset_password_revokes_sessions_and_sets_must_change(
    client: TestClient, db: Session
) -> None:
    admin, admin_pw = _admin_user(db)
    target, target_pw = _user(db, must_change_password=False)
    _login(client, target.email, target_pw)
    assert len(_active_sessions(db, target.id)) == 1

    _login(client, admin.email, admin_pw)
    r = client.post(
        f"/api/v1/admin/users/{target.id}/reset-password",
        json={"temporary_password": "reset-pass-05"},
        headers=_auth_headers(client),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["must_change_password"] is True
    db.expire_all()
    assert len(_active_sessions(db, target.id)) == 0


def test_admin_self_protection(client: TestClient, db: Session) -> None:
    admin, pw = _admin_user(db)
    _login(client, admin.email, pw)
    headers = _auth_headers(client)

    r = client.patch(
        f"/api/v1/admin/users/{admin.id}",
        json={"status": "INACTIVE"},
        headers=headers,
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "SELF_PROTECTION"

    r = client.patch(
        f"/api/v1/admin/users/{admin.id}",
        json={"system_role": "USER"},
        headers=headers,
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "SELF_PROTECTION"

    r = client.post(
        f"/api/v1/admin/users/{admin.id}/reset-password",
        json={"temporary_password": "self-reset-06"},
        headers=headers,
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "SELF_PROTECTION"


def test_last_system_admin_required(db: Session) -> None:
    other_admins = list(
        db.scalars(
            select(User).where(
                User.system_role == SystemRole.SYSTEM_ADMIN.value,
                User.status == UserStatus.ACTIVE.value,
                User.deleted_at.is_(None),
            )
        ).all()
    )
    saved_roles = {admin.id: admin.system_role for admin in other_admins}
    for admin in other_admins:
        admin.system_role = SystemRole.USER.value
    db.commit()

    try:
        sole, _ = _admin_user(db)
        actor, _ = _user(db)

        with pytest.raises(AppError) as exc_info:
            admin_user_service.update_user(
                db,
                actor_id=actor.id,
                user_id=sole.id,
                payload=AdminUserUpdateRequest(system_role=SystemRole.USER),
            )
        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "LAST_SYSTEM_ADMIN_REQUIRED"
    finally:
        for admin in other_admins:
            row = db.get(User, admin.id)
            if row is not None:
                row.system_role = saved_roles[admin.id]
        db.commit()


def test_global_llm_disabled_blocks_ai_session(client: TestClient, db: Session) -> None:
    admin, admin_pw = _admin_user(db)
    owner, owner_pw = _user(db)
    ws = _team(db, owner)
    _login(client, admin.email, admin_pw)
    client.patch(
        "/api/v1/admin/system-settings",
        json={"global_llm_enabled": False},
        headers=_auth_headers(client),
    )

    _login(client, owner.email, owner_pw)
    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions",
        json={"input_text": "blocked by global policy"},
        headers=_auth_headers(client),
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "SYSTEM_LLM_DISABLED"


def test_global_web_search_disabled_blocks_research_preview(
    client: TestClient, db: Session
) -> None:
    admin, admin_pw = _admin_user(db)
    owner, owner_pw = _user(db)
    ws = _team(db, owner, allow_llm=True, allow_web_search=True)
    _login(client, owner.email, owner_pw)
    session_r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions",
        json={"input_text": "research preview block test"},
        headers=_auth_headers(client),
    )
    assert session_r.status_code == 202, session_r.text
    session_id = session_r.json()["id"]

    _login(client, admin.email, admin_pw)
    client.patch(
        "/api/v1/admin/system-settings",
        json={"global_web_search_enabled": False},
        headers=_auth_headers(client),
    )

    _login(client, owner.email, owner_pw)
    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions/{session_id}/research-runs/preview",
        json={
            "queries": ["idea management software"],
            "current_draft": {"title": "Draft"},
            "user_edited_fields": [],
        },
        headers=_auth_headers(client),
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "SYSTEM_WEB_SEARCH_DISABLED"


def test_team_workspace_create_uses_default_team_flags(client: TestClient, db: Session) -> None:
    admin, admin_pw = _admin_user(db)
    owner, owner_pw = _user(db)
    ensure_personal_workspace_for_user(db, owner)

    _login(client, admin.email, admin_pw)
    client.patch(
        "/api/v1/admin/system-settings",
        json={
            "default_team_allow_llm": False,
            "default_team_allow_web_search": False,
        },
        headers=_auth_headers(client),
    )

    _login(client, owner.email, owner_pw)
    r = client.post(
        "/api/v1/workspaces",
        json={"name": "Defaults Team"},
        headers=_auth_headers(client),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["allow_llm"] is False
    assert body["allow_web_search"] is False


def test_workspace_response_includes_effective_allow_flags(
    client: TestClient, db: Session
) -> None:
    admin, admin_pw = _admin_user(db)
    owner, owner_pw = _user(db)
    ws = _team(db, owner, allow_llm=True, allow_web_search=True)

    _login(client, admin.email, admin_pw)
    client.patch(
        "/api/v1/admin/system-settings",
        json={"global_llm_enabled": False},
        headers=_auth_headers(client),
    )

    _login(client, owner.email, owner_pw)
    r = client.get(f"/api/v1/workspaces/{ws.id}", headers=_auth_headers(client))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["allow_llm"] is True
    assert body["allow_web_search"] is True
    assert body["effective_allow_llm"] is False
    assert body["effective_allow_web_search"] is False


def test_integrations_get_does_not_leak_secret_keys(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_API_KEY", "SUPER_SECRET_LLM_KEY_123")
    monkeypatch.setenv("WEB_SEARCH_API_KEY", "SUPER_SECRET_SEARCH_KEY_456")
    monkeypatch.setenv("LLM_API_URL", "https://user:password@example.com/api?token=URL_SECRET")
    monkeypatch.setenv("LLM_CHAT_COMPLETIONS_PATH", "/v1/chat/completions?token=PATH_SECRET")
    monkeypatch.setenv(
        "WEB_SEARCH_API_URL", "https://user:password@example.com/search?key=SEARCH_URL_SECRET"
    )
    get_settings.cache_clear()
    reset_engine()

    admin, pw = _admin_user(db)
    _login(client, admin.email, pw)
    r = client.get("/api/v1/admin/integrations", headers=_auth_headers(client))
    assert r.status_code == 200, r.text
    dumped = json.dumps(r.json())
    for secret in (
        "SUPER_SECRET_LLM_KEY_123",
        "SUPER_SECRET_SEARCH_KEY_456",
        "password",
        "URL_SECRET",
        "PATH_SECRET",
        "SEARCH_URL_SECRET",
    ):
        assert secret not in dumped
    body = r.json()
    assert body["llm"]["api_key_configured"] is True
    assert body["llm"]["configured"] is True
    assert body["web_search"]["api_key_configured"] is True
    assert body["llm"]["api_url"] == "https://example.com/api"
    assert body["llm"]["chat_completions_path"] == "/v1/chat/completions"
    assert body["web_search"]["api_url"] == "https://example.com/search"


def test_llm_configured_without_api_key(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_API_URL", "https://internal-llm.example.com/v1")
    monkeypatch.setenv("LLM_MODEL_NAME", "Qwen3-14B")
    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()
    reset_engine()

    admin, pw = _admin_user(db)
    _login(client, admin.email, pw)
    r = client.get("/api/v1/admin/integrations", headers=_auth_headers(client))
    assert r.status_code == 200, r.text
    body = r.json()
    dumped = json.dumps(body)
    assert body["llm"]["configured"] is True
    assert body["llm"]["api_key_configured"] is False
    assert "api_key" not in body["llm"] or "api_key_configured" in body["llm"]
    assert body["llm"].get("api_key") is None
    assert "Qwen3-14B" in dumped
    # No secret-like key field value beyond the boolean flag.
    assert '"api_key":' not in dumped


def test_llm_not_configured_when_url_empty(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_API_URL", "")
    monkeypatch.setenv("LLM_MODEL_NAME", "Qwen3-14B")
    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()
    reset_engine()

    admin, pw = _admin_user(db)
    _login(client, admin.email, pw)
    r = client.get("/api/v1/admin/integrations", headers=_auth_headers(client))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["llm"]["configured"] is False
    assert body["llm"]["api_key_configured"] is False


def test_llm_connection_test_uses_fake_provider_metadata_only(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeLlmProvider()
    monkeypatch.setattr(admin_integration_service, "get_llm_provider", lambda _settings=None: fake)

    admin, pw = _admin_user(db)
    _login(client, admin.email, pw)
    r = client.post(
        "/api/v1/admin/integrations/llm/test",
        headers=_auth_headers(client),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "OK"
    assert body["provider"] == "fake"
    assert body["model"] == "fake-model"
    assert body["latency_ms"] is not None
    assert fake.calls == 1
    assert fake.last_request is not None
    assert fake.last_request.categories == [
        CategoryOption(slug="product_service", name="제품·서비스"),
        CategoryOption(slug="technology_rd", name="기술·R&D"),
    ]
    dumped = json.dumps(body)
    assert "Probe" not in dumped
    assert "draft" not in dumped


def test_web_search_connection_test_not_configured_when_url_empty(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WEB_SEARCH_API_URL", "")
    get_settings.cache_clear()
    reset_engine()

    admin, pw = _admin_user(db)
    _login(client, admin.email, pw)
    r = client.post(
        "/api/v1/admin/integrations/web-search/test",
        json={"query": "idea management"},
        headers=_auth_headers(client),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "NOT_CONFIGURED"
    assert body["error_code"] == "WEB_SEARCH_NOT_CONFIGURED"
    assert body["safe_message"]


def test_withdrawn_user_is_read_only(client: TestClient, db: Session) -> None:
    admin, admin_pw = _admin_user(db)
    target, _ = _user(db, status=UserStatus.WITHDRAWN.value)
    _login(client, admin.email, admin_pw)
    headers = _auth_headers(client)

    listed = client.get("/api/v1/admin/users", params={"status": "WITHDRAWN"}, headers=headers)
    assert listed.status_code == 200, listed.text
    assert any(item["id"] == str(target.id) for item in listed.json()["items"])

    r = client.patch(
        f"/api/v1/admin/users/{target.id}",
        json={"status": "ACTIVE"},
        headers=headers,
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "USER_WITHDRAWN_READ_ONLY"
    db.refresh(target)
    assert target.status == UserStatus.WITHDRAWN.value

    r = client.patch(
        f"/api/v1/admin/users/{target.id}",
        json={"name": "복원된 사용자"},
        headers=headers,
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "USER_WITHDRAWN_READ_ONLY"

    r = client.patch(
        f"/api/v1/admin/users/{target.id}",
        json={"system_role": "SYSTEM_ADMIN"},
        headers=headers,
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "USER_WITHDRAWN_READ_ONLY"

    r = client.post(
        f"/api/v1/admin/users/{target.id}/reset-password",
        json={"temporary_password": "temporary-password"},
        headers=headers,
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "USER_WITHDRAWN_READ_ONLY"

    r = client.post(
        f"/api/v1/admin/users/{target.id}/unlock-login",
        headers=headers,
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "USER_WITHDRAWN_READ_ONLY"


def test_cannot_set_active_user_withdrawn(client: TestClient, db: Session) -> None:
    admin, admin_pw = _admin_user(db)
    target, _ = _user(db)
    _login(client, admin.email, admin_pw)
    r = client.patch(
        f"/api/v1/admin/users/{target.id}",
        json={"status": "WITHDRAWN"},
        headers=_auth_headers(client),
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "INVALID_STATUS"
    db.refresh(target)
    assert target.status == UserStatus.ACTIVE.value


def test_web_search_connection_test_configured_fake_provider(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WEB_SEARCH_API_URL", "https://search.example.com")
    get_settings.cache_clear()
    reset_engine()

    fake = FakeWebSearchProvider(
        results=[
            WebSearchResult(
                title="Python",
                url="https://docs.python.org/3/",
                snippet="Official Python documentation",
                source="Python Docs",
                published_at=None,
            )
        ]
    )
    monkeypatch.setattr(
        admin_integration_service, "get_web_search_provider", lambda _settings=None: fake
    )

    admin, pw = _admin_user(db)
    _login(client, admin.email, pw)
    r = client.post(
        "/api/v1/admin/integrations/web-search/test",
        json={"query": "Python official documentation"},
        headers=_auth_headers(client),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "OK"
    assert body["provider"] == "fake"
    assert body["result_count"] == 1
    assert body["results"][0]["title"] == "Python"
    assert body["results"][0]["source"] == "Python Docs"
    assert fake.calls == 1 or len(fake.calls) == 1
    assert fake.calls[0]["query"] == "Python official documentation"
    assert int(fake.calls[0]["max_results"]) <= 5  # type: ignore[arg-type]
    dumped = json.dumps(fake.calls) + json.dumps(body)
    assert "input_text" not in dumped
    assert "draft" not in dumped
    assert "one_line_definition" not in dumped


def test_web_search_connection_test_unknown_provider(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WEB_SEARCH_API_URL", "https://search.example.com")
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", "unknown")
    get_settings.cache_clear()
    reset_engine()

    admin, pw = _admin_user(db)
    _login(client, admin.email, pw)
    r = client.post(
        "/api/v1/admin/integrations/web-search/test",
        json={"query": "Python official documentation"},
        headers=_auth_headers(client),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "NOT_CONFIGURED"
    assert body["error_code"] == "WEB_SEARCH_NOT_CONFIGURED"
    dumped = json.dumps(body)
    assert "Traceback" not in dumped
    assert "Exception" not in dumped
    assert "SUPER_SECRET" not in dumped


def test_llm_connection_test_configuration_error(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_API_URL", "")
    get_settings.cache_clear()
    reset_engine()

    admin, pw = _admin_user(db)
    _login(client, admin.email, pw)
    r = client.post(
        "/api/v1/admin/integrations/llm/test",
        headers=_auth_headers(client),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ERROR"
    assert body["error_code"] == "LLM_CONFIGURATION_ERROR"
    assert body["retryable"] is False
    dumped = json.dumps(body)
    assert "Traceback" not in dumped


def test_llm_connection_test_timeout_and_auth_errors(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin, pw = _admin_user(db)
    _login(client, admin.email, pw)

    class TimeoutProvider(FakeLlmProvider):
        def structure_idea(self, request: IdeaStructuringRequest) -> IdeaStructuringResult:
            self.calls += 1
            raise LlmTimeoutError()

    monkeypatch.setattr(
        admin_integration_service, "get_llm_provider", lambda _settings=None: TimeoutProvider()
    )
    r = client.post("/api/v1/admin/integrations/llm/test", headers=_auth_headers(client))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ERROR"
    assert r.json()["error_code"] == "LLM_TIMEOUT"
    assert r.json()["retryable"] is True

    class AuthProvider(FakeLlmProvider):
        def structure_idea(self, request: IdeaStructuringRequest) -> IdeaStructuringResult:
            self.calls += 1
            raise LlmAuthenticationError()

    monkeypatch.setattr(
        admin_integration_service, "get_llm_provider", lambda _settings=None: AuthProvider()
    )
    r = client.post("/api/v1/admin/integrations/llm/test", headers=_auth_headers(client))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ERROR"
    assert r.json()["error_code"] == "LLM_AUTH_ERROR"


def test_web_search_connection_test_provider_errors(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WEB_SEARCH_API_URL", "https://search.example.com")
    get_settings.cache_clear()
    reset_engine()
    admin, pw = _admin_user(db)
    _login(client, admin.email, pw)

    cases = [
        (WebSearchTimeoutError(), "WEB_SEARCH_TIMEOUT", True),
        (WebSearchAuthenticationError(), "WEB_SEARCH_AUTH_ERROR", False),
        (WebSearchRateLimitError(), "WEB_SEARCH_RATE_LIMIT", True),
    ]
    for error, code, retryable in cases:
        fake = FakeWebSearchProvider(error=error)
        monkeypatch.setattr(
            admin_integration_service, "get_web_search_provider", lambda _settings=None, f=fake: f
        )
        r = client.post(
            "/api/v1/admin/integrations/web-search/test",
            json={"query": "Python official documentation"},
            headers=_auth_headers(client),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "ERROR"
        assert body["error_code"] == code
        assert body["retryable"] is retryable


def test_integrations_get_includes_embedding_without_secrets(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EMBEDDING_ENABLED", "true")
    monkeypatch.setenv("EMBEDDING_API_URL", "https://user:password@embed.example.com/v1?token=EMB_SECRET")
    monkeypatch.setenv("EMBEDDING_API_KEY", "SUPER_SECRET_EMBEDDING_KEY")
    monkeypatch.setenv("EMBEDDING_MODEL_NAME", "bge-m3")
    get_settings.cache_clear()
    reset_engine()

    admin, pw = _admin_user(db)
    _login(client, admin.email, pw)
    r = client.get("/api/v1/admin/integrations", headers=_auth_headers(client))
    assert r.status_code == 200, r.text
    body = r.json()
    dumped = json.dumps(body)
    assert "SUPER_SECRET_EMBEDDING_KEY" not in dumped
    assert "EMB_SECRET" not in dumped
    assert "password" not in dumped
    emb = body["embedding"]
    assert emb["api_key_configured"] is True
    assert emb["api_url"] == "https://embed.example.com/v1"
    assert emb["enabled"] is True
    assert emb["model_name"] == "bge-m3"
    assert "stored_embedding_count" in emb
    assert set(emb["job_counts"].keys()) >= {"queued", "running", "succeeded", "failed"}


def test_embedding_connection_test_requires_csrf(client: TestClient, db: Session) -> None:
    admin, pw = _admin_user(db)
    _login(client, admin.email, pw)
    r = client.post("/api/v1/admin/integrations/embedding/test")
    assert r.status_code in (401, 403)


def test_embedding_connection_test_not_configured(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EMBEDDING_ENABLED", "false")
    monkeypatch.setenv("EMBEDDING_API_URL", "")
    get_settings.cache_clear()
    reset_engine()

    called = {"n": 0}

    def _should_not_call(_settings=None):
        called["n"] += 1
        raise AssertionError("provider must not be called when disabled")

    monkeypatch.setattr(admin_integration_service, "get_embedding_provider", _should_not_call)

    admin, pw = _admin_user(db)
    _login(client, admin.email, pw)
    r = client.post(
        "/api/v1/admin/integrations/embedding/test",
        headers=_auth_headers(client),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "NOT_CONFIGURED"
    assert called["n"] == 0
    assert body["safe_message"]


def test_embedding_connection_test_ok_with_fake_provider(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.embeddings.fake import FakeEmbeddingProvider

    monkeypatch.setenv("EMBEDDING_ENABLED", "true")
    monkeypatch.setenv("EMBEDDING_API_URL", "https://embed.example.com")
    monkeypatch.setenv("EMBEDDING_API_KEY", "test-key")
    get_settings.cache_clear()
    reset_engine()

    settings = get_settings()
    fake = FakeEmbeddingProvider(settings)
    monkeypatch.setattr(
        admin_integration_service, "get_embedding_provider", lambda _settings=None: fake
    )

    admin, pw = _admin_user(db)
    _login(client, admin.email, pw)
    r = client.post(
        "/api/v1/admin/integrations/embedding/test",
        headers=_auth_headers(client),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "OK"
    assert body["provider"] == "fake"
    assert body["dimension"] == settings.embedding_dimension
    assert body["latency_ms"] is not None
    dumped = json.dumps(body)
    assert "test-key" not in dumped
    assert "IdeaFlow embedding" not in dumped


def test_embedding_connection_test_dimension_mismatch(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EMBEDDING_ENABLED", "true")
    monkeypatch.setenv("EMBEDDING_API_URL", "https://embed.example.com")
    get_settings.cache_clear()
    reset_engine()

    class BadDimProvider:
        provider_name = "bad"
        model_name = "bad-model"

        def embed_text(self, text: str) -> list[float]:
            return [0.1, 0.2]

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        admin_integration_service, "get_embedding_provider", lambda _settings=None: BadDimProvider()
    )

    admin, pw = _admin_user(db)
    _login(client, admin.email, pw)
    r = client.post(
        "/api/v1/admin/integrations/embedding/test",
        headers=_auth_headers(client),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ERROR"
    assert body["error_code"] == "EMBEDDING_DIMENSION_MISMATCH"
    assert body["safe_message"]
    assert "0.1" not in json.dumps(body)


def test_embedding_connection_test_provider_failure_safe(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.embeddings.exceptions import EmbeddingServerError

    monkeypatch.setenv("EMBEDDING_ENABLED", "true")
    monkeypatch.setenv("EMBEDDING_API_URL", "https://embed.example.com")
    get_settings.cache_clear()
    reset_engine()

    class FailingProvider:
        provider_name = "fail"
        model_name = "fail-model"

        def embed_text(self, text: str) -> list[float]:
            raise EmbeddingServerError("raw secret body KEY=abc")

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        admin_integration_service, "get_embedding_provider", lambda _settings=None: FailingProvider()
    )

    admin, pw = _admin_user(db)
    _login(client, admin.email, pw)
    r = client.post(
        "/api/v1/admin/integrations/embedding/test",
        headers=_auth_headers(client),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ERROR"
    dumped = json.dumps(body)
    assert "KEY=abc" not in dumped
    assert "raw secret" not in dumped
    assert body["safe_message"]
