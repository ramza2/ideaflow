"""OpenAI-compatible HTTP LLM provider (httpx)."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import httpx

from app.core.config import Settings
from app.llm.exceptions import (
    LlmAuthenticationError,
    LlmConfigurationError,
    LlmConnectionError,
    LlmRateLimitError,
    LlmRequestError,
    LlmResponseValidationError,
    LlmServerError,
    LlmTimeoutError,
)
from app.llm.prompts import IDEA_STRUCTURE_PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt
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
        url = self._settings.llm_chat_completions_url
        headers: dict[str, str] = {"Content-Type": "application/json"}
        api_key = self._settings.llm_api_key.strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        body: dict[str, Any] = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(request)},
            ],
            "temperature": self._settings.llm_temperature,
            "max_tokens": self._settings.llm_max_tokens,
        }
        # Tri-state: unset → omit; true/false → chat_template_kwargs.enable_thinking
        if self._settings.llm_enable_thinking is not None:
            body["chat_template_kwargs"] = {
                "enable_thinking": bool(self._settings.llm_enable_thinking),
            }

        try:
            response = self._client.post(url, headers=headers, json=body)
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
            payload = response.json()
        except ValueError as exc:
            raise LlmResponseValidationError("LLM response is not JSON") from exc

        content = self._extract_content(payload)
        # Never log content / input_text / Authorization.
        content_bytes = content.encode("utf-8")
        logger.info(
            "llm_ok provider=%s model=%s status=%s bytes=%s sha256=%s",
            self.provider_name,
            self.model_name,
            response.status_code,
            len(content_bytes),
            hashlib.sha256(content_bytes).hexdigest()[:12],
        )
        return parse_structuring_result(content)

    def refine_idea_with_evidence(
        self, request: EvidenceRefinementRequest
    ) -> EvidenceRefinementResult:
        url = self._settings.llm_chat_completions_url
        headers: dict[str, str] = {"Content-Type": "application/json"}
        api_key = self._settings.llm_api_key.strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        body: dict[str, Any] = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": RESEARCH_SYSTEM_PROMPT},
                {"role": "user", "content": build_research_user_prompt(request)},
            ],
            "temperature": self._settings.llm_temperature,
            "max_tokens": self._settings.web_research_refine_max_tokens,
        }
        if self._settings.llm_enable_thinking is not None:
            body["chat_template_kwargs"] = {
                "enable_thinking": bool(self._settings.llm_enable_thinking),
            }

        try:
            response = self._client.post(url, headers=headers, json=body)
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
            payload = response.json()
        except ValueError as exc:
            raise LlmResponseValidationError("LLM response is not JSON") from exc

        content = self._extract_content(payload)
        content_bytes = content.encode("utf-8")
        logger.info(
            "llm_research_ok provider=%s model=%s status=%s bytes=%s sha256=%s",
            self.provider_name,
            self.model_name,
            response.status_code,
            len(content_bytes),
            hashlib.sha256(content_bytes).hexdigest()[:12],
        )
        return parse_refinement_result(content)

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
    def _extract_content(payload: Any) -> str:
        if not isinstance(payload, dict):
            raise LlmResponseValidationError("LLM response root must be an object")
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LlmResponseValidationError("LLM response missing choices")
        first = choices[0]
        if not isinstance(first, dict):
            raise LlmResponseValidationError("LLM response choice invalid")
        message = first.get("message")
        if not isinstance(message, dict):
            raise LlmResponseValidationError("LLM response missing message")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise LlmResponseValidationError("LLM response missing message.content")
        return content
