"""Authentication service — login, sessions, password change, logout."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    generate_csrf_token,
    generate_session_token,
    hash_password,
    sha256_hex,
    verify_and_update_password,
    verify_password,
)
from app.models.auth import AuthSession
from app.models.enums import SystemRole, UserStatus
from app.models.user import User


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class SessionTokens:
    raw_session_token: str
    raw_csrf_token: str
    session: AuthSession


@dataclass
class SessionLookupResult:
    session: AuthSession
    user: User
    touched: bool = False


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _tokens_match(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    return secrets.compare_digest(left, right)


def set_auth_cookies(
    response,
    *,
    session_token: str,
    csrf_token: str,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    samesite = settings.auth_cookie_samesite
    response.set_cookie(
        settings.auth_session_cookie_name,
        session_token,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=samesite,
        path="/",
        max_age=settings.auth_session_absolute_seconds,
    )
    response.set_cookie(
        settings.auth_csrf_cookie_name,
        csrf_token,
        httponly=False,
        secure=settings.auth_cookie_secure,
        samesite=samesite,
        path="/",
        max_age=settings.auth_session_absolute_seconds,
    )


def clear_auth_cookies(response, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    for name in (settings.auth_session_cookie_name, settings.auth_csrf_cookie_name):
        response.delete_cookie(name, path="/")


def issue_preauth_csrf() -> str:
    return generate_csrf_token()


def validate_preauth_csrf(cookie_token: str | None, header_token: str | None) -> None:
    if not _tokens_match(cookie_token, header_token):
        raise AppError("Invalid CSRF token.", code="CSRF_INVALID", status_code=403)


def validate_session_csrf(
    session: AuthSession,
    cookie_token: str | None,
    header_token: str | None,
) -> None:
    if not _tokens_match(cookie_token, header_token):
        raise AppError("Invalid CSRF token.", code="CSRF_INVALID", status_code=403)
    if not secrets.compare_digest(sha256_hex(cookie_token), session.csrf_token_hash):
        raise AppError("Invalid CSRF token.", code="CSRF_INVALID", status_code=403)


def create_session(
    db: Session,
    user: User,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> SessionTokens:
    settings = settings or get_settings()
    now = now or utcnow()
    raw_session = generate_session_token()
    raw_csrf = generate_csrf_token()
    session = AuthSession(
        user_id=user.id,
        token_hash=sha256_hex(raw_session),
        csrf_token_hash=sha256_hex(raw_csrf),
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(seconds=settings.auth_session_idle_seconds),
        absolute_expires_at=now + timedelta(seconds=settings.auth_session_absolute_seconds),
        ip_address=ip_address,
        user_agent=(user_agent[:512] if user_agent else None),
    )
    db.add(session)
    db.flush()
    return SessionTokens(
        raw_session_token=raw_session,
        raw_csrf_token=raw_csrf,
        session=session,
    )


def revoke_session(session: AuthSession, *, now: datetime | None = None) -> None:
    session.revoked_at = now or utcnow()


def revoke_other_sessions_for_user(
    db: Session,
    user_id: UUID,
    *,
    keep_session_id: UUID | None = None,
    now: datetime | None = None,
) -> int:
    now = now or utcnow()
    stmt = select(AuthSession).where(
        AuthSession.user_id == user_id,
        AuthSession.revoked_at.is_(None),
    )
    if keep_session_id is not None:
        stmt = stmt.where(AuthSession.id != keep_session_id)
    count = 0
    for session in db.scalars(stmt):
        session.revoked_at = now
        count += 1
    return count


def _is_session_valid(session: AuthSession, user: User, now: datetime) -> bool:
    if session.revoked_at is not None:
        return False
    if now >= session.expires_at or now >= session.absolute_expires_at:
        return False
    if user.deleted_at is not None:
        return False
    if user.status != UserStatus.ACTIVE.value:
        return False
    return True


def get_session_by_raw_token(
    db: Session,
    raw_token: str | None,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
    touch: bool = True,
) -> SessionLookupResult | None:
    if not raw_token:
        return None
    settings = settings or get_settings()
    now = now or utcnow()
    token_hash = sha256_hex(raw_token)
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash))
    if session is None:
        return None
    user = db.get(User, session.user_id)
    if user is None or not _is_session_valid(session, user, now):
        return None
    touched = False
    if touch:
        elapsed = (now - session.last_seen_at).total_seconds()
        if elapsed >= settings.auth_session_touch_interval_seconds:
            session.last_seen_at = now
            idle = timedelta(seconds=settings.auth_session_idle_seconds)
            candidate = now + idle
            session.expires_at = min(candidate, session.absolute_expires_at)
            db.flush()
            touched = True
    return SessionLookupResult(session=session, user=user, touched=touched)


def login(
    db: Session,
    *,
    email: str,
    password: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> SessionTokens:
    settings = settings or get_settings()
    now = now or utcnow()
    normalized = normalize_email(email)
    user = db.scalar(select(User).where(User.email == normalized))

    if user is None:
        verify_password(password, DUMMY_PASSWORD_HASH)
        raise AppError("Invalid email or password.", code="INVALID_CREDENTIALS", status_code=401)

    if user.locked_until is not None and user.locked_until > now:
        verify_password(password, DUMMY_PASSWORD_HASH)
        raise AppError("Invalid email or password.", code="INVALID_CREDENTIALS", status_code=401)

    # Temporary lock expired — clear counters before password verification.
    if user.locked_until is not None and user.locked_until <= now:
        user.failed_login_count = 0
        user.locked_until = None

    if user.deleted_at is not None or user.status != UserStatus.ACTIVE.value:
        verify_password(password, DUMMY_PASSWORD_HASH)
        raise AppError("Invalid email or password.", code="INVALID_CREDENTIALS", status_code=401)

    ok, new_hash = verify_and_update_password(password, user.password_hash)
    if not ok:
        user.failed_login_count += 1
        if user.failed_login_count >= settings.auth_login_max_failures:
            user.locked_until = now + timedelta(seconds=settings.auth_login_lock_seconds)
        db.flush()
        raise AppError("Invalid email or password.", code="INVALID_CREDENTIALS", status_code=401)

    if new_hash is not None:
        user.password_hash = new_hash

    user.failed_login_count = 0
    user.locked_until = None
    tokens = create_session(
        db,
        user,
        ip_address=ip_address,
        user_agent=user_agent,
        settings=settings,
        now=now,
    )
    db.flush()
    return tokens


def change_password(
    db: Session,
    *,
    user: User,
    session: AuthSession,
    current_password: str,
    new_password: str,
    now: datetime | None = None,
) -> None:
    now = now or utcnow()
    if not verify_password(current_password, user.password_hash):
        raise AppError("Current password is incorrect.", code="PASSWORD_INVALID", status_code=400)
    if current_password == new_password:
        raise AppError(
            "New password must differ from current password.",
            code="PASSWORD_INVALID",
            status_code=400,
        )
    if len(new_password) < 10 or len(new_password) > 256:
        raise AppError("Invalid password.", code="PASSWORD_INVALID", status_code=400)

    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    user.failed_login_count = 0
    user.locked_until = None
    revoke_other_sessions_for_user(db, user.id, keep_session_id=session.id, now=now)
    db.flush()


def create_admin_user(
    db: Session,
    *,
    email: str,
    name: str,
    password: str,
) -> User:
    if len(password) < 10 or len(password) > 256:
        raise AppError(
            "Password must be 10–256 characters.",
            code="PASSWORD_INVALID",
            status_code=400,
        )
    normalized = normalize_email(email)
    existing = db.scalar(select(User).where(User.email == normalized))
    if existing is not None:
        raise AppError(
            "A user with this email already exists.",
            code="EMAIL_EXISTS",
            status_code=409,
        )
    user = User(
        email=normalized,
        name=name.strip(),
        password_hash=hash_password(password),
        status=UserStatus.ACTIVE.value,
        system_role=SystemRole.SYSTEM_ADMIN.value,
        must_change_password=False,
    )
    db.add(user)
    db.flush()
    return user
