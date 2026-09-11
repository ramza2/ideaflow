"""Health check endpoints."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import get_engine

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness: process is up. Does not check DB or remote AI."""
    settings = get_settings()
    payload = {
        "status": "ok",
        "service": "ideaflow-backend",
        "version": settings.app_version,
        "env": settings.app_env,
    }
    if settings.build_git_sha.strip():
        payload["git_sha"] = settings.build_git_sha.strip()
    return payload


@router.get("/health/ready", response_model=None)
def health_ready() -> JSONResponse:
    """Database readiness probe (does not call LLM, Web Search, or Embedding)."""
    settings = get_settings()
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "service": "ideaflow-backend",
            },
        )
    body: dict[str, str] = {
        "status": "ready",
        "service": "ideaflow-backend",
        "version": settings.app_version,
    }
    if settings.build_git_sha.strip():
        body["git_sha"] = settings.build_git_sha.strip()
    return JSONResponse(content=body)
