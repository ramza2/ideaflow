"""Probe configured OpenAI-compatible LLM endpoint (no secrets / raw dumps)."""

from __future__ import annotations

import sys
import time

from app.core.config import get_settings
from app.llm.exceptions import LlmError
from app.llm.factory import get_llm_provider
from app.llm.schemas import CategoryOption, IdeaStructuringRequest

PROBE_INPUT = "회의 내용을 정리해 팀 아이디어로 저장하는 도구"


def main() -> int:
    settings = get_settings()
    provider = get_llm_provider(settings)
    print(f"provider: {provider.provider_name}")
    print(f"model: {provider.model_name}")
    print(f"url_host_path: configured (path={settings.llm_chat_completions_path})")

    request = IdeaStructuringRequest(
        input_text=PROBE_INPUT,
        categories=[
            CategoryOption(slug="product_service", name="제품·서비스"),
            CategoryOption(slug="technology_rd", name="기술·R&D"),
        ],
    )

    started = time.perf_counter()
    try:
        result = provider.structure_idea(request)
        latency_ms = int((time.perf_counter() - started) * 1000)
        print("status: ok")
        print("HTTP: 200")
        print(f"latency_ms: {latency_ms}")
        print("parsed: true")
        print(f"decision: {result.decision.value}")
        return 0
    except LlmError as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        print("status: error")
        print(f"error_code: {exc.code}")
        print(f"retryable: {exc.retryable}")
        print(f"latency_ms: {latency_ms}")
        print("parsed: false")
        print(
            "note: endpoint may still be reachable; "
            "strict JSON-only parsing rejected the message.content shape "
            "(e.g. non-JSON prefix). No raw response is printed."
        )
        # Do not print API keys, prompts, or raw responses.
        return 1
    finally:
        provider.close()


if __name__ == "__main__":
    sys.exit(main())
