"""LLM provider abstraction.

Business logic never talks to OpenAI/Gemini directly: it asks a provider for a
completion. Adding a provider only requires implementing `LLMProvider`.

Two distinct completion flavours are exposed:

* `complete` - free-form text, used for source-code generation.
* `complete_json` - a completion that is expected to contain a single JSON
  document. Providers that support a native JSON response format enable it so
  the model cannot wrap the payload in prose; others fall back to plain text
  and the parsing layer has to cope.

Keeping the two apart matters: asking a code-generation prompt for "JSON mode"
would degrade code quality, and asking a structured prompt for free-form text is
what produced unparseable answers in the first place.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Optional, Type

from app.core.config import settings
from app.core.errors import (
    AIEmptyResponseError,
    AIInvalidRequestError,
    AIProviderError,
    AIRateLimitError,
    AIRefusalError,
    AITruncatedResponseError,
    CodeBridgeError,
    ConfigurationError,
)
from app.core.logging_config import get_logger

logger = get_logger(__name__)

#: Finish reasons that mean "the model stopped before finishing its answer".
TRUNCATION_FINISH_REASONS = {"length", "max_tokens", "max_output_tokens"}


@dataclass
class Completion:
    """A provider answer plus the metadata needed to classify failures."""

    text: str = ""
    finish_reason: Optional[str] = None
    refused: bool = False

    @property
    def truncated(self) -> bool:
        return (self.finish_reason or "").lower() in TRUNCATION_FINISH_REASONS


class LLMProvider(ABC):
    name: str = "base"

    #: True when the provider can force a JSON-only response natively.
    supports_json_mode: bool = False

    @abstractmethod
    def is_configured(self) -> bool:
        """True when the provider has everything it needs (e.g. an API key)."""

    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str, temperature: float = 0.1) -> str:
        """Return the raw text completion for the given prompts."""

    def complete_json(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.1
    ) -> Completion:
        """Return a completion expected to hold a single JSON document.

        The default implementation delegates to `complete`, which keeps simple
        test doubles working; real providers override it to enable native JSON
        response formats.
        """
        return Completion(text=self.complete(system_prompt, user_prompt, temperature))

    def ensure_configured(self) -> None:
        if not self.is_configured():
            raise ConfigurationError(
                f"AI provider '{self.name}' is not configured. "
                f"Set the corresponding API key environment variable and restart the backend."
            )


class OpenAIProvider(LLMProvider):
    name = "openai"
    supports_json_mode = True

    def is_configured(self) -> bool:
        return bool(settings.openai_api_key)

    def _client(self):
        self.ensure_configured()
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise ConfigurationError("The 'openai' package is not installed.") from exc
        return OpenAI(api_key=settings.openai_api_key, timeout=settings.ai_request_timeout)

    def _create(self, system_prompt: str, user_prompt: str, temperature: float, json_mode: bool):
        """Single Chat Completions call, translating SDK errors into domain errors."""
        try:
            import openai
        except ImportError as exc:  # pragma: no cover
            raise ConfigurationError("The 'openai' package is not installed.") from exc

        kwargs = {
            "model": settings.openai_model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            return self._client().chat.completions.create(**kwargs)
        except CodeBridgeError:
            # Configuration errors (missing/invalid key) must keep their own
            # status code; do not downgrade them to a generic provider failure.
            raise
        except openai.RateLimitError as exc:
            raise AIRateLimitError(
                "The AI provider is rate limiting requests. Retry in a moment."
            ) from exc
        except openai.AuthenticationError as exc:
            raise ConfigurationError("The OpenAI API key was rejected.") from exc
        except openai.BadRequestError as exc:
            raise AIInvalidRequestError(
                f"OpenAI rejected the request ({exc}). The configured model may not support it."
            ) from exc
        except openai.APITimeoutError as exc:
            raise AIProviderError("OpenAI request timed out.") from exc
        except openai.APIError as exc:
            raise AIProviderError(f"OpenAI request failed: {exc}") from exc
        except Exception as exc:  # pragma: no cover - transport level surprises
            raise AIProviderError(f"OpenAI request failed: {exc}") from exc

    def _to_completion(self, response) -> Completion:
        if not getattr(response, "choices", None):
            raise AIEmptyResponseError("OpenAI returned no completion choices.")
        choice = response.choices[0]
        message = getattr(choice, "message", None)
        finish_reason = getattr(choice, "finish_reason", None)
        refused = bool(getattr(message, "refusal", None))
        content = getattr(message, "content", None) or ""
        return Completion(text=content.strip(), finish_reason=finish_reason, refused=refused)

    def complete(self, system_prompt: str, user_prompt: str, temperature: float = 0.1) -> str:
        completion = self._to_completion(
            self._create(system_prompt, user_prompt, temperature, json_mode=False)
        )
        self._raise_if_unusable(completion)
        return completion.text

    def complete_json(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.1
    ) -> Completion:
        completion = self._to_completion(
            self._create(system_prompt, user_prompt, temperature, json_mode=True)
        )
        self._raise_if_unusable(completion)
        return completion

    @staticmethod
    def _raise_if_unusable(completion: Completion) -> None:
        if completion.refused:
            raise AIRefusalError("The model refused to answer this request.")
        if not completion.text:
            if completion.truncated:
                raise AITruncatedResponseError(
                    "The model hit its output limit before producing any content."
                )
            raise AIEmptyResponseError("OpenAI returned an empty response.")
        if completion.truncated:
            raise AITruncatedResponseError(
                "The model stopped at its output limit, so the response is incomplete."
            )


class GeminiProvider(LLMProvider):
    name = "gemini"
    supports_json_mode = True

    def is_configured(self) -> bool:
        return bool(settings.gemini_api_key)

    def _generate(self, system_prompt: str, user_prompt: str, temperature: float, json_mode: bool):
        self.ensure_configured()
        try:
            import google.generativeai as genai
        except ImportError as exc:  # pragma: no cover
            raise ConfigurationError("The 'google-generativeai' package is not installed.") from exc

        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel(settings.gemini_model, system_instruction=system_prompt)
        generation_config = {"temperature": temperature}
        if json_mode:
            generation_config["response_mime_type"] = "application/json"
        try:
            return model.generate_content(user_prompt, generation_config=generation_config)
        except Exception as exc:
            raise AIProviderError(f"Gemini request failed: {exc}") from exc

    @staticmethod
    def _to_completion(response) -> Completion:
        finish_reason = None
        candidates = getattr(response, "candidates", None) or []
        if candidates:
            raw_reason = getattr(candidates[0], "finish_reason", None)
            finish_reason = getattr(raw_reason, "name", None) or (
                str(raw_reason) if raw_reason is not None else None
            )
        blocked = finish_reason in {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT"}
        try:
            text = (response.text or "").strip()
        except Exception:
            # `response.text` raises when the candidate was blocked or has no parts.
            text = ""
            blocked = True
        return Completion(text=text, finish_reason=finish_reason, refused=blocked)

    @staticmethod
    def _raise_if_unusable(completion: Completion) -> None:
        if completion.refused:
            raise AIRefusalError("The model refused to answer this request.")
        if not completion.text:
            if completion.truncated:
                raise AITruncatedResponseError(
                    "The model hit its output limit before producing any content."
                )
            raise AIEmptyResponseError("Gemini returned an empty response.")
        if completion.truncated:
            raise AITruncatedResponseError(
                "The model stopped at its output limit, so the response is incomplete."
            )

    def complete(self, system_prompt: str, user_prompt: str, temperature: float = 0.1) -> str:
        completion = self._to_completion(
            self._generate(system_prompt, user_prompt, temperature, json_mode=False)
        )
        self._raise_if_unusable(completion)
        return completion.text

    def complete_json(
        self, system_prompt: str, user_prompt: str, temperature: float = 0.1
    ) -> Completion:
        completion = self._to_completion(
            self._generate(system_prompt, user_prompt, temperature, json_mode=True)
        )
        self._raise_if_unusable(completion)
        return completion


PROVIDERS: Dict[str, Type[LLMProvider]] = {
    OpenAIProvider.name: OpenAIProvider,
    GeminiProvider.name: GeminiProvider,
}


def get_provider(name: Optional[str] = None) -> LLMProvider:
    key = (name or settings.ai_provider or "openai").strip().lower()
    provider_cls = PROVIDERS.get(key)
    if provider_cls is None:
        raise ConfigurationError(
            f"Unknown AI provider '{key}'. Supported providers: {', '.join(sorted(PROVIDERS))}."
        )
    return provider_cls()
