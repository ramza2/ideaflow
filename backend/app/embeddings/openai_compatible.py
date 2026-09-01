"""OpenAI-compatible HTTP embedding provider."""

from __future__ import annotations

import logging
import math
from typing import Any

import httpx

from app.core.config import EMBEDDING_DIMENSION, Settings
from app.embeddings.exceptions import (
    EmbeddingAuthenticationError,
    EmbeddingConfigurationError,
    EmbeddingConnectionError,
    EmbeddingRequestError,
    EmbeddingResponseValidationError,
    EmbeddingServerError,
    EmbeddingTimeoutError,
)

logger = logging.getLogger(__name__)


def _validate_vector(values: list[float], *, dimension: int) -> list[float]:
    if len(values) != dimension:
        raise EmbeddingResponseValidationError(
            f"Embedding dimension mismatch: expected {dimension}, got {len(values)}"
        )
    for value in values:
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise EmbeddingResponseValidationError("Embedding contains non-finite values")
    return [float(v) for v in values]


class OpenAICompatibleEmbeddingProvider:
    provider_name = "openai_compatible"

    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        if not settings.embedding_api_url.strip():
            raise EmbeddingConfigurationError("EMBEDDING_API_URL is not configured")
        if not settings.embedding_model_name.strip():
            raise EmbeddingConfigurationError("EMBEDDING_MODEL_NAME is not configured")

        self._settings = settings
        self.model_name = settings.embedding_model_name
        self._dimension = settings.embedding_dimension
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(
                settings.embedding_timeout_seconds,
                connect=settings.embedding_connect_timeout_seconds,
            ),
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    @property
    def embeddings_url(self) -> str:
        base = self._settings.embedding_api_url.rstrip("/")
        path = self._settings.embedding_path.strip() or "/v1/embeddings"
        if not path.startswith("/"):
            path = "/" + path
        return f"{base}{path}"

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        headers: dict[str, str] = {"Content-Type": "application/json"}
        api_key = self._settings.embedding_api_key.strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        body: dict[str, Any] = {
            "model": self.model_name,
            "input": texts,
        }

        try:
            response = self._client.post(self.embeddings_url, headers=headers, json=body)
        except httpx.TimeoutException as exc:
            raise EmbeddingTimeoutError("Embedding request timed out") from exc
        except httpx.ConnectError as exc:
            raise EmbeddingConnectionError("Embedding connection failed") from exc
        except httpx.RequestError as exc:
            raise EmbeddingRequestError(f"Embedding request failed: {exc}") from exc

        if response.status_code in {401, 403}:
            raise EmbeddingAuthenticationError("Embedding authentication failed")
        if response.status_code >= 500:
            raise EmbeddingServerError(f"Embedding server error: HTTP {response.status_code}")
        if response.status_code >= 400:
            raise EmbeddingRequestError(f"Embedding request rejected: HTTP {response.status_code}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise EmbeddingResponseValidationError("Embedding response is not valid JSON") from exc

        data = payload.get("data")
        if not isinstance(data, list) or len(data) != len(texts):
            raise EmbeddingResponseValidationError("Embedding response missing data array")

        vectors: list[list[float]] = []
        for item in data:
            if not isinstance(item, dict):
                raise EmbeddingResponseValidationError("Embedding data item must be an object")
            embedding = item.get("embedding")
            if not isinstance(embedding, list):
                raise EmbeddingResponseValidationError("Embedding data item missing embedding array")
            vectors.append(_validate_vector(embedding, dimension=self._dimension))
        return vectors
