"""Tests for create_admin CLI."""

from __future__ import annotations

import os
import sys
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.cli.create_admin import active_system_admin_exists, main
from app.core.security import hash_password
from app.db.session import reset_engine
from app.models.enums import SystemRole, UserStatus
from app.models.user import User

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — skipping create_admin CLI tests",
)


@pytest.fixture(scope="module")
def engine():
    reset_engine()
    eng = create_engine(DATABASE_URL, pool_pre_ping=True)
    yield eng
    eng.dispose()
    reset_engine()


@pytest.fixture
def db(engine) -> Session:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _create_user(
    db: Session,
    *,
    email: str | None = None,
    system_role: str = SystemRole.USER.value,
    status: str = UserStatus.ACTIVE.value,
    deleted: bool = False,
) -> User:
    from datetime import datetime, timezone

    email = email or f"cli-{uuid.uuid4().hex[:10]}@example.com"
    user = User(
        email=email.lower(),
        name="CLI User",
        password_hash=hash_password("password-ok-12345"),
        status=status,
        system_role=system_role,
        deleted_at=datetime.now(timezone.utc) if deleted else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_active_system_admin_exists_false_when_scalar_none(db: Session) -> None:
    with patch.object(db, "scalar", return_value=None):
        assert active_system_admin_exists(db) is False


def test_active_system_admin_exists_true_for_active_admin(db: Session) -> None:
    _create_user(db, system_role=SystemRole.SYSTEM_ADMIN.value)
    assert active_system_admin_exists(db) is True


def test_withdrawn_system_admin_not_counted(db: Session) -> None:
    withdrawn = _create_user(
        db,
        system_role=SystemRole.SYSTEM_ADMIN.value,
        status=UserStatus.WITHDRAWN.value,
    )
    active_admins = db.scalars(
        select(User).where(
            User.system_role == SystemRole.SYSTEM_ADMIN.value,
            User.deleted_at.is_(None),
            User.status == UserStatus.ACTIVE.value,
        )
    ).all()
    assert all(user.id != withdrawn.id for user in active_admins)


def test_deleted_system_admin_not_counted(db: Session) -> None:
    deleted = _create_user(db, system_role=SystemRole.SYSTEM_ADMIN.value, deleted=True)
    active_admins = db.scalars(
        select(User).where(
            User.system_role == SystemRole.SYSTEM_ADMIN.value,
            User.deleted_at.is_(None),
            User.status == UserStatus.ACTIVE.value,
        )
    ).all()
    assert all(user.id != deleted.id for user in active_admins)


def test_non_admin_user_not_counted_as_system_admin(db: Session) -> None:
    regular = _create_user(db, system_role=SystemRole.USER.value)
    active_admins = db.scalars(
        select(User).where(
            User.system_role == SystemRole.SYSTEM_ADMIN.value,
            User.deleted_at.is_(None),
            User.status == UserStatus.ACTIVE.value,
        )
    ).all()
    assert all(user.id != regular.id for user in active_admins)


def test_create_admin_exists_exit_code_when_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.cli.create_admin.active_system_admin_exists", lambda _s: False)
    monkeypatch.setattr(sys, "argv", ["create_admin", "--exists"])
    assert main() == 1


def test_create_admin_exists_exit_code_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.cli.create_admin.active_system_admin_exists", lambda _s: True)
    monkeypatch.setattr(sys, "argv", ["create_admin", "--exists"])
    assert main() == 0


def test_create_admin_exists_exit_code_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(_session):
        raise RuntimeError("db down")

    monkeypatch.setattr("app.cli.create_admin.active_system_admin_exists", _boom)
    monkeypatch.setattr(sys, "argv", ["create_admin", "--exists"])
    assert main() == 2


def _mock_interactive_create(
    monkeypatch: pytest.MonkeyPatch,
    *,
    inputs: list[str],
    passwords: list[str],
) -> None:
    mock_user = type("MockUser", (), {"id": "user-id", "email": "admin@example.com"})()
    mock_session = type(
        "MockSession",
        (),
        {
            "commit": lambda self: None,
            "rollback": lambda self: None,
            "close": lambda self: None,
        },
    )()

    monkeypatch.setattr("app.cli.create_admin.reset_engine", lambda: None)
    monkeypatch.setattr("app.cli.create_admin.get_session_factory", lambda: (lambda: mock_session))
    monkeypatch.setattr(
        "app.cli.create_admin.create_admin_user",
        lambda _session, *, email, name, password: mock_user,
    )
    monkeypatch.setattr("builtins.input", lambda _prompt="": inputs.pop(0))
    monkeypatch.setattr(
        "app.cli.create_admin.getpass.getpass",
        lambda _prompt="": passwords.pop(0),
    )
    monkeypatch.setattr(sys, "argv", ["create_admin"])


def test_create_admin_retries_short_password_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_interactive_create(
        monkeypatch,
        inputs=["admin@example.com", "Admin User"],
        passwords=["short", "short", "validpass12", "validpass12"],
    )
    assert main() == 0


def test_create_admin_retries_long_password_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    long_password = "a" * 257
    _mock_interactive_create(
        monkeypatch,
        inputs=["admin@example.com", "Admin User"],
        passwords=[long_password, long_password, "validpass12", "validpass12"],
    )
    assert main() == 0


def test_create_admin_retries_password_mismatch_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_interactive_create(
        monkeypatch,
        inputs=["admin@example.com", "Admin User"],
        passwords=["validpass12", "different12", "validpass12", "validpass12"],
    )
    assert main() == 0


def test_create_admin_retries_empty_email_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_interactive_create(
        monkeypatch,
        inputs=["", "admin@example.com", "Admin User"],
        passwords=["validpass12", "validpass12"],
    )
    assert main() == 0


def test_create_admin_retries_empty_name_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_interactive_create(
        monkeypatch,
        inputs=["admin@example.com", "", "Admin User"],
        passwords=["validpass12", "validpass12"],
    )
    assert main() == 0
