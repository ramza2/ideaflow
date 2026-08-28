"""Admin integration diagnostics service (Step 11)."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.llm.exceptions import LlmError
from app.llm.factory import get_llm_provider
from app.llm.schemas import CategoryOption, IdeaStructuringRequest
from app.schemas.admin import (
    AdminIntegrationConfigResponse,
    LlmConnectionTestResult,
    LlmIntegrationConfig,
    WebSearchConnectionTestResult,
    WebSearchIntegrationConfig,
    WebSearchTestResultItem,
)
from app.services import system_setting as system_setting_service
from app.models.enums import SystemSettingKey
from app.web_search.exceptions import WebSearchConfigurationError, WebSearchError
from app.web_search.factory import get_web_search_provider

PROBE_INPUT = "회의 내용을 정리해 팀 아이디어로 저장하는 도구"


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


def get_integration_config(db: Session, settings: Settings | None = None) -> AdminIntegrationConfigResponse:
    cfg = settings or get_settings()
    ws_url = sanitize_url_for_display(cfg.web_search_api_url) if cfg.web_search_api_url.strip() else None
    return AdminIntegrationConfigResponse(
        llm=LlmIntegrationConfig(
            provider="openai_compatible",
            api_url=sanitize_url_for_display(cfg.llm_api_url),
            chat_completions_path=cfg.llm_chat_completions_path,
            model_name=cfg.llm_model_name,
            api_key_configured=bool(cfg.llm_api_key.strip()),
            timeout_seconds=cfg.llm_timeout_seconds,
            connect_timeout_seconds=cfg.llm_connect_timeout_seconds,
            max_tokens=cfg.llm_max_tokens,
            temperature=cfg.llm_temperature,
            enable_thinking=cfg.llm_enable_thinking,
            configuration_source="ENVIRONMENT",
        ),
        web_search=WebSearchIntegrationConfig(
            provider=cfg.web_search_provider,
            api_url=ws_url,
            api_key_configured=bool(cfg.web_search_api_key.strip()),
            timeout_seconds=cfg.web_search_timeout_seconds,
            connect_timeout_seconds=cfg.web_search_connect_timeout_seconds,
            max_queries=cfg.web_search_max_queries,
            max_results_per_query=cfg.web_search_max_results_per_query,
            max_total_results=cfg.web_search_max_total_results,
            configured=bool(cfg.web_search_api_url.strip()),
            configuration_source="ENVIRONMENT",
        ),
        global_llm_enabled=system_setting_service.get_bool_setting(
            db, SystemSettingKey.GLOBAL_LLM_ENABLED
        ),
        global_web_search_enabled=system_setting_service.get_bool_setting(
            db, SystemSettingKey.GLOBAL_WEB_SEARCH_ENABLED
        ),
    )


def test_llm_connection(settings: Settings | None = None) -> LlmConnectionTestResult:
    cfg = settings or get_settings()
    provider = get_llm_provider(cfg)
    tested_at = utcnow()
    request = IdeaStructuringRequest(
        input_text=PROBE_INPUT,
        categories=[
            CategoryOption(slug="product_service", name="제품·서비스"),
            CategoryOption(slug="technology_rd", name="기술·R&D"),
        ],
    )
    started = time.perf_counter()
    try:
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
            provider=provider.provider_name,
            model=provider.model_name,
            latency_ms=latency_ms,
            tested_at=tested_at,
            error_code=exc.code,
            retryable=exc.retryable,
            safe_message=str(exc),
        )
    finally:
        provider.close()


def test_web_search_connection(
    query: str,
    settings: Settings | None = None,
) -> WebSearchConnectionTestResult:
    cfg = settings or get_settings()
    tested_at = utcnow()
    if not cfg.web_search_api_url.strip():
        return WebSearchConnectionTestResult(
            status="NOT_CONFIGURED",
            provider=cfg.web_search_provider,
            tested_at=tested_at,
            safe_message="Web search API URL is not configured.",
        )
    provider = get_web_search_provider(cfg)
    started = time.perf_counter()
    try:
        results = provider.search(query, max_results=min(cfg.web_search_max_results_per_query, 5))
        latency_ms = int((time.perf_counter() - started) * 1000)
        items = [
            WebSearchTestResultItem(
                title=item.title,
                url=item.url,
                source=item.source_name,
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
            safe_message=str(exc),
        )
    except WebSearchError as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        return WebSearchConnectionTestResult(
            status="ERROR",
            provider=provider.provider_name,
            latency_ms=latency_ms,
            tested_at=tested_at,
            error_code=exc.code,
            retryable=exc.retryable,
            safe_message=str(exc),
        )
    finally:
        provider.close()
