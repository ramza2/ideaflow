"""LLM exception hierarchy (Step 7)."""

from __future__ import annotations


class LlmError(Exception):
    """Base LLM provider error."""

    code: str = "LLM_ERROR"
    retryable: bool = False
    safe_message: str = "AI 처리 중 오류가 발생했습니다."

    def __init__(self, message: str | None = None, *, code: str | None = None) -> None:
        self.safe_message = message or type(self).safe_message
        if code is not None:
            self.code = code
        super().__init__(self.safe_message)


class LlmTimeoutError(LlmError):
    code = "LLM_TIMEOUT"
    retryable = True
    safe_message = "AI 처리 중 일시적인 오류가 발생했습니다."


class LlmConnectionError(LlmError):
    code = "LLM_CONNECTION_ERROR"
    retryable = True
    safe_message = "AI 처리 중 일시적인 오류가 발생했습니다."


class LlmAuthenticationError(LlmError):
    code = "LLM_AUTH_ERROR"
    retryable = False
    safe_message = "AI 서비스 인증에 실패했습니다."


class LlmRateLimitError(LlmError):
    code = "LLM_RATE_LIMIT"
    retryable = True
    safe_message = "AI 처리 중 일시적인 오류가 발생했습니다."


class LlmServerError(LlmError):
    code = "LLM_SERVER_ERROR"
    retryable = True
    safe_message = "AI 처리 중 일시적인 오류가 발생했습니다."


class LlmRequestError(LlmError):
    code = "LLM_REQUEST_ERROR"
    retryable = False
    safe_message = "AI 요청이 거부되었습니다."


class LlmResponseValidationError(LlmError):
    code = "LLM_RESPONSE_INVALID"
    retryable = True
    safe_message = "AI 응답을 해석하지 못했습니다."


class LlmConfigurationError(LlmError):
    code = "LLM_CONFIGURATION_ERROR"
    retryable = False
    safe_message = "AI 서비스 설정 오류가 발생했습니다."


class LlmUnavailableError(LlmError):
    code = "LLM_UNAVAILABLE"
    retryable = True
    safe_message = "AI 처리 중 일시적인 오류가 발생했습니다."
