"""Health check endpoints."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import get_engine

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "service": "ideaflow-backend",
        "version": settings.app_version,
    }


@router.get("/health/ready", response_model=None)
def health_ready() -> JSONResponse:
    """Database readiness probe (does not call LLM or Web Search)."""
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
    return JSONResponse(
        content={
            "status": "ready",
            "service": "ideaflow-backend",
        },
    )
