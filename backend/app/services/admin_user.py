"""Admin user management service (Step 11)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import hash_password
from app.models.auth import AuthSession
from app.models.enums import SystemRole, UserStatus
from app.models.user import User
from app.schemas.admin import (
    AdminUserCreateRequest,
    AdminUserPublic,
    AdminUserUpdateRequest,
)
from app.services.auth import normalize_email, revoke_other_sessions_for_user
from app.services.workspace import ensure_personal_workspace_for_user


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _temporary_login_locked(user: User, now: datetime) -> bool:
    return user.locked_until is not None and user.locked_until > now


def _active_session_count(db: Session, user: User, now: datetime) -> int:
    if user.status != UserStatus.ACTIVE.value:
        return 0
    return (
        db.scalar(
            select(func.count())
            .select_from(AuthSession)
            .where(
                AuthSession.user_id == user.id,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
                AuthSession.absolute_expires_at > now,
            )
        )
        or 0
    )


def _last_seen_at(db: Session, user_id: UUID) -> datetime | None:
    return db.scalar(
        select(func.max(AuthSession.last_seen_at)).where(AuthSession.user_id == user_id)
    )


def _to_public(db: Session, user: User, *, current_user_id: UUID, now: datetime) -> AdminUserPublic:
    return AdminUserPublic(
        id=user.id,
        email=user.email,
        name=user.name,
        status=UserStatus(user.status),
        system_role=SystemRole(user.system_role),
        must_change_password=user.must_change_password,
        failed_login_count=user.failed_login_count,
        locked_until=user.locked_until,
        temporary_login_locked=_temporary_login_locked(user, now),
        active_session_count=_active_session_count(db, user, now),
        last_seen_at=_last_seen_at(db, user.id),
        created_at=user.created_at,
        updated_at=user.updated_at,
        is_current_user=user.id == current_user_id,
    )


def _lock_active_system_admins(db: Session) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .where(
                User.system_role == SystemRole.SYSTEM_ADMIN.value,
                User.status == UserStatus.ACTIVE.value,
                User.deleted_at.is_(None),
            )
            .order_by(User.id)
            .with_for_update()
        ).all()
    )


def _ensure_not_last_system_admin(
    db: Session,
    *,
    target: User,
    new_status: str | None = None,
    new_role: str | None = None,
) -> None:
    if target.system_role != SystemRole.SYSTEM_ADMIN.value:
        return
    if target.status != UserStatus.ACTIVE.value:
        return
    would_remove = False
    if new_status in {UserStatus.INACTIVE.value, UserStatus.LOCKED.value}:
        would_remove = True
    if new_role == SystemRole.USER.value:
        would_remove = True
    if not would_remove:
        return
    admins = _lock_active_system_admins(db)
    remaining = [a for a in admins if a.id != target.id]
    if not remaining:
        raise AppError(
            "At least one active system admin is required.",
            code="LAST_SYSTEM_ADMIN_REQUIRED",
            status_code=409,
        )


def list_users(
    db: Session,
    *,
    current_user_id: UUID,
    q: str | None = None,
    status: str | None = None,
    system_role: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AdminUserPublic], int]:
    now = utcnow()
    limit = min(max(limit, 1), 100)
    base = select(User).where(User.deleted_at.is_(None))
    if q:
        term = f"%{q.strip()[:120]}%"
        base = base.where(or_(User.email.ilike(term), User.name.ilike(term)))
    if status:
        base = base.where(User.status == status)
    if system_role:
        base = base.where(User.system_role == system_role)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(base.order_by(User.created_at.desc()).offset(offset).limit(limit)).all()
    return [_to_public(db, row, current_user_id=current_user_id, now=now) for row in rows], total


def create_user(db: Session, *, actor_id: UUID, payload: AdminUserCreateRequest) -> AdminUserPublic:
    normalized = normalize_email(str(payload.email))
    existing = db.scalar(select(User).where(User.email == normalized))
    if existing is not None:
        raise AppError(
            "A user with this email already exists.",
            code="EMAIL_EXISTS",
            status_code=409,
        )
    user = User(
        email=normalized,
        name=payload.name,
        password_hash=hash_password(payload.temporary_password),
        status=UserStatus.ACTIVE.value,
        system_role=payload.system_role.value,
        must_change_password=True,
        failed_login_count=0,
        locked_until=None,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        raise AppError(
            "A user with this email already exists.",
            code="EMAIL_EXISTS",
            status_code=409,
        ) from None
    ensure_personal_workspace_for_user(db, user)
    db.flush()
    return _to_public(db, user, current_user_id=actor_id, now=utcnow())


def update_user(
    db: Session,
    *,
    actor_id: UUID,
    user_id: UUID,
    payload: AdminUserUpdateRequest,
) -> AdminUserPublic:
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise AppError("User not found.", code="USER_NOT_FOUND", status_code=404)

    if user_id == actor_id:
        if payload.status in {UserStatus.INACTIVE, UserStatus.LOCKED}:
            raise AppError("Self status change is forbidden.", code="SELF_PROTECTION", status_code=403)
        if payload.system_role == SystemRole.USER:
            raise AppError("Self role change is forbidden.", code="SELF_PROTECTION", status_code=403)

    if payload.status == UserStatus.WITHDRAWN:
        raise AppError("Withdrawn status is not supported.", code="INVALID_STATUS", status_code=400)

    new_status = payload.status.value if payload.status is not None else None
    new_role = payload.system_role.value if payload.system_role is not None else None
    _ensure_not_last_system_admin(db, target=user, new_status=new_status, new_role=new_role)

    previous_status = user.status
    if payload.name is not None:
        user.name = payload.name
    if payload.status is not None:
        user.status = payload.status.value
        if payload.status == UserStatus.ACTIVE:
            user.failed_login_count = 0
            user.locked_until = None
    if payload.system_role is not None:
        user.system_role = payload.system_role.value

    if (
        payload.status is not None
        and payload.status in {UserStatus.INACTIVE, UserStatus.LOCKED}
        and previous_status == UserStatus.ACTIVE.value
    ):
        revoke_other_sessions_for_user(db, user.id)

    db.flush()
    return _to_public(db, user, current_user_id=actor_id, now=utcnow())


def reset_password(
    db: Session,
    *,
    actor_id: UUID,
    user_id: UUID,
    temporary_password: str,
) -> AdminUserPublic:
    if user_id == actor_id:
        raise AppError("Self password reset is forbidden.", code="SELF_PROTECTION", status_code=403)
    if len(temporary_password) < 10 or len(temporary_password) > 256:
        raise AppError("Invalid password.", code="PASSWORD_INVALID", status_code=400)
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise AppError("User not found.", code="USER_NOT_FOUND", status_code=404)
    user.password_hash = hash_password(temporary_password)
    user.must_change_password = True
    user.failed_login_count = 0
    user.locked_until = None
    revoke_other_sessions_for_user(db, user.id)
    db.flush()
    return _to_public(db, user, current_user_id=actor_id, now=utcnow())


def unlock_login(db: Session, *, actor_id: UUID, user_id: UUID) -> AdminUserPublic:
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise AppError("User not found.", code="USER_NOT_FOUND", status_code=404)
    user.failed_login_count = 0
    user.locked_until = None
    db.flush()
    return _to_public(db, user, current_user_id=actor_id, now=utcnow())
