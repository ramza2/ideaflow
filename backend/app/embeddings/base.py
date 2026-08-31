"""Embedding provider interface."""

from __future__ import annotations

from typing import Protocol


class EmbeddingProvider(Protocol):
  provider_name: str
  model_name: str

  def embed_text(self, text: str) -> list[float]:
    ...

  def embed_texts(self, texts: list[str]) -> list[list[float]]:
    ...

  def close(self) -> None:
    ...
