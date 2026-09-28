"""Deterministic stand-ins for the AI provider used by the API tests.

Only the LLM transport is stubbed: Docker execution, output comparison and the
verification pipeline still run for real.
"""
from typing import Any, Dict, List

from app.services.ai_service import AIService
from app.services.ai_providers import LLMProvider

PYTHON_ADDER = "import sys\n" "a, b = [int(x) for x in sys.stdin.read().split()[:2]]\n" "print(a + b)\n"
PYTHON_ADDER_BROKEN = (
    "import sys\n" "a, b = [int(x) for x in sys.stdin.read().split()[:2]]\n" "print(a - b)\n"
)


class ScriptedProvider(LLMProvider):
    """Returns canned completions in order, per prompt kind."""

    name = "scripted"

    def __init__(self, migrations: List[str] = None, tests: str = "", corrections: List[str] = None):
        self.migrations = list(migrations or [])
        self.tests = tests
        self.corrections = list(corrections or [])
        self.calls: List[str] = []

    def is_configured(self) -> bool:
        return True

    def complete(self, system_prompt: str, user_prompt: str, temperature: float = 0.1) -> str:
        if "test case" in user_prompt.lower() or "test cases" in user_prompt.lower():
            self.calls.append("tests")
            return self.tests
        if "does not reproduce" in user_prompt:
            self.calls.append("correct")
            return self.corrections.pop(0) if self.corrections else "```python\n```"
        self.calls.append("migrate")
        return self.migrations.pop(0) if self.migrations else "```python\npass\n```"


def scripted_ai(**kwargs: Any) -> AIService:
    return AIService(provider=ScriptedProvider(**kwargs))


def build_tests_payload(inputs: List[str]) -> str:
    import json

    return json.dumps(
        [
            {
                "input": value,
                "expected_behavior": "behaves like the original",
                "description": f"case {index + 1}",
                "category": "normal",
            }
            for index, value in enumerate(inputs)
        ]
    )


def fenced(code: str, language: str = "python", section: str = "### Notes\nstubbed") -> str:
    return f"```{language}\n{code}```\n{section}"


def patch_ai(monkeypatch, provider: LLMProvider) -> None:
    """Point every service at the given provider."""
    service = AIService(provider=provider)
    for module in (
        "app.services.migration_service",
        "app.services.test_generation_service",
        "app.services.verification_service",
    ):
        monkeypatch.setattr(f"{module}.get_ai_service", lambda: service)


def failure_report_stub() -> Dict[str, Any]:
    return {"failed_tests": [{"input": "1 2", "original_output": "3", "migrated_output": "-1"}]}
