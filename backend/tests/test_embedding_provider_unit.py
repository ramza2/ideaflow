"""Embedding provider unit tests (mock HTTP)."""

from __future__ import annotations

import json
import logging
import math

import httpx
import pytest

from app.core.config import EMBEDDING_DIMENSION, Settings
from app.embeddings.exceptions import (
    EmbeddingAuthenticationError,
    EmbeddingResponseValidationError,
    EmbeddingServerError,
    EmbeddingTimeoutError,
)
from app.embeddings.fake import FakeEmbeddingProvider
from app.embeddings.exceptions import EmbeddingConfigurationError
from app.embeddings.factory import get_embedding_provider
from app.embeddings.openai_compatible import OpenAICompatibleEmbeddingProvider, _validate_vector


def _settings(**overrides) -> Settings:
    base = {
        "EMBEDDING_ENABLED": True,
        "EMBEDDING_API_URL": "http://embed.test",
        "EMBEDDING_MODEL_NAME": "BAAI/bge-m3",
        "EMBEDDING_DIMENSION": EMBEDDING_DIMENSION,
        "EMBEDDING_TIMEOUT_SECONDS": 5,
        "EMBEDDING_CONNECT_TIMEOUT_SECONDS": 1,
        "APP_ENV": "development",
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)


def _vector(dimension: int = EMBEDDING_DIMENSION) -> list[float]:
    return [0.1] * dimension


def test_openai_compatible_valid_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("Authorization") is None
        body = json.loads(request.content.decode())
        assert body["model"] == "BAAI/bge-m3"
        payload = {"data": [{"embedding": _vector()}]}
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    provider = OpenAICompatibleEmbeddingProvider(_settings(), client=client)
    vec = provider.embed_text("hello")
    assert len(vec) == EMBEDDING_DIMENSION
    provider.close()


def test_openai_compatible_sends_auth_when_key_set() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization", "")
        return httpx.Response(200, json={"data": [{"embedding": _vector()}]})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    provider = OpenAICompatibleEmbeddingProvider(
        _settings(EMBEDDING_API_KEY="secret-key"),
        client=client,
    )
    provider.embed_text("hello")
    assert seen["auth"] == "Bearer secret-key"
    provider.close()


def test_openai_compatible_auth_not_logged(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "bad key"})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    provider = OpenAICompatibleEmbeddingProvider(
        _settings(EMBEDDING_API_KEY="super-secret"),
        client=client,
    )
    with pytest.raises(EmbeddingAuthenticationError):
        provider.embed_text("hello")
    assert "super-secret" not in caplog.text
    provider.close()


@pytest.mark.parametrize(
    "status,exc_type",
    [
        (500, EmbeddingServerError),
        (401, EmbeddingAuthenticationError),
    ],
)
def test_openai_compatible_http_errors(status: int, exc_type: type[Exception]) -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(status, json={}))
    client = httpx.Client(transport=transport)
    provider = OpenAICompatibleEmbeddingProvider(_settings(), client=client)
    with pytest.raises(exc_type):
        provider.embed_text("x")
    provider.close()


def test_openai_compatible_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    provider = OpenAICompatibleEmbeddingProvider(_settings(), client=client)
    with pytest.raises(EmbeddingTimeoutError):
        provider.embed_text("x")
    provider.close()


def test_openai_compatible_malformed_and_dimension() -> None:
    with pytest.raises(EmbeddingResponseValidationError):
        _validate_vector([float("nan")] * EMBEDDING_DIMENSION, dimension=EMBEDDING_DIMENSION)

    transport = httpx.MockTransport(
        lambda r: httpx.Response(200, json={"data": [{"embedding": [0.1] * (EMBEDDING_DIMENSION - 1)}]})
    )
    client = httpx.Client(transport=transport)
    provider = OpenAICompatibleEmbeddingProvider(_settings(), client=client)
    with pytest.raises(EmbeddingResponseValidationError):
        provider.embed_text("x")
    provider.close()


def test_fake_provider_is_deterministic() -> None:
    settings = _settings(EMBEDDING_PROVIDER="fake", APP_ENV="development")
    provider = FakeEmbeddingProvider(settings)
    a = provider.embed_text("alpha")
    b = provider.embed_text("alpha")
    c = provider.embed_text("beta")
    assert a == b
    assert a != c
    assert all(math.isfinite(v) for v in a)


def test_fake_provider_rejected_in_production() -> None:
    settings = _settings(EMBEDDING_PROVIDER="fake", APP_ENV="production", EMBEDDING_ENABLED=True)
    with pytest.raises(EmbeddingConfigurationError, match="fake"):
        get_embedding_provider(settings)


def test_fake_provider_allowed_in_development() -> None:
    settings = _settings(EMBEDDING_PROVIDER="fake", APP_ENV="development", EMBEDDING_ENABLED=True)
    provider = get_embedding_provider(settings)
    assert isinstance(provider, FakeEmbeddingProvider)
    provider.close()


def test_fake_provider_allowed_in_test_env() -> None:
    settings = _settings(EMBEDDING_PROVIDER="fake", APP_ENV="test", EMBEDDING_ENABLED=True)
    provider = get_embedding_provider(settings)
    assert isinstance(provider, FakeEmbeddingProvider)
    provider.close()
