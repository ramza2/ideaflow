"""PostgreSQL review / comment / notification integration tests (Step 10)."""

from __future__ import annotations

import os
import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
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
from app.models.idea import Idea
from app.models.relations import IdeaShare
from app.models.user import User
from app.models.workspace import Workspace, WorkspaceMember, WorkspaceStage
from app.services.workspace import seed_workspace_defaults

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="DATABASE_URL not set — skipping collaboration integration tests",
)


@pytest.fixture(autouse=True)
def _clean_collaboration_tables(engine):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM notifications"))
        conn.execute(text("DELETE FROM idea_comment_mentions"))
        conn.execute(text("DELETE FROM idea_comments"))
        conn.execute(text("DELETE FROM idea_review_requests"))
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
) -> tuple[User, str]:
    email = email or f"collab-{uuid.uuid4().hex[:10]}@example.com"
    user = User(
        email=email.lower(),
        name=email.split("@")[0],
        password_hash=hash_password(password),
        status=status,
        system_role=system_role,
        must_change_password=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user, password


def _team(db: Session, owner: User, name: str = "Collab Team") -> Workspace:
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
) -> None:
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


def _ideas_url(workspace_id) -> str:
    return f"/api/v1/workspaces/{workspace_id}/ideas"


def _reviews_url(workspace_id, idea_id) -> str:
    return f"{_ideas_url(workspace_id)}/{idea_id}/reviews"


def _comments_url(workspace_id, idea_id) -> str:
    return f"{_ideas_url(workspace_id)}/{idea_id}/comments"


def _notifications_url(workspace_id) -> str:
    return f"/api/v1/workspaces/{workspace_id}/notifications"


def _review_inbox_url(workspace_id) -> str:
    return f"/api/v1/workspaces/{workspace_id}/review-inbox"


def _share_count(db: Session, idea_id: uuid.UUID) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(IdeaShare)
            .where(IdeaShare.idea_id == idea_id)
        )
        or 0
    )


def _create_idea(
    client: TestClient,
    workspace_id,
    *,
    title: str = "collab idea",
    visibility: str = "WORKSPACE",
    shares: list[dict] | None = None,
    **extra,
) -> dict:
    body: dict = {"title": title, "visibility": visibility, **extra}
    if shares is not None:
        body["shares"] = shares
    r = client.post(_ideas_url(workspace_id), json=body, headers=_headers(client))
    assert r.status_code == 201, r.text
    return r.json()


def test_private_review_rejects_non_author_reviewer_and_admin_404(
    client: TestClient, db: Session
) -> None:
    author, author_pw = _user(db)
    member, _ = _user(db)
    admin, admin_pw = _user(db)
    ws = _team(db, admin)
    _add_member(db, ws, author)
    _add_member(db, ws, member)

    _login(client, author.email, author_pw)
    idea_id = _create_idea(client, ws.id, visibility="PRIVATE")["id"]

    r = client.post(
        _reviews_url(ws.id, idea_id),
        json={"reviewer_id": str(member.id), "kind": "GENERAL"},
        headers=_headers(client),
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "REVIEW_REVIEWER_NOT_ELIGIBLE"

    _login(client, admin.email, admin_pw)
    for path in (
        _reviews_url(ws.id, idea_id),
        _comments_url(ws.id, idea_id),
        f"{_ideas_url(ws.id)}/{idea_id}/eligible-reviewers",
        f"{_ideas_url(ws.id)}/{idea_id}/mention-candidates",
    ):
        assert client.get(path).status_code == 404
        assert client.get(path).json()["error"]["code"] == "IDEA_NOT_FOUND"

    r_post = client.post(
        _reviews_url(ws.id, idea_id),
        json={"reviewer_id": str(member.id)},
        headers=_headers(client),
    )
    assert r_post.status_code == 404


def test_selected_users_reviewer_eligibility_no_share_created(
    client: TestClient, db: Session
) -> None:
    author, author_pw = _user(db)
    shared_b, _ = _user(db)
    outsider_c, _ = _user(db)
    ws = _team(db, author)
    _add_member(db, ws, shared_b)
    _add_member(db, ws, outsider_c)

    _login(client, author.email, author_pw)
    idea = _create_idea(
        client,
        ws.id,
        visibility="SELECTED_USERS",
        shares=[{"user_id": str(shared_b.id), "permission": "READ"}],
    )
    idea_id = idea["id"]
    idea_uuid = uuid.UUID(idea_id)
    shares_before = _share_count(db, idea_uuid)

    ok = client.post(
        _reviews_url(ws.id, idea_id),
        json={"reviewer_id": str(shared_b.id), "kind": "GENERAL"},
        headers=_headers(client),
    )
    assert ok.status_code == 201, ok.text

    bad = client.post(
        _reviews_url(ws.id, idea_id),
        json={"reviewer_id": str(outsider_c.id), "kind": "GENERAL"},
        headers=_headers(client),
    )
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "REVIEW_REVIEWER_NOT_ELIGIBLE"
    assert _share_count(db, idea_uuid) == shares_before
    assert db.scalar(
        select(IdeaShare.id).where(
            IdeaShare.idea_id == idea_uuid,
            IdeaShare.user_id == outsider_c.id,
        )
    ) is None


def test_edit_share_can_request_review_read_share_cannot(
    client: TestClient, db: Session
) -> None:
    author, author_pw = _user(db)
    editor, editor_pw = _user(db)
    reader, reader_pw = _user(db)
    reviewer, _ = _user(db)
    ws = _team(db, author)
    for u in (editor, reader, reviewer):
        _add_member(db, ws, u)

    _login(client, author.email, author_pw)
    idea_id = _create_idea(
        client,
        ws.id,
        visibility="SELECTED_USERS",
        shares=[
            {"user_id": str(editor.id), "permission": "EDIT"},
            {"user_id": str(reader.id), "permission": "READ"},
            {"user_id": str(reviewer.id), "permission": "READ"},
        ],
    )["id"]

    _login(client, editor.email, editor_pw)
    r = client.post(
        _reviews_url(ws.id, idea_id),
        json={"reviewer_id": str(reviewer.id), "kind": "GENERAL"},
        headers=_headers(client),
    )
    assert r.status_code == 201, r.text

    _login(client, reader.email, reader_pw)
    r = client.post(
        _reviews_url(ws.id, idea_id),
        json={"reviewer_id": str(reviewer.id), "kind": "GENERAL"},
        headers=_headers(client),
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "IDEA_EDIT_FORBIDDEN"


def test_duplicate_open_review_returns_409(client: TestClient, db: Session) -> None:
    author, author_pw = _user(db)
    reviewer, _ = _user(db)
    ws = _team(db, author)
    _add_member(db, ws, reviewer)

    _login(client, author.email, author_pw)
    idea_id = _create_idea(client, ws.id, visibility="WORKSPACE")["id"]
    payload = {"reviewer_id": str(reviewer.id), "kind": "GENERAL", "message": "please review"}
    assert (
        client.post(_reviews_url(ws.id, idea_id), json=payload, headers=_headers(client)).status_code
        == 201
    )
    dup = client.post(_reviews_url(ws.id, idea_id), json=payload, headers=_headers(client))
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "REVIEW_ALREADY_OPEN"


def test_review_complete_reviewer_only_stage_unchanged_double_complete_409(
    client: TestClient, db: Session
) -> None:
    author, author_pw = _user(db)
    reviewer, reviewer_pw = _user(db)
    ws = _team(db, author)
    _add_member(db, ws, reviewer)
    stage = db.scalar(
        select(WorkspaceStage).where(
            WorkspaceStage.workspace_id == ws.id,
            WorkspaceStage.slug == "organizing",
        )
    )
    assert stage is not None
    next_review = date.today() + timedelta(days=30)

    _login(client, author.email, author_pw)
    idea_id = _create_idea(
        client,
        ws.id,
        visibility="WORKSPACE",
        stage_id=str(stage.id),
        next_review_date=next_review.isoformat(),
    )["id"]
    idea_uuid = uuid.UUID(idea_id)

    review = client.post(
        _reviews_url(ws.id, idea_id),
        json={"reviewer_id": str(reviewer.id), "kind": "GENERAL"},
        headers=_headers(client),
    ).json()
    review_id = review["id"]

    _login(client, author.email, author_pw)
    forbidden = client.post(
        f"/api/v1/workspaces/{ws.id}/reviews/{review_id}/complete",
        json={"result": "KEEP"},
        headers=_headers(client),
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "REVIEW_COMPLETE_FORBIDDEN"

    _login(client, reviewer.email, reviewer_pw)
    complete = client.post(
        f"/api/v1/workspaces/{ws.id}/reviews/{review_id}/complete",
        json={
            "result": "KEEP",
            "completion_note": "looks good",
            "suggested_next_review_date": (date.today() + timedelta(days=7)).isoformat(),
        },
        headers=_headers(client),
    )
    assert complete.status_code == 200, complete.text
    assert complete.json()["status"] == "COMPLETED"

    row = db.get(Idea, idea_uuid)
    assert row is not None
    assert row.stage_id == stage.id
    assert row.next_review_date == next_review

    again = client.post(
        f"/api/v1/workspaces/{ws.id}/reviews/{review_id}/complete",
        json={"result": "KEEP"},
        headers=_headers(client),
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "REVIEW_ALREADY_COMPLETED"


def test_review_notifications_create_and_complete_no_self(
    client: TestClient, db: Session
) -> None:
    author, author_pw = _user(db)
    reviewer, reviewer_pw = _user(db)
    ws = _team(db, author)
    _add_member(db, ws, reviewer)

    _login(client, author.email, author_pw)
    idea_id = _create_idea(client, ws.id, visibility="WORKSPACE")["id"]
    review_id = client.post(
        _reviews_url(ws.id, idea_id),
        json={"reviewer_id": str(reviewer.id), "kind": "GENERAL"},
        headers=_headers(client),
    ).json()["id"]

    author_notes = client.get(_notifications_url(ws.id)).json()["items"]
    assert all(n["type"] != "REVIEW_REQUESTED" for n in author_notes)

    _login(client, reviewer.email, reviewer_pw)
    reviewer_notes = client.get(_notifications_url(ws.id)).json()["items"]
    requested = [n for n in reviewer_notes if n["type"] == "REVIEW_REQUESTED"]
    assert len(requested) == 1
    assert requested[0]["review_request_id"] == review_id
    assert requested[0]["actor"]["id"] == str(author.id)

    client.post(
        f"/api/v1/workspaces/{ws.id}/reviews/{review_id}/complete",
        json={"result": "KEEP"},
        headers=_headers(client),
    )

    reviewer_after = client.get(_notifications_url(ws.id)).json()["items"]
    assert all(n["type"] != "REVIEW_COMPLETED" for n in reviewer_after)

    _login(client, author.email, author_pw)
    author_after = client.get(_notifications_url(ws.id)).json()["items"]
    completed = [n for n in author_after if n["type"] == "REVIEW_COMPLETED"]
    assert len(completed) == 1
    assert completed[0]["review_request_id"] == review_id
    assert completed[0]["actor"]["id"] == str(reviewer.id)


def test_comment_acl_private_workspace_selected(client: TestClient, db: Session) -> None:
    author, author_pw = _user(db)
    member, member_pw = _user(db)
    shared, shared_pw = _user(db)
    outsider, outsider_pw = _user(db)
    ws = _team(db, author)
    for u in (member, shared, outsider):
        _add_member(db, ws, u)

    _login(client, author.email, author_pw)
    private_id = _create_idea(client, ws.id, visibility="PRIVATE")["id"]
    workspace_id = _create_idea(client, ws.id, visibility="WORKSPACE")["id"]
    selected_id = _create_idea(
        client,
        ws.id,
        visibility="SELECTED_USERS",
        shares=[{"user_id": str(shared.id), "permission": "READ"}],
    )["id"]

    _login(client, member.email, member_pw)
    assert client.get(_comments_url(ws.id, private_id)).status_code == 404
    assert (
        client.post(
            _comments_url(ws.id, private_id),
            json={"body": "nope"},
            headers=_headers(client),
        ).status_code
        == 404
    )
    assert client.post(
        _comments_url(ws.id, workspace_id),
        json={"body": "workspace comment"},
        headers=_headers(client),
    ).status_code == 201
    assert client.get(_comments_url(ws.id, workspace_id)).json()["total"] == 1

    assert client.get(_comments_url(ws.id, selected_id)).status_code == 404
    assert (
        client.post(
            _comments_url(ws.id, selected_id),
            json={"body": "nope"},
            headers=_headers(client),
        ).status_code
        == 404
    )

    _login(client, shared.email, shared_pw)
    assert (
        client.post(
            _comments_url(ws.id, selected_id),
            json={"body": "shared comment"},
            headers=_headers(client),
        ).status_code
        == 201
    )

    _login(client, outsider.email, outsider_pw)
    assert client.get(_comments_url(ws.id, selected_id)).status_code == 404

    _login(client, author.email, author_pw)
    assert client.get(_comments_url(ws.id, private_id)).json()["total"] == 0
    assert (
        client.post(
            _comments_url(ws.id, private_id),
            json={"body": "author private comment"},
            headers=_headers(client),
        ).status_code
        == 201
    )


def test_comment_author_edit_delete_only_admin_cannot_delete_others(
    client: TestClient, db: Session
) -> None:
    author, author_pw = _user(db)
    commenter, commenter_pw = _user(db)
    admin, admin_pw = _user(db)
    ws = _team(db, admin)
    _add_member(db, ws, author)
    _add_member(db, ws, commenter)

    _login(client, author.email, author_pw)
    idea_id = _create_idea(client, ws.id, visibility="WORKSPACE")["id"]

    _login(client, commenter.email, commenter_pw)
    comment_id = client.post(
        _comments_url(ws.id, idea_id),
        json={"body": "original"},
        headers=_headers(client),
    ).json()["id"]

    updated = client.patch(
        f"{_comments_url(ws.id, idea_id)}/{comment_id}",
        json={"body": "edited"},
        headers=_headers(client),
    )
    assert updated.status_code == 200
    assert updated.json()["body"] == "edited"
    assert updated.json()["edited"] is True

    _login(client, admin.email, admin_pw)
    assert (
        client.patch(
            f"{_comments_url(ws.id, idea_id)}/{comment_id}",
            json={"body": "admin edit"},
            headers=_headers(client),
        ).status_code
        == 403
    )
    assert (
        client.delete(
            f"{_comments_url(ws.id, idea_id)}/{comment_id}",
            headers=_headers(client),
        ).status_code
        == 403
    )

    _login(client, commenter.email, commenter_pw)
    assert (
        client.delete(
            f"{_comments_url(ws.id, idea_id)}/{comment_id}",
            headers=_headers(client),
        ).status_code
        == 204
    )
    assert client.get(_comments_url(ws.id, idea_id)).json()["total"] == 0


def test_mention_selected_users_eligibility_no_share_created(
    client: TestClient, db: Session
) -> None:
    author, author_pw = _user(db)
    shared_b, _ = _user(db)
    outsider_c, _ = _user(db)
    ws = _team(db, author)
    _add_member(db, ws, shared_b)
    _add_member(db, ws, outsider_c)

    _login(client, author.email, author_pw)
    idea_id = _create_idea(
        client,
        ws.id,
        visibility="SELECTED_USERS",
        shares=[{"user_id": str(shared_b.id), "permission": "READ"}],
    )["id"]
    idea_uuid = uuid.UUID(idea_id)
    shares_before = _share_count(db, idea_uuid)

    ok = client.post(
        _comments_url(ws.id, idea_id),
        json={"body": "hi @b", "mention_user_ids": [str(shared_b.id)]},
        headers=_headers(client),
    )
    assert ok.status_code == 201, ok.text

    bad = client.post(
        _comments_url(ws.id, idea_id),
        json={"body": "hi @c", "mention_user_ids": [str(outsider_c.id)]},
        headers=_headers(client),
    )
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "COMMENT_MENTION_NOT_ELIGIBLE"
    assert _share_count(db, idea_uuid) == shares_before


def test_mention_notification_and_self_mention_skipped(
    client: TestClient, db: Session
) -> None:
    author, author_pw = _user(db)
    commenter, commenter_pw = _user(db)
    mentioned, mentioned_pw = _user(db)
    ws = _team(db, author)
    _add_member(db, ws, commenter)
    _add_member(db, ws, mentioned)

    _login(client, author.email, author_pw)
    idea_id = _create_idea(client, ws.id, visibility="WORKSPACE")["id"]

    _login(client, commenter.email, commenter_pw)
    client.post(
        _comments_url(ws.id, idea_id),
        json={"body": "ping", "mention_user_ids": [str(mentioned.id)]},
        headers=_headers(client),
    )
    client.post(
        _comments_url(ws.id, idea_id),
        json={"body": "self", "mention_user_ids": [str(commenter.id)]},
        headers=_headers(client),
    )

    _login(client, commenter.email, commenter_pw)
    self_notes = client.get(_notifications_url(ws.id)).json()["items"]
    assert all(n["type"] != "MENTION" for n in self_notes)

    _login(client, mentioned.email, mentioned_pw)
    mention_notes = client.get(_notifications_url(ws.id)).json()["items"]
    mentions = [n for n in mention_notes if n["type"] == "MENTION"]
    assert len(mentions) == 1
    assert mentions[0]["actor"]["id"] == str(commenter.id)


def test_comment_added_vs_mention_notification_precedence(
    client: TestClient, db: Session
) -> None:
    author, author_pw = _user(db)
    commenter, commenter_pw = _user(db)
    ws = _team(db, author)
    _add_member(db, ws, commenter)

    _login(client, author.email, author_pw)
    idea_id = _create_idea(client, ws.id, visibility="WORKSPACE")["id"]

    _login(client, commenter.email, commenter_pw)
    client.post(
        _comments_url(ws.id, idea_id),
        json={"body": "plain comment"},
        headers=_headers(client),
    )

    _login(client, author.email, author_pw)
    notes_plain = client.get(_notifications_url(ws.id)).json()["items"]
    added = [n for n in notes_plain if n["type"] == "COMMENT_ADDED"]
    assert len(added) == 1
    assert all(n["type"] != "MENTION" for n in notes_plain)

    _login(client, commenter.email, commenter_pw)
    client.post(
        _comments_url(ws.id, idea_id),
        json={"body": "@author", "mention_user_ids": [str(author.id)]},
        headers=_headers(client),
    )

    _login(client, author.email, author_pw)
    notes_mention = client.get(_notifications_url(ws.id)).json()["items"]
    mention_only = [n for n in notes_mention if n["type"] == "MENTION"]
    added_after = [n for n in notes_mention if n["type"] == "COMMENT_ADDED"]
    assert len(mention_only) == 1
    assert len(added_after) == 1  # only from the first plain comment


def test_notification_acl_revoked_on_share_removal(client: TestClient, db: Session) -> None:
    author, author_pw = _user(db)
    shared, shared_pw = _user(db)
    ws = _team(db, author)
    _add_member(db, ws, shared)

    _login(client, author.email, author_pw)
    idea_id = _create_idea(
        client,
        ws.id,
        visibility="SELECTED_USERS",
        shares=[{"user_id": str(shared.id), "permission": "READ"}],
    )["id"]
    client.post(
        _reviews_url(ws.id, idea_id),
        json={"reviewer_id": str(shared.id), "kind": "GENERAL"},
        headers=_headers(client),
    )

    _login(client, shared.email, shared_pw)
    assert client.get(f"{_notifications_url(ws.id)}/unread-count").json()["count"] == 1
    assert len(client.get(_notifications_url(ws.id)).json()["items"]) == 1

    _login(client, author.email, author_pw)
    client.put(
        f"{_ideas_url(ws.id)}/{idea_id}/shares",
        json={"shares": []},
        headers=_headers(client),
    )

    _login(client, shared.email, shared_pw)
    assert client.get(f"{_notifications_url(ws.id)}/unread-count").json()["count"] == 0
    assert client.get(_notifications_url(ws.id)).json()["items"] == []


def test_notification_recipient_isolation_404(client: TestClient, db: Session) -> None:
    author, author_pw = _user(db)
    reviewer, reviewer_pw = _user(db)
    other_member, other_pw = _user(db)
    ws = _team(db, author)
    _add_member(db, ws, reviewer)
    _add_member(db, ws, other_member)

    _login(client, author.email, author_pw)
    idea_id = _create_idea(client, ws.id, visibility="WORKSPACE")["id"]
    review_id = client.post(
        _reviews_url(ws.id, idea_id),
        json={"reviewer_id": str(reviewer.id), "kind": "GENERAL"},
        headers=_headers(client),
    ).json()["id"]

    _login(client, reviewer.email, reviewer_pw)
    note_id = client.get(_notifications_url(ws.id)).json()["items"][0]["id"]

    _login(client, other_member.email, other_pw)
    r = client.post(
        f"{_notifications_url(ws.id)}/{note_id}/read",
        headers=_headers(client),
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOTIFICATION_NOT_FOUND"

    _login(client, reviewer.email, reviewer_pw)
    assert (
        client.post(
            f"/api/v1/workspaces/{ws.id}/reviews/{review_id}/complete",
            json={"result": "KEEP"},
            headers=_headers(client),
        ).status_code
        == 200
    )


def test_review_inbox_tabs_and_pending_total_dedup(
    client: TestClient, db: Session
) -> None:
    author, author_pw = _user(db)
    reviewer, reviewer_pw = _user(db)
    mentioner, mentioner_pw = _user(db)
    ws = _team(db, author)
    _add_member(db, ws, reviewer)
    _add_member(db, ws, mentioner)

    today = date.today()
    past = (today - timedelta(days=3)).isoformat()
    future = (today + timedelta(days=5)).isoformat()

    _login(client, author.email, author_pw)
    idea_ws = _create_idea(
        client,
        ws.id,
        visibility="WORKSPACE",
        assignee_id=str(reviewer.id),
    )["id"]
    idea_selected = _create_idea(
        client,
        ws.id,
        visibility="SELECTED_USERS",
        shares=[{"user_id": str(reviewer.id), "permission": "READ"}],
    )["id"]

    client.post(
        _reviews_url(ws.id, idea_ws),
        json={"reviewer_id": str(reviewer.id), "kind": "NEEDS_INFO", "due_date": future},
        headers=_headers(client),
    )
    client.post(
        _reviews_url(ws.id, idea_selected),
        json={"reviewer_id": str(reviewer.id), "kind": "NEXT_STAGE", "due_date": past},
        headers=_headers(client),
    )

    _login(client, mentioner.email, mentioner_pw)
    client.post(
        _comments_url(ws.id, idea_ws),
        json={"body": "fyi", "mention_user_ids": [str(reviewer.id)]},
        headers=_headers(client),
    )

    _login(client, reviewer.email, reviewer_pw)
    counts = client.get(f"{_review_inbox_url(ws.id)}/counts").json()
    assert counts["pending_total"] == 2
    assert counts["scheduled"] == 1
    assert counts["overdue"] == 1
    assert counts["needs_info"] == 1
    assert counts["next_stage"] == 1
    assert counts["assigned"] >= 1
    assert counts["mentioned"] == 1

    scheduled = client.get(_review_inbox_url(ws.id), params={"tab": "scheduled"}).json()
    overdue = client.get(_review_inbox_url(ws.id), params={"tab": "overdue"}).json()
    needs_info = client.get(_review_inbox_url(ws.id), params={"tab": "needs_info"}).json()
    next_stage = client.get(_review_inbox_url(ws.id), params={"tab": "next_stage"}).json()
    assigned = client.get(_review_inbox_url(ws.id), params={"tab": "assigned"}).json()
    mentioned = client.get(_review_inbox_url(ws.id), params={"tab": "mentioned"}).json()

    assert len(scheduled["items"]) >= 1
    assert len(overdue["items"]) >= 1
    assert len(needs_info["items"]) >= 1
    assert len(next_stage["items"]) >= 1
    assert len(assigned["items"]) >= 1
    assert len(mentioned["items"]) >= 1
    assert scheduled["items"][0]["review_request"] is not None
    assert mentioned["items"][0]["comment"] is not None


def test_assignment_notification_on_assignee_patch(client: TestClient, db: Session) -> None:
    author, author_pw = _user(db)
    assignee, assignee_pw = _user(db)
    no_access, _ = _user(db)
    ws = _team(db, author)
    _add_member(db, ws, assignee)
    _add_member(db, ws, no_access)

    _login(client, author.email, author_pw)
    workspace_idea = _create_idea(client, ws.id, visibility="WORKSPACE")["id"]
    private_idea = _create_idea(client, ws.id, visibility="PRIVATE")["id"]

    r = client.patch(
        f"{_ideas_url(ws.id)}/{workspace_idea}",
        json={"assignee_id": str(assignee.id)},
        headers=_headers(client),
    )
    assert r.status_code == 200, r.text

    _login(client, assignee.email, assignee_pw)
    notes = client.get(_notifications_url(ws.id)).json()["items"]
    assigned = [n for n in notes if n["type"] == "ASSIGNED"]
    assert len(assigned) == 1
    assert assigned[0]["idea"]["id"] == workspace_idea

    _login(client, author.email, author_pw)
    client.patch(
        f"{_ideas_url(ws.id)}/{private_idea}",
        json={"assignee_id": str(no_access.id)},
        headers=_headers(client),
    )

    _login(client, no_access.email, "password-ok-1")
    assert all(n["type"] != "ASSIGNED" for n in client.get(_notifications_url(ws.id)).json()["items"])
