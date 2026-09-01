"""Embedding package."""

from app.embeddings.base import EmbeddingProvider
from app.embeddings.canonical import (
    EMBEDDING_CONTENT_FIELDS,
    build_idea_embedding_text,
    compute_content_hash,
    embedding_fields_changed,
    is_embedding_current,
)
from app.embeddings.factory import get_embedding_provider

__all__ = [
    "EmbeddingProvider",
    "EMBEDDING_CONTENT_FIELDS",
    "build_idea_embedding_text",
    "compute_content_hash",
    "embedding_fields_changed",
    "get_embedding_provider",
    "is_embedding_current",
]
