"""LLM provider protocol."""

from __future__ import annotations

from typing import Protocol

from app.llm.research_schemas import EvidenceRefinementRequest, EvidenceRefinementResult
from app.llm.schemas import IdeaStructuringRequest, IdeaStructuringResult


class LlmProvider(Protocol):
    provider_name: str
    model_name: str

    def structure_idea(self, request: IdeaStructuringRequest) -> IdeaStructuringResult:
        """Structure a natural-language idea into a validated draft."""
        ...

    def refine_idea_with_evidence(
        self, request: EvidenceRefinementRequest
    ) -> EvidenceRefinementResult:
        """Refine a draft using web search evidence."""
        ...
