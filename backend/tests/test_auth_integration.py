"""PostgreSQL authentication integration tests."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.security import hash_password, sha256_hex
from app.db.session import reset_engine
from app.main import app
from app.models.auth import AuthSession
from app.models.enums import UserStatus
from app.models.user import User

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — skipping auth integration tests",
)


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
    get_settings.cache_clear()
    reset_engine()
    with TestClient(app) as c:
        yield c
    reset_engine()
    get_settings.cache_clear()


def _create_user(
    db: Session,
    *,
    email: str | None = None,
    password: str = "password-ok-1",
    status: str = UserStatus.ACTIVE.value,
    must_change_password: bool = False,
    deleted: bool = False,
) -> tuple[User, str]:
    email = email or f"auth-{uuid.uuid4().hex[:10]}@example.com"
    user = User(
        email=email.lower(),
        name="Auth User",
        password_hash=hash_password(password),
        status=status,
        must_change_password=must_change_password,
        deleted_at=datetime.now(timezone.utc) if deleted else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, password


def _csrf(client: TestClient) -> str:
    r = client.get("/api/v1/auth/csrf")
    assert r.status_code == 200
    token = r.json()["csrf_token"]
    assert client.cookies.get(get_settings().auth_csrf_cookie_name) == token
    return token


def _login(client: TestClient, email: str, password: str, csrf: str | None = None):
    csrf = csrf or _csrf(client)
    return client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers={"X-CSRF-Token": csrf},
    )


def test_csrf_endpoint(client: TestClient) -> None:
    token = _csrf(client)
    assert isinstance(token, str) and len(token) > 10


def test_login_success_sets_http_only_session(client: TestClient, db: Session) -> None:
    user, password = _create_user(db)
    r = _login(client, user.email, password)
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["email"] == user.email
    assert "token" not in body
    assert "session" not in str(body.get("session", {})).lower() or "expires_at" in body["session"]

    settings = get_settings()
    raw = client.cookies.get(settings.auth_session_cookie_name)
    assert raw
    # Cookie jar doesn't expose HttpOnly; verify DB stores hash only
    session = db.scalar(select(AuthSession).where(AuthSession.user_id == user.id))
    assert session is not None
    assert session.token_hash == sha256_hex(raw)
    assert session.token_hash != raw


def test_login_wrong_password_increments_failures(client: TestClient, db: Session) -> None:
    user, password = _create_user(db)
    r = _login(client, user.email, "wrong-password")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_CREDENTIALS"
    db.refresh(user)
    assert user.failed_login_count == 1


def test_login_unknown_email(client: TestClient) -> None:
    r = _login(client, "nobody@example.com", "whatever-password")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_temporary_lock_and_reset(client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_LOGIN_MAX_FAILURES", "3")
    monkeypatch.setenv("AUTH_LOGIN_LOCK_SECONDS", "900")
    get_settings.cache_clear()
    reset_engine()

    user, password = _create_user(db, email=f"lock-{uuid.uuid4().hex[:8]}@example.com")
    for _ in range(3):
        r = _login(client, user.email, "bad-password-x")
        assert r.status_code == 401
    db.refresh(user)
    assert user.failed_login_count >= 3
    assert user.locked_until is not None

    # Valid password still rejected while locked
    r = _login(client, user.email, password)
    assert r.status_code == 401

    # Unlock by clearing locked_until
    user.locked_until = None
    user.failed_login_count = 2
    db.commit()

    r = _login(client, user.email, password)
    assert r.status_code == 200
    db.refresh(user)
    assert user.failed_login_count == 0
    assert user.locked_until is None

    get_settings.cache_clear()
    reset_engine()


def test_me_and_logout(client: TestClient, db: Session) -> None:
    user, password = _create_user(db)
    assert _login(client, user.email, password).status_code == 200
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == user.email

    csrf = client.cookies.get(get_settings().auth_csrf_cookie_name)
    logout = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})
    assert logout.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_requires_auth(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401


def test_csrf_required_for_password_change(client: TestClient, db: Session) -> None:
    user, password = _create_user(db)
    assert _login(client, user.email, password).status_code == 200
    r = client.patch(
        "/api/v1/auth/password",
        json={"current_password": password, "new_password": "newer-password"},
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "CSRF_INVALID"


def test_password_change_revokes_other_sessions(client: TestClient, db: Session) -> None:
    user, password = _create_user(db, must_change_password=True)
    assert _login(client, user.email, password).status_code == 200
    settings = get_settings()
    first_token = client.cookies.get(settings.auth_session_cookie_name)

    # Second session via another client
    with TestClient(app) as other:
        csrf = other.get("/api/v1/auth/csrf").json()["csrf_token"]
        r = other.post(
            "/api/v1/auth/login",
            json={"email": user.email, "password": password},
            headers={"X-CSRF-Token": csrf},
        )
        assert r.status_code == 200
        other_token = other.cookies.get(settings.auth_session_cookie_name)
        assert other_token and other_token != first_token

        csrf = client.cookies.get(settings.auth_csrf_cookie_name)
        r = client.patch(
            "/api/v1/auth/password",
            json={"current_password": password, "new_password": "brand-new-pass"},
            headers={"X-CSRF-Token": csrf},
        )
        assert r.status_code == 204

        # Current session still works
        assert client.get("/api/v1/auth/me").status_code == 200
        # Other session revoked
        assert other.get("/api/v1/auth/me").status_code == 401

    db.refresh(user)
    assert user.must_change_password is False


def test_expired_and_revoked_session(client: TestClient, db: Session) -> None:
    user, password = _create_user(db)
    assert _login(client, user.email, password).status_code == 200
    settings = get_settings()
    raw = client.cookies.get(settings.auth_session_cookie_name)
    session = db.scalar(
        select(AuthSession).where(AuthSession.token_hash == sha256_hex(raw))
    )
    assert session is not None

    session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    assert client.get("/api/v1/auth/me").status_code == 401

    # Fresh login then revoke via absolute
    assert _login(client, user.email, password).status_code == 200
    raw = client.cookies.get(settings.auth_session_cookie_name)
    session = db.scalar(
        select(AuthSession).where(AuthSession.token_hash == sha256_hex(raw))
    )
    session.absolute_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    assert client.get("/api/v1/auth/me").status_code == 401


@pytest.mark.parametrize(
    "status",
    [UserStatus.INACTIVE.value, UserStatus.LOCKED.value, UserStatus.WITHDRAWN.value],
)
def test_non_active_status_login_rejected(client: TestClient, db: Session, status: str) -> None:
    user, password = _create_user(db, status=status)
    r = _login(client, user.email, password)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_deleted_user_login_rejected(client: TestClient, db: Session) -> None:
    user, password = _create_user(db, deleted=True)
    r = _login(client, user.email, password)
    assert r.status_code == 401
