"""Regression tests for AI JSON generation and parsing (Priority 1).

The failure this covers: the model returned HTTP 200 with content that could not
be parsed into a test-case list, and the API surfaced a generic 502. Each case
below is one documented failure mode; all of them must produce a *specific*
error, and the recoverable ones must be retried exactly once.
"""
import json

import pytest

from app.core.errors import (
    AIEmptyResponseError,
    AIInvalidRequestError,
    AIJSONParseError,
    AIProviderError,
    AIRateLimitError,
    AIRefusalError,
    AITestSchemaError,
    AITruncatedResponseError,
)
from app.services.ai_json import extract_json, strip_code_fence
from app.services.ai_providers import Completion, LLMProvider
from app.services.ai_service import AIService
from app.services.test_case_schema import normalize_test_cases


class ScriptedProvider(LLMProvider):
    """Returns a queued sequence of answers and records how often it was called."""

    name = "scripted"

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def is_configured(self) -> bool:
        return True

    def complete(self, system_prompt: str, user_prompt: str, temperature: float = 0.1) -> str:
        self.calls.append(system_prompt)
        return self._next()

    def complete_json(self, system_prompt, user_prompt, temperature=0.1) -> Completion:
        self.calls.append(system_prompt)
        return self._next()

    def _next(self):
        if not self.answers:
            raise AssertionError("provider called more often than expected")
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, Completion):
            return answer
        return Completion(text=answer)


VALID = [
    {"input": "5\n10\n", "expected_behavior": "sum", "description": "normal", "category": "normal"},
    {"input": "0\n0\n", "expected_behavior": "zero", "description": "zero", "category": "zero"},
]


# -- 1. valid JSON returned directly -------------------------------------------
def test_direct_json_array_is_accepted():
    service = AIService(provider=ScriptedProvider([json.dumps(VALID)]))
    cases = service.generate_test_cases("code", "python", count=5)
    assert len(cases) == 2
    assert cases[0]["input"] == "5\n10\n"
    assert cases[1]["category"] == "zero"


# -- 2. JSON surrounded by markdown fences -------------------------------------
def test_fenced_json_is_accepted():
    fenced = "```json\n" + json.dumps(VALID) + "\n```"
    service = AIService(provider=ScriptedProvider([fenced]))
    assert len(service.generate_test_cases("code", "python", count=5)) == 2


def test_unlabelled_fence_is_accepted():
    fenced = "```\n" + json.dumps(VALID) + "\n```"
    service = AIService(provider=ScriptedProvider([fenced]))
    assert len(service.generate_test_cases("code", "python", count=5)) == 2


# -- 3. JSON with harmless surrounding text ------------------------------------
def test_json_with_leading_prose_is_accepted():
    payload = "Sure! Here are the test cases:\n" + json.dumps(VALID) + "\nLet me know if you need more."
    service = AIService(provider=ScriptedProvider([payload]))
    assert len(service.generate_test_cases("code", "python", count=5)) == 2


def test_json_with_wrapper_object_is_unwrapped():
    payload = json.dumps({"test_cases": VALID})
    service = AIService(provider=ScriptedProvider([payload]))
    assert len(service.generate_test_cases("code", "python", count=5)) == 2


# -- 4. invalid JSON -----------------------------------------------------------
def test_invalid_json_is_retried_once_then_raises():
    provider = ScriptedProvider(["this is not json at all", "still not json"])
    service = AIService(provider=provider)
    with pytest.raises(AIJSONParseError):
        service.generate_test_cases("code", "python", count=5)
    assert len(provider.calls) == 2, "a malformed answer must be retried exactly once"


def test_invalid_json_recovers_on_the_single_retry():
    provider = ScriptedProvider(["not json", json.dumps(VALID)])
    service = AIService(provider=provider)
    cases = service.generate_test_cases("code", "python", count=5)
    assert len(cases) == 2
    assert len(provider.calls) == 2


def test_two_conflicting_json_documents_are_rejected():
    text = json.dumps([{"input": "1"}]) + "\n" + json.dumps([{"input": "2"}])
    with pytest.raises(AIJSONParseError):
        extract_json(text)


def test_duplicate_json_documents_are_not_ambiguous():
    payload = json.dumps([{"input": "1"}])
    assert extract_json(payload + "\n" + payload) == [{"input": "1"}]


# -- 5. missing required fields ------------------------------------------------
def test_missing_input_field_is_rejected():
    with pytest.raises(AITestSchemaError):
        normalize_test_cases([{"description": "no input here"}])


def test_entries_missing_input_are_dropped_when_enough_valid_ones_remain():
    payload = [{"description": "bad"}, {"input": "1"}, {"input": "2"}]
    cases = normalize_test_cases(payload)
    assert [case["input"] for case in cases] == ["1", "2"]


def test_mostly_malformed_payload_is_rejected_so_the_model_is_asked_again():
    payload = [{"description": "bad"}] * 5 + [{"input": "1"}]
    with pytest.raises(AITestSchemaError):
        normalize_test_cases(payload)


# -- 6. incorrect field types --------------------------------------------------
def test_non_object_entries_are_rejected():
    with pytest.raises(AITestSchemaError):
        normalize_test_cases(["just a string", 42])


def test_null_input_is_an_invalid_type():
    with pytest.raises(AITestSchemaError):
        normalize_test_cases([{"input": None}])


def test_object_input_is_an_invalid_type():
    with pytest.raises(AITestSchemaError):
        normalize_test_cases([{"input": {"nested": True}}])


def test_object_where_array_expected_is_rejected():
    with pytest.raises(AITestSchemaError):
        normalize_test_cases({"unexpected": "shape"})


def test_scalar_and_list_inputs_are_coerced():
    cases = normalize_test_cases([{"input": 5}, {"input": ["a", "b"]}, {"input": 3.5}])
    assert [case["input"] for case in cases] == ["5", "a\nb", "3.5"]


def test_unknown_category_is_normalized_not_rejected():
    cases = normalize_test_cases([{"input": "1", "category": "Nonsense"}])
    assert cases[0]["category"] == "normal"


def test_duplicate_inputs_are_collapsed():
    cases = normalize_test_cases([{"input": "same"}, {"input": "same"}])
    assert len(cases) == 1


# -- 7. empty test-case lists --------------------------------------------------
def test_empty_array_is_rejected():
    with pytest.raises(AITestSchemaError):
        normalize_test_cases([])


def test_empty_payload_is_rejected():
    with pytest.raises(AITestSchemaError):
        normalize_test_cases(None)


def test_empty_list_from_provider_raises_schema_error():
    service = AIService(provider=ScriptedProvider(["[]", "[]"]))
    with pytest.raises(AITestSchemaError):
        service.generate_test_cases("code", "python", count=5)


# -- 8. truncated model output -------------------------------------------------
def test_truncated_answer_raises_a_truncation_error():
    completion = Completion(text='[{"input": "1"', finish_reason="length")
    service = AIService(provider=ScriptedProvider([completion, completion]))
    with pytest.raises(AITruncatedResponseError):
        service.generate_test_cases("code", "python", count=5)


def test_truncated_but_parseable_answer_is_accepted():
    """A cut that happened to land after the last element is still usable."""
    completion = Completion(text=json.dumps(VALID), finish_reason="length")
    service = AIService(provider=ScriptedProvider([completion]))
    assert len(service.generate_test_cases("code", "python", count=5)) == 2


def test_truncated_answer_is_retried():
    provider = ScriptedProvider(
        [Completion(text='[{"input":', finish_reason="length"), json.dumps(VALID)]
    )
    service = AIService(provider=provider)
    assert len(service.generate_test_cases("code", "python", count=5)) == 2
    assert len(provider.calls) == 2


# -- 9. API errors and rate limits --------------------------------------------
def test_rate_limit_is_not_retried():
    provider = ScriptedProvider([AIRateLimitError("slow down")])
    service = AIService(provider=provider)
    with pytest.raises(AIRateLimitError):
        service.generate_test_cases("code", "python", count=5)
    assert len(provider.calls) == 1, "a rate limit must never be retried immediately"


def test_invalid_request_is_not_retried():
    provider = ScriptedProvider([AIInvalidRequestError("bad model")])
    service = AIService(provider=provider)
    with pytest.raises(AIInvalidRequestError):
        service.generate_test_cases("code", "python", count=5)
    assert len(provider.calls) == 1


def test_generic_provider_error_is_not_retried():
    provider = ScriptedProvider([AIProviderError("upstream exploded")])
    service = AIService(provider=provider)
    with pytest.raises(AIProviderError):
        service.generate_test_cases("code", "python", count=5)
    assert len(provider.calls) == 1


def test_empty_response_is_retried_then_succeeds():
    provider = ScriptedProvider([AIEmptyResponseError("empty"), json.dumps(VALID)])
    service = AIService(provider=provider)
    assert len(service.generate_test_cases("code", "python", count=5)) == 2


# -- 10. refusal or unusable model responses ----------------------------------
def test_refusal_is_not_retried():
    provider = ScriptedProvider([AIRefusalError("I cannot help with that")])
    service = AIService(provider=provider)
    with pytest.raises(AIRefusalError):
        service.generate_test_cases("code", "python", count=5)
    assert len(provider.calls) == 1


def test_prose_only_answer_raises_a_parse_error():
    provider = ScriptedProvider(["I would suggest testing the sum.", "Still prose."])
    service = AIService(provider=provider)
    with pytest.raises(AIJSONParseError):
        service.generate_test_cases("code", "python", count=5)


# -- 11. successful retry after a malformed first response --------------------
def test_retry_uses_a_stricter_system_prompt():
    provider = ScriptedProvider(["garbage", json.dumps(VALID)])
    AIService(provider=provider).generate_test_cases("code", "python", count=5)
    assert "JSON only" in provider.calls[0] or "test engineer" in provider.calls[0].lower()
    assert "previous answer could not be parsed" in provider.calls[1]


def test_count_limit_is_respected():
    payload = json.dumps([{"input": str(index)} for index in range(20)])
    service = AIService(provider=ScriptedProvider([payload]))
    assert len(service.generate_test_cases("code", "python", count=3)) == 3


def test_code_fence_extraction_prefers_the_largest_block():
    text = "```python\nx = 1\n```\nand then\n```python\ny = 2\nz = 3\n```"
    assert strip_code_fence(text) == "y = 2\nz = 3"
