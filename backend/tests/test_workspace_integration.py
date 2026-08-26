"""PostgreSQL Workspace / RBAC integration tests."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import reset_engine
from app.main import app
from app.models.enums import (
    SystemRole,
    UserStatus,
    WorkspaceMemberStatus,
    WorkspaceRole,
    WorkspaceType,
)
from app.models.user import User
from app.models.workspace import (
    Workspace,
    WorkspaceCategory,
    WorkspaceMember,
    WorkspaceStage,
)
from app.services.auth import create_admin_user
from app.services.workspace import (
    PERSONAL_WORKSPACE_NAME,
    backfill_personal_workspaces,
    ensure_personal_workspace_for_user,
)

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — skipping workspace integration tests",
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
    system_role: str = SystemRole.USER.value,
    must_change_password: bool = False,
    deleted: bool = False,
) -> tuple[User, str]:
    email = email or f"ws-{uuid.uuid4().hex[:10]}@example.com"
    user = User(
        email=email.lower(),
        name="WS User",
        password_hash=hash_password(password),
        status=status,
        system_role=system_role,
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
    return r.json()["csrf_token"]


def _login(client: TestClient, email: str, password: str) -> None:
    csrf = _csrf(client)
    r = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text


def _auth_headers(client: TestClient) -> dict[str, str]:
    token = client.cookies.get(get_settings().auth_csrf_cookie_name)
    assert token
    return {"X-CSRF-Token": token}


def _count_stages(db: Session, workspace_id) -> int:
    return db.scalar(
        select(func.count()).select_from(WorkspaceStage).where(
            WorkspaceStage.workspace_id == workspace_id,
            WorkspaceStage.deleted_at.is_(None),
        )
    )


def _count_categories(db: Session, workspace_id) -> int:
    return db.scalar(
        select(func.count()).select_from(WorkspaceCategory).where(
            WorkspaceCategory.workspace_id == workspace_id,
            WorkspaceCategory.deleted_at.is_(None),
        )
    )


def _assert_defaults(db: Session, workspace_id) -> None:
    assert _count_stages(db, workspace_id) == 10
    assert _count_categories(db, workspace_id) == 8
    stages = list(
        db.scalars(
            select(WorkspaceStage)
            .where(WorkspaceStage.workspace_id == workspace_id)
            .order_by(WorkspaceStage.sort_order)
        )
    )
    defaults = [s for s in stages if s.is_default]
    assert len(defaults) == 1 and defaults[0].slug == "memo"
    terminals = {s.slug for s in stages if s.is_terminal}
    assert terminals == {"completed", "discarded"}


def test_ensure_personal_workspace_and_idempotency(db: Session) -> None:
    user, _ = _create_user(db)
    ws1, created1 = ensure_personal_workspace_for_user(db, user)
    db.commit()
    assert created1 is True
    assert ws1.type == WorkspaceType.PERSONAL.value
    assert ws1.owner_id == user.id
    assert ws1.name == PERSONAL_WORKSPACE_NAME

    members = list(
        db.scalars(select(WorkspaceMember).where(WorkspaceMember.workspace_id == ws1.id))
    )
    assert len(members) == 1
    assert members[0].role == WorkspaceRole.ADMIN.value
    assert members[0].status == WorkspaceMemberStatus.ACTIVE.value
    assert members[0].user_id == user.id
    _assert_defaults(db, ws1.id)

    ws2, created2 = ensure_personal_workspace_for_user(db, user)
    db.commit()
    assert created2 is False
    assert ws2.id == ws1.id
    count = db.scalar(
        select(func.count()).select_from(Workspace).where(
            Workspace.owner_id == user.id,
            Workspace.type == WorkspaceType.PERSONAL.value,
            Workspace.deleted_at.is_(None),
        )
    )
    assert count == 1
    assert _count_stages(db, ws1.id) == 10
    assert _count_categories(db, ws1.id) == 8


def test_create_admin_provisions_personal_workspace(db: Session) -> None:
    email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    user = create_admin_user(db, email=email, name="Admin", password="admin-password")
    db.commit()
    ws = db.scalar(
        select(Workspace).where(
            Workspace.owner_id == user.id,
            Workspace.type == WorkspaceType.PERSONAL.value,
            Workspace.deleted_at.is_(None),
        )
    )
    assert ws is not None
    member = db.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == ws.id,
            WorkspaceMember.user_id == user.id,
        )
    )
    assert member is not None
    assert member.role == WorkspaceRole.ADMIN.value
    _assert_defaults(db, ws.id)


def test_backfill_personal_workspaces(db: Session) -> None:
    user_a, _ = _create_user(db)
    user_b, _ = _create_user(db)
    ensure_personal_workspace_for_user(db, user_b)
    db.commit()

    result = backfill_personal_workspaces(db)
    db.commit()
    assert result.failed == 0
    assert result.created >= 1
    assert result.existing >= 1

    for user in (user_a, user_b):
        count = db.scalar(
            select(func.count()).select_from(Workspace).where(
                Workspace.owner_id == user.id,
                Workspace.type == WorkspaceType.PERSONAL.value,
                Workspace.deleted_at.is_(None),
            )
        )
        assert count == 1


def test_team_workspace_create_list_detail_stages_categories(
    client: TestClient, db: Session
) -> None:
    user, password = _create_user(db)
    ensure_personal_workspace_for_user(db, user)
    db.commit()
    _login(client, user.email, password)

    r = client.post(
        "/api/v1/workspaces",
        json={"name": "AI 연구팀", "allow_llm": True, "allow_web_search": False},
        headers=_auth_headers(client),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["type"] == WorkspaceType.TEAM.value
    assert body["owner_id"] == str(user.id)
    assert body["current_user_role"] == WorkspaceRole.ADMIN.value
    assert body["allow_web_search"] is False
    team_id = body["id"]

    listed = client.get("/api/v1/workspaces")
    assert listed.status_code == 200
    ids = [w["id"] for w in listed.json()]
    assert team_id in ids
    assert listed.json()[0]["type"] == WorkspaceType.PERSONAL.value

    detail = client.get(f"/api/v1/workspaces/{team_id}")
    assert detail.status_code == 200
    assert detail.json()["name"] == "AI 연구팀"

    stages = client.get(f"/api/v1/workspaces/{team_id}/stages")
    assert stages.status_code == 200
    assert len(stages.json()) == 10
    assert [s["sort_order"] for s in stages.json()] == sorted(s["sort_order"] for s in stages.json())

    cats = client.get(f"/api/v1/workspaces/{team_id}/categories")
    assert cats.status_code == 200
    assert len(cats.json()) == 8
    assert [c["sort_order"] for c in cats.json()] == sorted(c["sort_order"] for c in cats.json())

    db.expire_all()
    _assert_defaults(db, uuid.UUID(team_id))


def test_workspace_list_filters_inactive_and_non_member(
    client: TestClient, db: Session
) -> None:
    owner, password = _create_user(db)
    other, _ = _create_user(db)
    personal, _ = ensure_personal_workspace_for_user(db, owner)

    team_a = Workspace(name="Team A", type=WorkspaceType.TEAM.value, owner_id=owner.id)
    team_b = Workspace(name="Team B", type=WorkspaceType.TEAM.value, owner_id=owner.id)
    team_c = Workspace(name="Team C", type=WorkspaceType.TEAM.value, owner_id=other.id)
    db.add_all([team_a, team_b, team_c])
    db.flush()
    db.add_all(
        [
            WorkspaceMember(
                workspace_id=team_a.id,
                user_id=owner.id,
                role=WorkspaceRole.ADMIN.value,
                status=WorkspaceMemberStatus.ACTIVE.value,
            ),
            WorkspaceMember(
                workspace_id=team_b.id,
                user_id=owner.id,
                role=WorkspaceRole.MEMBER.value,
                status=WorkspaceMemberStatus.INACTIVE.value,
            ),
        ]
    )
    db.commit()

    _login(client, owner.email, password)
    r = client.get("/api/v1/workspaces")
    assert r.status_code == 200
    ids = {w["id"] for w in r.json()}
    assert str(personal.id) in ids
    assert str(team_a.id) in ids
    assert str(team_b.id) not in ids
    assert str(team_c.id) not in ids


def test_rbac_admin_member_viewer_and_non_member(client: TestClient, db: Session) -> None:
    admin, admin_pw = _create_user(db)
    member_user, member_pw = _create_user(db)
    viewer_user, viewer_pw = _create_user(db)
    outsider, outsider_pw = _create_user(db)

    ensure_personal_workspace_for_user(db, admin)
    team = Workspace(name="RBAC Team", type=WorkspaceType.TEAM.value, owner_id=admin.id)
    db.add(team)
    db.flush()
    db.add_all(
        [
            WorkspaceMember(
                workspace_id=team.id,
                user_id=admin.id,
                role=WorkspaceRole.ADMIN.value,
                status=WorkspaceMemberStatus.ACTIVE.value,
            ),
            WorkspaceMember(
                workspace_id=team.id,
                user_id=member_user.id,
                role=WorkspaceRole.MEMBER.value,
                status=WorkspaceMemberStatus.ACTIVE.value,
            ),
            WorkspaceMember(
                workspace_id=team.id,
                user_id=viewer_user.id,
                role=WorkspaceRole.VIEWER.value,
                status=WorkspaceMemberStatus.ACTIVE.value,
            ),
        ]
    )
    # inactive member visible only to admin
    ghost, _ = _create_user(db)
    db.add(
        WorkspaceMember(
            workspace_id=team.id,
            user_id=ghost.id,
            role=WorkspaceRole.MEMBER.value,
            status=WorkspaceMemberStatus.INACTIVE.value,
        )
    )
    db.commit()
    wid = str(team.id)

    # ADMIN
    _login(client, admin.email, admin_pw)
    assert client.get(f"/api/v1/workspaces/{wid}").status_code == 200
    assert (
        client.patch(
            f"/api/v1/workspaces/{wid}",
            json={"name": "RBAC Team Renamed"},
            headers=_auth_headers(client),
        ).status_code
        == 200
    )
    members = client.get(f"/api/v1/workspaces/{wid}/members")
    assert members.status_code == 200
    assert any(m["status"] == WorkspaceMemberStatus.INACTIVE.value for m in members.json())

    eligible, _ = _create_user(db)
    add = client.post(
        f"/api/v1/workspaces/{wid}/members",
        json={"email": eligible.email, "role": "VIEWER"},
        headers=_auth_headers(client),
    )
    assert add.status_code == 201
    role_patch = client.patch(
        f"/api/v1/workspaces/{wid}/members/{eligible.id}",
        json={"role": "MEMBER"},
        headers=_auth_headers(client),
    )
    assert role_patch.status_code == 200
    assert (
        client.delete(
            f"/api/v1/workspaces/{wid}/members/{eligible.id}",
            headers=_auth_headers(client),
        ).status_code
        == 204
    )
    client.cookies.clear()

    # MEMBER
    _login(client, member_user.email, member_pw)
    assert client.get(f"/api/v1/workspaces/{wid}").status_code == 200
    member_list = client.get(f"/api/v1/workspaces/{wid}/members")
    assert member_list.status_code == 200
    assert all(m["status"] == WorkspaceMemberStatus.ACTIVE.value for m in member_list.json())
    assert (
        client.patch(
            f"/api/v1/workspaces/{wid}",
            json={"name": "Nope"},
            headers=_auth_headers(client),
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/workspaces/{wid}/members",
            json={"email": outsider.email, "role": "MEMBER"},
            headers=_auth_headers(client),
        ).status_code
        == 403
    )
    client.cookies.clear()

    # VIEWER
    _login(client, viewer_user.email, viewer_pw)
    assert client.get(f"/api/v1/workspaces/{wid}").status_code == 200
    assert client.get(f"/api/v1/workspaces/{wid}/members").status_code == 200
    assert (
        client.patch(
            f"/api/v1/workspaces/{wid}",
            json={"allow_llm": False},
            headers=_auth_headers(client),
        ).status_code
        == 403
    )
    client.cookies.clear()

    # Non-member
    _login(client, outsider.email, outsider_pw)
    r = client.get(f"/api/v1/workspaces/{wid}")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"


def test_system_admin_without_membership_has_no_bypass(
    client: TestClient, db: Session
) -> None:
    owner, _ = _create_user(db)
    admin, admin_pw = _create_user(db, system_role=SystemRole.SYSTEM_ADMIN.value)
    team = Workspace(name="Secret", type=WorkspaceType.TEAM.value, owner_id=owner.id)
    db.add(team)
    db.flush()
    db.add(
        WorkspaceMember(
            workspace_id=team.id,
            user_id=owner.id,
            role=WorkspaceRole.ADMIN.value,
            status=WorkspaceMemberStatus.ACTIVE.value,
        )
    )
    db.commit()

    _login(client, admin.email, admin_pw)
    r = client.get(f"/api/v1/workspaces/{team.id}")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"


def test_personal_membership_mutations_blocked(client: TestClient, db: Session) -> None:
    owner, password = _create_user(db)
    other, _ = _create_user(db)
    personal, _ = ensure_personal_workspace_for_user(db, owner)
    db.commit()
    _login(client, owner.email, password)
    headers = _auth_headers(client)
    wid = str(personal.id)

    r = client.post(
        f"/api/v1/workspaces/{wid}/members",
        json={"email": other.email, "role": "MEMBER"},
        headers=headers,
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "PERSONAL_WORKSPACE_MEMBERSHIP_IMMUTABLE"

    r = client.patch(
        f"/api/v1/workspaces/{wid}/members/{owner.id}",
        json={"role": "MEMBER"},
        headers=headers,
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "PERSONAL_WORKSPACE_MEMBERSHIP_IMMUTABLE"

    r = client.delete(f"/api/v1/workspaces/{wid}/members/{owner.id}", headers=headers)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "PERSONAL_WORKSPACE_MEMBERSHIP_IMMUTABLE"


def test_team_owner_role_and_membership_protected(client: TestClient, db: Session) -> None:
    owner, password = _create_user(db)
    ensure_personal_workspace_for_user(db, owner)
    db.commit()
    _login(client, owner.email, password)
    headers = _auth_headers(client)
    team = client.post(
        "/api/v1/workspaces",
        json={"name": "Owner Protect"},
        headers=headers,
    ).json()
    wid = team["id"]

    r = client.patch(
        f"/api/v1/workspaces/{wid}/members/{owner.id}",
        json={"role": "MEMBER"},
        headers=headers,
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "WORKSPACE_OWNER_ROLE_IMMUTABLE"

    r = client.patch(
        f"/api/v1/workspaces/{wid}/members/{owner.id}",
        json={"role": "VIEWER"},
        headers=headers,
    )
    assert r.status_code == 409

    r = client.delete(f"/api/v1/workspaces/{wid}/members/{owner.id}", headers=headers)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "WORKSPACE_OWNER_MEMBERSHIP_IMMUTABLE"


def test_member_reactivation_reuses_row(client: TestClient, db: Session) -> None:
    owner, password = _create_user(db)
    target, _ = _create_user(db)
    ensure_personal_workspace_for_user(db, owner)
    db.commit()
    _login(client, owner.email, password)
    headers = _auth_headers(client)
    team_id = client.post(
        "/api/v1/workspaces",
        json={"name": "React Team"},
        headers=headers,
    ).json()["id"]

    r1 = client.post(
        f"/api/v1/workspaces/{team_id}/members",
        json={"email": target.email, "role": "MEMBER"},
        headers=headers,
    )
    assert r1.status_code == 201
    assert (
        client.delete(
            f"/api/v1/workspaces/{team_id}/members/{target.id}",
            headers=headers,
        ).status_code
        == 204
    )

    before = db.scalar(
        select(func.count()).select_from(WorkspaceMember).where(
            WorkspaceMember.workspace_id == uuid.UUID(team_id)
        )
    )
    r2 = client.post(
        f"/api/v1/workspaces/{team_id}/members",
        json={"email": target.email, "role": "VIEWER"},
        headers=headers,
    )
    assert r2.status_code == 201
    assert r2.json()["status"] == WorkspaceMemberStatus.ACTIVE.value
    assert r2.json()["role"] == WorkspaceRole.VIEWER.value
    after = db.scalar(
        select(func.count()).select_from(WorkspaceMember).where(
            WorkspaceMember.workspace_id == uuid.UUID(team_id)
        )
    )
    assert after == before

    # Idempotent already-active
    r3 = client.post(
        f"/api/v1/workspaces/{team_id}/members",
        json={"email": target.email, "role": "ADMIN"},
        headers=headers,
    )
    assert r3.status_code == 200
    assert r3.json()["role"] == WorkspaceRole.VIEWER.value  # unchanged


def test_member_eligibility(client: TestClient, db: Session) -> None:
    owner, password = _create_user(db)
    ensure_personal_workspace_for_user(db, owner)
    db.commit()
    _login(client, owner.email, password)
    headers = _auth_headers(client)
    team_id = client.post(
        "/api/v1/workspaces",
        json={"name": "Elig"},
        headers=headers,
    ).json()["id"]

    for status in (
        UserStatus.INACTIVE.value,
        UserStatus.LOCKED.value,
        UserStatus.WITHDRAWN.value,
    ):
        u, _ = _create_user(db, status=status)
        r = client.post(
            f"/api/v1/workspaces/{team_id}/members",
            json={"email": u.email, "role": "MEMBER"},
            headers=headers,
        )
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "USER_NOT_ELIGIBLE"

    deleted, _ = _create_user(db, deleted=True)
    r = client.post(
        f"/api/v1/workspaces/{team_id}/members",
        json={"email": deleted.email, "role": "MEMBER"},
        headers=headers,
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "USER_NOT_ELIGIBLE"

    r = client.post(
        f"/api/v1/workspaces/{team_id}/members",
        json={"email": "missing-user@example.com", "role": "MEMBER"},
        headers=headers,
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "USER_NOT_FOUND"


def test_workspace_mutations_require_csrf(client: TestClient, db: Session) -> None:
    user, password = _create_user(db)
    ensure_personal_workspace_for_user(db, user)
    db.commit()
    _login(client, user.email, password)

    assert (
        client.post("/api/v1/workspaces", json={"name": "No CSRF"}).status_code == 403
    )
    personal = client.get("/api/v1/workspaces").json()[0]["id"]
    assert (
        client.patch(f"/api/v1/workspaces/{personal}", json={"name": "X"}).status_code
        == 403
    )


def test_must_change_password_blocks_workspace_apis(
    client: TestClient, db: Session
) -> None:
    user, password = _create_user(db, must_change_password=True)
    ensure_personal_workspace_for_user(db, user)
    db.commit()
    _login(client, user.email, password)

    for path in ("/api/v1/workspaces",):
        r = client.get(path)
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "PASSWORD_CHANGE_REQUIRED"

    r = client.post(
        "/api/v1/workspaces",
        json={"name": "Blocked"},
        headers=_auth_headers(client),
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "PASSWORD_CHANGE_REQUIRED"


def test_stages_categories_non_member_404(client: TestClient, db: Session) -> None:
    owner, _ = _create_user(db)
    outsider, outsider_pw = _create_user(db)
    team = Workspace(name="Stages", type=WorkspaceType.TEAM.value, owner_id=owner.id)
    db.add(team)
    db.flush()
    db.add(
        WorkspaceMember(
            workspace_id=team.id,
            user_id=owner.id,
            role=WorkspaceRole.ADMIN.value,
            status=WorkspaceMemberStatus.ACTIVE.value,
        )
    )
    db.commit()

    _login(client, outsider.email, outsider_pw)
    assert client.get(f"/api/v1/workspaces/{team.id}/stages").status_code == 404
    assert client.get(f"/api/v1/workspaces/{team.id}/categories").status_code == 404
