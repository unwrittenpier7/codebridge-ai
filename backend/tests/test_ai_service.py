import json

import pytest

from app.core.errors import AIProviderError, ConfigurationError
from app.services.ai_providers import LLMProvider, OpenAIProvider, get_provider
from app.services.ai_service import AIService, extract_code, extract_json


class StubProvider(LLMProvider):
    name = "stub"

    def __init__(self, response: str):
        self.response = response
        self.calls = []

    def is_configured(self) -> bool:
        return True

    def complete(self, system_prompt: str, user_prompt: str, temperature: float = 0.1) -> str:
        self.calls.append((system_prompt, user_prompt, temperature))
        return self.response


def test_extract_code_prefers_fenced_block():
    text = "Here you go:\n```python\nprint(1)\n```\nDone."
    assert extract_code(text) == "print(1)"


def test_extract_json_handles_prose_around_the_payload():
    assert extract_json('Sure!\n[{"input": "1"}]') == [{"input": "1"}]


def test_extract_json_raises_on_garbage():
    with pytest.raises(AIProviderError):
        extract_json("no json at all")


def test_migrate_code_returns_code_and_notes():
    provider = StubProvider("```python\nprint(1)\n```\n### Notes\nUsed print.")
    service = AIService(provider=provider)
    result = service.migrate_code("System.out.println(1);", "java", "python")
    assert result["code"] == "print(1)"
    assert "Used print" in result["explanation"]


def test_migrate_code_errors_when_no_code_comes_back():
    with pytest.raises(AIProviderError):
        AIService(provider=StubProvider("")).migrate_code("x", "python", "go")


def test_generate_test_cases_normalizes_entries():
    payload = json.dumps(
        [
            {"input": "5\n10\n", "expected_behavior": "sum", "description": "normal", "category": "normal"},
            {"input": ["1", "2"], "description": "list input"},
        ]
    )
    cases = AIService(provider=StubProvider(payload)).generate_test_cases("code", "python", count=5)
    assert cases[0]["input"] == "5\n10\n"
    assert cases[1]["input"] == "1\n2"
    assert cases[1]["category"] == "normal"


def test_correct_code_extracts_reason():
    provider = StubProvider("```go\npackage main\n```\n### Reason\nOff-by-one.")
    result = AIService(provider=provider).correct_code(
        "src", "python", "bad", "go", {"failed_tests": []}
    )
    assert result["code"] == "package main"
    assert "Off-by-one" in result["reason"]


def test_unconfigured_provider_raises_configuration_error(monkeypatch):
    provider = OpenAIProvider()
    monkeypatch.setattr("app.core.config.settings.openai_api_key", "", raising=False)
    assert not provider.is_configured()
    with pytest.raises(ConfigurationError):
        provider.ensure_configured()


def test_unknown_provider_is_rejected():
    with pytest.raises(ConfigurationError):
        get_provider("not-a-provider")
