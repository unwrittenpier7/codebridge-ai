"""Schema enforcement for AI-generated test cases.

The model is asked for a JSON array of objects. Real answers sometimes arrive as
a wrapper object, with a missing key, with the wrong type, or with most of the
array malformed. This module is the single place that decides what a usable test
case is, so the rule is testable in isolation.

Policy (deliberately explicit):

* A wrapper object is unwrapped only through the documented keys
  (`test_cases`, `tests`, `cases`, `data`).
* `input` is required and must be a string, a scalar, or a list of scalars;
  it may be empty (programs that read nothing), but `null` is not a value the
  prompt permits and is treated as an invalid type.
* Unknown categories are normalized to `normal`; over-long text is truncated to
  the database column widths rather than rejected.
* Malformed items are dropped, but if they are at least half of the payload the
  whole answer is rejected so the model can be asked again. A payload in which
  most items do not match the schema usually means the schema was misunderstood,
  not that a couple of entries were sloppy.
* Duplicate inputs are collapsed: re-running the same stdin proves nothing.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.core.errors import AITestSchemaError

WRAPPER_KEYS = ("test_cases", "tests", "cases", "data")

VALID_CATEGORIES = {"normal", "boundary", "zero", "negative", "empty", "large", "edge"}
DEFAULT_CATEGORY = "normal"

DESCRIPTION_MAX = 500  # matches TestCase.description (String(500))
CATEGORY_MAX = 64  # matches TestCase.category (String(64))
INPUT_MAX_CHARS = 64_000  # a stdin payload beyond this is not a test case
SCALAR_TYPES = (str, int, float, bool)


def _coerce_input(value: Any) -> Tuple[bool, str]:
    """Return (ok, normalized_input)."""
    if isinstance(value, str):
        return True, value
    if isinstance(value, bool):
        return True, "true" if value else "false"
    if isinstance(value, (int, float)):
        return True, str(value)
    if isinstance(value, (list, tuple)):
        parts: List[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, bool):
                parts.append("true" if item else "false")
            elif isinstance(item, (int, float)):
                parts.append(str(item))
            else:
                return False, ""
        return True, "\n".join(parts)
    return False, ""


def _unwrap(payload: Any) -> Any:
    """Accept a bare array or one of the documented wrapper objects."""
    if isinstance(payload, dict):
        for key in WRAPPER_KEYS:
            if key in payload:
                return payload[key]
        return payload
    return payload


def normalize_test_cases(payload: Any, count: Optional[int] = None) -> List[Dict[str, str]]:
    """Validate and normalize an AI payload into test-case dictionaries.

    Raises `AITestSchemaError` (retryable) when nothing usable can be extracted.
    """
    if payload is None:
        raise AITestSchemaError("The AI returned no test-case payload.")

    data = _unwrap(payload)
    if isinstance(data, dict):
        raise AITestSchemaError(
            "The AI returned a JSON object where a list of test cases was required."
        )
    if not isinstance(data, list):
        raise AITestSchemaError(
            f"The AI returned {type(data).__name__} where a list of test cases was required."
        )
    if not data:
        raise AITestSchemaError("The AI returned an empty test-case list.")

    valid: List[Dict[str, str]] = []
    invalid = 0
    first_reason = ""
    seen_inputs: set[str] = set()

    for item in data:
        if not isinstance(item, dict):
            invalid += 1
            first_reason = first_reason or "A test-case entry was not a JSON object."
            continue
        if "input" not in item:
            invalid += 1
            first_reason = first_reason or 'A test-case entry was missing the required "input" field.'
            continue

        ok, normalized_input = _coerce_input(item.get("input"))
        if not ok:
            invalid += 1
            first_reason = first_reason or (
                'A test-case "input" was neither a string, a number nor a list of scalars.'
            )
            continue
        if len(normalized_input) > INPUT_MAX_CHARS:
            invalid += 1
            first_reason = first_reason or "A test-case input was implausibly large."
            continue

        if normalized_input in seen_inputs:
            # Duplicate stdin: keep the first occurrence, do not count as invalid.
            continue
        seen_inputs.add(normalized_input)

        category = str(item.get("category") or DEFAULT_CATEGORY).strip().lower()
        if category not in VALID_CATEGORIES:
            category = DEFAULT_CATEGORY

        valid.append(
            {
                "input": normalized_input,
                "expected_behavior": str(item.get("expected_behavior") or "").strip()[:2000],
                "description": (
                    str(item.get("description") or "").strip()[:DESCRIPTION_MAX]
                    or "AI generated case"
                ),
                "category": category[:CATEGORY_MAX],
            }
        )

    if not valid:
        raise AITestSchemaError(
            "No usable test cases were found in the AI response. " + (first_reason or "")
        )

    if invalid and invalid >= len(valid):
        raise AITestSchemaError(
            f"{invalid} of {len(data)} test-case entries did not match the required schema "
            f"({first_reason}). The answer looks like a different format."
        )

    return valid[:count] if count else valid
