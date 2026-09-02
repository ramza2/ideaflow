"""Tavily Search API Web Search provider."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import Settings
from app.web_search.base import WebSearchResult
from app.web_search.exceptions import (
    WebSearchAuthenticationError,
    WebSearchConfigurationError,
    WebSearchConnectionError,
    WebSearchRateLimitError,
    WebSearchRequestError,
    WebSearchResponseValidationError,
    WebSearchServerError,
    WebSearchTimeoutError,
)
from app.web_search.http_json import _normalize_url, _parse_published_at, _truncate

logger = logging.getLogger(__name__)


class TavilyWebSearchProvider:
    provider_name = "tavily"

    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        if not settings.web_search_api_url.strip() or not settings.web_search_api_key.strip():
            raise WebSearchConfigurationError()
        self._settings = settings
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(
                settings.web_search_timeout_seconds,
                connect=settings.web_search_connect_timeout_seconds,
            ),
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def search(self, *, query: str, max_results: int) -> list[WebSearchResult]:
        url = self._settings.web_search_api_url.strip()
        api_key = self._settings.web_search_api_key.strip()
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
        }

        try:
            response = self._client.post(url, headers=headers, json=body)
        except httpx.TimeoutException as exc:
            logger.warning("web_search_timeout provider=%s", self.provider_name)
            raise WebSearchTimeoutError() from exc
        except httpx.RequestError as exc:
            logger.warning(
                "web_search_connection_error provider=%s category=%s",
                self.provider_name,
                type(exc).__name__,
            )
            raise WebSearchConnectionError() from exc

        self._raise_for_status(response)

        try:
            data = response.json()
        except ValueError as exc:
            raise WebSearchResponseValidationError() from exc

        return self._parse_results(data)

    def _raise_for_status(self, response: httpx.Response) -> None:
        code = response.status_code
        if code == 200:
            return
        if code in {401, 403}:
            raise WebSearchAuthenticationError()
        if code == 429:
            raise WebSearchRateLimitError()
        if code == 400:
            raise WebSearchRequestError()
        if 500 <= code < 600:
            raise WebSearchServerError()
        raise WebSearchRequestError()

    def _parse_item(self, item: Any) -> WebSearchResult | None:
        if not isinstance(item, dict):
            return None
        title = item.get("title")
        url = item.get("url")
        if not isinstance(title, str) or not isinstance(url, str):
            return None
        title_text = _truncate(title, 500) or ""
        if not title_text.strip():
            return None
        url_text = _truncate(url, 2048) or ""
        try:
            url_text = _normalize_url(url_text)
        except WebSearchResponseValidationError:
            return None
        content = item.get("content")
        snippet = _truncate(content if isinstance(content, str) else None, 2000)
        published_at = _parse_published_at(item.get("published_at"))
        return WebSearchResult(
            title=title_text.strip(),
            url=url_text,
            snippet=snippet,
            source=None,
            published_at=published_at,
        )

    def _parse_results(self, data: Any) -> list[WebSearchResult]:
        if not isinstance(data, dict):
            raise WebSearchResponseValidationError()
        raw_results = data.get("results")
        if not isinstance(raw_results, list):
            raise WebSearchResponseValidationError()

        parsed: list[WebSearchResult] = []
        for item in raw_results:
            result = self._parse_item(item)
            if result is not None:
                parsed.append(result)
        return parsed
