"""Robust extraction and validation of structured JSON from LLM answers.

Models wrap JSON in prose, Markdown fences, or both, and occasionally emit two
competing payloads. This module turns such a response into *one* validated JSON
document, or fails loudly with a specific error. It deliberately never guesses:
a response with two different top-level documents is rejected rather than
silently resolved, because picking the wrong one would corrupt the test suite.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterator, List, Optional, Tuple

from app.core.errors import AIJSONParseError
from app.core.logging_config import get_logger

logger = get_logger(__name__)

#: ```json ... ``` / ``` ... ``` blocks, with optional info string.
FENCE = re.compile(r"```[ \t]*([A-Za-z0-9_+#-]*)[ \t]*\r?\n(.*?)```", re.DOTALL)

#: Characters that may legitimately follow a balanced JSON document.
_ALLOWED_TRAILING = " \t\r\n.,;:!?)]}\"'`*_-"


@dataclass
class ExtractedJSON:
    value: Any
    source: str  # "fenced" | "direct" | "embedded"


def _balanced_spans(text: str) -> Iterator[Tuple[int, int, str]]:
    """Yield (start, end_exclusive, kind) for every balanced {..} / [..] region.

    Scans with a small state machine that is aware of JSON string literals and
    escapes, so braces inside strings do not confuse the depth counter.
    """
    stack: List[str] = []
    start_index = 0
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char in "{[":
            if not stack:
                start_index = index
            stack.append(char)
        elif char in "}]":
            if not stack:
                continue
            opener = stack.pop()
            if (opener, char) not in (("{", "}"), ("[", "]")):
                # Mismatched nesting: the candidate region is not valid JSON.
                stack.clear()
                continue
            if not stack:
                yield start_index, index + 1, "object" if opener == "{" else "array"


def _iter_candidates(text: str) -> Iterator[Tuple[str, str]]:
    """Yield (raw_json, source) candidates in priority order."""
    stripped = (text or "").strip()
    if not stripped:
        return

    # 1. Fenced blocks (prefer json-labelled ones, then any fence, longest first).
    fences = list(FENCE.finditer(stripped))
    ordered = sorted(
        fences,
        key=lambda match: (match.group(1).lower() != "json", -len(match.group(2))),
    )
    for match in ordered:
        body = match.group(2).strip()
        if body:
            yield body, "fenced"

    # 2. The whole response, when it is already a bare JSON document.
    yield stripped, "direct"

    # 3. Balanced regions embedded in surrounding prose.
    for start, end, _kind in _balanced_spans(stripped):
        yield stripped[start:end], "embedded"


def _load(candidate: str) -> Tuple[bool, Any]:
    try:
        return True, json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return False, None


def extract_json(text: str) -> Any:
    """Return the single JSON document contained in an LLM answer.

    Raises `AIJSONParseError` when the answer contains no JSON, or when it
    contains several *different* top-level documents and there is no
    unambiguous way to choose.
    """
    if not (text or "").strip():
        raise AIJSONParseError("The AI response was empty; no JSON to parse.")

    accepted: List[Tuple[str, Any]] = []
    for candidate, source in _iter_candidates(text):
        ok, value = _load(candidate)
        if ok:
            accepted.append((source, value))
            if source in {"fenced", "direct"}:
                # An explicit fence or a bare document is authoritative.
                return value

    if not accepted:
        raise AIJSONParseError(
            "The AI response did not contain valid JSON. "
            "The model may have answered with prose or a malformed document."
        )

    distinct = [value for _source, value in accepted]
    first = distinct[0]
    if all(value == first for value in distinct[1:]):
        return first

    raise AIJSONParseError(
        "The AI response contained multiple conflicting JSON documents, "
        "so the intended payload is ambiguous."
    )


def strip_code_fence(text: str) -> str:
    """Return the largest fenced code block, or the trimmed text when unfenced."""
    matches = FENCE.findall(text or "")
    bodies = [body.strip() for _info, body in matches if body.strip()]
    if bodies:
        return max(bodies, key=len)
    return (text or "").strip()


def find_notes_section(text: str, heading: str) -> str:
    """Return the prose after a `### <heading>` marker, or an empty string."""
    marker = f"### {heading}"
    if marker not in (text or ""):
        return ""
    return text.split(marker, 1)[1].strip()


def trailing_garbage(candidate: str, value: Any) -> Optional[str]:
    """Diagnostic helper: the text that follows a parsed JSON document."""
    if isinstance(value, (dict, list)):
        encoded = json.dumps(value)
        position = (candidate or "").find(encoded[: min(len(encoded), 40)])
        if position >= 0:
            return candidate[position + len(encoded) :][:200]
    return None
