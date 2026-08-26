"""PostgreSQL Idea CRUD / ACL / search integration tests."""

from __future__ import annotations

import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import reset_engine
from app.main import app
from app.models.enums import (
    IdeaVisibility,
    SystemRole,
    UserStatus,
    WorkspaceMemberStatus,
    WorkspaceRole,
    WorkspaceType,
)
from app.models.idea import Idea
from app.models.relations import IdeaShare
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceCategory, WorkspaceMember, WorkspaceStage
from app.schemas.idea import IdeaCreate
from app.services.idea import create_idea
from app.services.workspace import seed_workspace_defaults

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — skipping idea integration tests",
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


def _user(
    db: Session,
    *,
    email: str | None = None,
    password: str = "password-ok-1",
    system_role: str = SystemRole.USER.value,
    status: str = UserStatus.ACTIVE.value,
    must_change_password: bool = False,
) -> tuple[User, str]:
    email = email or f"idea-{uuid.uuid4().hex[:10]}@example.com"
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


def _team_with_defaults(db: Session, owner: User, name: str = "Idea Team") -> Workspace:
    ws = Workspace(name=name, type=WorkspaceType.TEAM.value, owner_id=owner.id)
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


def _add_member(
    db: Session,
    workspace: Workspace,
    user: User,
    *,
    role: str = WorkspaceRole.MEMBER.value,
    status: str = WorkspaceMemberStatus.ACTIVE.value,
) -> None:
    db.add(
        WorkspaceMember(
            workspace_id=workspace.id,
            user_id=user.id,
            role=role,
            status=status,
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


def _ideas_url(workspace_id) -> str:
    return f"/api/v1/workspaces/{workspace_id}/ideas"


def test_create_idea_defaults_and_codes(client: TestClient, db: Session) -> None:
    author, password = _user(db)
    ws = _team_with_defaults(db, author)
    _login(client, author.email, password)

    r1 = client.post(
        _ideas_url(ws.id),
        json={"title": "첫 아이디어"},
        headers=_headers(client),
    )
    assert r1.status_code == 201, r1.text
    body = r1.json()
    assert body["idea_code"] == "IF-001"
    assert body["author"]["id"] == str(author.id)
    assert body["visibility"] == IdeaVisibility.PRIVATE.value
    assert body["priority"] == "MEDIUM"
    assert body["feasibility"] == "UNKNOWN"
    assert body["stage"]["slug"] == "memo"
    assert body["current_user_access"] == "OWNER"

    r2 = client.post(
        _ideas_url(ws.id),
        json={"title": "두번째", "tags": ["AI", "AI", " 업무 "]},
        headers=_headers(client),
    )
    assert r2.status_code == 201
    assert r2.json()["idea_code"] == "IF-002"
    names = [t["name"] for t in r2.json()["tags"]]
    assert names == ["AI", "업무"]


def test_cross_workspace_references_rejected(client: TestClient, db: Session) -> None:
    a, pw = _user(db)
    b, _ = _user(db)
    ws_a = _team_with_defaults(db, a, "A")
    ws_b = _team_with_defaults(db, b, "B")
    stage_b = db.scalar(
        select(WorkspaceStage).where(WorkspaceStage.workspace_id == ws_b.id)
    )
    cat_b = db.scalar(
        select(WorkspaceCategory).where(WorkspaceCategory.workspace_id == ws_b.id)
    )
    _login(client, a.email, pw)
    headers = _headers(client)

    r = client.post(
        _ideas_url(ws_a.id),
        json={"title": "bad stage", "stage_id": str(stage_b.id)},
        headers=headers,
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_IDEA_REFERENCE"

    r = client.post(
        _ideas_url(ws_a.id),
        json={"title": "bad cat", "category_id": str(cat_b.id)},
        headers=headers,
    )
    assert r.status_code == 400

    r = client.post(
        _ideas_url(ws_a.id),
        json={"title": "bad assignee", "assignee_id": str(b.id)},
        headers=headers,
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "ASSIGNEE_NOT_ELIGIBLE"


def test_private_acl_hides_from_workspace_admin(client: TestClient, db: Session) -> None:
    author, author_pw = _user(db)
    admin, admin_pw = _user(db)
    member, member_pw = _user(db)
    viewer, viewer_pw = _user(db)
    ws = _team_with_defaults(db, admin)
    _add_member(db, ws, author, role=WorkspaceRole.MEMBER.value)
    _add_member(db, ws, member, role=WorkspaceRole.MEMBER.value)
    _add_member(db, ws, viewer, role=WorkspaceRole.VIEWER.value)

    _login(client, author.email, author_pw)
    idea_id = client.post(
        _ideas_url(ws.id),
        json={"title": "비밀", "visibility": "PRIVATE"},
        headers=_headers(client),
    ).json()["id"]

    assert client.get(f"{_ideas_url(ws.id)}/{idea_id}").status_code == 200
    assert any(i["id"] == idea_id for i in client.get(_ideas_url(ws.id)).json()["items"])

    for email, pw in (
        (admin.email, admin_pw),
        (member.email, member_pw),
        (viewer.email, viewer_pw),
    ):
        _login(client, email, pw)
        r = client.get(f"{_ideas_url(ws.id)}/{idea_id}")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "IDEA_NOT_FOUND"
        items = client.get(_ideas_url(ws.id)).json()["items"]
        assert all(i["id"] != idea_id for i in items)
        search = client.get(_ideas_url(ws.id), params={"q": "비밀"}).json()["items"]
        assert all(i["id"] != idea_id for i in search)


def test_system_admin_no_private_bypass(client: TestClient, db: Session) -> None:
    author, author_pw = _user(db)
    sysadmin, sys_pw = _user(db, system_role=SystemRole.SYSTEM_ADMIN.value)
    ws = _team_with_defaults(db, author)
    _add_member(db, ws, sysadmin, role=WorkspaceRole.ADMIN.value)

    _login(client, author.email, author_pw)
    idea_id = client.post(
        _ideas_url(ws.id),
        json={"title": "sys private", "visibility": "PRIVATE"},
        headers=_headers(client),
    ).json()["id"]

    _login(client, sysadmin.email, sys_pw)
    assert client.get(f"{_ideas_url(ws.id)}/{idea_id}").status_code == 404


def test_workspace_visibility_acl(client: TestClient, db: Session) -> None:
    author, author_pw = _user(db)
    member, member_pw = _user(db)
    ws = _team_with_defaults(db, author)
    _add_member(db, ws, member)

    _login(client, author.email, author_pw)
    idea_id = client.post(
        _ideas_url(ws.id),
        json={"title": "공개", "visibility": "WORKSPACE"},
        headers=_headers(client),
    ).json()["id"]

    _login(client, member.email, member_pw)
    assert client.get(f"{_ideas_url(ws.id)}/{idea_id}").status_code == 200
    assert (
        client.patch(
            f"{_ideas_url(ws.id)}/{idea_id}",
            json={"title": "해킹"},
            headers=_headers(client),
        ).status_code
        == 403
    )
    assert (
        client.delete(
            f"{_ideas_url(ws.id)}/{idea_id}",
            headers=_headers(client),
        ).status_code
        == 403
    )


def test_selected_users_acl_and_shares(client: TestClient, db: Session) -> None:
    author, author_pw = _user(db)
    reader, reader_pw = _user(db)
    editor, editor_pw = _user(db)
    outsider, out_pw = _user(db)
    ws = _team_with_defaults(db, author)
    for u, role in (
        (reader, WorkspaceRole.MEMBER.value),
        (editor, WorkspaceRole.MEMBER.value),
        (outsider, WorkspaceRole.MEMBER.value),
    ):
        _add_member(db, ws, u, role=role)

    _login(client, author.email, author_pw)
    body = {
        "title": "선택공유",
        "visibility": "SELECTED_USERS",
        "shares": [
            {"user_id": str(reader.id), "permission": "READ"},
            {"user_id": str(editor.id), "permission": "EDIT"},
        ],
    }
    idea = client.post(_ideas_url(ws.id), json=body, headers=_headers(client)).json()
    idea_id = idea["id"]

    _login(client, reader.email, reader_pw)
    assert client.get(f"{_ideas_url(ws.id)}/{idea_id}").json()["current_user_access"] == "READ"
    assert (
        client.patch(
            f"{_ideas_url(ws.id)}/{idea_id}",
            json={"title": "nope"},
            headers=_headers(client),
        ).status_code
        == 403
    )

    _login(client, editor.email, editor_pw)
    assert client.get(f"{_ideas_url(ws.id)}/{idea_id}").json()["current_user_access"] == "EDIT"
    assert (
        client.patch(
            f"{_ideas_url(ws.id)}/{idea_id}",
            json={"title": "편집됨", "background": "ok"},
            headers=_headers(client),
        ).status_code
        == 200
    )
    # EDIT share may not change original_text (author provenance)
    before = db.get(Idea, uuid.UUID(idea_id))
    assert before is not None
    original_before = before.original_text
    r_orig = client.patch(
        f"{_ideas_url(ws.id)}/{idea_id}",
        json={"original_text": "해킹된 원문"},
        headers=_headers(client),
    )
    assert r_orig.status_code == 403
    assert r_orig.json()["error"]["code"] == "IDEA_OWNER_REQUIRED"
    db.refresh(before)
    assert before.original_text == original_before

    assert (
        client.patch(
            f"{_ideas_url(ws.id)}/{idea_id}",
            json={"visibility": "WORKSPACE"},
            headers=_headers(client),
        ).status_code
        == 403
    )
    assert (
        client.delete(
            f"{_ideas_url(ws.id)}/{idea_id}",
            headers=_headers(client),
        ).status_code
        == 403
    )

    _login(client, outsider.email, out_pw)
    assert client.get(f"{_ideas_url(ws.id)}/{idea_id}").status_code == 404
    assert all(
        i["id"] != idea_id
        for i in client.get(_ideas_url(ws.id), params={"q": "선택공유"}).json()["items"]
    )


def test_patch_explicit_null_semantics(client: TestClient, db: Session) -> None:
    author, password = _user(db)
    assignee, _ = _user(db)
    ws = _team_with_defaults(db, author)
    _add_member(db, ws, assignee)
    stage = db.scalar(
        select(WorkspaceStage).where(
            WorkspaceStage.workspace_id == ws.id,
            WorkspaceStage.is_default.is_(True),
        )
    )
    category = db.scalar(
        select(WorkspaceCategory).where(WorkspaceCategory.workspace_id == ws.id)
    )
    assert stage is not None and category is not None

    _login(client, author.email, password)
    headers = _headers(client)
    created = client.post(
        _ideas_url(ws.id),
        json={
            "title": "null-test",
            "original_text": "원문",
            "visibility": "WORKSPACE",
            "category_id": str(category.id),
            "assignee_id": str(assignee.id),
            "stage_id": str(stage.id),
        },
        headers=headers,
    ).json()
    idea_id = created["id"]
    idea_uuid = uuid.UUID(idea_id)

    for payload in (
        {"title": None},
        {"stage_id": None},
        {"priority": None},
        {"feasibility": None},
        {"visibility": None},
    ):
        r = client.patch(f"{_ideas_url(ws.id)}/{idea_id}", json=payload, headers=headers)
        assert r.status_code == 422, payload

    row = db.get(Idea, idea_uuid)
    assert row is not None
    assert row.title == "null-test"
    assert row.stage_id == stage.id
    assert row.visibility == IdeaVisibility.WORKSPACE.value
    assert row.priority == "MEDIUM"
    assert row.feasibility == "UNKNOWN"

    r = client.patch(
        f"{_ideas_url(ws.id)}/{idea_id}",
        json={"category_id": None, "assignee_id": None},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["category"] is None
    assert r.json()["assignee"] is None
    db.refresh(row)
    assert row.category_id is None
    assert row.assignee_id is None


def test_inactive_member_cannot_use_share(client: TestClient, db: Session) -> None:
    author, author_pw = _user(db)
    shared, shared_pw = _user(db)
    ws = _team_with_defaults(db, author)
    _add_member(db, ws, shared, status=WorkspaceMemberStatus.INACTIVE.value)

    _login(client, author.email, author_pw)
    # cannot even add share for inactive member
    r = client.post(
        _ideas_url(ws.id),
        json={
            "title": "share inactive",
            "visibility": "SELECTED_USERS",
            "shares": [{"user_id": str(shared.id), "permission": "READ"}],
        },
        headers=_headers(client),
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "SHARE_USER_NOT_ELIGIBLE"

    # If share somehow exists but membership inactive — workspace API 404
    idea = Idea(
        idea_code="IF-900",
        workspace_id=ws.id,
        author_id=author.id,
        title="orphan share",
        stage_id=db.scalar(
            select(WorkspaceStage.id).where(WorkspaceStage.workspace_id == ws.id)
        ),
        visibility=IdeaVisibility.SELECTED_USERS.value,
    )
    db.add(idea)
    db.flush()
    db.add(IdeaShare(idea_id=idea.id, user_id=shared.id, permission="READ"))
    db.commit()

    _login(client, shared.email, shared_pw)
    assert client.get(f"{_ideas_url(ws.id)}/{idea.id}").status_code == 404


def test_visibility_change_clears_shares(client: TestClient, db: Session) -> None:
    author, author_pw = _user(db)
    shared, shared_pw = _user(db)
    ws = _team_with_defaults(db, author)
    _add_member(db, ws, shared)

    _login(client, author.email, author_pw)
    idea_id = client.post(
        _ideas_url(ws.id),
        json={
            "title": "vis change",
            "visibility": "SELECTED_USERS",
            "shares": [{"user_id": str(shared.id), "permission": "READ"}],
        },
        headers=_headers(client),
    ).json()["id"]

    assert (
        client.patch(
            f"{_ideas_url(ws.id)}/{idea_id}",
            json={"visibility": "PRIVATE"},
            headers=_headers(client),
        ).status_code
        == 200
    )
    assert db.scalar(select(func.count()).select_from(IdeaShare).where(IdeaShare.idea_id == uuid.UUID(idea_id))) == 0

    _login(client, shared.email, shared_pw)
    assert client.get(f"{_ideas_url(ws.id)}/{idea_id}").status_code == 404

    _login(client, author.email, author_pw)
    client.patch(
        f"{_ideas_url(ws.id)}/{idea_id}",
        json={"visibility": "SELECTED_USERS"},
        headers=_headers(client),
    )
    # shares not restored
    assert client.get(f"{_ideas_url(ws.id)}/{idea_id}/shares").json() == []


def test_share_replace(client: TestClient, db: Session) -> None:
    author, author_pw = _user(db)
    a, _ = _user(db)
    b, _ = _user(db)
    c, _ = _user(db)
    ws = _team_with_defaults(db, author)
    for u in (a, b, c):
        _add_member(db, ws, u)

    _login(client, author.email, author_pw)
    idea_id = client.post(
        _ideas_url(ws.id),
        json={
            "title": "replace",
            "visibility": "SELECTED_USERS",
            "shares": [
                {"user_id": str(a.id), "permission": "READ"},
                {"user_id": str(b.id), "permission": "EDIT"},
            ],
        },
        headers=_headers(client),
    ).json()["id"]

    r = client.put(
        f"{_ideas_url(ws.id)}/{idea_id}/shares",
        json={
            "shares": [
                {"user_id": str(b.id), "permission": "READ"},
                {"user_id": str(c.id), "permission": "EDIT"},
            ]
        },
        headers=_headers(client),
    )
    assert r.status_code == 200
    by_user = {row["user_id"]: row["permission"] for row in r.json()}
    assert str(a.id) not in by_user
    assert by_user[str(b.id)] == "READ"
    assert by_user[str(c.id)] == "EDIT"


def test_soft_delete(client: TestClient, db: Session) -> None:
    author, password = _user(db)
    ws = _team_with_defaults(db, author)
    _login(client, author.email, password)
    idea_id = client.post(
        _ideas_url(ws.id),
        json={"title": "삭제할것", "visibility": "WORKSPACE"},
        headers=_headers(client),
    ).json()["id"]
    code = client.get(f"{_ideas_url(ws.id)}/{idea_id}").json()["idea_code"]

    assert (
        client.delete(f"{_ideas_url(ws.id)}/{idea_id}", headers=_headers(client)).status_code
        == 204
    )
    assert client.get(f"{_ideas_url(ws.id)}/{idea_id}").status_code == 404
    assert all(i["id"] != idea_id for i in client.get(_ideas_url(ws.id)).json()["items"])
    assert all(
        i["id"] != idea_id
        for i in client.get(_ideas_url(ws.id), params={"q": "삭제할것"}).json()["items"]
    )

    next_idea = client.post(
        _ideas_url(ws.id),
        json={"title": "다음"},
        headers=_headers(client),
    ).json()
    assert next_idea["idea_code"] != code
    assert next_idea["idea_code"] == "IF-002"


def test_search_korean_english_and_acl(client: TestClient, db: Session) -> None:
    author, author_pw = _user(db)
    member, member_pw = _user(db)
    ws = _team_with_defaults(db, author)
    _add_member(db, ws, member)

    _login(client, author.email, author_pw)
    headers = _headers(client)
    private_id = client.post(
        _ideas_url(ws.id),
        json={
            "title": "군 의료 의무기록 자동화",
            "visibility": "PRIVATE",
            "core_concept": "workflow automation platform",
        },
        headers=headers,
    ).json()["id"]
    workspace_id = client.post(
        _ideas_url(ws.id),
        json={
            "title": "공개 의무기록",
            "visibility": "WORKSPACE",
            "core_concept": "workflow automation platform",
        },
        headers=headers,
    ).json()["id"]

    # author sees both korean matches
    kr = client.get(_ideas_url(ws.id), params={"q": "의무기록"}).json()["items"]
    assert {i["id"] for i in kr} >= {private_id, workspace_id}

    en = client.get(_ideas_url(ws.id), params={"q": "automation"}).json()["items"]
    assert {i["id"] for i in en} >= {private_id, workspace_id}

    _login(client, member.email, member_pw)
    kr2 = client.get(_ideas_url(ws.id), params={"q": "의무기록"}).json()["items"]
    ids = {i["id"] for i in kr2}
    assert workspace_id in ids
    assert private_id not in ids


def test_filters_and_pagination(client: TestClient, db: Session) -> None:
    author, password = _user(db)
    ws = _team_with_defaults(db, author)
    stage = db.scalar(
        select(WorkspaceStage).where(
            WorkspaceStage.workspace_id == ws.id,
            WorkspaceStage.slug == "organizing",
        )
    )
    cat = db.scalar(
        select(WorkspaceCategory).where(WorkspaceCategory.workspace_id == ws.id)
    )
    _login(client, author.email, password)
    headers = _headers(client)
    ids = []
    for i in range(5):
        body = {
            "title": f"item-{i}",
            "visibility": "WORKSPACE",
            "priority": "HIGH" if i % 2 == 0 else "LOW",
            "stage_id": str(stage.id) if i == 0 else None,
            "category_id": str(cat.id) if i == 1 else None,
        }
        ids.append(client.post(_ideas_url(ws.id), json=body, headers=headers).json()["id"])

    page1 = client.get(_ideas_url(ws.id), params={"limit": 2, "offset": 0}).json()
    page2 = client.get(_ideas_url(ws.id), params={"limit": 2, "offset": 2}).json()
    assert page1["total"] == 5
    assert len(page1["items"]) == 2
    assert len(page2["items"]) == 2
    assert {i["id"] for i in page1["items"]}.isdisjoint({i["id"] for i in page2["items"]})

    high = client.get(_ideas_url(ws.id), params={"priority": "HIGH"}).json()
    assert all(i["priority"] == "HIGH" for i in high["items"])
    assert high["total"] == 3

    staged = client.get(_ideas_url(ws.id), params={"stage_id": str(stage.id)}).json()
    assert staged["total"] == 1
    assert staged["items"][0]["id"] == ids[0]


def test_mutations_require_csrf_and_password_gate(client: TestClient, db: Session) -> None:
    user, password = _user(db, must_change_password=True)
    ws = _team_with_defaults(db, user)
    _login(client, user.email, password)
    r = client.get(_ideas_url(ws.id))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "PASSWORD_CHANGE_REQUIRED"

    user2, pw2 = _user(db)
    ws2 = _team_with_defaults(db, user2)
    _login(client, user2.email, pw2)
    assert client.post(_ideas_url(ws2.id), json={"title": "x"}).status_code == 403


def test_idea_code_concurrency(engine, db: Session) -> None:
    owner, _ = _user(db)
    ws = _team_with_defaults(db, owner)
    workspace_id = ws.id
    author_id = owner.id
    stage_id = db.scalar(
        select(WorkspaceStage.id).where(
            WorkspaceStage.workspace_id == workspace_id,
            WorkspaceStage.is_default.is_(True),
        )
    )
    barrier = threading.Barrier(2)
    results: list[str] = []
    errors: list[BaseException] = []

    def worker(n: int) -> None:
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        session = factory()
        try:
            author = session.get(User, author_id)
            barrier.wait(timeout=5)
            idea = create_idea(
                session,
                workspace_id=workspace_id,
                author=author,
                payload=IdeaCreate(title=f"concurrent-{n}"),
            )
            session.commit()
            results.append(idea.idea_code)
        except BaseException as exc:  # noqa: BLE001
            session.rollback()
            errors.append(exc)
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker, i) for i in range(2)]
        for f in as_completed(futures):
            f.result()

    assert not errors, errors
    assert sorted(results) == ["IF-001", "IF-002"]
    codes = db.scalars(select(Idea.idea_code).where(Idea.workspace_id == workspace_id)).all()
    assert len(codes) == len(set(codes))
