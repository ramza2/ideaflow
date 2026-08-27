"""IdeaFlow FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.ai_sessions import router as ai_sessions_router
from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.ideas import router as ideas_router
from app.api.workspaces import router as workspaces_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.services.ai_worker import AiWorker

_ai_worker: AiWorker | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _ai_worker
    settings = get_settings()
    setup_logging(settings.log_level)
    logger = get_logger("app.main")
    logger.info(
        "Starting %s v%s (env=%s)",
        settings.app_name,
        settings.app_version,
        settings.app_env,
    )
    if settings.ai_worker_enabled:
        _ai_worker = AiWorker(settings=settings)
        _ai_worker.start()
    else:
        _ai_worker = None
        logger.info("AI worker disabled (AI_WORKER_ENABLED=false)")
    try:
        yield
    finally:
        if _ai_worker is not None:
            _ai_worker.stop()
            _ai_worker = None
        logger.info("Shutting down %s", settings.app_name)


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(application)
    application.include_router(health_router, prefix=settings.api_v1_prefix)
    application.include_router(auth_router, prefix=settings.api_v1_prefix)
    application.include_router(workspaces_router, prefix=settings.api_v1_prefix)
    application.include_router(ideas_router, prefix=settings.api_v1_prefix)
    application.include_router(ai_sessions_router, prefix=settings.api_v1_prefix)
    return application


app = create_app()
