"""Admin integration diagnostics service (Step 11 / Step 17.5 / Step 17.6)."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse, urlunparse
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.embeddings.exceptions import EmbeddingConfigurationError, EmbeddingError
from app.embeddings.factory import get_embedding_provider
from app.llm.exceptions import LlmError
from app.llm.factory import get_llm_provider
from app.llm.schemas import CategoryOption, IdeaStructuringRequest
from app.models.embedding import IdeaEmbedding, IdeaEmbeddingJob
from app.models.enums import IdeaEmbeddingJobStatus, IntegrationKey, SystemSettingKey
from app.models.user import User
from app.schemas.admin import (
    AdminIntegrationConfigResponse,
    AdminUserRef,
    EmbeddingConnectionTestResult,
    EmbeddingIntegrationConfig,
    EmbeddingJobCounts,
    IntegrationConfigAuditItem,
    IntegrationConfigAuditListResponse,
    LlmConnectionTestResult,
    LlmIntegrationConfig,
    WebSearchConnectionTestResult,
    WebSearchIntegrationConfig,
    WebSearchTestResultItem,
)
from app.services import system_setting as system_setting_service
from app.core.errors import AppError
from app.services.integration_runtime_config import (
    RuntimeMeta,
    build_runtime_meta,
    build_runtime_meta_from_row_safe,
    list_config_audits,
    resolve_embedding_settings,
    resolve_llm_settings,
    resolve_web_search_settings,
)
from app.web_search.exceptions import WebSearchConfigurationError, WebSearchError
from app.web_search.factory import get_web_search_provider, is_web_search_configured

logger = logging.getLogger(__name__)

PROBE_INPUT = "회의 내용을 정리해 팀 아이디어로 저장하는 도구"
EMBEDDING_PROBE_TEXT = "IdeaFlow embedding connection test"

_EMBEDDING_SAFE_MESSAGES: dict[str, str] = {
    "EMBEDDING_CONFIGURATION_ERROR": "임베딩이 구성되지 않았거나 설정을 확인할 수 없습니다.",
    "EMBEDDING_UNAVAILABLE": "임베딩 서비스를 사용할 수 없습니다.",
    "EMBEDDING_AUTHENTICATION_ERROR": "임베딩 인증에 실패했습니다.",
    "EMBEDDING_TIMEOUT": "임베딩 요청 시간이 초과되었습니다.",
    "EMBEDDING_REQUEST_ERROR": "임베딩 요청 중 오류가 발생했습니다.",
    "EMBEDDING_CONNECTION_ERROR": "임베딩 서버에 연결할 수 없습니다.",
    "EMBEDDING_SERVER_ERROR": "임베딩 서버 오류가 발생했습니다.",
    "EMBEDDING_RESPONSE_VALIDATION_ERROR": "임베딩 응답이 올바르지 않습니다.",
    "EMBEDDING_DIMENSION_MISMATCH": "임베딩 차원 수가 설정과 일치하지 않습니다.",
    "EMBEDDING_ERROR": "임베딩 처리 중 오류가 발생했습니다.",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def sanitize_url_for_display(url: str) -> str:
    stripped = url.strip()
    if not stripped:
        return ""
    parsed = urlparse(stripped)
    hostname = parsed.hostname or ""
    if parsed.port:
        netloc = f"{hostname}:{parsed.port}"
    else:
        netloc = hostname
    return urlunparse((parsed.scheme, netloc, parsed.path or "", "", "", ""))


def sanitize_path_for_display(path: str) -> str:
    """Strip query/fragment from a path used only in Admin display responses."""
    stripped = path.strip()
    if not stripped:
        return ""
    parsed = urlparse(stripped)
    if parsed.scheme and parsed.netloc:
        return parsed.path or "/"
    return parsed.path or stripped.split("?", 1)[0].split("#", 1)[0]


def _updated_by_ref(meta: RuntimeMeta) -> AdminUserRef | None:
    if meta.updated_by_id is None:
        return None
    return AdminUserRef(id=meta.updated_by_id, name=meta.updated_by_name or "")


def runtime_meta_response_fields(meta: RuntimeMeta) -> dict[str, Any]:
    """Map RuntimeMeta onto Admin integration response fields (never secrets)."""
    return {
        "configuration_source": meta.configuration_source,
        "runtime_override_exists": meta.runtime_override_exists,
        "runtime_revision": meta.runtime_revision,
        "updated_at": meta.updated_at,
        "updated_by": _updated_by_ref(meta),
        "api_key_source": meta.api_key_source,
        "secret_mode": meta.secret_mode,
        "secret_storage_ready": meta.secret_storage_ready,
        "api_key_configured": meta.api_key_configured,
        "runtime_error_code": meta.runtime_error_code,
        "runtime_safe_message": meta.runtime_safe_message,
    }


def _embedding_job_counts(db: Session) -> EmbeddingJobCounts:
    rows = db.execute(
        select(IdeaEmbeddingJob.status, func.count()).group_by(IdeaEmbeddingJob.status)
    ).all()
    counts = {status: int(n) for status, n in rows}
    return EmbeddingJobCounts(
        queued=counts.get(IdeaEmbeddingJobStatus.QUEUED.value, 0),
        running=counts.get(IdeaEmbeddingJobStatus.RUNNING.value, 0),
        succeeded=counts.get(IdeaEmbeddingJobStatus.SUCCEEDED.value, 0),
        failed=counts.get(IdeaEmbeddingJobStatus.FAILED.value, 0),
    )


def _llm_config(effective: Settings, meta: RuntimeMeta) -> LlmIntegrationConfig:
    return LlmIntegrationConfig(
        provider="openai_compatible",
        api_url=sanitize_url_for_display(effective.llm_api_url),
        chat_completions_path=sanitize_path_for_display(effective.llm_chat_completions_path),
        model_name=effective.llm_model_name,
        timeout_seconds=effective.llm_timeout_seconds,
        connect_timeout_seconds=effective.llm_connect_timeout_seconds,
        max_tokens=effective.llm_max_tokens,
        temperature=effective.llm_temperature,
        enable_thinking=effective.llm_enable_thinking,
        # API key is optional for openai_compatible providers (e.g. internal Qwen).
        configured=bool(effective.llm_api_url.strip() and effective.llm_model_name.strip()),
        **runtime_meta_response_fields(meta),
    )


def _web_search_config(effective: Settings, meta: RuntimeMeta) -> WebSearchIntegrationConfig:
    ws_url = (
        sanitize_url_for_display(effective.web_search_api_url)
        if effective.web_search_api_url.strip()
        else None
    )
    return WebSearchIntegrationConfig(
        provider=effective.web_search_provider,
        api_url=ws_url,
        timeout_seconds=effective.web_search_timeout_seconds,
        connect_timeout_seconds=effective.web_search_connect_timeout_seconds,
        max_queries=effective.web_search_max_queries,
        max_results_per_query=effective.web_search_max_results_per_query,
        max_total_results=effective.web_search_max_total_results,
        configured=is_web_search_configured(effective),
        **runtime_meta_response_fields(meta),
    )


def _embedding_config(
    db: Session, effective: Settings, meta: RuntimeMeta
) -> EmbeddingIntegrationConfig:
    url = (
        sanitize_url_for_display(effective.embedding_api_url)
        if effective.embedding_api_url.strip()
        else None
    )
    configured = bool(effective.embedding_enabled and effective.embedding_api_url.strip())
    stored = int(db.scalar(select(func.count()).select_from(IdeaEmbedding)) or 0)
    return EmbeddingIntegrationConfig(
        enabled=bool(effective.embedding_enabled),
        provider=effective.embedding_provider,
        api_url=url,
        embedding_path=sanitize_path_for_display(effective.embedding_path),
        model_name=effective.embedding_model_name,
        dimension=effective.embedding_dimension,
        timeout_seconds=effective.embedding_timeout_seconds,
        connect_timeout_seconds=effective.embedding_connect_timeout_seconds,
        max_input_chars=effective.embedding_max_input_chars,
        worker_enabled=bool(effective.embedding_worker_enabled),
        configured=configured,
        stored_embedding_count=stored,
        job_counts=_embedding_job_counts(db),
        **runtime_meta_response_fields(meta),
    )


def get_integration_config(
    db: Session, settings: Settings | None = None
) -> AdminIntegrationConfigResponse:
    base = settings or get_settings()

    try:
        llm_effective = resolve_llm_settings(db, base_settings=base)
        llm_meta = build_runtime_meta(
            db, IntegrationKey.LLM, base=base, effective=llm_effective
        )
    except AppError as exc:
        llm_effective, llm_meta = build_runtime_meta_from_row_safe(
            db, IntegrationKey.LLM, base=base, error=exc
        )

    try:
        web_search_effective = resolve_web_search_settings(db, base_settings=base)
        web_search_meta = build_runtime_meta(
            db, IntegrationKey.WEB_SEARCH, base=base, effective=web_search_effective
        )
    except AppError as exc:
        web_search_effective, web_search_meta = build_runtime_meta_from_row_safe(
            db, IntegrationKey.WEB_SEARCH, base=base, error=exc
        )

    try:
        embedding_effective = resolve_embedding_settings(db, base_settings=base)
        embedding_meta = build_runtime_meta(
            db, IntegrationKey.EMBEDDING, base=base, effective=embedding_effective
        )
    except AppError as exc:
        embedding_effective, embedding_meta = build_runtime_meta_from_row_safe(
            db, IntegrationKey.EMBEDDING, base=base, error=exc
        )

    return AdminIntegrationConfigResponse(
        llm=_llm_config(llm_effective, llm_meta),
        web_search=_web_search_config(web_search_effective, web_search_meta),
        embedding=_embedding_config(db, embedding_effective, embedding_meta),
        global_llm_enabled=system_setting_service.get_bool_setting(
            db, SystemSettingKey.GLOBAL_LLM_ENABLED
        ),
        global_web_search_enabled=system_setting_service.get_bool_setting(
            db, SystemSettingKey.GLOBAL_WEB_SEARCH_ENABLED
        ),
    )


def test_llm_connection(
    db: Session, settings: Settings | None = None
) -> LlmConnectionTestResult:
    cfg = resolve_llm_settings(db, base_settings=settings)
    tested_at = utcnow()
    provider = None
    started = time.perf_counter()
    try:
        provider = get_llm_provider(cfg)
        request = IdeaStructuringRequest(
            input_text=PROBE_INPUT,
            categories=[
                CategoryOption(slug="product_service", name="제품·서비스"),
                CategoryOption(slug="technology_rd", name="기술·R&D"),
            ],
        )
        result = provider.structure_idea(request)
        del result
        latency_ms = int((time.perf_counter() - started) * 1000)
        return LlmConnectionTestResult(
            status="OK",
            provider=provider.provider_name,
            model=provider.model_name,
            latency_ms=latency_ms,
            tested_at=tested_at,
        )
    except LlmError as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return LlmConnectionTestResult(
            status="ERROR",
            provider=getattr(provider, "provider_name", None),
            model=getattr(provider, "model_name", None),
            latency_ms=latency_ms,
            tested_at=tested_at,
            error_code=exc.code,
            retryable=exc.retryable,
            safe_message=exc.safe_message,
        )
    except Exception:
        logger.exception("Admin LLM diagnostic failed")
        latency_ms = int((time.perf_counter() - started) * 1000)
        return LlmConnectionTestResult(
            status="ERROR",
            provider=getattr(provider, "provider_name", None) if provider is not None else None,
            latency_ms=latency_ms,
            tested_at=tested_at,
            error_code="LLM_ERROR",
            retryable=False,
            safe_message="AI 처리 중 오류가 발생했습니다.",
        )
    finally:
        if provider is not None:
            provider.close()


def test_web_search_connection(
    db: Session,
    query: str,
    settings: Settings | None = None,
) -> WebSearchConnectionTestResult:
    cfg = resolve_web_search_settings(db, base_settings=settings)
    tested_at = utcnow()
    if not cfg.web_search_api_url.strip():
        return WebSearchConnectionTestResult(
            status="NOT_CONFIGURED",
            provider=cfg.web_search_provider,
            tested_at=tested_at,
            error_code="WEB_SEARCH_NOT_CONFIGURED",
            safe_message="Web search API URL is not configured.",
        )
    provider = None
    started = time.perf_counter()
    try:
        provider = get_web_search_provider(cfg)
        results = provider.search(
            query=query,
            max_results=min(cfg.web_search_max_results_per_query, 5),
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        items = [
            WebSearchTestResultItem(
                title=item.title,
                url=item.url,
                source=item.source,
                published_at=item.published_at.isoformat() if item.published_at else None,
            )
            for item in results[:5]
        ]
        return WebSearchConnectionTestResult(
            status="OK",
            provider=provider.provider_name,
            latency_ms=latency_ms,
            result_count=len(results),
            tested_at=tested_at,
            results=items,
        )
    except WebSearchConfigurationError as exc:
        return WebSearchConnectionTestResult(
            status="NOT_CONFIGURED",
            provider=cfg.web_search_provider,
            tested_at=tested_at,
            error_code=exc.code,
            retryable=False,
            safe_message=exc.safe_message,
        )
    except WebSearchError as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return WebSearchConnectionTestResult(
            status="ERROR",
            provider=getattr(provider, "provider_name", None) if provider is not None else None,
            latency_ms=latency_ms,
            tested_at=tested_at,
            error_code=exc.code,
            retryable=exc.retryable,
            safe_message=exc.safe_message,
        )
    except Exception:
        logger.exception("Admin web search diagnostic failed")
        latency_ms = int((time.perf_counter() - started) * 1000)
        return WebSearchConnectionTestResult(
            status="ERROR",
            provider=getattr(provider, "provider_name", None) if provider is not None else None,
            latency_ms=latency_ms,
            tested_at=tested_at,
            error_code="WEB_SEARCH_ERROR",
            retryable=False,
            safe_message="웹 검색 중 오류가 발생했습니다.",
        )
    finally:
        if provider is not None:
            provider.close()


def test_embedding_connection(
    db: Session, settings: Settings | None = None
) -> EmbeddingConnectionTestResult:
    cfg = resolve_embedding_settings(db, base_settings=settings)
    tested_at = utcnow()
    if not cfg.embedding_enabled or not cfg.embedding_api_url.strip():
        return EmbeddingConnectionTestResult(
            status="NOT_CONFIGURED",
            provider=cfg.embedding_provider,
            model=cfg.embedding_model_name,
            dimension=cfg.embedding_dimension,
            tested_at=tested_at,
            error_code="EMBEDDING_NOT_CONFIGURED",
            retryable=False,
            safe_message="임베딩이 비활성화되었거나 API URL이 구성되지 않았습니다.",
        )

    provider = None
    started = time.perf_counter()
    try:
        provider = get_embedding_provider(cfg)
        vector = provider.embed_text(EMBEDDING_PROBE_TEXT)
        latency_ms = int((time.perf_counter() - started) * 1000)
        if not isinstance(vector, list) or len(vector) != cfg.embedding_dimension:
            del vector
            return EmbeddingConnectionTestResult(
                status="ERROR",
                provider=provider.provider_name,
                model=provider.model_name,
                dimension=cfg.embedding_dimension,
                latency_ms=latency_ms,
                tested_at=tested_at,
                error_code="EMBEDDING_DIMENSION_MISMATCH",
                retryable=False,
                safe_message=_EMBEDDING_SAFE_MESSAGES["EMBEDDING_DIMENSION_MISMATCH"],
            )
        del vector
        return EmbeddingConnectionTestResult(
            status="OK",
            provider=provider.provider_name,
            model=provider.model_name,
            dimension=cfg.embedding_dimension,
            latency_ms=latency_ms,
            tested_at=tested_at,
        )
    except EmbeddingConfigurationError as exc:
        return EmbeddingConnectionTestResult(
            status="NOT_CONFIGURED",
            provider=cfg.embedding_provider,
            model=cfg.embedding_model_name,
            dimension=cfg.embedding_dimension,
            tested_at=tested_at,
            error_code=exc.code,
            retryable=False,
            safe_message=_EMBEDDING_SAFE_MESSAGES.get(
                exc.code, _EMBEDDING_SAFE_MESSAGES["EMBEDDING_ERROR"]
            ),
        )
    except EmbeddingError as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return EmbeddingConnectionTestResult(
            status="ERROR",
            provider=getattr(provider, "provider_name", None) if provider is not None else None,
            model=getattr(provider, "model_name", None) if provider is not None else None,
            dimension=cfg.embedding_dimension,
            latency_ms=latency_ms,
            tested_at=tested_at,
            error_code=exc.code,
            retryable=False,
            safe_message=_EMBEDDING_SAFE_MESSAGES.get(
                exc.code, _EMBEDDING_SAFE_MESSAGES["EMBEDDING_ERROR"]
            ),
        )
    except Exception:
        logger.exception("Admin embedding diagnostic failed")
        latency_ms = int((time.perf_counter() - started) * 1000)
        return EmbeddingConnectionTestResult(
            status="ERROR",
            provider=getattr(provider, "provider_name", None) if provider is not None else None,
            dimension=cfg.embedding_dimension,
            latency_ms=latency_ms,
            tested_at=tested_at,
            error_code="EMBEDDING_ERROR",
            retryable=False,
            safe_message=_EMBEDDING_SAFE_MESSAGES["EMBEDDING_ERROR"],
        )
    finally:
        if provider is not None:
            provider.close()


def get_config_audit_list(
    db: Session,
    *,
    integration: IntegrationKey | None = None,
    limit: int = 20,
) -> IntegrationConfigAuditListResponse:
    rows = list_config_audits(db, integration=integration, limit=limit)
    actor_ids = {row.actor_id for row in rows if row.actor_id is not None}
    actors: dict[UUID, User] = {}
    if actor_ids:
        for user in db.execute(select(User).where(User.id.in_(actor_ids))).scalars().all():
            actors[user.id] = user

    items: list[IntegrationConfigAuditItem] = []
    for row in rows:
        actor_ref = None
        if row.actor_id is not None:
            actor = actors.get(row.actor_id)
            actor_ref = AdminUserRef(
                id=row.actor_id,
                name=actor.name if actor is not None else "",
            )
        changed = row.changed_fields if isinstance(row.changed_fields, list) else []
        items.append(
            IntegrationConfigAuditItem(
                id=row.id,
                integration_key=row.integration_key,
                action=row.action,
                changed_fields=[str(f) for f in changed],
                revision=int(row.revision),
                actor=actor_ref,
                created_at=row.created_at,
            )
        )
    return IntegrationConfigAuditListResponse(items=items)
