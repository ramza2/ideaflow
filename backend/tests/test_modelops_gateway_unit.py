"""Targeted ModelOps Gateway alias, token-count, and compatibility tests."""

from __future__ import annotations

import json
import uuid

import httpx
import pytest

from app.core.config import EMBEDDING_DIMENSION, Settings
from app.embeddings.openai_compatible import OpenAICompatibleEmbeddingProvider
from app.llm.exceptions import (
    LlmOutputLengthError,
    LlmRateLimitError,
    LlmRequestError,
    LlmResponseValidationError,
    LlmServerError,
    LlmUnavailableError,
)
from app.llm.openai_compatible import OpenAICompatibleLlmProvider
from app.llm.refine_schemas import IdeaRefinementRequest
from app.llm.research_schemas import EvidenceInput, EvidenceRefinementRequest
from app.llm.schemas import IdeaStructuringRequest
from app.models.enums import IdeaRefineDirection


_GATEWAY = "https://model-gateway.example.invalid"
_DEPLOYMENT = "dep-a"
_ROUTE = "route-a"


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


def _token_count_response(
    prompt_tokens: int,
    *,
    context_window: int = 8192,
    deployment_id: str = _DEPLOYMENT,
    route_id: str = _ROUTE,
    routing_version: int = 1,
) -> dict:
    return {
        "object": "modelops.token_count",
        "model": "qwen3-14b",
        "prompt_tokens": prompt_tokens,
        "context_window": context_window,
        "status": "VERIFIED",
        "deployment_id": deployment_id,
        "route_id": route_id,
        "routing_version": routing_version,
    }


def _capability_response(
    *,
    context_window: int = 8192,
    deployment_id: str = _DEPLOYMENT,
    route_id: str = _ROUTE,
    routing_version: int = 1,
) -> dict:
    return {
        "id": "qwen3-14b",
        "object": "model.capabilities",
        "status": "VERIFIED",
        "context_window": context_window,
        "supports_thinking": True,
        "supports_tools": True,
        "source": "CURRENT_CONTAINER_ARGV",
        "evidence_reason": "CURRENT_CONTAINER_ARGV_VERIFIED",
        "observed_at": "2026-10-19T00:00:00Z",
        "deployment_id": deployment_id,
        "route_id": route_id,
        "routing_version": routing_version,
    }


def test_llm_uses_gateway_alias_and_token_count_matches_chat_prompt() -> None:
    captured: dict[str, list[dict]] = {"count": [], "chat": []}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode()) if request.content else {}
        if request.url.path == "/v1/token-count":
            captured["count"].append(body)
            return httpx.Response(200, json=_token_count_response(100))
        if request.url.path == "/v1/models/qwen3-14b/capabilities":
            return httpx.Response(200, json=_capability_response())
        if request.url.path == "/v1/chat/completions":
            captured["chat"].append(body)
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {"content": json.dumps(_ready_payload())},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 100},
                },
            )
        raise AssertionError(f"unexpected path: {request.url.path}")

    provider = OpenAICompatibleLlmProvider(
        _settings(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    provider.structure_idea(IdeaStructuringRequest(input_text="gateway test"))

    count_body = captured["count"][0]
    chat_body = captured["chat"][0]
    assert count_body["model"] == chat_body["model"] == "qwen3-14b"
    assert count_body["messages"] == chat_body["messages"]
    assert count_body["chat_template_kwargs"] == chat_body["chat_template_kwargs"] == {
        "enable_thinking": False
    }
    assert chat_body["max_tokens"] == int(8192 * 0.30)


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
        if request.url.path == "/v1/token-count":
            return httpx.Response(200, json=_token_count_response(100))
        if request.url.path.endswith("/capabilities"):
            return httpx.Response(200, json=_capability_response())
        if request.url.path == "/v1/chat/completions":
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": f"<think>{private_reasoning}</think>\n{{}}"
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 100},
                },
            )
        raise AssertionError(request.url.path)

    provider = OpenAICompatibleLlmProvider(
        _settings(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(LlmResponseValidationError) as caught:
        provider.structure_idea(IdeaStructuringRequest(input_text="gateway test"))

    assert private_reasoning not in str(caught.value)


@pytest.mark.parametrize(
    "status,expected",
    [
        (503, LlmServerError),
        (422, LlmRequestError),
        (413, LlmRequestError),
        (429, LlmRateLimitError),
    ],
)
def test_token_count_failures_never_fall_back_to_guessed_tokens(
    status: int, expected: type[Exception]
) -> None:
    chat_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal chat_calls
        if request.url.path == "/v1/token-count":
            return httpx.Response(status, json={"error": {"code": "x"}})
        if request.url.path == "/v1/chat/completions":
            chat_calls += 1
        return httpx.Response(500)

    provider = OpenAICompatibleLlmProvider(
        _settings(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(expected):
        provider.structure_idea(IdeaStructuringRequest(input_text="x"))
    assert chat_calls == 0


def test_token_count_unknown_is_fail_closed() -> None:
    chat_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal chat_calls
        if request.url.path == "/v1/token-count":
            body = _token_count_response(100)
            body["status"] = "UNKNOWN"
            body["context_window"] = None
            return httpx.Response(200, json=body)
        if request.url.path == "/v1/chat/completions":
            chat_calls += 1
        return httpx.Response(500)

    provider = OpenAICompatibleLlmProvider(
        _settings(), client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(LlmUnavailableError):
        provider.structure_idea(IdeaStructuringRequest(input_text="x"))
    assert chat_calls == 0


def test_route_change_recounts_before_chat() -> None:
    count_calls = 0
    chat_bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal count_calls
        body = json.loads(request.content.decode()) if request.content else {}
        if request.url.path == "/v1/token-count":
            count_calls += 1
            if count_calls == 1:
                return httpx.Response(
                    200,
                    json=_token_count_response(
                        100,
                        context_window=8192,
                        deployment_id="dep-old",
                        route_id="route-old",
                        routing_version=10,
                    ),
                )
            return httpx.Response(
                200,
                json=_token_count_response(
                    100,
                    context_window=12288,
                    deployment_id="dep-new",
                    route_id="route-new",
                    routing_version=11,
                ),
            )
        if request.url.path.endswith("/capabilities"):
            return httpx.Response(
                200,
                json=_capability_response(
                    context_window=12288,
                    deployment_id="dep-new",
                    route_id="route-new",
                    routing_version=11,
                ),
            )
        if request.url.path == "/v1/chat/completions":
            chat_bodies.append(body)
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {"content": json.dumps(_ready_payload())},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 100},
                },
            )
        raise AssertionError(request.url.path)

    provider = OpenAICompatibleLlmProvider(
        _settings(), client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    provider.structure_idea(IdeaStructuringRequest(input_text="route switch"))
    assert count_calls == 2
    assert len(chat_bodies) == 1
    assert chat_bodies[0]["max_tokens"] == 2500


def test_route_change_after_chat_discards_result_and_rebudgets() -> None:
    route_version = 1
    chat_calls = 0
    count_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal route_version, chat_calls, count_calls
        if request.url.path == "/v1/token-count":
            count_calls += 1
            if route_version == 1:
                return httpx.Response(
                    200,
                    json=_token_count_response(
                        100,
                        context_window=8192,
                        deployment_id="dep-a",
                        route_id="route-a",
                        routing_version=1,
                    ),
                )
            return httpx.Response(
                200,
                json=_token_count_response(
                    100,
                    context_window=12288,
                    deployment_id="dep-b",
                    route_id="route-b",
                    routing_version=2,
                ),
            )
        if request.url.path.endswith("/capabilities"):
            if route_version == 1:
                return httpx.Response(
                    200,
                    json=_capability_response(
                        context_window=8192,
                        deployment_id="dep-a",
                        route_id="route-a",
                        routing_version=1,
                    ),
                )
            return httpx.Response(
                200,
                json=_capability_response(
                    context_window=12288,
                    deployment_id="dep-b",
                    route_id="route-b",
                    routing_version=2,
                ),
            )
        if request.url.path == "/v1/chat/completions":
            chat_calls += 1
            title = "discarded old route" if chat_calls == 1 else "accepted new route"
            payload = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {**_ready_payload(), "draft": {**_ready_payload()["draft"], "title": title}}
                            )
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 100},
            }
            if chat_calls == 1:
                route_version = 2
            return httpx.Response(200, json=payload)
        raise AssertionError(request.url.path)

    provider = OpenAICompatibleLlmProvider(
        _settings(), client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    result = provider.structure_idea(IdeaStructuringRequest(input_text="route changes after chat"))

    assert result.draft.title == "accepted new route"
    assert chat_calls == 2
    assert count_calls == 2


def test_finish_reason_length_reduces_input_and_never_parses_truncated_json() -> None:
    count_messages: list[list[dict]] = []
    chat_messages: list[list[dict]] = []
    chat_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal chat_calls
        body = json.loads(request.content.decode()) if request.content else {}
        if request.url.path == "/v1/token-count":
            count_messages.append(body["messages"])
            return httpx.Response(200, json=_token_count_response(200))
        if request.url.path.endswith("/capabilities"):
            return httpx.Response(200, json=_capability_response())
        if request.url.path == "/v1/chat/completions":
            chat_calls += 1
            chat_messages.append(body["messages"])
            if chat_calls == 1:
                return httpx.Response(
                    200,
                    json={
                        "choices": [
                            {
                                "message": {"content": '{"decision":"READY'},
                                "finish_reason": "length",
                            }
                        ],
                        "usage": {"prompt_tokens": 200},
                    },
                )
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {"content": json.dumps(_ready_payload())},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 200},
                },
            )
        raise AssertionError(request.url.path)

    provider = OpenAICompatibleLlmProvider(
        _settings(), client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    result = provider.structure_idea(
        IdeaStructuringRequest(input_text="x" * 4000)
    )
    assert result.draft.title == "Gateway test"
    assert chat_calls == 2
    assert len(chat_messages[1][1]["content"]) < len(chat_messages[0][1]["content"])
    assert len(count_messages) >= 2


def test_repeated_finish_reason_length_fails_without_accepting_partial_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode()) if request.content else {}
        if request.url.path == "/v1/token-count":
            return httpx.Response(200, json=_token_count_response(100))
        if request.url.path.endswith("/capabilities"):
            return httpx.Response(200, json=_capability_response())
        if request.url.path == "/v1/chat/completions":
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {"content": '{"decision":"READY'},
                            "finish_reason": "length",
                        }
                    ],
                    "usage": {"prompt_tokens": 100},
                },
            )
        raise AssertionError(body)

    provider = OpenAICompatibleLlmProvider(
        _settings(), client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(LlmOutputLengthError):
        provider.structure_idea(IdeaStructuringRequest(input_text="x" * 4000))


def test_web_research_adaptively_shrinks_evidence_and_recounts() -> None:
    first_prompt_len: int | None = None
    count_calls = 0
    chat_body: dict = {}
    first_id = uuid.uuid4()
    second_id = uuid.uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal first_prompt_len, count_calls, chat_body
        body = json.loads(request.content.decode()) if request.content else {}
        if request.url.path == "/v1/token-count":
            count_calls += 1
            current_len = len(body["messages"][1]["content"])
            if first_prompt_len is None:
                first_prompt_len = current_len
            prompt_tokens = 2500 if current_len > first_prompt_len * 0.85 else 1800
            return httpx.Response(
                200,
                json=_token_count_response(prompt_tokens, context_window=3000),
            )
        if request.url.path.endswith("/capabilities"):
            return httpx.Response(200, json=_capability_response(context_window=3000))
        if request.url.path == "/v1/chat/completions":
            chat_body = body
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "draft": {"background": "근거 기반 보완"},
                                        "evidence_links": {
                                            "background": [str(first_id)]
                                        },
                                        "research_summary": "요약",
                                    },
                                    ensure_ascii=False,
                                )
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 1800},
                },
            )
        raise AssertionError(request.url.path)

    request = EvidenceRefinementRequest(
        input_text="raw is excluded from prompt",
        base_draft={"title": "T", "background": "기존"},
        evidence=[
            EvidenceInput(
                evidence_id=first_id,
                title="상위 근거",
                source="source-a",
                snippet="a" * 800,
            ),
            EvidenceInput(
                evidence_id=second_id,
                title="하위 근거",
                source="source-b",
                snippet="b" * 800,
            ),
        ],
    )
    provider = OpenAICompatibleLlmProvider(
        _settings(), client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    result = provider.refine_idea_with_evidence(request)

    assert result.evidence_links["background"] == [str(first_id)]
    assert count_calls >= 2
    assert chat_body["max_tokens"] == 450
    assert request.evidence[0].evidence_id == first_id
    assert request.evidence[-1].snippet is None or len(request.evidence[-1].snippet or "") < 800


def test_refine_phase_uses_dynamic_cap_and_existing_hard_limit() -> None:
    chat_body: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal chat_body
        body = json.loads(request.content.decode()) if request.content else {}
        if request.url.path == "/v1/token-count":
            return httpx.Response(200, json=_token_count_response(100))
        if request.url.path.endswith("/capabilities"):
            return httpx.Response(200, json=_capability_response())
        if request.url.path == "/v1/chat/completions":
            chat_body = body
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "decision": "READY_FOR_REVIEW",
                                        "draft_patch": {"background": "보완"},
                                        "field_provenance": {},
                                        "clarifying_questions": [],
                                        "research_recommended": False,
                                        "research_topics": [],
                                    },
                                    ensure_ascii=False,
                                )
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 100},
                },
            )
        raise AssertionError(request.url.path)

    provider = OpenAICompatibleLlmProvider(
        _settings(), client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    provider.refine_idea(
        IdeaRefinementRequest(
            direction=IdeaRefineDirection.EXPAND_DETAIL,
            source_context={"title": "T", "background": "기존"},
        )
    )
    assert chat_body["max_tokens"] == 1600
