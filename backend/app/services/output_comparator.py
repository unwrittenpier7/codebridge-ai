"""Behavioral comparison of two program outputs.

Kept deliberately separate from execution and from migration so that the
comparison policy can be stated, tested and tightened in isolation.

Normalization policy (exhaustive - anything not listed here is a difference):

* CRLF and lone CR are converted to LF. Line endings are a platform artifact,
  not program behavior.
* Trailing spaces/tabs at the end of a line are removed. Trailing horizontal
  whitespace is invisible in a terminal and is produced inconsistently by
  different runtimes.
* Trailing empty lines at the end of the output are removed.

Everything else is significant, including leading whitespace, internal runs of
spaces, the number of trailing newlines *within* the body, and case.

Numeric tolerance is **off by default**: `3.0` and `3` are different bytes and a
migration that changes them has changed observable behavior. Callers that have a
reason to treat them as equal pass `numeric_tolerance=True` explicitly.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import List, Optional

#: Matches a complete numeric token, including exponent and sign.
NUMBER = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$")

#: Default relative/absolute tolerance when numeric comparison is requested.
DEFAULT_REL_TOLERANCE = 1e-9
DEFAULT_ABS_TOLERANCE = 1e-9

#: Longest token sequence compared numerically; keeps pathological output cheap.
MAX_NUMERIC_TOKENS = 100_000


@dataclass
class ComparisonOutcome:
    matches: bool
    difference: Optional[str] = None


def normalize_output(text: str) -> str:
    """Apply the documented normalization policy to a program's stdout."""
    if text is None:
        return ""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip(" \t") for line in normalized.split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def _tokens(text: str) -> List[str]:
    return text.split()


def _numerically_equal(
    left: str,
    right: str,
    rel_tolerance: float = DEFAULT_REL_TOLERANCE,
    abs_tolerance: float = DEFAULT_ABS_TOLERANCE,
) -> bool:
    """True when both outputs are token-wise equal, comparing numbers numerically.

    Only *whole* tokens are compared numerically: a token that is not a number
    must match its counterpart exactly, so `1e` vs `1.0` is not silently equal.
    """
    left_tokens, right_tokens = _tokens(left), _tokens(right)
    if len(left_tokens) != len(right_tokens):
        return False
    if len(left_tokens) > MAX_NUMERIC_TOKENS:
        return False
    for a, b in zip(left_tokens, right_tokens):
        if a == b:
            continue
        if NUMBER.match(a) and NUMBER.match(b):
            try:
                if math.isclose(float(a), float(b), rel_tol=rel_tolerance, abs_tol=abs_tolerance):
                    continue
            except (ValueError, OverflowError):
                return False
        return False
    return True


def first_difference(left: str, right: str) -> str:
    """Human readable description of where two outputs diverge."""
    left_lines = left.split("\n")
    right_lines = right.split("\n")
    for index in range(max(len(left_lines), len(right_lines))):
        original = left_lines[index] if index < len(left_lines) else "<no output>"
        migrated = right_lines[index] if index < len(right_lines) else "<no output>"
        if original != migrated:
            return f"Line {index + 1}: expected {original!r} but received {migrated!r}."
    if len(left_lines) != len(right_lines):
        return (
            f"Output line count differs: expected {len(left_lines)}, "
            f"received {len(right_lines)}."
        )
    return "Outputs differ in trailing content."


def compare_outputs(
    original: str,
    migrated: str,
    numeric_tolerance: bool = False,
    rel_tolerance: float = DEFAULT_REL_TOLERANCE,
    abs_tolerance: float = DEFAULT_ABS_TOLERANCE,
) -> ComparisonOutcome:
    """Compare two program outputs and describe the difference when they diverge.

    Numeric tolerance is opt-in: by default two outputs must be identical after
    the documented whitespace normalization.
    """
    normalized_original = normalize_output(original)
    normalized_migrated = normalize_output(migrated)

    if normalized_original == normalized_migrated:
        return ComparisonOutcome(matches=True)
    if numeric_tolerance and _numerically_equal(
        normalized_original, normalized_migrated, rel_tolerance, abs_tolerance
    ):
        return ComparisonOutcome(matches=True)
    return ComparisonOutcome(
        matches=False, difference=first_difference(normalized_original, normalized_migrated)
    )
