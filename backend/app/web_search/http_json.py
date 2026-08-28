"""Generic HTTP JSON Web Search provider."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

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

logger = logging.getLogger(__name__)

_ALLOWED_URL_SCHEMES = {"http", "https"}
_REJECTED_URL_PREFIXES = ("javascript:", "data:", "file:", "ftp:")


def _normalize_url(url: str) -> str:
    stripped = url.strip()
    lower = stripped.lower()
    for prefix in _REJECTED_URL_PREFIXES:
        if lower.startswith(prefix):
            raise WebSearchResponseValidationError("Rejected URL scheme in search result")
    parsed = urlparse(stripped)
    if parsed.scheme not in _ALLOWED_URL_SCHEMES:
        raise WebSearchResponseValidationError("Invalid URL scheme in search result")
    if not parsed.netloc:
        raise WebSearchResponseValidationError("Invalid URL in search result")
    return stripped


def _truncate(text: str | None, max_len: int) -> str | None:
    if text is None:
        return None
    cleaned = "".join(ch for ch in text if ord(ch) >= 32 or ch in "\n\t")
    return cleaned[:max_len]


def _parse_published_at(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        if len(text) == 10 and text[4] == "-" and text[7] == "-":
            return datetime.fromisoformat(text + "T00:00:00")
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


class HttpJsonWebSearchProvider:
    provider_name = "http_json"

    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        if not settings.web_search_api_url.strip():
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
        headers: dict[str, str] = {"Content-Type": "application/json"}
        api_key = self._settings.web_search_api_key.strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        body = {"query": query, "max_results": max_results}

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

    def _parse_results(self, data: Any) -> list[WebSearchResult]:
        if not isinstance(data, dict):
            raise WebSearchResponseValidationError()
        raw_results = data.get("results")
        if not isinstance(raw_results, list):
            raise WebSearchResponseValidationError()

        parsed: list[WebSearchResult] = []
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            title = item.get("title")
            url = item.get("url")
            if not isinstance(title, str) or not isinstance(url, str):
                continue
            title = _truncate(title, 500) or ""
            url = _normalize_url(_truncate(url, 2048) or "")
            snippet = _truncate(item.get("snippet") if item.get("snippet") is not None else None, 2000)
            source = _truncate(item.get("source") if item.get("source") is not None else None, 255)
            published_at = _parse_published_at(item.get("published_at"))
            if not title.strip():
                continue
            parsed.append(
                WebSearchResult(
                    title=title.strip(),
                    url=url,
                    snippet=snippet,
                    source=source,
                    published_at=published_at,
                )
            )
        return parsed
