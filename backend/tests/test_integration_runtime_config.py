"""PostgreSQL Runtime Integration Config tests (Step 17.6)."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import EMBEDDING_DIMENSION, get_settings
from app.core.security import hash_password
from app.db.session import reset_engine
from app.embeddings.canonical import compute_content_hash
from app.embeddings.fake import FakeEmbeddingProvider, _text_to_vector
from app.llm.schemas import (
    FieldProvenanceEntry,
    IdeaDraftPayload,
    IdeaStructuringRequest,
    IdeaStructuringResult,
)
from app.main import app
from app.models.embedding import IdeaEmbedding, IdeaEmbeddingJob
from app.models.enums import (
    AiLlmDecision,
    FieldProvenanceSource,
    IdeaEmbeddingJobStatus,
    IdeaVisibility,
    IntegrationKey,
    IntegrationSecretMode,
    SystemRole,
    UserStatus,
    WebResearchRunStatus,
    WorkspaceMemberStatus,
    WorkspaceRole,
    WorkspaceType,
)
from app.models.idea import Idea
from app.models.integration_runtime import IntegrationConfigAudit, IntegrationRuntimeConfig
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember
from app.schemas.idea import IdeaCreate
from app.services import admin_integration as admin_integration_service
from app.services import ai_worker
from app.services import embedding_worker
from app.services import idea as idea_service
from app.services.embedding_worker import (
    claim_next_embedding_job,
    finalize_embedding_result,
    prepare_claimed_embedding_work,
)
from app.services.integration_runtime_config import (
    resolve_llm_settings,
    upsert_runtime_config,
)
from app.services.workspace import seed_workspace_defaults
from app.web_search.base import WebSearchResult
from tests.pgvector_helpers import requires_pgvector

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — skipping runtime integration config tests",
)


class FakeLlmProvider:
    provider_name = "fake"
    prompt_version = "v2"

    def __init__(self, settings=None) -> None:
        self.settings = settings
        self.model_name = getattr(settings, "llm_model_name", "fake-model") if settings else "fake-model"
        self.calls = 0

    def structure_idea(self, request: IdeaStructuringRequest) -> IdeaStructuringResult:
        self.calls += 1
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

    def refine_idea_with_evidence(self, request):
        raise NotImplementedError

    def close(self) -> None:
        pass


class FakeWebSearchProvider:
    provider_name = "fake"

    def __init__(self, settings=None) -> None:
        self.settings = settings
        self.calls: list[dict[str, object]] = []

    def search(self, *, query: str, max_results: int) -> list[WebSearchResult]:
        self.calls.append({"query": query, "max_results": max_results})
        return [
            WebSearchResult(
                title="Result",
                url="https://example.com/r",
                snippet="snippet",
                source="example.com",
                published_at=None,
            )
        ]

    def close(self) -> None:
        pass


class RecordingEmbeddingProvider:
    """Records model_name from settings passed at construction."""

    provider_name = "recording"
    seen_models: list[str] = []

    def __init__(self, settings) -> None:
        self._settings = settings
        self.model_name = settings.embedding_model_name
        type(self).seen_models.append(settings.embedding_model_name)

    def close(self) -> None:
        return None

    def embed_text(self, text: str) -> list[float]:
        return _text_to_vector(text, dimension=self._settings.embedding_dimension)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(t) for t in texts]


@pytest.fixture(scope="module")
def engine():
    reset_engine()
    get_settings.cache_clear()
    eng = create_engine(DATABASE_URL, pool_pre_ping=True)
    with eng.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(cfg, "head")
    yield eng
    eng.dispose()
    reset_engine()
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _clean_runtime_tables(engine):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM integration_config_audits"))
        conn.execute(text("DELETE FROM integration_runtime_configs"))
    yield


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
    monkeypatch.setenv("EMBEDDING_WORKER_ENABLED", "false")
    monkeypatch.setenv("APP_ENV", "development")
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
    must_change_password: bool = False,
) -> tuple[User, str]:
    email = email or f"rt-{uuid.uuid4().hex[:10]}@example.com"
    user = User(
        email=email.lower(),
        name=email.split("@")[0],
        password_hash=hash_password(password),
        status=UserStatus.ACTIVE.value,
        system_role=system_role,
        must_change_password=must_change_password,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, password


def _admin_user(db: Session, **kwargs) -> tuple[User, str]:
    return _user(db, system_role=SystemRole.SYSTEM_ADMIN.value, **kwargs)


def _team(db: Session, owner: User) -> Workspace:
    ws = Workspace(
        name=f"RT Team {uuid.uuid4().hex[:6]}",
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


def _assert_no_secret_leak(payload: object, *forbidden: str) -> None:
    dumped = json.dumps(payload)
    for value in forbidden:
        if value:
            assert value not in dumped
    assert '"api_key":' not in dumped
    assert "secret_ciphertext" not in dumped


def _create_idea(db: Session, ws: Workspace, author: User, **kwargs) -> Idea:
    payload = IdeaCreate(
        title=kwargs.get("title", "Runtime idea"),
        one_line_definition=kwargs.get("one_line_definition"),
        problem=kwargs.get("problem", "problem"),
        core_concept=kwargs.get("core_concept", "concept"),
        tags=kwargs.get("tags", []),
        visibility=kwargs.get("visibility", IdeaVisibility.WORKSPACE),
    )
    idea = idea_service.create_idea(db, workspace_id=ws.id, author=author, payload=payload)
    db.commit()
    db.refresh(idea)
    return idea


def _store_embedding(db: Session, idea: Idea, *, text: str, model_name: str | None = None) -> None:
    settings = get_settings()
    vector = _text_to_vector(text, dimension=settings.embedding_dimension)
    content_hash = compute_content_hash(text)
    row = db.get(IdeaEmbedding, idea.id)
    model = model_name or settings.embedding_model_name
    if row is None:
        db.add(
            IdeaEmbedding(
                idea_id=idea.id,
                workspace_id=idea.workspace_id,
                embedding=vector,
                content_hash=content_hash,
                model_name=model,
                dimension=settings.embedding_dimension,
            )
        )
    else:
        row.embedding = vector
        row.content_hash = content_hash
        row.model_name = model
    db.commit()


# --- ENV fallback / non-secret override ---


def test_env_fallback_when_no_runtime_row(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_MODEL_NAME", "ENV_MODEL_FALLBACK")
    monkeypatch.setenv("LLM_API_URL", "https://llm.env.example/v1")
    get_settings.cache_clear()
    reset_engine()

    admin, pw = _admin_user(db)
    _login(client, admin.email, pw)
    r = client.get("/api/v1/admin/integrations", headers=_auth_headers(client))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["llm"]["configuration_source"] == "ENVIRONMENT"
    assert body["llm"]["runtime_override_exists"] is False
    assert body["llm"]["runtime_revision"] == 0
    assert body["llm"]["model_name"] == "ENV_MODEL_FALLBACK"
    assert body["llm"]["api_url"] == "https://llm.env.example/v1"
    assert body["web_search"]["configuration_source"] == "ENVIRONMENT"
    assert body["embedding"]["configuration_source"] == "ENVIRONMENT"


def test_runtime_non_secret_override_and_env_fallback(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_MODEL_NAME", "ENV_MODEL")
    monkeypatch.setenv("LLM_API_URL", "https://llm.env.example/v1")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.3")
    monkeypatch.setenv("LLM_API_KEY", "ENV_LLM_KEY_SHOULD_NOT_LEAK")
    get_settings.cache_clear()
    reset_engine()

    admin, pw = _admin_user(db)
    _login(client, admin.email, pw)
    headers = _auth_headers(client)

    r = client.patch(
        "/api/v1/admin/integrations/llm",
        json={"expected_revision": 0, "model_name": "RUNTIME_MODEL"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["llm"]["configuration_source"] == "RUNTIME"
    assert body["llm"]["runtime_override_exists"] is True
    assert body["llm"]["runtime_revision"] == 1
    assert body["llm"]["model_name"] == "RUNTIME_MODEL"
    # unset fields fall back to ENV
    assert body["llm"]["api_url"] == "https://llm.env.example/v1"
    assert body["llm"]["temperature"] == 0.3
    _assert_no_secret_leak(body, "ENV_LLM_KEY_SHOULD_NOT_LEAK")

    row = db.get(IntegrationRuntimeConfig, IntegrationKey.LLM.value)
    assert row is not None
    assert "api_key" not in (row.config_json or {})
    dumped_row = json.dumps(row.config_json)
    assert "ENV_LLM_KEY_SHOULD_NOT_LEAK" not in dumped_row


# --- Secret modes ---


def test_secret_modes_inherit_replace_clear(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    fernet_key = Fernet.generate_key().decode("utf-8")
    env_key = "ENV_SECRET_KEY_VALUE_AAA"
    runtime_key = "RUNTIME_SECRET_KEY_VALUE_BBB"
    monkeypatch.setenv("INTEGRATION_SECRET_ENCRYPTION_KEY", fernet_key)
    monkeypatch.setenv("LLM_API_KEY", env_key)
    monkeypatch.setenv("LLM_API_URL", "https://llm.env.example/v1")
    monkeypatch.setenv("LLM_MODEL_NAME", "ENV_MODEL")
    get_settings.cache_clear()
    reset_engine()

    admin, pw = _admin_user(db)
    _login(client, admin.email, pw)
    headers = _auth_headers(client)

    # Baseline: INHERIT_ENV uses ENV key
    r = client.get("/api/v1/admin/integrations", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["llm"]["api_key_source"] == "ENVIRONMENT"
    assert body["llm"]["api_key_configured"] is True
    assert body["llm"]["secret_mode"] == "INHERIT_ENV"
    assert body["llm"]["secret_storage_ready"] is True
    _assert_no_secret_leak(body, env_key, runtime_key, fernet_key)

    # Create runtime row with KEEP (still inherit)
    r = client.patch(
        "/api/v1/admin/integrations/llm",
        json={"expected_revision": 0, "model_name": "M1", "api_key_action": "KEEP"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["llm"]["api_key_source"] == "ENVIRONMENT"
    assert body["llm"]["secret_mode"] == "INHERIT_ENV"
    rev = body["llm"]["runtime_revision"]

    # REPLACE stores encrypted ciphertext (no plaintext in DB)
    r = client.patch(
        "/api/v1/admin/integrations/llm",
        json={
            "expected_revision": rev,
            "api_key_action": "REPLACE",
            "api_key": runtime_key,
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["llm"]["api_key_source"] == "RUNTIME"
    assert body["llm"]["api_key_configured"] is True
    assert body["llm"]["secret_mode"] == "ENCRYPTED"
    _assert_no_secret_leak(body, env_key, runtime_key)

    db.expire_all()
    row = db.get(IntegrationRuntimeConfig, IntegrationKey.LLM.value)
    assert row is not None
    assert row.secret_mode == IntegrationSecretMode.ENCRYPTED.value
    assert row.secret_ciphertext is not None
    assert row.secret_ciphertext != runtime_key
    assert runtime_key not in json.dumps(row.config_json or {})
    assert runtime_key not in (row.secret_ciphertext or "")
    effective = resolve_llm_settings(db)
    assert effective.llm_api_key == runtime_key
    rev = body["llm"]["runtime_revision"]

    # CLEAR → effective empty key
    r = client.patch(
        "/api/v1/admin/integrations/llm",
        json={"expected_revision": rev, "api_key_action": "CLEAR"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["llm"]["api_key_source"] == "NONE"
    assert body["llm"]["api_key_configured"] is False
    assert body["llm"]["secret_mode"] == "CLEARED"
    _assert_no_secret_leak(body, env_key, runtime_key)
    db.expire_all()
    effective = resolve_llm_settings(db)
    assert effective.llm_api_key == ""
    rev = body["llm"]["runtime_revision"]

    # INHERIT_ENV again → ENV key
    r = client.patch(
        "/api/v1/admin/integrations/llm",
        json={"expected_revision": rev, "api_key_action": "INHERIT_ENV"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["llm"]["api_key_source"] == "ENVIRONMENT"
    assert body["llm"]["api_key_configured"] is True
    assert body["llm"]["secret_mode"] == "INHERIT_ENV"
    _assert_no_secret_leak(body, env_key, runtime_key)
    db.expire_all()
    effective = resolve_llm_settings(db)
    assert effective.llm_api_key == env_key


# --- Revision concurrency ---


def test_revision_concurrency_conflict(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_MODEL_NAME", "ENV_MODEL")
    get_settings.cache_clear()
    reset_engine()

    admin, pw = _admin_user(db)
    _login(client, admin.email, pw)
    headers = _auth_headers(client)

    r = client.patch(
        "/api/v1/admin/integrations/llm",
        json={"expected_revision": 0, "model_name": "M1"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["llm"]["runtime_revision"] == 1

    r = client.patch(
        "/api/v1/admin/integrations/llm",
        json={"expected_revision": 1, "model_name": "M2"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["llm"]["runtime_revision"] == 2

    # Stale expected_revision
    r = client.patch(
        "/api/v1/admin/integrations/llm",
        json={"expected_revision": 1, "model_name": "STALE"},
        headers=headers,
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "INTEGRATION_CONFIG_CHANGED"
    db.expire_all()
    row = db.get(IntegrationRuntimeConfig, IntegrationKey.LLM.value)
    assert row is not None
    assert row.config_json.get("model_name") == "M2"
    assert row.revision == 2

    # Stale reset
    r = client.request(
        "DELETE",
        "/api/v1/admin/integrations/llm/runtime-config",
        json={"expected_revision": 1},
        headers=headers,
    )
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "INTEGRATION_CONFIG_CHANGED"
    db.expire_all()
    assert db.get(IntegrationRuntimeConfig, IntegrationKey.LLM.value) is not None


# --- Auth ---


def test_runtime_config_auth_gates(client: TestClient, db: Session) -> None:
    admin, admin_pw = _admin_user(db)
    user, user_pw = _user(db)

    # Unauthenticated
    r = client.patch(
        "/api/v1/admin/integrations/llm",
        json={"expected_revision": 0, "model_name": "X"},
    )
    assert r.status_code in (401, 403)

    r = client.get("/api/v1/admin/integrations/config-audit")
    assert r.status_code in (401, 403)

    # Regular USER forbidden
    _login(client, user.email, user_pw)
    headers = _auth_headers(client)
    r = client.patch(
        "/api/v1/admin/integrations/llm",
        json={"expected_revision": 0, "model_name": "X"},
        headers=headers,
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"

    r = client.get("/api/v1/admin/integrations/config-audit", headers=headers)
    assert r.status_code == 403

    r = client.request(
        "DELETE",
        "/api/v1/admin/integrations/llm/runtime-config",
        json={"expected_revision": 0},
        headers=headers,
    )
    assert r.status_code == 403

    # Admin without CSRF denied
    _login(client, admin.email, admin_pw)
    r = client.patch(
        "/api/v1/admin/integrations/llm",
        json={"expected_revision": 0, "model_name": "X"},
    )
    assert r.status_code in (401, 403)

    r = client.request(
        "DELETE",
        "/api/v1/admin/integrations/llm/runtime-config",
        json={"expected_revision": 0},
    )
    assert r.status_code in (401, 403)

    # Admin + CSRF ok
    headers = _auth_headers(client)
    r = client.patch(
        "/api/v1/admin/integrations/llm",
        json={"expected_revision": 0, "model_name": "AUTH_OK"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    rev = r.json()["llm"]["runtime_revision"]

    r = client.get("/api/v1/admin/integrations/config-audit", headers=headers)
    assert r.status_code == 200, r.text

    r = client.request(
        "DELETE",
        "/api/v1/admin/integrations/llm/runtime-config",
        json={"expected_revision": rev},
        headers=headers,
    )
    assert r.status_code == 200, r.text


# --- Validation ---


def test_validation_rejects_invalid_values_without_db_write(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_MODEL_NAME", "ENV_MODEL")
    monkeypatch.setenv("WEB_SEARCH_API_URL", "https://search.env.example/q")
    monkeypatch.setenv("EMBEDDING_ENABLED", "false")
    monkeypatch.setenv("EMBEDDING_API_URL", "")
    get_settings.cache_clear()
    reset_engine()

    admin, pw = _admin_user(db)
    _login(client, admin.email, pw)
    headers = _auth_headers(client)

    # Seed a valid LLM runtime row
    r = client.patch(
        "/api/v1/admin/integrations/llm",
        json={"expected_revision": 0, "model_name": "GOOD"},
        headers=headers,
    )
    assert r.status_code == 200
    good_rev = r.json()["llm"]["runtime_revision"]
    db.expire_all()
    before = db.get(IntegrationRuntimeConfig, IntegrationKey.LLM.value)
    assert before is not None
    before_json = dict(before.config_json)
    before_rev = before.revision

    # Negative timeout
    r = client.patch(
        "/api/v1/admin/integrations/llm",
        json={"expected_revision": good_rev, "timeout_seconds": -1},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "INTEGRATION_RUNTIME_CONFIG_INVALID"

    # temperature > 2
    r = client.patch(
        "/api/v1/admin/integrations/llm",
        json={"expected_revision": good_rev, "temperature": 2.5},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "INTEGRATION_RUNTIME_CONFIG_INVALID"

    db.expire_all()
    after = db.get(IntegrationRuntimeConfig, IntegrationKey.LLM.value)
    assert after is not None
    assert after.revision == before_rev
    assert after.config_json == before_json

    # max_queries > 10
    r = client.patch(
        "/api/v1/admin/integrations/web-search",
        json={"expected_revision": 0, "max_queries": 11},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "INTEGRATION_RUNTIME_CONFIG_INVALID"
    assert db.get(IntegrationRuntimeConfig, IntegrationKey.WEB_SEARCH.value) is None

    # embedding dimension in request → 422 (extra forbid)
    r = client.patch(
        "/api/v1/admin/integrations/embedding",
        json={"expected_revision": 0, "dimension": 512},
        headers=headers,
    )
    assert r.status_code == 422, r.text
    assert db.get(IntegrationRuntimeConfig, IntegrationKey.EMBEDDING.value) is None

    # enabled=true with empty URL invalid
    r = client.patch(
        "/api/v1/admin/integrations/embedding",
        json={"expected_revision": 0, "enabled": True, "api_url": ""},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "INTEGRATION_RUNTIME_CONFIG_INVALID"
    assert db.get(IntegrationRuntimeConfig, IntegrationKey.EMBEDDING.value) is None


# --- Reset / audit ---


def test_reset_to_env_deletes_row(client: TestClient, db: Session) -> None:
    admin, pw = _admin_user(db)
    _login(client, admin.email, pw)
    headers = _auth_headers(client)

    r = client.patch(
        "/api/v1/admin/integrations/llm",
        json={"expected_revision": 0, "model_name": "RUNTIME_THEN_RESET"},
        headers=headers,
    )
    assert r.status_code == 200
    rev = r.json()["llm"]["runtime_revision"]
    assert db.get(IntegrationRuntimeConfig, IntegrationKey.LLM.value) is not None

    r = client.request(
        "DELETE",
        "/api/v1/admin/integrations/llm/runtime-config",
        json={"expected_revision": rev},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["llm"]["configuration_source"] == "ENVIRONMENT"
    assert body["llm"]["runtime_override_exists"] is False
    assert body["llm"]["runtime_revision"] == 0
    db.expire_all()
    assert db.get(IntegrationRuntimeConfig, IntegrationKey.LLM.value) is None


def test_audit_list_returns_field_names_only(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    fernet_key = Fernet.generate_key().decode("utf-8")
    secret = "AUDIT_SHOULD_NOT_SHOW_THIS_KEY"
    monkeypatch.setenv("INTEGRATION_SECRET_ENCRYPTION_KEY", fernet_key)
    get_settings.cache_clear()
    reset_engine()

    admin, pw = _admin_user(db)
    _login(client, admin.email, pw)
    headers = _auth_headers(client)

    r = client.patch(
        "/api/v1/admin/integrations/llm",
        json={
            "expected_revision": 0,
            "model_name": "AUDITED_MODEL",
            "api_key_action": "REPLACE",
            "api_key": secret,
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text

    r = client.get("/api/v1/admin/integrations/config-audit?integration=LLM", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["items"]
    dumped = json.dumps(body)
    assert secret not in dumped
    assert fernet_key not in dumped
    for item in body["items"]:
        assert isinstance(item["changed_fields"], list)
        for field in item["changed_fields"]:
            assert isinstance(field, str)
            assert field in {"model_name", "api_key"} or field.isidentifier() or "_" in field
        assert secret not in json.dumps(item["changed_fields"])


# --- Connection test uses runtime ---


def test_connection_test_uses_runtime_override(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_MODEL_NAME", "ENV_MODEL")
    monkeypatch.setenv("LLM_API_URL", "https://llm.env.example/v1")
    get_settings.cache_clear()
    reset_engine()

    captured: list[str] = []

    def capture_provider(settings=None):
        assert settings is not None
        captured.append(settings.llm_model_name)
        return FakeLlmProvider(settings)

    monkeypatch.setattr(admin_integration_service, "get_llm_provider", capture_provider)

    admin, pw = _admin_user(db)
    _login(client, admin.email, pw)
    headers = _auth_headers(client)

    r = client.patch(
        "/api/v1/admin/integrations/llm",
        json={"expected_revision": 0, "model_name": "RUNTIME_PROBE_MODEL"},
        headers=headers,
    )
    assert r.status_code == 200, r.text

    r = client.post("/api/v1/admin/integrations/llm/test", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "OK"
    assert captured == ["RUNTIME_PROBE_MODEL"]


# --- Embedding identity / fencing / hot reload ---


@requires_pgvector
def test_embedding_identity_change_schedules_reindex_url_only_does_not(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EMBEDDING_ENABLED", "true")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "fake")
    monkeypatch.setenv("EMBEDDING_API_URL", "http://embed.env.example")
    monkeypatch.setenv("EMBEDDING_MODEL_NAME", "model-v1")
    get_settings.cache_clear()
    reset_engine()

    admin, pw = _admin_user(db)
    ws = _team(db, admin)
    idea = _create_idea(db, ws, admin, title="Reindex me")
    # Clear auto-enqueued job so we control state
    job = db.get(IdeaEmbeddingJob, idea.id)
    if job is not None:
        db.delete(job)
        db.commit()
    _store_embedding(db, idea, text="canonical text for idea", model_name="model-v1")
    emb_before = db.get(IdeaEmbedding, idea.id)
    assert emb_before is not None
    hash_before = emb_before.content_hash

    _login(client, admin.email, pw)
    headers = _auth_headers(client)

    # URL-only change: no full reindex
    r = client.patch(
        "/api/v1/admin/integrations/embedding",
        json={
            "expected_revision": 0,
            "api_url": "http://embed.runtime.example",
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    db.expire_all()
    emb = db.get(IdeaEmbedding, idea.id)
    assert emb is not None
    assert emb.model_name == "model-v1"
    assert emb.content_hash == hash_before
    assert db.get(IdeaEmbeddingJob, idea.id) is None
    rev = r.json()["embedding"]["runtime_revision"]

    # Identity (model) change: delete embedding + queue jobs
    r = client.patch(
        "/api/v1/admin/integrations/embedding",
        json={
            "expected_revision": rev,
            "model_name": "model-v2",
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(IdeaEmbedding, idea.id) is None
    job = db.get(IdeaEmbeddingJob, idea.id)
    assert job is not None
    assert job.status == IdeaEmbeddingJobStatus.QUEUED.value


@requires_pgvector
def test_embedding_in_flight_revision_fencing(
    db: Session, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EMBEDDING_ENABLED", "true")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "fake")
    monkeypatch.setenv("EMBEDDING_API_URL", "http://embed.env.example")
    monkeypatch.setenv("EMBEDDING_MODEL_NAME", "fence-model")
    get_settings.cache_clear()

    # Avoid claiming unrelated leftover jobs from other tests
    db.execute(
        text(
            "UPDATE idea_embedding_jobs SET status = 'SUCCEEDED', "
            "worker_id = NULL, locked_at = NULL, lease_until = NULL "
            "WHERE status IN ('QUEUED', 'RUNNING')"
        )
    )
    db.commit()

    admin, _ = _admin_user(db)
    ws = _team(db, admin)
    idea = _create_idea(db, ws, admin, title="Fence idea")
    settings = get_settings()

    job = db.get(IdeaEmbeddingJob, idea.id)
    if job is None:
        from app.services.embedding_service import sync_embedding_desired_state

        sync_embedding_desired_state(db, idea, settings=settings, force=True)
        db.commit()
        job = db.get(IdeaEmbeddingJob, idea.id)
    assert job is not None
    job.status = IdeaEmbeddingJobStatus.QUEUED.value
    job.available_at = datetime.now(timezone.utc)
    db.commit()

    # Create runtime revision 1 (same identity as ENV → no reindex)
    upsert_runtime_config(
        db,
        key=IntegrationKey.EMBEDDING,
        actor_id=admin.id,
        expected_revision=0,
        patch_fields={"api_url": "http://embed.env.example"},
        api_key_action="KEEP",
        api_key=None,
        base_settings=settings,
    )
    db.commit()
    claimed_revision = 1

    worker_id = "fence-worker-1"
    claim_db = session_factory()
    try:
        claimed = claim_next_embedding_job(claim_db, worker_id=worker_id, settings=settings)
        assert claimed is not None
        assert claimed.idea_id == idea.id
        work = prepare_claimed_embedding_work(
            claim_db,
            job=claimed,
            worker_id=worker_id,
            claimed_revision=claimed_revision,
        )
        assert work is not None
        claim_db.commit()
    finally:
        claim_db.close()

    # Bump revision via URL-only change (no identity reindex that would reset the lease)
    upsert_runtime_config(
        db,
        key=IntegrationKey.EMBEDDING,
        actor_id=admin.id,
        expected_revision=1,
        patch_fields={"api_url": "http://embed.other.example"},
        api_key_action="KEEP",
        api_key=None,
        base_settings=settings,
    )
    db.commit()

    old_vector = [0.01] * EMBEDDING_DIMENSION
    finalize_db = session_factory()
    try:
        finalize_embedding_result(
            finalize_db,
            idea_id=work.idea_id,
            workspace_id=work.workspace_id,
            worker_id=worker_id,
            claimed_hash=work.content_hash,
            vector=old_vector,
            settings=settings,
            claimed_revision=claimed_revision,
        )
    finally:
        finalize_db.close()

    db.expire_all()
    assert db.get(IdeaEmbedding, idea.id) is None
    refreshed = db.get(IdeaEmbeddingJob, idea.id)
    assert refreshed is not None
    assert refreshed.status == IdeaEmbeddingJobStatus.QUEUED.value
    assert refreshed.last_error_code == "EMBEDDING_RUNTIME_CONFIG_CHANGED"


@requires_pgvector
def test_ai_and_embedding_worker_hot_reload_without_restart(
    client: TestClient,
    db: Session,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_API_URL", "https://llm.env.example/v1")
    monkeypatch.setenv("LLM_MODEL_NAME", "ENV_LLM")
    monkeypatch.setenv("WEB_SEARCH_API_URL", "https://search.env.example/q")
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", "http_json")
    monkeypatch.setenv("EMBEDDING_ENABLED", "true")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "fake")
    monkeypatch.setenv("EMBEDDING_API_URL", "http://embed.env.example")
    monkeypatch.setenv("EMBEDDING_MODEL_NAME", "emb-env")
    monkeypatch.setenv("AI_WORKER_ENABLED", "false")
    get_settings.cache_clear()
    reset_engine()

    admin, pw = _admin_user(db)
    ws = _team(db, admin)
    _login(client, admin.email, pw)
    headers = _auth_headers(client)

    # Drain leftover queue rows so this test claims only its own work
    db.execute(
        text(
            "UPDATE ai_jobs SET status = 'FAILED' "
            "WHERE status IN ('QUEUED', 'RUNNING')"
        )
    )
    db.execute(
        text(
            "UPDATE idea_embedding_jobs SET status = 'SUCCEEDED', "
            "worker_id = NULL, locked_at = NULL, lease_until = NULL "
            "WHERE status IN ('QUEUED', 'RUNNING')"
        )
    )
    db.commit()

    # Two AI sessions → two STRUCTURE jobs
    for i in range(2):
        r = client.post(
            f"/api/v1/workspaces/{ws.id}/ai-sessions",
            json={"input_text": f"hot reload idea {i}"},
            headers=headers,
        )
        assert r.status_code == 202, r.text

    seen_llm_models: list[str] = []
    seen_ws_urls: list[str] = []

    def llm_factory(settings=None):
        assert settings is not None
        seen_llm_models.append(settings.llm_model_name)
        return FakeLlmProvider(settings)

    def ws_factory(settings=None):
        assert settings is not None
        seen_ws_urls.append(settings.web_search_api_url)
        return FakeWebSearchProvider(settings)

    monkeypatch.setattr("app.services.ai_worker.get_llm_provider", llm_factory)
    monkeypatch.setattr("app.services.ai_worker.get_web_search_provider", ws_factory)

    operational = get_settings()
    worker_id = "hot-reload-worker"

    # Upsert model A, process one job without injected provider
    upsert_runtime_config(
        db,
        key=IntegrationKey.LLM,
        actor_id=admin.id,
        expected_revision=0,
        patch_fields={"model_name": "MODEL_A"},
        api_key_action="KEEP",
        api_key=None,
        base_settings=operational,
    )
    db.commit()

    did = ai_worker.run_once(
        session_factory=session_factory,
        provider=None,
        search_provider=None,
        settings=operational,
        worker_id=worker_id,
        recover=False,
    )
    assert did is True

    # Upsert model B on same worker settings object; next job resolves new model
    upsert_runtime_config(
        db,
        key=IntegrationKey.LLM,
        actor_id=admin.id,
        expected_revision=1,
        patch_fields={"model_name": "MODEL_B"},
        api_key_action="KEEP",
        api_key=None,
        base_settings=operational,
    )
    db.commit()

    did = ai_worker.run_once(
        session_factory=session_factory,
        provider=None,
        search_provider=None,
        settings=operational,
        worker_id=worker_id,
        recover=False,
    )
    assert did is True
    assert seen_llm_models == ["MODEL_A", "MODEL_B"]

    # Web search provider hot reload (WEB_RESEARCH jobs need research runs — exercise factory via resolve path)
    # Patch web-search runtime and ensure connection-test / resolve path sees new URL.
    upsert_runtime_config(
        db,
        key=IntegrationKey.WEB_SEARCH,
        actor_id=admin.id,
        expected_revision=0,
        patch_fields={"api_url": "https://search.runtime-a.example/q"},
        api_key_action="KEEP",
        api_key=None,
        base_settings=operational,
    )
    db.commit()
    monkeypatch.setattr(admin_integration_service, "get_web_search_provider", ws_factory)
    r = client.post(
        "/api/v1/admin/integrations/web-search/test",
        json={"query": "ideaflow"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "OK"
    assert seen_ws_urls[-1] == "https://search.runtime-a.example/q"

    upsert_runtime_config(
        db,
        key=IntegrationKey.WEB_SEARCH,
        actor_id=admin.id,
        expected_revision=1,
        patch_fields={"api_url": "https://search.runtime-b.example/q"},
        api_key_action="KEEP",
        api_key=None,
        base_settings=operational,
    )
    db.commit()
    r = client.post(
        "/api/v1/admin/integrations/web-search/test",
        json={"query": "ideaflow"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert seen_ws_urls[-1] == "https://search.runtime-b.example/q"

    # Embedding: two ideas / jobs; change model between run_once calls
    RecordingEmbeddingProvider.seen_models = []
    db.execute(
        text(
            "UPDATE idea_embedding_jobs SET status = 'SUCCEEDED', "
            "worker_id = NULL, locked_at = NULL, lease_until = NULL "
            "WHERE status IN ('QUEUED', 'RUNNING')"
        )
    )
    db.commit()

    idea1 = _create_idea(db, ws, admin, title="Emb hot 1")
    idea2 = _create_idea(db, ws, admin, title="Emb hot 2")
    for idea in (idea1, idea2):
        job = db.get(IdeaEmbeddingJob, idea.id)
        assert job is not None
        job.status = IdeaEmbeddingJobStatus.QUEUED.value
        job.available_at = datetime.now(timezone.utc)
    db.commit()

    upsert_runtime_config(
        db,
        key=IntegrationKey.EMBEDDING,
        actor_id=admin.id,
        expected_revision=0,
        patch_fields={
            "model_name": "emb-A",
            "enabled": True,
            "api_url": "http://embed.env.example",
        },
        api_key_action="KEEP",
        api_key=None,
        base_settings=operational,
    )
    db.commit()
    emb_rev = 1

    emb_db = session_factory()
    try:
        assert embedding_worker.run_once(
            emb_db,
            worker_id="emb-hot-1",
            settings=operational,
            provider_factory=RecordingEmbeddingProvider,
            session_factory=session_factory,
            resolve_runtime=True,
        )
    finally:
        emb_db.close()

    upsert_runtime_config(
        db,
        key=IntegrationKey.EMBEDDING,
        actor_id=admin.id,
        expected_revision=emb_rev,
        patch_fields={"model_name": "emb-B"},
        api_key_action="KEEP",
        api_key=None,
        base_settings=operational,
    )
    db.commit()
    emb_rev = 2

    emb_db = session_factory()
    try:
        assert embedding_worker.run_once(
            emb_db,
            worker_id="emb-hot-1",
            settings=operational,
            provider_factory=RecordingEmbeddingProvider,
            session_factory=session_factory,
            resolve_runtime=True,
        )
    finally:
        emb_db.close()

    assert RecordingEmbeddingProvider.seen_models == ["emb-A", "emb-B"]

    # enabled=false skips claim
    upsert_runtime_config(
        db,
        key=IntegrationKey.EMBEDDING,
        actor_id=admin.id,
        expected_revision=emb_rev,
        patch_fields={"enabled": False},
        api_key_action="KEEP",
        api_key=None,
        base_settings=operational,
    )
    db.commit()

    idea3 = _create_idea(db, ws, admin, title="Emb skip")
    job3 = db.get(IdeaEmbeddingJob, idea3.id)
    if job3 is None:
        db.add(
            IdeaEmbeddingJob(
                idea_id=idea3.id,
                content_hash="deadbeef" + "0" * 56,
                status=IdeaEmbeddingJobStatus.QUEUED.value,
                max_attempts=3,
            )
        )
        db.commit()
    else:
        job3.status = IdeaEmbeddingJobStatus.QUEUED.value
        db.commit()

    before_status = db.get(IdeaEmbeddingJob, idea3.id).status
    emb_db = session_factory()
    try:
        did = embedding_worker.run_once(
            emb_db,
            worker_id="emb-hot-skip",
            settings=operational,
            provider_factory=RecordingEmbeddingProvider,
            session_factory=session_factory,
            resolve_runtime=True,
        )
        assert did is False
    finally:
        emb_db.close()
    db.expire_all()
    assert db.get(IdeaEmbeddingJob, idea3.id).status == before_status


# --- Step 17.6 static review corrections ---


@requires_pgvector
def test_embedding_reset_model_to_env_schedules_reindex(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EMBEDDING_ENABLED", "true")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "fake")
    monkeypatch.setenv("EMBEDDING_API_URL", "http://embed.env.example")
    monkeypatch.setenv("EMBEDDING_MODEL_NAME", "env-model")
    get_settings.cache_clear()
    reset_engine()

    admin, pw = _admin_user(db)
    ws = _team(db, admin)
    idea = _create_idea(db, ws, admin, title="Reset reindex")
    job = db.get(IdeaEmbeddingJob, idea.id)
    if job is not None:
        db.delete(job)
        db.commit()
    _store_embedding(db, idea, text="reset reindex text", model_name="runtime-model")

    _login(client, admin.email, pw)
    headers = _auth_headers(client)
    r = client.patch(
        "/api/v1/admin/integrations/embedding",
        json={
            "expected_revision": 0,
            "model_name": "runtime-model",
            "api_url": "http://embed.env.example",
            "enabled": True,
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    rev = r.json()["embedding"]["runtime_revision"]
    # Clear reindex jobs from identity change so reset is the only enqueue
    job = db.get(IdeaEmbeddingJob, idea.id)
    if job is not None:
        db.delete(job)
    emb = db.get(IdeaEmbedding, idea.id)
    if emb is None:
        _store_embedding(db, idea, text="reset reindex text", model_name="runtime-model")
    else:
        db.commit()

    r = client.request(
        "DELETE",
        "/api/v1/admin/integrations/embedding/runtime-config",
        json={"expected_revision": rev},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(IdeaEmbedding, idea.id) is None
    job = db.get(IdeaEmbeddingJob, idea.id)
    assert job is not None
    assert job.status == IdeaEmbeddingJobStatus.QUEUED.value


@requires_pgvector
def test_embedding_disabled_to_enabled_backfill(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EMBEDDING_ENABLED", "false")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "fake")
    monkeypatch.setenv("EMBEDDING_API_URL", "http://embed.env.example")
    monkeypatch.setenv("EMBEDDING_MODEL_NAME", "backfill-model")
    get_settings.cache_clear()
    reset_engine()

    admin, pw = _admin_user(db)
    ws = _team(db, admin)
    idea = _create_idea(db, ws, admin, title="Created while disabled")
    assert db.get(IdeaEmbeddingJob, idea.id) is None

    _login(client, admin.email, pw)
    headers = _auth_headers(client)
    r = client.patch(
        "/api/v1/admin/integrations/embedding",
        json={
            "expected_revision": 0,
            "enabled": True,
            "api_url": "http://embed.env.example",
            "model_name": "backfill-model",
            "provider": "fake",
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    db.expire_all()
    job = db.get(IdeaEmbeddingJob, idea.id)
    assert job is not None
    assert job.status == IdeaEmbeddingJobStatus.QUEUED.value


@requires_pgvector
def test_embedding_reset_disabled_to_env_enabled_backfill(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EMBEDDING_ENABLED", "true")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "fake")
    monkeypatch.setenv("EMBEDDING_API_URL", "http://embed.env.example")
    monkeypatch.setenv("EMBEDDING_MODEL_NAME", "env-enabled")
    get_settings.cache_clear()
    reset_engine()

    admin, pw = _admin_user(db)
    ws = _team(db, admin)
    _login(client, admin.email, pw)
    headers = _auth_headers(client)

    r = client.patch(
        "/api/v1/admin/integrations/embedding",
        json={
            "expected_revision": 0,
            "enabled": False,
            "api_url": "http://embed.env.example",
            "model_name": "env-enabled",
            "provider": "fake",
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    rev = r.json()["embedding"]["runtime_revision"]

    idea = _create_idea(db, ws, admin, title="While runtime disabled")
    assert db.get(IdeaEmbeddingJob, idea.id) is None

    r = client.request(
        "DELETE",
        "/api/v1/admin/integrations/embedding/runtime-config",
        json={"expected_revision": rev},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    db.expire_all()
    job = db.get(IdeaEmbeddingJob, idea.id)
    assert job is not None
    assert job.status == IdeaEmbeddingJobStatus.QUEUED.value


@requires_pgvector
def test_resolver_failure_on_idea_edit_invalidates_stale_vector(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EMBEDDING_ENABLED", "true")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "fake")
    monkeypatch.setenv("EMBEDDING_API_URL", "http://embed.env.example")
    monkeypatch.setenv("EMBEDDING_MODEL_NAME", "stale-model")
    monkeypatch.setenv("EMBEDDING_JOB_LEASE_SECONDS", "120")
    monkeypatch.setenv("EMBEDDING_TIMEOUT_SECONDS", "30")
    get_settings.cache_clear()
    reset_engine()

    admin, pw = _admin_user(db)
    ws = _team(db, admin)
    idea = _create_idea(db, ws, admin, title="Stale vector idea")
    job = db.get(IdeaEmbeddingJob, idea.id)
    if job is not None:
        db.delete(job)
        db.commit()
    _store_embedding(db, idea, text="stale vector content", model_name="stale-model")
    assert db.get(IdeaEmbedding, idea.id) is not None

    # Bypass upsert validation: persist invalid runtime so resolve fails at read time.
    db.add(
        IntegrationRuntimeConfig(
            integration_key=IntegrationKey.EMBEDDING.value,
            config_json={"timeout_seconds": 200.0},
            secret_mode=IntegrationSecretMode.INHERIT_ENV.value,
            secret_ciphertext=None,
            revision=1,
            updated_by=admin.id,
        )
    )
    db.commit()

    _login(client, admin.email, pw)
    headers = _auth_headers(client)
    r = client.patch(
        f"/api/v1/workspaces/{ws.id}/ideas/{idea.id}",
        json={"title": "Updated while config broken"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(IdeaEmbedding, idea.id) is None


def test_combined_llm_web_one_shot_valid_resolve(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services.integration_runtime_config import (
        resolve_llm_and_web_search_settings,
        resolve_web_search_settings,
    )

    monkeypatch.setenv("AI_JOB_LEASE_SECONDS", "300")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("WEB_SEARCH_TIMEOUT_SECONDS", "20")
    monkeypatch.setenv("WEB_SEARCH_MAX_QUERIES", "5")
    monkeypatch.setenv("LLM_API_URL", "https://llm.env.example/v1")
    monkeypatch.setenv("LLM_MODEL_NAME", "env-llm")
    monkeypatch.setenv("WEB_SEARCH_API_URL", "https://search.env.example/q")
    get_settings.cache_clear()

    admin, _ = _admin_user(db)
    base = get_settings()

    # LLM timeout=220 alone vs ENV web (max_queries=5) would be invalid,
    # but individual resolvers must overlay counterpart NON-SECRET runtime.
    row_llm = IntegrationRuntimeConfig(
        integration_key=IntegrationKey.LLM.value,
        config_json={"timeout_seconds": 220.0},
        secret_mode=IntegrationSecretMode.INHERIT_ENV.value,
        secret_ciphertext=None,
        revision=1,
        updated_by=admin.id,
    )
    row_web = IntegrationRuntimeConfig(
        integration_key=IntegrationKey.WEB_SEARCH.value,
        config_json={"max_queries": 1},
        secret_mode=IntegrationSecretMode.INHERIT_ENV.value,
        secret_ciphertext=None,
        revision=1,
        updated_by=admin.id,
    )
    db.add(row_llm)
    db.add(row_web)
    db.commit()

    llm_eff = resolve_llm_settings(db, base_settings=base)
    assert llm_eff.llm_timeout_seconds == 220.0
    assert llm_eff.web_search_max_queries == 1

    web_eff = resolve_web_search_settings(db, base_settings=base)
    assert web_eff.llm_timeout_seconds == 220.0
    assert web_eff.web_search_max_queries == 1

    combined = resolve_llm_and_web_search_settings(db, base_settings=base)
    assert combined.llm_timeout_seconds == 220.0
    assert combined.web_search_max_queries == 1


def test_combined_llm_web_invalid_final_rejects_patch(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AI_JOB_LEASE_SECONDS", "300")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("WEB_SEARCH_TIMEOUT_SECONDS", "20")
    monkeypatch.setenv("WEB_SEARCH_MAX_QUERIES", "5")
    monkeypatch.setenv("LLM_API_URL", "https://llm.env.example/v1")
    monkeypatch.setenv("LLM_MODEL_NAME", "env-llm")
    monkeypatch.setenv("WEB_SEARCH_API_URL", "https://search.env.example/q")
    get_settings.cache_clear()
    reset_engine()

    admin, pw = _admin_user(db)
    _login(client, admin.email, pw)
    headers = _auth_headers(client)

    r = client.patch(
        "/api/v1/admin/integrations/llm",
        json={"expected_revision": 0, "timeout_seconds": 220.0},
        headers=headers,
    )
    # Cross-validation with ENV web (max_queries=5) → invalid
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "INTEGRATION_RUNTIME_CONFIG_INVALID"

    # Valid LLM+WEB pair first
    r = client.patch(
        "/api/v1/admin/integrations/web-search",
        json={"expected_revision": 0, "max_queries": 1},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    web_rev = r.json()["web_search"]["runtime_revision"]

    r = client.patch(
        "/api/v1/admin/integrations/llm",
        json={"expected_revision": 0, "timeout_seconds": 220.0},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    llm_rev = r.json()["llm"]["runtime_revision"]

    # Bumping web max_queries makes combined invalid
    r = client.patch(
        "/api/v1/admin/integrations/web-search",
        json={"expected_revision": web_rev, "max_queries": 5},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "INTEGRATION_RUNTIME_CONFIG_INVALID"
    db.expire_all()
    row = db.execute(
        select(IntegrationRuntimeConfig).where(
            IntegrationRuntimeConfig.integration_key == IntegrationKey.WEB_SEARCH.value
        )
    ).scalar_one()
    assert int(row.revision) == web_rev
    assert row.config_json.get("max_queries") == 1
    del llm_rev


def test_concurrent_revision_zero_create_one_success_one_conflict(
    db: Session, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading

    from app.core.errors import AppError

    monkeypatch.setenv("LLM_API_URL", "https://llm.env.example/v1")
    monkeypatch.setenv("LLM_MODEL_NAME", "env-llm")
    get_settings.cache_clear()

    admin, _ = _admin_user(db)
    base = get_settings()
    results: list[str] = []
    barrier = threading.Barrier(2)

    def worker(model_name: str) -> None:
        session = session_factory()
        try:
            barrier.wait(timeout=10)
            upsert_runtime_config(
                session,
                key=IntegrationKey.LLM,
                actor_id=admin.id,
                expected_revision=0,
                patch_fields={"model_name": model_name},
                api_key_action="KEEP",
                api_key=None,
                base_settings=base,
            )
            session.commit()
            results.append("ok")
        except AppError as exc:
            session.rollback()
            results.append(exc.code)
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            results.append(type(exc).__name__)
        finally:
            session.close()

    t1 = threading.Thread(target=worker, args=("model-a",))
    t2 = threading.Thread(target=worker, args=("model-b",))
    t1.start()
    t2.start()
    t1.join(timeout=30)
    t2.join(timeout=30)
    assert sorted(results) == ["INTEGRATION_CONFIG_CHANGED", "ok"]
    db.expire_all()
    rows = list(
        db.execute(select(IntegrationRuntimeConfig)).scalars().all()
    )
    assert len(rows) == 1
    assert int(rows[0].revision) == 1


def test_concurrent_llm_and_web_patch_cannot_create_invalid_pair(
    db: Session, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Write-skew guard: concurrent LLM+Web PATCHes must not commit invalid lease budget."""
    import threading

    from app.core.errors import AppError
    from app.services.integration_runtime_config import (
        resolve_llm_and_web_search_settings,
    )

    monkeypatch.setenv("AI_JOB_LEASE_SECONDS", "300")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "100")
    monkeypatch.setenv("WEB_SEARCH_TIMEOUT_SECONDS", "20")
    monkeypatch.setenv("WEB_SEARCH_MAX_QUERIES", "1")
    monkeypatch.setenv("LLM_API_URL", "https://llm.env.example/v1")
    monkeypatch.setenv("LLM_MODEL_NAME", "env-llm")
    monkeypatch.setenv("WEB_SEARCH_API_URL", "https://search.env.example/q")
    get_settings.cache_clear()

    admin, _ = _admin_user(db)
    # Ensure no leftover runtime rows for these keys
    db.execute(
        text(
            "DELETE FROM integration_runtime_configs "
            "WHERE integration_key IN ('LLM', 'WEB_SEARCH')"
        )
    )
    db.commit()
    base = get_settings()
    results: list[str] = []
    barrier = threading.Barrier(2)

    def worker_llm() -> None:
        session = session_factory()
        try:
            barrier.wait(timeout=10)
            upsert_runtime_config(
                session,
                key=IntegrationKey.LLM,
                actor_id=admin.id,
                expected_revision=0,
                patch_fields={"timeout_seconds": 200.0},
                api_key_action="KEEP",
                api_key=None,
                base_settings=base,
            )
            session.commit()
            results.append("ok")
        except AppError as exc:
            session.rollback()
            results.append(exc.code)
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            results.append(type(exc).__name__)
        finally:
            session.close()

    def worker_web() -> None:
        session = session_factory()
        try:
            barrier.wait(timeout=10)
            upsert_runtime_config(
                session,
                key=IntegrationKey.WEB_SEARCH,
                actor_id=admin.id,
                expected_revision=0,
                patch_fields={"max_queries": 5},
                api_key_action="KEEP",
                api_key=None,
                base_settings=base,
            )
            session.commit()
            results.append("ok")
        except AppError as exc:
            session.rollback()
            results.append(exc.code)
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            results.append(type(exc).__name__)
        finally:
            session.close()

    t1 = threading.Thread(target=worker_llm)
    t2 = threading.Thread(target=worker_web)
    t1.start()
    t2.start()
    t1.join(timeout=30)
    t2.join(timeout=30)

    assert results.count("ok") == 1, results
    assert results.count("INTEGRATION_RUNTIME_CONFIG_INVALID") == 1, results

    db.expire_all()
    effective = resolve_llm_and_web_search_settings(db, base_settings=get_settings())
    budget = (
        effective.llm_timeout_seconds
        + effective.web_search_timeout_seconds * effective.web_search_max_queries
    )
    assert effective.ai_job_lease_seconds > budget


def test_concurrent_llm_reset_and_web_patch_keeps_valid_pair(
    db: Session, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Shared invariant lock serializes reset + counterpart PATCH."""
    import threading

    from app.core.errors import AppError
    from app.services.integration_runtime_config import (
        reset_runtime_config,
        resolve_llm_and_web_search_settings,
    )

    monkeypatch.setenv("AI_JOB_LEASE_SECONDS", "300")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "100")
    monkeypatch.setenv("WEB_SEARCH_TIMEOUT_SECONDS", "20")
    monkeypatch.setenv("WEB_SEARCH_MAX_QUERIES", "1")
    monkeypatch.setenv("LLM_API_URL", "https://llm.env.example/v1")
    monkeypatch.setenv("LLM_MODEL_NAME", "env-llm")
    monkeypatch.setenv("WEB_SEARCH_API_URL", "https://search.env.example/q")
    get_settings.cache_clear()

    admin, _ = _admin_user(db)
    db.execute(
        text(
            "DELETE FROM integration_runtime_configs "
            "WHERE integration_key IN ('LLM', 'WEB_SEARCH')"
        )
    )
    db.commit()
    base = get_settings()

    # Valid starting pair: LLM timeout 200 + Web q=1
    upsert_runtime_config(
        db,
        key=IntegrationKey.LLM,
        actor_id=admin.id,
        expected_revision=0,
        patch_fields={"timeout_seconds": 200.0},
        api_key_action="KEEP",
        api_key=None,
        base_settings=base,
    )
    upsert_runtime_config(
        db,
        key=IntegrationKey.WEB_SEARCH,
        actor_id=admin.id,
        expected_revision=0,
        patch_fields={"max_queries": 1},
        api_key_action="KEEP",
        api_key=None,
        base_settings=base,
    )
    db.commit()

    results: list[str] = []
    barrier = threading.Barrier(2)

    def worker_reset_llm() -> None:
        session = session_factory()
        try:
            barrier.wait(timeout=10)
            reset_runtime_config(
                session,
                key=IntegrationKey.LLM,
                actor_id=admin.id,
                expected_revision=1,
                base_settings=base,
            )
            session.commit()
            results.append("ok")
        except AppError as exc:
            session.rollback()
            results.append(exc.code)
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            results.append(type(exc).__name__)
        finally:
            session.close()

    def worker_patch_web() -> None:
        session = session_factory()
        try:
            barrier.wait(timeout=10)
            upsert_runtime_config(
                session,
                key=IntegrationKey.WEB_SEARCH,
                actor_id=admin.id,
                expected_revision=1,
                patch_fields={"max_queries": 5},
                api_key_action="KEEP",
                api_key=None,
                base_settings=base,
            )
            session.commit()
            results.append("ok")
        except AppError as exc:
            session.rollback()
            results.append(exc.code)
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            results.append(type(exc).__name__)
        finally:
            session.close()

    t1 = threading.Thread(target=worker_reset_llm)
    t2 = threading.Thread(target=worker_patch_web)
    t1.start()
    t2.start()
    t1.join(timeout=30)
    t2.join(timeout=30)

    # Serialized: either both succeed in a valid order, or one is rejected —
    # never an invalid final Settings combination.
    assert "IntegrityError" not in results, results
    assert all(
        r in ("ok", "INTEGRATION_RUNTIME_CONFIG_INVALID", "INTEGRATION_CONFIG_CHANGED")
        for r in results
    ), results

    db.expire_all()
    effective = resolve_llm_and_web_search_settings(db, base_settings=get_settings())
    budget = (
        effective.llm_timeout_seconds
        + effective.web_search_timeout_seconds * effective.web_search_max_queries
    )
    assert effective.ai_job_lease_seconds > budget


def test_enable_thinking_explicit_null_survives_reload(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_API_URL", "https://llm.env.example/v1")
    monkeypatch.setenv("LLM_MODEL_NAME", "env-llm")
    monkeypatch.setenv("LLM_ENABLE_THINKING", "false")
    get_settings.cache_clear()
    reset_engine()

    admin, pw = _admin_user(db)
    _login(client, admin.email, pw)
    headers = _auth_headers(client)

    r = client.patch(
        "/api/v1/admin/integrations/llm",
        json={"expected_revision": 0, "enable_thinking": None},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["llm"]["enable_thinking"] is None

    db.expire_all()
    row = db.execute(
        select(IntegrationRuntimeConfig).where(
            IntegrationRuntimeConfig.integration_key == IntegrationKey.LLM.value
        )
    ).scalar_one()
    assert "enable_thinking" in row.config_json
    assert row.config_json["enable_thinking"] is None

    effective = resolve_llm_settings(db, base_settings=get_settings())
    assert effective.llm_enable_thinking is None


def test_broken_encrypted_llm_secret_get_isolates_other_integrations(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    fernet_key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("INTEGRATION_SECRET_ENCRYPTION_KEY", fernet_key)
    monkeypatch.setenv("LLM_API_URL", "https://llm.env.example/v1")
    monkeypatch.setenv("LLM_MODEL_NAME", "env-llm")
    monkeypatch.setenv("WEB_SEARCH_API_URL", "https://search.env.example/q")
    monkeypatch.setenv("EMBEDDING_ENABLED", "true")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "fake")
    monkeypatch.setenv("EMBEDDING_API_URL", "http://embed.env.example")
    get_settings.cache_clear()
    reset_engine()

    admin, pw = _admin_user(db)
    db.add(
        IntegrationRuntimeConfig(
            integration_key=IntegrationKey.LLM.value,
            config_json={"model_name": "runtime-llm"},
            secret_mode=IntegrationSecretMode.ENCRYPTED.value,
            secret_ciphertext="gAAAAABnot-a-valid-fernet-token-xxxx",
            revision=1,
            updated_by=admin.id,
        )
    )
    db.commit()

    _login(client, admin.email, pw)
    headers = _auth_headers(client)
    r = client.get("/api/v1/admin/integrations", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["llm"]["runtime_error_code"] == "INTEGRATION_SECRET_DECRYPTION_FAILED"
    assert body["llm"]["runtime_safe_message"]
    assert body["llm"]["model_name"] == "runtime-llm"
    assert body["llm"]["api_key_configured"] is True
    assert body["web_search"].get("runtime_error_code") in (None, "")
    assert body["embedding"].get("runtime_error_code") in (None, "")
    assert body["web_search"]["api_url"]
    _assert_no_secret_leak(body)


def test_broken_secret_reset_to_env_clears_error(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    fernet_key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("INTEGRATION_SECRET_ENCRYPTION_KEY", fernet_key)
    monkeypatch.setenv("LLM_API_URL", "https://llm.env.example/v1")
    monkeypatch.setenv("LLM_MODEL_NAME", "env-llm")
    get_settings.cache_clear()
    reset_engine()

    admin, pw = _admin_user(db)
    db.add(
        IntegrationRuntimeConfig(
            integration_key=IntegrationKey.LLM.value,
            config_json={"model_name": "broken-llm"},
            secret_mode=IntegrationSecretMode.ENCRYPTED.value,
            secret_ciphertext="gAAAAABbroken-ciphertext-payload",
            revision=3,
            updated_by=admin.id,
        )
    )
    db.commit()

    _login(client, admin.email, pw)
    headers = _auth_headers(client)
    r = client.request(
        "DELETE",
        "/api/v1/admin/integrations/llm/runtime-config",
        json={"expected_revision": 3},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["llm"].get("runtime_error_code") in (None, "")
    assert body["llm"]["model_name"] == "env-llm"
    assert body["llm"]["configuration_source"] == "ENVIRONMENT"


def test_production_rejects_fake_embedding_provider(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("EMBEDDING_ENABLED", "true")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai_compatible")
    monkeypatch.setenv("EMBEDDING_API_URL", "http://embed.env.example")
    monkeypatch.setenv("EMBEDDING_MODEL_NAME", "prod-model")
    get_settings.cache_clear()
    reset_engine()

    admin, pw = _admin_user(db)
    _login(client, admin.email, pw)
    headers = _auth_headers(client)
    r = client.patch(
        "/api/v1/admin/integrations/embedding",
        json={
            "expected_revision": 0,
            "provider": "fake",
            "api_url": "http://embed.env.example",
        },
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "INTEGRATION_RUNTIME_CONFIG_INVALID"
    db.expire_all()
    assert (
        db.execute(
            select(IntegrationRuntimeConfig).where(
                IntegrationRuntimeConfig.integration_key == IntegrationKey.EMBEDDING.value
            )
        ).scalar_one_or_none()
        is None
    )


def test_web_research_worker_hot_reload_a_to_b(
    db: Session, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.llm.research_schemas import EvidenceRefinementResult
    from app.models.ai import AiJob, IdeaAiSession
    from app.models.enums import (
        AiJobStatus,
        AiJobType,
        IdeaAiSessionStatus,
    )
    from app.models.research import WebResearchRun

    monkeypatch.setenv("LLM_API_URL", "https://llm.env.example/v1")
    monkeypatch.setenv("LLM_MODEL_NAME", "env-llm")
    monkeypatch.setenv("WEB_SEARCH_API_URL", "https://search.env.example/q")
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", "http_json")
    monkeypatch.setenv("AI_WORKER_ENABLED", "false")
    get_settings.cache_clear()

    admin, _ = _admin_user(db)
    ws = _team(db, admin)

    db.execute(
        text(
            "UPDATE ai_jobs SET status = 'FAILED' "
            "WHERE status IN ('QUEUED', 'RUNNING')"
        )
    )
    db.commit()

    seen_ws_urls: list[str] = []

    class ResearchLlm:
        provider_name = "fake"
        model_name = "fake-model"
        prompt_version = "v2"

        def __init__(self, settings=None) -> None:
            self.settings = settings

        def structure_idea(self, request):
            raise NotImplementedError

        def refine_idea(self, request):
            raise NotImplementedError

        def refine_idea_with_evidence(self, request):
            # Keep base draft unchanged so evidence_links are not required.
            return EvidenceRefinementResult(
                draft=dict(request.base_draft or {}),
                evidence_links={},
                research_summary="ok",
            )

        def close(self) -> None:
            return None

    def llm_factory(settings=None):
        return ResearchLlm(settings)

    def ws_factory(settings=None):
        assert settings is not None
        seen_ws_urls.append(settings.web_search_api_url)
        return FakeWebSearchProvider(settings)

    monkeypatch.setattr("app.services.ai_worker.get_llm_provider", llm_factory)
    monkeypatch.setattr("app.services.ai_worker.get_web_search_provider", ws_factory)

    def _enqueue_research(label: str) -> uuid.UUID:
        session = IdeaAiSession(
            workspace_id=ws.id,
            requester_id=admin.id,
            purpose="CREATE",
            status=IdeaAiSessionStatus.READY_FOR_REVIEW.value,
            input_text=f"research {label}",
            draft_payload={"title": "AI Draft", "background": "A"},
            research_recommended=False,
        )
        db.add(session)
        db.flush()
        run = WebResearchRun(
            session_id=session.id,
            requester_id=admin.id,
            status=WebResearchRunStatus.QUEUED.value,
            queries_to_send=[f"query-{label}"],
            base_draft_payload={"title": "AI Draft", "background": "A"},
        )
        db.add(run)
        db.flush()
        job = AiJob(
            session_id=session.id,
            research_run_id=run.id,
            job_type=AiJobType.WEB_RESEARCH.value,
            status=AiJobStatus.QUEUED.value,
            attempts=0,
            max_attempts=3,
            available_at=datetime.now(timezone.utc),
        )
        db.add(job)
        db.commit()
        return run.id

    operational = get_settings()
    upsert_runtime_config(
        db,
        key=IntegrationKey.WEB_SEARCH,
        actor_id=admin.id,
        expected_revision=0,
        patch_fields={"api_url": "https://search.runtime-a.example/q"},
        api_key_action="KEEP",
        api_key=None,
        base_settings=operational,
    )
    db.commit()
    run_a = _enqueue_research("A")

    assert ai_worker.run_once(
        session_factory=session_factory,
        provider=None,
        search_provider=None,
        settings=operational,
        worker_id="wr-hot-a",
        recover=False,
    )
    db.expire_all()
    assert db.get(WebResearchRun, run_a).status == WebResearchRunStatus.READY.value
    assert seen_ws_urls[-1] == "https://search.runtime-a.example/q"

    upsert_runtime_config(
        db,
        key=IntegrationKey.WEB_SEARCH,
        actor_id=admin.id,
        expected_revision=1,
        patch_fields={"api_url": "https://search.runtime-b.example/q"},
        api_key_action="KEEP",
        api_key=None,
        base_settings=operational,
    )
    db.commit()
    run_b = _enqueue_research("B")

    assert ai_worker.run_once(
        session_factory=session_factory,
        provider=None,
        search_provider=None,
        settings=operational,
        worker_id="wr-hot-b",
        recover=False,
    )
    db.expire_all()
    assert db.get(WebResearchRun, run_b).status == WebResearchRunStatus.READY.value
    assert seen_ws_urls[-1] == "https://search.runtime-b.example/q"
    assert "https://search.runtime-a.example/q" in seen_ws_urls
    assert "https://search.runtime-b.example/q" in seen_ws_urls


def _install_valid_cross_runtime_pair(db: Session, admin: User) -> None:
    """LLM timeout=220 + Web max_queries=1 under lease=300 (valid pair)."""
    db.add(
        IntegrationRuntimeConfig(
            integration_key=IntegrationKey.LLM.value,
            config_json={"timeout_seconds": 220.0, "model_name": "runtime-cross-llm"},
            secret_mode=IntegrationSecretMode.INHERIT_ENV.value,
            secret_ciphertext=None,
            revision=1,
            updated_by=admin.id,
        )
    )
    db.add(
        IntegrationRuntimeConfig(
            integration_key=IntegrationKey.WEB_SEARCH.value,
            config_json={"max_queries": 1},
            secret_mode=IntegrationSecretMode.INHERIT_ENV.value,
            secret_ciphertext=None,
            revision=1,
            updated_by=admin.id,
        )
    )
    db.commit()


def test_llm_and_web_resolvers_see_counterpart_non_secret(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services.integration_runtime_config import resolve_web_search_settings

    monkeypatch.setenv("AI_JOB_LEASE_SECONDS", "300")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("WEB_SEARCH_TIMEOUT_SECONDS", "20")
    monkeypatch.setenv("WEB_SEARCH_MAX_QUERIES", "5")
    monkeypatch.setenv("LLM_API_URL", "https://llm.env.example/v1")
    monkeypatch.setenv("LLM_MODEL_NAME", "env-llm")
    monkeypatch.setenv("WEB_SEARCH_API_URL", "https://search.env.example/q")
    get_settings.cache_clear()

    admin, _ = _admin_user(db)
    _install_valid_cross_runtime_pair(db, admin)
    base = get_settings()

    llm_eff = resolve_llm_settings(db, base_settings=base)
    assert llm_eff.llm_timeout_seconds == 220.0
    assert llm_eff.web_search_max_queries == 1

    web_eff = resolve_web_search_settings(db, base_settings=base)
    assert web_eff.llm_timeout_seconds == 220.0
    assert web_eff.web_search_max_queries == 1


def test_resolvers_do_not_decrypt_counterpart_secrets(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.integration_secrets import encrypt_integration_secret
    from app.services.integration_runtime_config import resolve_web_search_settings

    fernet_key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("INTEGRATION_SECRET_ENCRYPTION_KEY", fernet_key)
    monkeypatch.setenv("AI_JOB_LEASE_SECONDS", "300")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("WEB_SEARCH_TIMEOUT_SECONDS", "20")
    monkeypatch.setenv("WEB_SEARCH_MAX_QUERIES", "5")
    monkeypatch.setenv("LLM_API_URL", "https://llm.env.example/v1")
    monkeypatch.setenv("LLM_MODEL_NAME", "env-llm")
    monkeypatch.setenv("LLM_API_KEY", "ENV_LLM_SECRET")
    monkeypatch.setenv("WEB_SEARCH_API_URL", "https://search.env.example/q")
    monkeypatch.setenv("WEB_SEARCH_API_KEY", "ENV_WEB_SECRET")
    get_settings.cache_clear()

    admin, _ = _admin_user(db)
    base = get_settings()
    llm_cipher = encrypt_integration_secret("RUNTIME_LLM_SECRET", base)
    web_cipher = encrypt_integration_secret("RUNTIME_WEB_SECRET", base)

    db.add(
        IntegrationRuntimeConfig(
            integration_key=IntegrationKey.LLM.value,
            config_json={"timeout_seconds": 220.0},
            secret_mode=IntegrationSecretMode.ENCRYPTED.value,
            secret_ciphertext=llm_cipher,
            revision=1,
            updated_by=admin.id,
        )
    )
    db.add(
        IntegrationRuntimeConfig(
            integration_key=IntegrationKey.WEB_SEARCH.value,
            config_json={"max_queries": 1},
            secret_mode=IntegrationSecretMode.ENCRYPTED.value,
            secret_ciphertext=web_cipher,
            revision=1,
            updated_by=admin.id,
        )
    )
    db.commit()

    decrypt_calls: list[str] = []
    real_decrypt = __import__(
        "app.core.integration_secrets", fromlist=["decrypt_integration_secret"]
    ).decrypt_integration_secret

    def spy_decrypt(ciphertext: str, settings):
        decrypt_calls.append(ciphertext)
        return real_decrypt(ciphertext, settings)

    monkeypatch.setattr(
        "app.services.integration_runtime_config.decrypt_integration_secret",
        spy_decrypt,
    )

    llm_eff = resolve_llm_settings(db, base_settings=base)
    assert llm_eff.llm_api_key == "RUNTIME_LLM_SECRET"
    assert llm_eff.web_search_api_key == "ENV_WEB_SECRET"  # ENV inherit for counterpart
    assert decrypt_calls == [llm_cipher]

    decrypt_calls.clear()
    web_eff = resolve_web_search_settings(db, base_settings=base)
    assert web_eff.web_search_api_key == "RUNTIME_WEB_SECRET"
    assert web_eff.llm_api_key == "ENV_LLM_SECRET"
    assert decrypt_calls == [web_cipher]


def test_valid_cross_runtime_pair_create_worker_and_connection_tests(
    client: TestClient,
    db: Session,
    session_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_JOB_LEASE_SECONDS", "300")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("WEB_SEARCH_TIMEOUT_SECONDS", "20")
    monkeypatch.setenv("WEB_SEARCH_MAX_QUERIES", "5")
    monkeypatch.setenv("LLM_API_URL", "https://llm.env.example/v1")
    monkeypatch.setenv("LLM_MODEL_NAME", "env-llm")
    monkeypatch.setenv("WEB_SEARCH_API_URL", "https://search.env.example/q")
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", "http_json")
    monkeypatch.setenv("AI_WORKER_ENABLED", "false")
    get_settings.cache_clear()
    reset_engine()

    admin, pw = _admin_user(db)
    ws = _team(db, admin)
    _install_valid_cross_runtime_pair(db, admin)

    db.execute(
        text(
            "UPDATE ai_jobs SET status = 'FAILED' "
            "WHERE status IN ('QUEUED', 'RUNNING')"
        )
    )
    db.commit()

    seen_llm: list[float] = []
    seen_web: list[int] = []

    def llm_factory(settings=None):
        assert settings is not None
        seen_llm.append(settings.llm_timeout_seconds)
        assert settings.web_search_max_queries == 1
        return FakeLlmProvider(settings)

    def ws_factory(settings=None):
        assert settings is not None
        seen_web.append(settings.web_search_max_queries)
        assert settings.llm_timeout_seconds == 220.0
        return FakeWebSearchProvider(settings)

    monkeypatch.setattr("app.services.ai_worker.get_llm_provider", llm_factory)
    monkeypatch.setattr("app.services.ai_worker.get_web_search_provider", ws_factory)
    monkeypatch.setattr("app.services.admin_integration.get_llm_provider", llm_factory)
    monkeypatch.setattr(
        "app.services.admin_integration.get_web_search_provider", ws_factory
    )

    _login(client, admin.email, pw)
    headers = _auth_headers(client)

    r = client.post(
        f"/api/v1/workspaces/{ws.id}/ai-sessions",
        json={"input_text": "cross runtime create job"},
        headers=headers,
    )
    assert r.status_code == 202, r.text
    session_id = r.json()["id"]

    operational = get_settings()
    assert ai_worker.run_once(
        session_factory=session_factory,
        provider=None,
        search_provider=None,
        settings=operational,
        worker_id="cross-create-worker",
        recover=False,
    )
    from app.models.ai import IdeaAiSession
    from app.models.enums import IdeaAiSessionStatus

    db.expire_all()
    session = db.get(IdeaAiSession, uuid.UUID(session_id))
    assert session is not None
    assert session.status == IdeaAiSessionStatus.READY_FOR_REVIEW.value
    assert seen_llm and seen_llm[-1] == 220.0

    r = client.post("/api/v1/admin/integrations/llm/test", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "OK"
    assert r.json().get("error_code") in (None, "")

    r = client.post(
        "/api/v1/admin/integrations/web-search/test",
        json={"query": "cross runtime probe"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "OK"
    assert seen_web and seen_web[-1] == 1


def test_invalid_web_reset_rejected_then_valid_reset_order(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.models.enums import IntegrationConfigAuditAction

    monkeypatch.setenv("AI_JOB_LEASE_SECONDS", "300")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("WEB_SEARCH_TIMEOUT_SECONDS", "20")
    monkeypatch.setenv("WEB_SEARCH_MAX_QUERIES", "5")
    monkeypatch.setenv("LLM_API_URL", "https://llm.env.example/v1")
    monkeypatch.setenv("LLM_MODEL_NAME", "env-llm")
    monkeypatch.setenv("WEB_SEARCH_API_URL", "https://search.env.example/q")
    get_settings.cache_clear()
    reset_engine()

    admin, pw = _admin_user(db)
    _install_valid_cross_runtime_pair(db, admin)
    _login(client, admin.email, pw)
    headers = _auth_headers(client)

    # Web reset with LLM timeout 220 + ENV web queries 5 → invalid
    r = client.request(
        "DELETE",
        "/api/v1/admin/integrations/web-search/runtime-config",
        json={"expected_revision": 1},
        headers=headers,
    )
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "INTEGRATION_RUNTIME_CONFIG_INVALID"
    db.expire_all()
    web_row = db.execute(
        select(IntegrationRuntimeConfig).where(
            IntegrationRuntimeConfig.integration_key == IntegrationKey.WEB_SEARCH.value
        )
    ).scalar_one()
    assert int(web_row.revision) == 1
    assert web_row.config_json.get("max_queries") == 1
    audits = db.execute(
        select(IntegrationConfigAudit).where(
            IntegrationConfigAudit.integration_key == IntegrationKey.WEB_SEARCH.value,
            IntegrationConfigAudit.action
            == IntegrationConfigAuditAction.RESET_TO_ENV.value,
        )
    ).scalars().all()
    assert audits == []

    # Reset LLM first → ENV LLM 120 + Web queries 1 → valid
    r = client.request(
        "DELETE",
        "/api/v1/admin/integrations/llm/runtime-config",
        json={"expected_revision": 1},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["llm"]["runtime_override_exists"] is False

    # Then Web reset → full ENV → valid
    r = client.request(
        "DELETE",
        "/api/v1/admin/integrations/web-search/runtime-config",
        json={"expected_revision": 1},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["web_search"]["runtime_override_exists"] is False
    db.expire_all()
    remaining = db.execute(select(IntegrationRuntimeConfig)).scalars().all()
    assert remaining == []
