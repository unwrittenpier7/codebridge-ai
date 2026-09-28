"""LLM provider abstraction.

Business logic never talks to OpenAI/Gemini directly: it asks a provider for a
completion. Adding a provider only requires implementing `LLMProvider`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Type

from app.core.config import settings
from app.core.errors import AIProviderError, ConfigurationError
from app.core.logging_config import get_logger

logger = get_logger(__name__)


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def is_configured(self) -> bool:
        """True when the provider has everything it needs (e.g. an API key)."""

    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str, temperature: float = 0.1) -> str:
        """Return the raw text completion for the given prompts."""

    def ensure_configured(self) -> None:
        if not self.is_configured():
            raise ConfigurationError(
                f"AI provider '{self.name}' is not configured. "
                f"Set the corresponding API key environment variable and restart the backend."
            )


class OpenAIProvider(LLMProvider):
    name = "openai"

    def is_configured(self) -> bool:
        return bool(settings.openai_api_key)

    def complete(self, system_prompt: str, user_prompt: str, temperature: float = 0.1) -> str:
        self.ensure_configured()
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise ConfigurationError("The 'openai' package is not installed.") from exc

        client = OpenAI(api_key=settings.openai_api_key, timeout=settings.ai_request_timeout)
        try:
            response = client.chat.completions.create(
                model=settings.openai_model,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except Exception as exc:
            raise AIProviderError(f"OpenAI request failed: {exc}") from exc

        content = (response.choices[0].message.content or "").strip()
        if not content:
            raise AIProviderError("OpenAI returned an empty response.")
        return content


class GeminiProvider(LLMProvider):
    name = "gemini"

    def is_configured(self) -> bool:
        return bool(settings.gemini_api_key)

    def complete(self, system_prompt: str, user_prompt: str, temperature: float = 0.1) -> str:
        self.ensure_configured()
        try:
            import google.generativeai as genai
        except ImportError as exc:  # pragma: no cover
            raise ConfigurationError("The 'google-generativeai' package is not installed.") from exc

        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel(
            settings.gemini_model, system_instruction=system_prompt
        )
        try:
            response = model.generate_content(
                user_prompt,
                generation_config={"temperature": temperature},
            )
            content = (response.text or "").strip()
        except Exception as exc:
            raise AIProviderError(f"Gemini request failed: {exc}") from exc

        if not content:
            raise AIProviderError("Gemini returned an empty response.")
        return content


PROVIDERS: Dict[str, Type[LLMProvider]] = {
    OpenAIProvider.name: OpenAIProvider,
    GeminiProvider.name: GeminiProvider,
}


def get_provider(name: str | None = None) -> LLMProvider:
    key = (name or settings.ai_provider or "openai").strip().lower()
    provider_cls = PROVIDERS.get(key)
    if provider_cls is None:
        raise ConfigurationError(
            f"Unknown AI provider '{key}'. Supported providers: {', '.join(sorted(PROVIDERS))}."
        )
    return provider_cls()
