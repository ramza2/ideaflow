"""Probe configured Web Search endpoint (no secrets / raw dumps)."""

from __future__ import annotations

import sys
import time

from app.core.config import get_settings
from app.web_search.exceptions import WebSearchError
from app.web_search.factory import get_web_search_provider

PROBE_QUERY = "Python programming language official documentation"


def main() -> int:
    settings = get_settings()
    if not settings.web_search_api_url.strip():
        print("provider: http_json")
        print("status: not_configured")
        return 0

    try:
        provider = get_web_search_provider(settings)
    except WebSearchError as exc:
        print(f"provider: {settings.web_search_provider}")
        print("status: not_configured")
        print(f"error_code: {exc.code}")
        return 0

    print(f"provider: {provider.provider_name}")
    started = time.perf_counter()
    try:
        results = provider.search(query=PROBE_QUERY, max_results=3)
        latency_ms = int((time.perf_counter() - started) * 1000)
        domains = sorted({r.url.split("/")[2] for r in results if "://" in r.url})
        print("status: ok")
        print("HTTP: 200")
        print(f"latency_ms: {latency_ms}")
        print(f"result_count: {len(results)}")
        print(f"domains: {', '.join(domains[:5])}")
        return 0
    except WebSearchError as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        print("status: error")
        print(f"error_code: {exc.code}")
        print(f"retryable: {exc.retryable}")
        print(f"latency_ms: {latency_ms}")
        return 1
    finally:
        provider.close()


if __name__ == "__main__":
    sys.exit(main())
