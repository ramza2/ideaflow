"""FastAPI auth dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.db.session import get_db
from app.models.auth import AuthSession
from app.models.enums import SystemRole
from app.models.user import User
from app.services import auth as auth_service


@dataclass
class AuthContext:
    user: User
    session: AuthSession


def get_current_settings() -> Settings:
    return get_settings()


def get_current_session(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_current_settings)],
) -> AuthContext:
    raw = request.cookies.get(settings.auth_session_cookie_name)
    result = auth_service.get_session_by_raw_token(db, raw, settings=settings)
    if result is None:
        raise AppError("Authentication required.", code="AUTH_REQUIRED", status_code=401)
    # Persist sliding expiration only when this request actually touched the session.
    # Keep this commit scoped to auth so future domain transactions stay independent.
    if result.touched:
        db.commit()
    return AuthContext(user=result.user, session=result.session)


def get_current_user(ctx: Annotated[AuthContext, Depends(get_current_session)]) -> User:
    return ctx.user


def require_csrf(
    ctx: Annotated[AuthContext, Depends(get_current_session)],
    settings: Annotated[Settings, Depends(get_current_settings)],
    request: Request,
    x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> AuthContext:
    cookie_token = request.cookies.get(settings.auth_csrf_cookie_name)
    auth_service.validate_session_csrf(ctx.session, cookie_token, x_csrf_token)
    return ctx


def require_system_admin(
    user: Annotated[User, Depends(require_password_changed)],
) -> User:
    if user.system_role != SystemRole.SYSTEM_ADMIN.value:
        raise AppError("System admin required.", code="FORBIDDEN", status_code=403)
    return user


def require_password_changed(user: Annotated[User, Depends(get_current_user)]) -> User:
    """Block domain APIs until password is changed (for future routes)."""
    if user.must_change_password:
        raise AppError(
            "Password change required.",
            code="PASSWORD_CHANGE_REQUIRED",
            status_code=403,
        )
    return user
