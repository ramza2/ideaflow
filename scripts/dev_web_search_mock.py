#!/usr/bin/env python3
"""Minimal http_json Web Search mock for local MVP smoke (not for production)."""

from __future__ import annotations

import argparse
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from pydantic import BaseModel


class SearchBody(BaseModel):
    query: str
    max_results: int = 5


def build_app(*, fail: bool = False) -> FastAPI:
    app = FastAPI(title="IdeaFlow Dev Web Search Mock")
    state = {"fail": fail, "calls": 0}

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "fail": state["fail"], "calls": state["calls"]}

    @app.post("/fail-next")
    def fail_next() -> dict[str, str]:
        state["fail"] = True
        return {"status": "will_fail"}

    @app.post("/recover")
    def recover() -> dict[str, str]:
        state["fail"] = False
        return {"status": "ok"}

    @app.post("/search")
    async def search(body: SearchBody, request: Request) -> dict[str, Any]:
        state["calls"] += 1
        if state["fail"]:
            from fastapi.responses import JSONResponse

            return JSONResponse({"error": "forced failure"}, status_code=503)
        q = body.query
        n = max(1, min(body.max_results, 5))
        results = []
        for i in range(n):
            results.append(
                {
                    "title": f"{q} — 참고 자료 {i + 1}",
                    "url": f"https://example.com/research/{abs(hash(q)) % 10000}/{i + 1}",
                    "snippet": f"{q}에 대한 공개 자료 요약입니다. (mock evidence {i + 1})",
                    "source": "example.com",
                    "published_at": "2026-01-15",
                }
            )
        return {"results": results}

    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8091)
    parser.add_argument("--fail", action="store_true")
    args = parser.parse_args()
    uvicorn.run(build_app(fail=args.fail), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
