"""OpenAI-compatible HTTP LLM provider (httpx)."""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Callable, TypeVar
from urllib.parse import quote

import httpx

from app.core.config import Settings
from app.llm.adaptive_budget import (
    REFINE_POLICY,
    STRUCTURE_POLICY,
    WEB_RESEARCH_POLICY,
    PhaseBudgetPolicy,
    VerifiedTokenCount,
    compute_phase_budget,
)
from app.llm.exceptions import (
    LlmAuthenticationError,
    LlmConfigurationError,
    LlmConnectionError,
    LlmContextBudgetError,
    LlmOutputLengthError,
    LlmRateLimitError,
    LlmRequestError,
    LlmResponseValidationError,
    LlmServerError,
    LlmTimeoutError,
    LlmUnavailableError,
)
from app.llm.prompts import IDEA_STRUCTURE_PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt
from app.llm.refine_prompts import (
    IDEA_REFINE_PROMPT_VERSION,
    REFINE_SYSTEM_PROMPT,
    build_refine_user_prompt,
)
from app.llm.refine_schemas import (
    IdeaRefinementRequest,
    IdeaRefinementResult,
    parse_refinement_result as parse_idea_refinement_result,
)
from app.llm.research_prompts import (
    IDEA_RESEARCH_REFINE_PROMPT_VERSION,
    RESEARCH_SYSTEM_PROMPT,
    build_research_user_prompt,
)
from app.llm.research_schemas import (
    EvidenceRefinementRequest,
    EvidenceRefinementResult,
    parse_refinement_result,
)
from app.llm.schemas import IdeaStructuringRequest, IdeaStructuringResult, parse_structuring_result

logger = logging.getLogger(__name__)

_RequestT = TypeVar("_RequestT")
_ResultT = TypeVar("_ResultT")

_MAX_ROUTE_VERIFY_ATTEMPTS = 2
_MAX_INPUT_SHRINK_ATTEMPTS = 16
_MAX_LENGTH_RETRIES = 1
_MAX_ROUTE_PARITY_RETRIES = 1


class _TokenCountUnsupported(Exception):
    """The configured OpenAI-compatible endpoint does not expose ModelOps P1-12."""


class OpenAICompatibleLlmProvider:
    provider_name = "openai_compatible"

    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        if not settings.llm_api_url.strip():
            raise LlmConfigurationError("LLM_API_URL is not configured")
        if not settings.llm_model_name.strip():
            raise LlmConfigurationError("LLM_MODEL_NAME is not configured")

        self._settings = settings
        self.model_name = settings.llm_model_name
        self.prompt_version = IDEA_STRUCTURE_PROMPT_VERSION
        self.refine_prompt_version = IDEA_REFINE_PROMPT_VERSION
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(
                settings.llm_timeout_seconds,
                connect=settings.llm_connect_timeout_seconds,
            ),
            # TLS verification stays enabled (never verify=False).
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def structure_idea(self, request: IdeaStructuringRequest) -> IdeaStructuringResult:
        result, _ = self._run_phase(
            phase="STRUCTURE_IDEA",
            request=request,
            policy=STRUCTURE_POLICY,
            hard_output_cap=self._settings.llm_max_tokens,
            body_builder=self._build_structure_body,
            shrinker=self._shrink_structure_request,
            parser=parse_structuring_result,
        )
        return result

    def refine_idea_with_evidence(
        self, request: EvidenceRefinementRequest
    ) -> EvidenceRefinementResult:
        result, final_request = self._run_phase(
            phase="WEB_RESEARCH_REFINE",
            request=request,
            policy=WEB_RESEARCH_POLICY,
            hard_output_cap=self._settings.web_research_refine_max_tokens,
            body_builder=self._build_research_body,
            shrinker=self._shrink_research_request,
            parser=parse_refinement_result,
        )
        # The worker validates evidence_links against request.evidence after this
        # call. Keep that exact set aligned with the token-adapted prompt so a
        # dropped evidence UUID can never be accepted as if it had been sent.
        request.evidence = list(final_request.evidence)
        return result

    def refine_idea(self, request: IdeaRefinementRequest) -> IdeaRefinementResult:
        result, _ = self._run_phase(
            phase="REFINE_IDEA",
            request=request,
            policy=REFINE_POLICY,
            hard_output_cap=self._settings.ai_refine_max_tokens,
            body_builder=self._build_refine_body,
            shrinker=self._shrink_refine_request,
            parser=lambda content: parse_idea_refinement_result(
                content, direction=request.direction
            ),
        )
        return result

    def _run_phase(
        self,
        *,
        phase: str,
        request: _RequestT,
        policy: PhaseBudgetPolicy,
        hard_output_cap: int,
        body_builder: Callable[[_RequestT, int], dict[str, Any]],
        shrinker: Callable[[_RequestT, bool], _RequestT | None],
        parser: Callable[[str], _ResultT],
    ) -> tuple[_ResultT, _RequestT]:
        current = request
        length_retries = 0
        parity_retries = 0

        while True:
            body, current, token_count = self._prepare_budgeted_body(
                phase=phase,
                request=current,
                policy=policy,
                hard_output_cap=hard_output_cap,
                body_builder=body_builder,
                shrinker=shrinker,
            )
            payload = self._post_chat_json(body)
            finish_reason = self._extract_finish_reason(payload)
            if finish_reason == "length":
                if length_retries >= _MAX_LENGTH_RETRIES:
                    raise LlmOutputLengthError()
                reduced = shrinker(current, True)
                if reduced is None:
                    raise LlmOutputLengthError()
                length_retries += 1
                current = reduced
                logger.warning(
                    "llm_length_retry provider=%s model=%s phase=%s retry=%s",
                    self.provider_name,
                    self.model_name,
                    phase,
                    length_retries,
                )
                continue

            if token_count is not None:
                # Count -> Chat is not route-pinned by ModelOps. Re-read the
                # observational capability after Chat and discard/re-budget if
                # ACTIVE routing changed anywhere across the pair.
                capability = self._get_capability()
                if not self._same_route(token_count, capability):
                    if parity_retries >= _MAX_ROUTE_PARITY_RETRIES:
                        raise LlmUnavailableError()
                    parity_retries += 1
                    logger.warning(
                        "llm_route_changed_after_chat provider=%s model=%s phase=%s "
                        "count_deployment=%s count_route=%s count_version=%s retry=%s",
                        self.provider_name,
                        self.model_name,
                        phase,
                        token_count.deployment_id,
                        token_count.route_id,
                        token_count.routing_version,
                        parity_retries,
                    )
                    continue

                chat_prompt_tokens = self._extract_usage_prompt_tokens(payload)
                if (
                    chat_prompt_tokens is not None
                    and chat_prompt_tokens != token_count.prompt_tokens
                ):
                    if parity_retries >= _MAX_ROUTE_PARITY_RETRIES:
                        raise LlmUnavailableError()
                    parity_retries += 1
                    logger.warning(
                        "llm_prompt_token_parity_changed provider=%s model=%s phase=%s "
                        "counted=%s chat=%s retry=%s",
                        self.provider_name,
                        self.model_name,
                        phase,
                        token_count.prompt_tokens,
                        chat_prompt_tokens,
                        parity_retries,
                    )
                    continue

            content = self._extract_content(payload)
            content_bytes = content.encode("utf-8")
            logger.info(
                "llm_ok provider=%s model=%s phase=%s bytes=%s sha256=%s",
                self.provider_name,
                self.model_name,
                phase,
                len(content_bytes),
                hashlib.sha256(content_bytes).hexdigest()[:12],
            )
            return parser(content), current

    def _prepare_budgeted_body(
        self,
        *,
        phase: str,
        request: _RequestT,
        policy: PhaseBudgetPolicy,
        hard_output_cap: int,
        body_builder: Callable[[_RequestT, int], dict[str, Any]],
        shrinker: Callable[[_RequestT, bool], _RequestT | None],
    ) -> tuple[dict[str, Any], _RequestT, VerifiedTokenCount | None]:
        current = request
        last_body: dict[str, Any] | None = None
        last_count: VerifiedTokenCount | None = None

        for attempt in range(_MAX_INPUT_SHRINK_ATTEMPTS):
            body = body_builder(current, hard_output_cap)
            last_body = body
            try:
                token_count = self._verified_token_count(body, phase=phase)
            except _TokenCountUnsupported:
                logger.info(
                    "llm_adaptive_budget_unsupported provider=%s model=%s phase=%s",
                    self.provider_name,
                    self.model_name,
                    phase,
                )
                return body, current, None

            last_count = token_count
            decision = compute_phase_budget(
                prompt_tokens=token_count.prompt_tokens,
                context_window=token_count.context_window,
                hard_output_cap=hard_output_cap,
                policy=policy,
                thinking_enabled=self._thinking_enabled(),
            )

            if decision.needs_input_shrink and attempt < _MAX_INPUT_SHRINK_ATTEMPTS - 1:
                reduced = shrinker(current, False)
                if reduced is not None:
                    logger.info(
                        "llm_prompt_shrink provider=%s model=%s phase=%s attempt=%s "
                        "prompt_tokens=%s desired_output=%s context_window=%s",
                        self.provider_name,
                        self.model_name,
                        phase,
                        attempt + 1,
                        decision.prompt_tokens,
                        decision.desired_output_tokens,
                        decision.context_window,
                    )
                    current = reduced
                    continue

            if not decision.fits_minimum:
                raise LlmContextBudgetError()

            body["max_tokens"] = decision.max_tokens
            logger.info(
                "llm_token_budget provider=%s model=%s phase=%s prompt_tokens=%s "
                "context_window=%s max_tokens=%s desired_output=%s safety_margin=%s "
                "deployment_id=%s route_id=%s routing_version=%s",
                self.provider_name,
                self.model_name,
                phase,
                decision.prompt_tokens,
                decision.context_window,
                decision.max_tokens,
                decision.desired_output_tokens,
                decision.safety_margin_tokens,
                token_count.deployment_id,
                token_count.route_id,
                token_count.routing_version,
            )
            return body, current, token_count

        if last_body is not None and last_count is not None:
            decision = compute_phase_budget(
                prompt_tokens=last_count.prompt_tokens,
                context_window=last_count.context_window,
                hard_output_cap=hard_output_cap,
                policy=policy,
                thinking_enabled=self._thinking_enabled(),
            )
            if decision.fits_minimum:
                last_body["max_tokens"] = decision.max_tokens
                return last_body, current, last_count
        raise LlmContextBudgetError()

    def _verified_token_count(
        self, body: dict[str, Any], *, phase: str
    ) -> VerifiedTokenCount:
        for attempt in range(_MAX_ROUTE_VERIFY_ATTEMPTS):
            count = self._post_token_count(body)
            capability = self._get_capability()
            if self._same_route(count, capability):
                return count
            logger.warning(
                "llm_route_changed_during_count provider=%s model=%s phase=%s attempt=%s "
                "count_deployment=%s count_route=%s count_version=%s",
                self.provider_name,
                self.model_name,
                phase,
                attempt + 1,
                count.deployment_id,
                count.route_id,
                count.routing_version,
            )
        raise LlmUnavailableError()

    def _post_token_count(self, body: dict[str, Any]) -> VerifiedTokenCount:
        count_body: dict[str, Any] = {
            "model": body["model"],
            "messages": body["messages"],
        }
        if "chat_template_kwargs" in body:
            count_body["chat_template_kwargs"] = body["chat_template_kwargs"]

        try:
            response = self._client.post(
                self._token_count_url(),
                headers=self._headers(),
                json=count_body,
            )
        except httpx.TimeoutException as exc:
            raise LlmTimeoutError() from exc
        except httpx.RequestError as exc:
            raise LlmConnectionError() from exc

        if response.status_code in (404, 405):
            raise _TokenCountUnsupported()
        self._raise_for_aux_status(response)
        try:
            payload = response.json()
        except ValueError as exc:
            raise LlmResponseValidationError("Token Count response is not JSON") from exc
        if not isinstance(payload, dict):
            raise LlmResponseValidationError("Token Count response root must be an object")
        if "status" not in payload:
            raise LlmResponseValidationError("Token Count response missing status")
        if payload.get("status") != "VERIFIED":
            raise LlmUnavailableError()

        prompt_tokens = payload.get("prompt_tokens")
        context_window = payload.get("context_window")
        deployment_id = payload.get("deployment_id")
        route_id = payload.get("route_id")
        routing_version = payload.get("routing_version")
        if (
            type(prompt_tokens) is not int
            or prompt_tokens < 0
            or type(context_window) is not int
            or context_window < 1
            or not isinstance(deployment_id, str)
            or not deployment_id
            or not isinstance(route_id, str)
            or not route_id
            or type(routing_version) is not int
        ):
            raise LlmResponseValidationError("Token Count response fields are invalid")
        return VerifiedTokenCount(
            prompt_tokens=prompt_tokens,
            context_window=context_window,
            deployment_id=deployment_id,
            route_id=route_id,
            routing_version=routing_version,
        )

    def _get_capability(self) -> dict[str, Any]:
        try:
            response = self._client.get(
                self._capabilities_url(),
                headers=self._headers(),
            )
        except httpx.TimeoutException as exc:
            raise LlmTimeoutError() from exc
        except httpx.RequestError as exc:
            raise LlmConnectionError() from exc

        self._raise_for_aux_status(response)
        try:
            payload = response.json()
        except ValueError as exc:
            raise LlmResponseValidationError("Capability response is not JSON") from exc
        if not isinstance(payload, dict):
            raise LlmResponseValidationError("Capability response root must be an object")
        if "status" not in payload:
            raise LlmResponseValidationError("Capability response missing status")
        if payload.get("status") != "VERIFIED":
            raise LlmUnavailableError()
        if type(payload.get("context_window")) is not int or payload["context_window"] < 1:
            raise LlmUnavailableError()
        return payload

    @staticmethod
    def _same_route(count: VerifiedTokenCount, capability: dict[str, Any]) -> bool:
        return (
            capability.get("deployment_id") == count.deployment_id
            and capability.get("route_id") == count.route_id
            and capability.get("routing_version") == count.routing_version
            and capability.get("context_window") == count.context_window
        )

    def _post_chat_json(self, body: dict[str, Any]) -> Any:
        try:
            response = self._client.post(
                self._settings.llm_chat_completions_url,
                headers=self._headers(),
                json=body,
            )
        except httpx.TimeoutException as exc:
            logger.warning(
                "llm_timeout provider=%s model=%s",
                self.provider_name,
                self.model_name,
            )
            raise LlmTimeoutError() from exc
        except httpx.RequestError as exc:
            logger.warning(
                "llm_connection_error provider=%s model=%s category=%s",
                self.provider_name,
                self.model_name,
                type(exc).__name__,
            )
            raise LlmConnectionError() from exc

        self._raise_for_status(response)
        try:
            return response.json()
        except ValueError as exc:
            raise LlmResponseValidationError("LLM response is not JSON") from exc

    def _build_structure_body(
        self, request: IdeaStructuringRequest, max_tokens: int
    ) -> dict[str, Any]:
        return self._chat_body(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(request)},
            ],
            max_tokens=max_tokens,
        )

    def _build_research_body(
        self, request: EvidenceRefinementRequest, max_tokens: int
    ) -> dict[str, Any]:
        return self._chat_body(
            messages=[
                {"role": "system", "content": RESEARCH_SYSTEM_PROMPT},
                {"role": "user", "content": build_research_user_prompt(request)},
            ],
            max_tokens=max_tokens,
        )

    def _build_refine_body(
        self, request: IdeaRefinementRequest, max_tokens: int
    ) -> dict[str, Any]:
        return self._chat_body(
            messages=[
                {"role": "system", "content": REFINE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_refine_user_prompt(
                        direction=request.direction.value,
                        source_context=request.source_context,
                        clarifying_questions=request.clarifying_questions,
                        clarification_answers=request.clarification_answers,
                    ),
                },
            ],
            max_tokens=max_tokens,
        )

    def _chat_body(
        self, *, messages: list[dict[str, Any]], max_tokens: int
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self._settings.llm_temperature,
            "max_tokens": max_tokens,
        }
        if self._settings.llm_enable_thinking is not None:
            body["chat_template_kwargs"] = {
                "enable_thinking": bool(self._settings.llm_enable_thinking),
            }
        return body

    @staticmethod
    def _shrink_structure_request(
        request: IdeaStructuringRequest, aggressive: bool
    ) -> IdeaStructuringRequest | None:
        ratio = 0.60 if aggressive else 0.80
        min_chars = 256 if aggressive else 512
        text = request.input_text
        if len(text) > min_chars:
            limit = max(min_chars, int(len(text) * ratio))
            if limit < len(text):
                return request.model_copy(update={"input_text": text[: limit - 1] + "…"})

        answers = [dict(item) for item in (request.clarification_answers or [])]
        best_index = -1
        best_len = 0
        for idx, item in enumerate(answers):
            answer = item.get("answer")
            if isinstance(answer, str) and len(answer) > best_len:
                best_index = idx
                best_len = len(answer)
        if best_index >= 0 and best_len > 128:
            answer = str(answers[best_index]["answer"])
            limit = max(128, int(len(answer) * ratio))
            answers[best_index]["answer"] = answer[: limit - 1] + "…"
            return request.model_copy(update={"clarification_answers": answers})

        draft = dict(request.prior_draft or {})
        key = OpenAICompatibleLlmProvider._longest_string_key(draft)
        if key is not None and len(str(draft[key])) > 128:
            value = str(draft[key])
            limit = max(128, int(len(value) * ratio))
            draft[key] = value[: limit - 1] + "…"
            return request.model_copy(update={"prior_draft": draft})
        return None

    @staticmethod
    def _shrink_research_request(
        request: EvidenceRefinementRequest, aggressive: bool
    ) -> EvidenceRefinementRequest | None:
        evidence = list(request.evidence)
        if not evidence:
            return None
        last = evidence[-1]
        if last.snippet:
            ratio = 0.50 if aggressive else 0.70
            min_chars = 80
            if len(last.snippet) > min_chars:
                limit = max(min_chars, int(len(last.snippet) * ratio))
                evidence[-1] = last.model_copy(
                    update={"snippet": last.snippet[: limit - 1] + "…"}
                )
                return request.model_copy(update={"evidence": evidence})
            evidence[-1] = last.model_copy(update={"snippet": None})
            return request.model_copy(update={"evidence": evidence})
        evidence.pop()
        return request.model_copy(update={"evidence": evidence})

    @staticmethod
    def _shrink_refine_request(
        request: IdeaRefinementRequest, aggressive: bool
    ) -> IdeaRefinementRequest | None:
        context = dict(request.source_context)
        ratio = 0.55 if aggressive else 0.75
        protected = {"title", "one_line_definition"}
        for key in reversed(list(context.keys())):
            if key in protected:
                continue
            value = context.get(key)
            if isinstance(value, str) and len(value) > 160:
                limit = max(160, int(len(value) * ratio))
                context[key] = value[: limit - 1] + "…"
                return request.model_copy(update={"source_context": context})
            context.pop(key, None)
            return request.model_copy(update={"source_context": context})

        for key in ("one_line_definition", "title"):
            value = context.get(key)
            if isinstance(value, str) and len(value) > 80:
                limit = max(80, int(len(value) * ratio))
                context[key] = value[: limit - 1] + "…"
                return request.model_copy(update={"source_context": context})
        return None

    @staticmethod
    def _longest_string_key(values: dict[str, Any]) -> str | None:
        candidates = [
            (len(value), key)
            for key, value in values.items()
            if isinstance(value, str) and value
        ]
        return max(candidates)[1] if candidates else None

    def _thinking_enabled(self) -> bool:
        return bool(self._settings.llm_enable_thinking)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        api_key = self._settings.llm_api_key.strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _token_count_url(self) -> str:
        return f"{self._settings.llm_api_url.rstrip('/')}/v1/token-count"

    def _capabilities_url(self) -> str:
        alias = quote(self.model_name, safe="")
        return f"{self._settings.llm_api_url.rstrip('/')}/v1/models/{alias}/capabilities"

    def _raise_for_aux_status(self, response: httpx.Response) -> None:
        status = response.status_code
        if status == 200:
            return
        logger.warning(
            "llm_budget_http_error provider=%s model=%s status=%s bytes=%s",
            self.provider_name,
            self.model_name,
            status,
            len(response.content),
        )
        if status in (401, 403):
            raise LlmAuthenticationError()
        if status == 429:
            raise LlmRateLimitError()
        if status in (400, 413, 422):
            raise LlmRequestError()
        if 500 <= status <= 599:
            raise LlmServerError()
        if 400 <= status < 500:
            raise LlmRequestError()
        raise LlmServerError()

    def _raise_for_status(self, response: httpx.Response) -> None:
        status = response.status_code
        if status == 200:
            return
        logger.warning(
            "llm_http_error provider=%s model=%s status=%s bytes=%s",
            self.provider_name,
            self.model_name,
            status,
            len(response.content),
        )
        if status in (401, 403):
            raise LlmAuthenticationError()
        if status == 429:
            raise LlmRateLimitError()
        if status == 400:
            raise LlmRequestError()
        if 500 <= status <= 599:
            raise LlmServerError()
        if 400 <= status < 500:
            raise LlmRequestError()
        raise LlmServerError()

    @staticmethod
    def _first_choice(payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise LlmResponseValidationError("LLM response root must be an object")
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LlmResponseValidationError("LLM response missing choices")
        first = choices[0]
        if not isinstance(first, dict):
            raise LlmResponseValidationError("LLM response choice invalid")
        return first

    @classmethod
    def _extract_finish_reason(cls, payload: Any) -> str | None:
        first = cls._first_choice(payload)
        value = first.get("finish_reason")
        return value if isinstance(value, str) else None

    @staticmethod
    def _extract_usage_prompt_tokens(payload: Any) -> int | None:
        if not isinstance(payload, dict):
            return None
        usage = payload.get("usage")
        if not isinstance(usage, dict):
            return None
        value = usage.get("prompt_tokens")
        return value if type(value) is int and value >= 0 else None

    @classmethod
    def _extract_content(cls, payload: Any) -> str:
        first = cls._first_choice(payload)
        if first.get("finish_reason") == "length":
            raise LlmOutputLengthError()
        message = first.get("message")
        if not isinstance(message, dict):
            raise LlmResponseValidationError("LLM response missing message")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise LlmResponseValidationError("LLM response missing message.content")
        return content
