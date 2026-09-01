"""Embedding provider exceptions."""


class EmbeddingError(Exception):
    """Base embedding error."""

    def __init__(self, message: str, *, code: str = "EMBEDDING_ERROR") -> None:
        super().__init__(message)
        self.code = code


class EmbeddingConfigurationError(EmbeddingError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="EMBEDDING_CONFIGURATION_ERROR")


class EmbeddingUnavailableError(EmbeddingError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="EMBEDDING_UNAVAILABLE")


class EmbeddingAuthenticationError(EmbeddingError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="EMBEDDING_AUTHENTICATION_ERROR")


class EmbeddingTimeoutError(EmbeddingError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="EMBEDDING_TIMEOUT")


class EmbeddingRequestError(EmbeddingError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="EMBEDDING_REQUEST_ERROR")


class EmbeddingConnectionError(EmbeddingRequestError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.code = "EMBEDDING_CONNECTION_ERROR"


class EmbeddingServerError(EmbeddingError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="EMBEDDING_SERVER_ERROR")


class EmbeddingResponseValidationError(EmbeddingError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="EMBEDDING_RESPONSE_VALIDATION_ERROR")
