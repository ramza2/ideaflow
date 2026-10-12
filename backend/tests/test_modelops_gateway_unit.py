"""Targeted gateway alias and compatibility tests."""

from __future__ import annotations

import json

import httpx
import pytest

from app.core.config import EMBEDDING_DIMENSION, Settings
from app.embeddings.openai_compatible import OpenAICompatibleEmbeddingProvider
from app.llm.exceptions import LlmResponseValidationError
from app.llm.openai_compatible import OpenAICompatibleLlmProvider
from app.llm.schemas import IdeaStructuringRequest


_GATEWAY = "https://model-gateway.example.invalid"


def _settings(**overrides) -> Settings:
    values = {
        "APP_ENV": "test",
        "DATABASE_URL": "",
        "LLM_API_URL": _GATEWAY,
        "LLM_MODEL_NAME": "qwen3-14b",
        "LLM_CHAT_COMPLETIONS_PATH": "/v1/chat/completions",
        "LLM_ENABLE_THINKING": False,
        "AI_WORKER_ENABLED": False,
        "EMBEDDING_ENABLED": True,
        "EMBEDDING_PROVIDER": "openai_compatible",
        "EMBEDDING_API_URL": _GATEWAY,
        "EMBEDDING_MODEL_NAME": "bge-m3",
        "EMBEDDING_PATH": "/v1/embeddings",
        "EMBEDDING_DIMENSION": EMBEDDING_DIMENSION,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _ready_payload() -> dict:
    return {
        "decision": "READY_FOR_REVIEW",
        "draft": {
            "title": "Gateway test",
            "one_line_definition": "Gateway alias request validation",
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


def test_llm_uses_gateway_alias_and_existing_path() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(_ready_payload())}}]},
        )

    provider = OpenAICompatibleLlmProvider(
        _settings(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    provider.structure_idea(IdeaStructuringRequest(input_text="gateway test"))

    assert captured["url"] == f"{_GATEWAY}/v1/chat/completions"
    assert captured["body"]["model"] == "qwen3-14b"
    assert captured["body"]["chat_template_kwargs"] == {"enable_thinking": False}


def test_embedding_uses_gateway_alias_and_keeps_1024_dimensions() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={"data": [{"embedding": [0.1] * EMBEDDING_DIMENSION}]},
        )

    provider = OpenAICompatibleEmbeddingProvider(
        _settings(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    vector = provider.embed_text("gateway embedding test")

    assert captured["url"] == f"{_GATEWAY}/v1/embeddings"
    assert captured["body"]["model"] == "bge-m3"
    assert len(vector) == 1024


def test_think_content_is_not_exposed_in_validation_error() -> None:
    private_reasoning = "PRIVATE_REASONING_SHOULD_NOT_SURFACE"

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": f"<think>{private_reasoning}</think>\n{{}}"
                        }
                    }
                ]
            },
        )

    provider = OpenAICompatibleLlmProvider(
        _settings(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(LlmResponseValidationError) as caught:
        provider.structure_idea(IdeaStructuringRequest(input_text="gateway test"))

    assert private_reasoning not in str(caught.value)
