"""Behavioral comparison of two program outputs.

Kept deliberately separate from execution and from migration so that the
comparison policy can be tested (and tightened) in isolation.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import List, Optional

NUMBER = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$")
FLOAT_TOLERANCE = 1e-9


@dataclass
class ComparisonOutcome:
    matches: bool
    difference: Optional[str] = None


def normalize_output(text: str) -> str:
    """Normalize insignificant formatting differences between runtimes.

    Trailing whitespace on each line, Windows line endings and trailing blank
    lines are not behavioral differences; anything else is.
    """
    if text is None:
        return ""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in normalized.split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def _tokens(text: str) -> List[str]:
    return text.split()


def _numerically_equal(left: str, right: str) -> bool:
    """True when both outputs are token-wise equal, comparing numbers numerically."""
    left_tokens, right_tokens = _tokens(left), _tokens(right)
    if len(left_tokens) != len(right_tokens):
        return False
    for a, b in zip(left_tokens, right_tokens):
        if a == b:
            continue
        if NUMBER.match(a) and NUMBER.match(b):
            try:
                if math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=FLOAT_TOLERANCE):
                    continue
            except ValueError:
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
            return (
                f"Line {index + 1}: expected {original!r} but received {migrated!r}."
            )
    return "Outputs differ in trailing content."


def compare_outputs(original: str, migrated: str, numeric_tolerance: bool = True) -> ComparisonOutcome:
    """Compare two program outputs and describe the difference when they diverge."""
    normalized_original = normalize_output(original)
    normalized_migrated = normalize_output(migrated)

    if normalized_original == normalized_migrated:
        return ComparisonOutcome(matches=True)
    if numeric_tolerance and _numerically_equal(normalized_original, normalized_migrated):
        return ComparisonOutcome(matches=True)
    return ComparisonOutcome(
        matches=False, difference=first_difference(normalized_original, normalized_migrated)
    )
