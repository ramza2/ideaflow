"""Unit tests for HTTP JSON Web Search provider."""

from __future__ import annotations

import json

import httpx
import pytest

from app.core.config import Settings
from app.web_search.exceptions import (
    WebSearchAuthenticationError,
    WebSearchConnectionError,
    WebSearchRateLimitError,
    WebSearchRequestError,
    WebSearchResponseValidationError,
    WebSearchServerError,
    WebSearchTimeoutError,
)
from app.web_search.http_json import HttpJsonWebSearchProvider


def make_settings(**overrides) -> Settings:
    base = dict(
        app_env="test",
        database_url="",
        llm_api_url="https://llm.example.test",
        llm_model_name="Qwen3-14B",
        llm_timeout_seconds=30.0,
        llm_connect_timeout_seconds=5.0,
        ai_job_lease_seconds=300,
        web_search_api_url="https://search.example.test/query",
        web_search_api_key="",
        web_search_timeout_seconds=20.0,
        web_search_connect_timeout_seconds=5.0,
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)


VALID_RESPONSE = {
    "results": [
        {
            "title": "Example",
            "url": "https://example.com/a",
            "snippet": "snippet text",
            "source": "Example",
            "published_at": "2026-08-01",
        }
    ]
}


def test_request_body_query_only() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json=VALID_RESPONSE)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = HttpJsonWebSearchProvider(make_settings(), client=client)
    results = provider.search(query="idea management software", max_results=5)
    assert captured["body"] == {"query": "idea management software", "max_results": 5}
    assert "Authorization" not in captured["headers"]
    assert len(results) == 1
    provider.close()


def test_authorization_when_api_key_set() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json=VALID_RESPONSE)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = HttpJsonWebSearchProvider(
        make_settings(web_search_api_key="secret-key"), client=client
    )
    provider.search(query="test", max_results=3)
    assert captured["auth"] == "Bearer secret-key"
    provider.close()


@pytest.mark.parametrize(
    "status,exc",
    [
        (400, WebSearchRequestError),
        (401, WebSearchAuthenticationError),
        (403, WebSearchAuthenticationError),
        (429, WebSearchRateLimitError),
        (500, WebSearchServerError),
    ],
)
def test_http_status_mapping(status: int, exc: type[Exception]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": "x"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = HttpJsonWebSearchProvider(make_settings(), client=client)
    with pytest.raises(exc):
        provider.search(query="test", max_results=1)
    provider.close()


def test_javascript_url_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {"title": "Bad", "url": "javascript:alert(1)", "snippet": "x"}
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = HttpJsonWebSearchProvider(make_settings(), client=client)
    with pytest.raises(WebSearchResponseValidationError):
        provider.search(query="test", max_results=1)
    provider.close()


def test_invalid_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = HttpJsonWebSearchProvider(make_settings(), client=client)
    with pytest.raises(WebSearchResponseValidationError):
        provider.search(query="test", max_results=1)
    provider.close()
