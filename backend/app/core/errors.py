"""Domain specific exceptions used across services."""


class CodeBridgeError(Exception):
    """Base error for all application specific failures."""

    status_code = 500

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ConfigurationError(CodeBridgeError):
    """Raised when a required piece of configuration (e.g. API key) is missing."""

    status_code = 503


class AIProviderError(CodeBridgeError):
    """Raised when the upstream LLM provider fails or returns unusable output."""

    status_code = 502

    #: Whether a second, stricter request has a realistic chance of succeeding.
    retryable = False


class AIEmptyResponseError(AIProviderError):
    """The provider answered, but with no usable text content."""

    retryable = True


class AIRefusalError(AIProviderError):
    """The model declined to answer, or the answer was filtered."""

    retryable = False


class AITruncatedResponseError(AIProviderError):
    """The model stopped early because of a token/output limit."""

    retryable = True


class AIJSONParseError(AIProviderError):
    """The response did not contain a single unambiguous JSON document."""

    retryable = True


class AITestSchemaError(AIProviderError):
    """The response was JSON, but did not satisfy the test-case schema."""

    retryable = True


class AIRateLimitError(AIProviderError):
    """The provider throttled the request; the caller should back off."""

    status_code = 429
    retryable = False


class AIInvalidRequestError(AIProviderError):
    """The provider rejected the request itself (bad model, bad parameter)."""

    status_code = 400
    retryable = False


class ExecutionServiceError(CodeBridgeError):
    """Raised when the Docker execution backend is unavailable or broken."""

    status_code = 503


class UnsupportedLanguageError(CodeBridgeError):
    status_code = 400


class ValidationError(CodeBridgeError):
    status_code = 400


class NotFoundError(CodeBridgeError):
    status_code = 404
