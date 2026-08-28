"""Web Search provider factory."""

from __future__ import annotations

from app.core.config import Settings, get_settings
from app.web_search.base import WebSearchProvider
from app.web_search.exceptions import WebSearchConfigurationError
from app.web_search.http_json import HttpJsonWebSearchProvider


def get_web_search_provider(settings: Settings | None = None) -> WebSearchProvider:
    cfg = settings or get_settings()
    provider = cfg.web_search_provider.strip().lower() or "http_json"
    if provider == "http_json":
        return HttpJsonWebSearchProvider(cfg)
    raise WebSearchConfigurationError(f"Unknown web search provider: {provider}")
