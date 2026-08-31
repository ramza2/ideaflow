"""Embedding provider factory."""

from __future__ import annotations

from app.core.config import Settings, get_settings
from app.embeddings.base import EmbeddingProvider
from app.embeddings.exceptions import EmbeddingConfigurationError
from app.embeddings.fake import FakeEmbeddingProvider
from app.embeddings.openai_compatible import OpenAICompatibleEmbeddingProvider


def get_embedding_provider(settings: Settings | None = None) -> EmbeddingProvider:
    cfg = settings or get_settings()
    if not cfg.embedding_enabled:
        raise EmbeddingConfigurationError("Embeddings are disabled (EMBEDDING_ENABLED=false)")

    provider = cfg.embedding_provider.strip().lower()
    if provider == "openai_compatible":
        return OpenAICompatibleEmbeddingProvider(cfg)
    if provider == "fake":
        return FakeEmbeddingProvider(cfg)
    raise EmbeddingConfigurationError(f"Unknown EMBEDDING_PROVIDER: {cfg.embedding_provider}")
