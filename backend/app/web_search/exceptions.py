"""Web Search provider exceptions."""

from __future__ import annotations


class WebSearchError(Exception):
    code: str = "WEB_SEARCH_ERROR"
    retryable: bool = False
    safe_message: str = "웹 검색 중 오류가 발생했습니다."

    def __init__(self, message: str | None = None, *, code: str | None = None) -> None:
        if code is not None:
            self.code = code
        if message is not None:
            self.safe_message = message
        super().__init__(self.safe_message)


class WebSearchTimeoutError(WebSearchError):
    code = "WEB_SEARCH_TIMEOUT"
    retryable = True
    safe_message = "웹 검색 요청이 시간 초과되었습니다."


class WebSearchConnectionError(WebSearchError):
    code = "WEB_SEARCH_CONNECTION_ERROR"
    retryable = True
    safe_message = "웹 검색 서비스에 연결할 수 없습니다."


class WebSearchAuthenticationError(WebSearchError):
    code = "WEB_SEARCH_AUTH_ERROR"
    retryable = False
    safe_message = "웹 검색 서비스 인증에 실패했습니다."


class WebSearchRateLimitError(WebSearchError):
    code = "WEB_SEARCH_RATE_LIMIT"
    retryable = True
    safe_message = "웹 검색 요청 한도를 초과했습니다."


class WebSearchServerError(WebSearchError):
    code = "WEB_SEARCH_SERVER_ERROR"
    retryable = True
    safe_message = "웹 검색 서비스가 일시적으로 사용할 수 없습니다."


class WebSearchRequestError(WebSearchError):
    code = "WEB_SEARCH_REQUEST_ERROR"
    retryable = False
    safe_message = "웹 검색 요청이 거부되었습니다."


class WebSearchResponseValidationError(WebSearchError):
    code = "WEB_SEARCH_RESPONSE_INVALID"
    retryable = False
    safe_message = "웹 검색 응답을 처리할 수 없습니다."


class WebSearchConfigurationError(WebSearchError):
    code = "WEB_SEARCH_NOT_CONFIGURED"
    retryable = False
    safe_message = "웹 검색 서비스가 설정되어 있지 않습니다."
