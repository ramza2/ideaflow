"""Unit tests for AiWorker provider lifecycle and safe logging."""

from __future__ import annotations

import logging
import threading
import time

import pytest

from app.core.config import Settings
from app.llm.schemas import IdeaStructuringRequest
from app.services.ai_worker import AiWorker, run_once


class CountingProvider:
    provider_name = "counting"
    model_name = "counting-model"
    prompt_version = "v1"
    created = 0
    closed = 0

    def __init__(self) -> None:
        type(self).created += 1
        self.closed_instance = False

    def structure_idea(self, request: IdeaStructuringRequest):
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
        ai_job_lease_seconds=60,
        ai_job_max_attempts=3,
        ai_job_poll_interval_seconds=0.05,
        ai_job_retry_base_seconds=2.0,
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)


def test_worker_reuses_provider_and_closes_once(monkeypatch: pytest.MonkeyPatch) -> None:
    CountingProvider.created = 0
    CountingProvider.closed = 0
    settings = make_settings()
    calls = {"n": 0}

    def fake_run_once(**kwargs):
        calls["n"] += 1
        assert kwargs["provider"] is shared["provider"]
        return False

    shared: dict = {}

    def factory():
        p = CountingProvider()
        shared["provider"] = p
        return p

    monkeypatch.setattr("app.services.ai_worker.run_once", fake_run_once)
    worker = AiWorker(settings=settings, provider_factory=factory)
    worker.start()
    time.sleep(0.25)
    worker.stop(timeout=2.0)

    assert CountingProvider.created == 1
    assert CountingProvider.closed == 1
    assert calls["n"] >= 2


def test_unexpected_exception_logging_omits_sensitive_text(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Worker loop errors log category only — not exception message payloads."""

    class Boom(Exception):
        pass

    settings = make_settings(ai_job_poll_interval_seconds=0.05)
    secret = "SECRET_USER_IDEA_TEXT_SHOULD_NOT_APPEAR"

    def boom_run_once(**kwargs):
        raise Boom(f"failed while processing {secret}")

    monkeypatch.setattr("app.services.ai_worker.run_once", boom_run_once)
    worker = AiWorker(settings=settings, provider_factory=CountingProvider)
    with caplog.at_level(logging.ERROR):
        worker.start()
        time.sleep(0.2)
        worker.stop(timeout=2.0)

    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "Boom" in joined or "category=Boom" in joined
    assert secret not in joined
