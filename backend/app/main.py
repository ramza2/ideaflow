"""IdeaFlow FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin import router as admin_router
from app.api.ai_sessions import router as ai_sessions_router
from app.api.auth import router as auth_router
from app.api.comments import router as comments_router
from app.api.health import router as health_router
from app.api.ideas import router as ideas_router
from app.api.notifications import router as notifications_router
from app.api.reviews import router as reviews_router
from app.api.web_research import router as web_research_router
from app.api.validations import router as validations_router
from app.api.workspaces import router as workspaces_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.services.ai_worker import AiWorker
from app.services.embedding_worker import EmbeddingWorker

_ai_worker: AiWorker | None = None
_embedding_worker: EmbeddingWorker | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _ai_worker, _embedding_worker
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
    if settings.embedding_worker_enabled and settings.embedding_enabled:
        _embedding_worker = EmbeddingWorker(settings=settings)
        _embedding_worker.start()
    else:
        _embedding_worker = None
        if not settings.embedding_worker_enabled:
            logger.info("Embedding worker disabled (EMBEDDING_WORKER_ENABLED=false)")
        else:
            logger.info("Embedding worker not started (EMBEDDING_ENABLED=false)")
    try:
        yield
    finally:
        if _embedding_worker is not None:
            _embedding_worker.stop()
            _embedding_worker = None
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
    application.include_router(reviews_router, prefix=settings.api_v1_prefix)
    application.include_router(comments_router, prefix=settings.api_v1_prefix)
    application.include_router(notifications_router, prefix=settings.api_v1_prefix)
    application.include_router(admin_router, prefix=settings.api_v1_prefix)
    application.include_router(ai_sessions_router, prefix=settings.api_v1_prefix)
    application.include_router(web_research_router, prefix=settings.api_v1_prefix)
    application.include_router(validations_router, prefix=settings.api_v1_prefix)
    return application


app = create_app()
