"""Unit tests for Tavily Web Search provider."""

from __future__ import annotations

import json
import logging

import httpx
import pytest

from app.core.config import Settings
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
from app.web_search.factory import get_web_search_provider, is_web_search_configured
from app.web_search.tavily import TavilyWebSearchProvider


def make_settings(**overrides) -> Settings:
    base = dict(
        app_env="test",
        database_url="",
        llm_api_url="https://llm.example.test",
        llm_model_name="Qwen3-14B",
        llm_timeout_seconds=30.0,
        llm_connect_timeout_seconds=5.0,
        ai_job_lease_seconds=300,
        web_search_provider="tavily",
        web_search_api_url="https://api.tavily.com/search",
        web_search_api_key="tvly-test-key",
        web_search_timeout_seconds=20.0,
        web_search_connect_timeout_seconds=5.0,
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)


TAVILY_RESPONSE = {
    "results": [
        {
            "title": "Python Docs",
            "url": "https://docs.python.org/3/",
            "content": "Official Python documentation",
        },
        {
            "title": "PEP 8",
            "url": "https://peps.python.org/pep-0008/",
            "content": "Style guide for Python code",
        },
    ]
}


def test_factory_selects_tavily() -> None:
    provider = get_web_search_provider(make_settings())
    assert isinstance(provider, TavilyWebSearchProvider)
    assert provider.provider_name == "tavily"
    provider.close()


def test_missing_api_url_raises_not_configured() -> None:
    with pytest.raises(WebSearchConfigurationError) as exc_info:
        TavilyWebSearchProvider(make_settings(web_search_api_url=""))
    assert exc_info.value.code == "WEB_SEARCH_NOT_CONFIGURED"


def test_missing_api_key_raises_not_configured() -> None:
    with pytest.raises(WebSearchConfigurationError) as exc_info:
        TavilyWebSearchProvider(make_settings(web_search_api_key=""))
    assert exc_info.value.code == "WEB_SEARCH_NOT_CONFIGURED"


def test_is_web_search_configured_requires_key_for_tavily() -> None:
    assert is_web_search_configured(make_settings()) is True
    assert is_web_search_configured(make_settings(web_search_api_key="")) is False
    assert is_web_search_configured(make_settings(web_search_api_url="")) is False


def test_request_shape_and_auth() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json=TAVILY_RESPONSE)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = TavilyWebSearchProvider(make_settings(), client=client)
    results = provider.search(query="Python programming", max_results=5)
    provider.close()

    assert captured["method"] == "POST"
    assert captured["url"] == "https://api.tavily.com/search"
    assert captured["headers"]["authorization"] == "Bearer tvly-test-key"
    assert captured["headers"]["content-type"] == "application/json"
    assert captured["body"] == {
        "query": "Python programming",
        "max_results": 5,
        "search_depth": "basic",
        "include_answer": False,
        "include_raw_content": False,
        "include_images": False,
    }
    assert len(results) == 2
    assert results[0].title == "Python Docs"
    assert results[0].url == "https://docs.python.org/3/"
    assert results[0].snippet == "Official Python documentation"
    assert results[0].source is None


def test_malformed_item_skipped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {"title": "Good", "url": "https://example.com/good", "content": "ok"},
                    {"title": 123, "url": "https://example.com/bad"},
                    {"url": "https://example.com/no-title"},
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = TavilyWebSearchProvider(make_settings(), client=client)
    results = provider.search(query="test", max_results=3)
    provider.close()
    assert len(results) == 1
    assert results[0].title == "Good"


def test_unsafe_url_item_skipped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {"title": "Bad", "url": "javascript:alert(1)", "content": "x"},
                    {"title": "Good", "url": "https://example.com/safe", "content": "y"},
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = TavilyWebSearchProvider(make_settings(), client=client)
    results = provider.search(query="test", max_results=2)
    provider.close()
    assert len(results) == 1
    assert results[0].url == "https://example.com/safe"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"not-json"),
        httpx.Response(200, json={"results": "not-a-list"}),
        httpx.Response(200, json=[]),
    ],
)
def test_invalid_root_or_results(response: httpx.Response) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return response

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = TavilyWebSearchProvider(make_settings(), client=client)
    with pytest.raises(WebSearchResponseValidationError) as exc_info:
        provider.search(query="test", max_results=1)
    assert exc_info.value.code == "WEB_SEARCH_RESPONSE_INVALID"
    provider.close()


@pytest.mark.parametrize(
    "status,exc",
    [
        (400, WebSearchRequestError),
        (401, WebSearchAuthenticationError),
        (403, WebSearchAuthenticationError),
        (404, WebSearchRequestError),
        (429, WebSearchRateLimitError),
        (500, WebSearchServerError),
        (503, WebSearchServerError),
    ],
)
def test_http_status_mapping(status: int, exc: type[Exception]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"detail": "error"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = TavilyWebSearchProvider(make_settings(), client=client)
    with pytest.raises(exc):
        provider.search(query="test", max_results=1)
    provider.close()


def test_timeout_maps_to_web_search_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = TavilyWebSearchProvider(make_settings(), client=client)
    with pytest.raises(WebSearchTimeoutError):
        provider.search(query="test", max_results=1)
    provider.close()


def test_connection_error_maps_to_web_search_connection_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = TavilyWebSearchProvider(make_settings(), client=client)
    with pytest.raises(WebSearchConnectionError):
        provider.search(query="test", max_results=1)
    provider.close()


def test_api_key_not_logged_on_auth_error(caplog: pytest.LogCaptureFixture) -> None:
    secret = "tvly-super-secret-key-xyz"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "unauthorized"})

    caplog.set_level(logging.WARNING)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = TavilyWebSearchProvider(make_settings(web_search_api_key=secret), client=client)
    with pytest.raises(WebSearchAuthenticationError) as exc_info:
        provider.search(query="test", max_results=1)
    provider.close()

    assert secret not in exc_info.value.safe_message
    assert secret not in caplog.text


def test_api_key_not_in_error_message_on_request_error() -> None:
    secret = "tvly-super-secret-key-xyz"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"detail": "bad request"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = TavilyWebSearchProvider(make_settings(web_search_api_key=secret), client=client)
    with pytest.raises(WebSearchRequestError) as exc_info:
        provider.search(query="test", max_results=1)
    provider.close()
    assert secret not in str(exc_info.value)
