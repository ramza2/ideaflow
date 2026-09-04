"""Unit tests for AiWorker provider lifecycle (Step 17.6: no process-lifetime cache)."""

from __future__ import annotations

import time

import pytest

from app.core.config import Settings
from app.llm.schemas import IdeaStructuringRequest
from app.services.ai_worker import AiWorker


class CountingProvider:
    provider_name = "counting"
    model_name = "counting-model"
    prompt_version = "v2"
    created = 0
    closed = 0

    def __init__(self) -> None:
        type(self).created += 1
        self.closed_instance = False

    def structure_idea(self, request: IdeaStructuringRequest):
        raise AssertionError("no jobs expected in empty-poll lifecycle test")

    def refine_idea_with_evidence(self, request):
        raise AssertionError("no jobs expected in empty-poll lifecycle test")

    def refine_idea(self, request):
        raise AssertionError("no jobs expected in empty-poll lifecycle test")

    def close(self) -> None:
        if not self.closed_instance:
            self.closed_instance = True
            type(self).closed += 1


def make_settings(**overrides) -> Settings:
    base = dict(
        app_env="test",
        database_url="",
        llm_api_url="https://llm.example.test",
        llm_api_key="",
        llm_model_name="Qwen3-14B",
        llm_chat_completions_path="/v1/chat/completions",
        llm_timeout_seconds=30.0,
        llm_connect_timeout_seconds=5.0,
        llm_temperature=0.2,
        llm_max_tokens=1000,
        llm_enable_thinking=False,
        ai_worker_enabled=True,
        ai_job_lease_seconds=300,
        ai_job_max_attempts=3,
        ai_job_poll_interval_seconds=0.05,
        ai_job_retry_base_seconds=2.0,
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)


def test_worker_does_not_cache_provider_across_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AiWorker must not create a process-lifetime provider; run_once gets none injected."""
    CountingProvider.created = 0
    CountingProvider.closed = 0
    settings = make_settings()
    calls = {"n": 0}

    def fake_run_once(**kwargs):
        calls["n"] += 1
        assert kwargs.get("provider") is None
        assert kwargs.get("search_provider") is None
        assert kwargs.get("settings") is settings
        return False

    monkeypatch.setattr("app.services.ai_worker.run_once", fake_run_once)
    worker = AiWorker(settings=settings, provider_factory=CountingProvider)
    worker.start()
    time.sleep(0.25)
    worker.stop(timeout=2.0)

    assert CountingProvider.created == 0
    assert CountingProvider.closed == 0
    assert calls["n"] >= 2


def test_unexpected_exception_logging_omits_sensitive_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Worker loop errors log category only — not exception message payloads."""

    class Boom(Exception):
        pass

    def boom_run_once(**kwargs):
        raise Boom("SECRET_API_KEY=sk-leak-should-not-appear")

    monkeypatch.setattr("app.services.ai_worker.run_once", boom_run_once)

    logged: list[str] = []

    def capture_error(msg, *args, **kwargs):
        try:
            rendered = msg % args if args else str(msg)
        except Exception:
            rendered = str(msg)
        logged.append(rendered)

    monkeypatch.setattr("app.services.ai_worker.logger.error", capture_error)
    worker = AiWorker(settings=make_settings(), provider_factory=CountingProvider)

    # Run one loop iteration on the main thread.
    def stop_after_wait(*_args, **_kwargs):
        worker._stop.set()
        return True

    monkeypatch.setattr(worker._stop, "wait", stop_after_wait)
    worker._loop()

    joined = " ".join(logged)
    assert logged
    assert "SECRET_API_KEY" not in joined
    assert "sk-leak" not in joined
    assert "Boom" in joined or "ai_worker_loop_error" in joined
