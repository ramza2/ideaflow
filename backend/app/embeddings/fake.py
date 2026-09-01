"""Deterministic test-only embedding provider."""

from __future__ import annotations

import hashlib
import math

from app.core.config import Settings


class FakeEmbeddingProvider:
    """Hash-based deterministic vectors for tests only."""

    provider_name = "fake"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.model_name = settings.embedding_model_name

    def close(self) -> None:
        return None

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [_text_to_vector(text, dimension=self._settings.embedding_dimension) for text in texts]


def _text_to_vector(text: str, *, dimension: int) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values: list[float] = []
    idx = 0
    while len(values) < dimension:
        chunk = digest[idx % len(digest) : (idx % len(digest)) + 4]
        if len(chunk) < 4:
            digest = hashlib.sha256(digest).digest()
            idx = 0
            continue
        raw = int.from_bytes(chunk.ljust(4, b"\x00")[:4], "big", signed=False)
        values.append((raw / 2**32) * 2 - 1)
        idx += 4
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]
