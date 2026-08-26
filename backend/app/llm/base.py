"""LLM provider protocol."""

from __future__ import annotations

from typing import Protocol

from app.llm.schemas import IdeaStructuringRequest, IdeaStructuringResult


class LlmProvider(Protocol):
    provider_name: str
    model_name: str

    def structure_idea(self, request: IdeaStructuringRequest) -> IdeaStructuringResult:
        """Structure a natural-language idea into a validated draft."""
        ...
