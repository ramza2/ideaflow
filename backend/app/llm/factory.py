"""LLM provider factory."""

from __future__ import annotations

from app.core.config import Settings, get_settings
from app.llm.openai_compatible import OpenAICompatibleLlmProvider


def get_llm_provider(settings: Settings | None = None) -> OpenAICompatibleLlmProvider:
    """Return the configured OpenAI-compatible provider.

    Tests should inject a fake provider into the worker/service rather than
    relying on a process-wide singleton.
    """
    return OpenAICompatibleLlmProvider(settings or get_settings())
