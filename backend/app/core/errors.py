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


class ExecutionServiceError(CodeBridgeError):
    """Raised when the Docker execution backend is unavailable or broken."""

    status_code = 503


class UnsupportedLanguageError(CodeBridgeError):
    status_code = 400


class ValidationError(CodeBridgeError):
    status_code = 400


class NotFoundError(CodeBridgeError):
    status_code = 404
