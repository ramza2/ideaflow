"""Authentication HTTP endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response, status
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_current_session, get_current_settings, require_csrf
from app.core.config import Settings
from app.core.errors import AppError
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    CsrfResponse,
    LoginRequest,
    LoginResponse,
    PasswordChangeRequest,
    SessionInfo,
    UserProfileUpdateRequest,
    UserPublic,
)
from app.services import auth as auth_service


router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/csrf", response_model=CsrfResponse)
def get_csrf(
    response: Response,
    settings: Annotated[Settings, Depends(get_current_settings)],
) -> CsrfResponse:
    token = auth_service.issue_preauth_csrf()
    response.set_cookie(
        settings.auth_csrf_cookie_name,
        token,
        httponly=False,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        path="/",
        max_age=settings.auth_session_absolute_seconds,
    )
    return CsrfResponse(csrf_token=token)


@router.post("/login", response_model=LoginResponse)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_current_settings)],
    x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> LoginResponse:
    cookie_csrf = request.cookies.get(settings.auth_csrf_cookie_name)
    auth_service.validate_preauth_csrf(cookie_csrf, x_csrf_token)

    try:
        tokens = auth_service.login(
            db,
            email=str(body.email),
            password=body.password,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            settings=settings,
        )
        db.commit()
        db.refresh(tokens.session)
    except AppError:
        # Persist failed_login_count / locked_until even when credentials fail.
        db.commit()
        raise
    except Exception:
        db.rollback()
        raise

    auth_service.set_auth_cookies(
        response,
        session_token=tokens.raw_session_token,
        csrf_token=tokens.raw_csrf_token,
        settings=settings,
    )
    user = db.get(User, tokens.session.user_id)
    assert user is not None
    return LoginResponse(
        user=UserPublic.model_validate(user),
        session=SessionInfo(
            expires_at=tokens.session.expires_at,
            absolute_expires_at=tokens.session.absolute_expires_at,
        ),
    )


@router.get("/me", response_model=UserPublic)
def me(ctx: Annotated[AuthContext, Depends(get_current_session)]) -> UserPublic:
    return UserPublic.model_validate(ctx.user)


@router.patch("/me", response_model=UserPublic)
def update_me(
    body: UserProfileUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_csrf)],
) -> UserPublic:
    """Update the current user's display name only."""
    try:
        user = ctx.user
        user.name = body.name
        db.commit()
        db.refresh(user)
        return UserPublic.model_validate(user)
    except AppError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


@router.patch("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: PasswordChangeRequest,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_csrf)],
) -> None:
    try:
        auth_service.change_password(
            db,
            user=ctx.user,
            session=ctx.session,
            current_password=body.current_password,
            new_password=body.new_password,
        )
        db.commit()
    except AppError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    ctx: Annotated[AuthContext, Depends(require_csrf)],
    settings: Annotated[Settings, Depends(get_current_settings)],
) -> None:
    try:
        auth_service.revoke_session(ctx.session)
        db.commit()
    except Exception:
        db.rollback()
        raise
    # Use the injected Response so delete_cookie Set-Cookie headers are kept.
    auth_service.clear_auth_cookies(response, settings=settings)
