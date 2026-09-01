"""Admin integration diagnostics service (Step 11)."""

from __future__ import annotations

import logging
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
from app.web_search.factory import get_web_search_provider, is_web_search_configured

logger = logging.getLogger(__name__)

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


def sanitize_path_for_display(path: str) -> str:
    """Strip query/fragment from a path used only in Admin display responses."""
    stripped = path.strip()
    if not stripped:
        return ""
    parsed = urlparse(stripped)
    if parsed.scheme and parsed.netloc:
        return parsed.path or "/"
    return parsed.path or stripped.split("?", 1)[0].split("#", 1)[0]


def get_integration_config(db: Session, settings: Settings | None = None) -> AdminIntegrationConfigResponse:
    cfg = settings or get_settings()
    ws_url = sanitize_url_for_display(cfg.web_search_api_url) if cfg.web_search_api_url.strip() else None
    return AdminIntegrationConfigResponse(
        llm=LlmIntegrationConfig(
            provider="openai_compatible",
            api_url=sanitize_url_for_display(cfg.llm_api_url),
            chat_completions_path=sanitize_path_for_display(cfg.llm_chat_completions_path),
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
            configured=is_web_search_configured(cfg),
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
