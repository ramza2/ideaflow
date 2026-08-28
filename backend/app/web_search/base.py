"""Web Search provider protocol."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str | None = None
    source: str | None = None
    published_at: datetime | None = None


class WebSearchProvider(Protocol):
    provider_name: str

    def search(
        self,
        *,
        query: str,
        max_results: int,
    ) -> list[WebSearchResult]:
        ...

    def close(self) -> None:
        ...
