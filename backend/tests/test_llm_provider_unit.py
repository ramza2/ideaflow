"""Unit tests for OpenAI-compatible LLM provider (httpx MockTransport)."""

from __future__ import annotations

import json
import logging

import httpx
import pytest

from app.core.config import Settings
from app.llm.exceptions import (
    LlmAuthenticationError,
    LlmConnectionError,
    LlmRateLimitError,
    LlmRequestError,
    LlmResponseValidationError,
    LlmServerError,
    LlmTimeoutError,
)
from app.llm.openai_compatible import OpenAICompatibleLlmProvider
from app.llm.schemas import IdeaStructuringRequest
from app.models.enums import AiLlmDecision


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
        ai_worker_enabled=False,
        ai_job_lease_seconds=60,
        ai_job_max_attempts=3,
        ai_job_poll_interval_seconds=1.0,
        ai_job_retry_base_seconds=2.0,
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)


READY_JSON = {
    "decision": "READY_FOR_REVIEW",
    "draft": {
        "title": "도구",
        "one_line_definition": None,
        "background": None,
        "problem": None,
        "core_concept": None,
        "major_features": None,
        "expected_effect": None,
        "target_users": None,
        "scenarios": None,
        "challenges": None,
        "minimum_validation": None,
        "related_project": None,
        "category_slug": None,
        "priority": "MEDIUM",
        "feasibility": "UNKNOWN",
        "tags": [],
    },
    "field_provenance": {},
    "clarifying_questions": [],
    "research_recommended": False,
    "research_topics": [],
}


def _ok_handler(request: httpx.Request) -> httpx.Response:
    body = {
        "choices": [{"message": {"content": json.dumps(READY_JSON)}}],
    }
    return httpx.Response(200, json=body)


def test_url_model_messages_and_timeout() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["json"] = json.loads(request.content.decode())
        return _ok_handler(request)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="")
    settings = make_settings()
    provider = OpenAICompatibleLlmProvider(settings, client=client)
    result = provider.structure_idea(IdeaStructuringRequest(input_text="짧은 아이디어"))
    assert result.decision == AiLlmDecision.READY_FOR_REVIEW
    assert captured["url"] == "https://llm.example.test/v1/chat/completions"
    assert captured["json"]["model"] == "Qwen3-14B"
    assert captured["json"]["messages"][0]["role"] == "system"
    assert captured["json"]["messages"][1]["role"] == "user"
    assert "Authorization" not in {k.title(): v for k, v in captured["headers"].items()} or (
        "authorization" not in captured["headers"]
    )
    # httpx lowercases headers
    assert "authorization" not in captured["headers"]


def test_authorization_when_api_key_set() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization")
        return _ok_handler(request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleLlmProvider(
        make_settings(llm_api_key="secret-key"),
        client=client,
    )
    provider.structure_idea(IdeaStructuringRequest(input_text="x"))
    assert captured["auth"] == "Bearer secret-key"


@pytest.mark.parametrize(
    "status,exc",
    [
        (400, LlmRequestError),
        (401, LlmAuthenticationError),
        (403, LlmAuthenticationError),
        (429, LlmRateLimitError),
        (500, LlmServerError),
        (503, LlmServerError),
    ],
)
def test_http_status_mapping(status: int, exc: type) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": "x"})

    provider = OpenAICompatibleLlmProvider(
        make_settings(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(exc) as caught:
        provider.structure_idea(IdeaStructuringRequest(input_text="x"))
    assert caught.value.retryable is (status in (429, 500, 503) or status >= 500)


def test_timeout_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    provider = OpenAICompatibleLlmProvider(
        make_settings(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(LlmTimeoutError) as caught:
        provider.structure_idea(IdeaStructuringRequest(input_text="x"))
    assert caught.value.retryable is True


def test_connection_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    provider = OpenAICompatibleLlmProvider(
        make_settings(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(LlmConnectionError) as caught:
        provider.structure_idea(IdeaStructuringRequest(input_text="x"))
    assert caught.value.retryable is True


def test_malformed_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    provider = OpenAICompatibleLlmProvider(
        make_settings(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(LlmResponseValidationError) as caught:
        provider.structure_idea(IdeaStructuringRequest(input_text="x"))
    assert caught.value.retryable is True


def test_secrets_not_logged(caplog: pytest.LogCaptureFixture) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _ok_handler(request)

    provider = OpenAICompatibleLlmProvider(
        make_settings(llm_api_key="super-secret-key-xyz"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with caplog.at_level(logging.DEBUG):
        provider.structure_idea(
            IdeaStructuringRequest(input_text="매우비밀한사용자아이디어원문XYZ")
        )
    joined = " ".join(r.message for r in caplog.records)
    assert "super-secret-key-xyz" not in joined
    assert "매우비밀한사용자아이디어원문XYZ" not in joined
    assert "Bearer " not in joined


def test_url_join_no_double_slash() -> None:
    settings = make_settings(
        llm_api_url="https://llm.example.test/",
        llm_chat_completions_path="/v1/chat/completions",
    )
    assert settings.llm_chat_completions_url == "https://llm.example.test/v1/chat/completions"
