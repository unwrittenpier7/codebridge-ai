"""AI-facing operations: migration, test generation, error analysis and correction.

This module owns prompt construction and response parsing only; the transport is
delegated to an `LLMProvider`.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.errors import AIProviderError
from app.core.languages import get_language
from app.core.logging_config import get_logger
from app.services.ai_providers import LLMProvider, get_provider

logger = get_logger(__name__)

CODE_FENCE = re.compile(r"```[a-zA-Z0-9+#]*\s*\n(.*?)```", re.DOTALL)

MIGRATION_SYSTEM_PROMPT = (
    "You are an expert compiler engineer performing source-to-source code migration. "
    "You translate programs between languages while preserving observable behavior exactly: "
    "the migrated program must read the same stdin format and produce byte-identical stdout "
    "for every input. Never add prompts, banners or extra logging to stdout. "
    "Return a single complete, compilable program."
)

TEST_SYSTEM_PROMPT = (
    "You are a test engineer. You design stdin payloads that exercise a program thoroughly: "
    "normal cases, boundary values, zero, negatives, empty input where applicable, large values "
    "and edge cases. You never invent expected outputs that you cannot justify from the code."
)

FIX_SYSTEM_PROMPT = (
    "You are an expert debugger. Given a source program, a failed migration, and concrete "
    "behavioral differences observed by running both programs, you produce a corrected version "
    "of the migrated program that matches the original's behavior exactly."
)


def extract_code(text: str) -> str:
    """Pull a code block out of an LLM response, tolerating prose around it."""
    matches = CODE_FENCE.findall(text or "")
    if matches:
        return max(matches, key=len).strip()
    return (text or "").strip()


def extract_json(text: str) -> Any:
    """Pull the first JSON object/array out of an LLM response."""
    candidate = (text or "").strip()
    fenced = CODE_FENCE.findall(candidate)
    for block in fenced:
        try:
            return json.loads(block)
        except json.JSONDecodeError:
            continue
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    for opener, closer in (("[", "]"), ("{", "}")):
        start = candidate.find(opener)
        end = candidate.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(candidate[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise AIProviderError("The AI response did not contain valid JSON.")


class AIService:
    """High level AI operations used by the migration and verification services."""

    def __init__(self, provider: Optional[LLMProvider] = None):
        self.provider = provider or get_provider()

    # -- introspection ----------------------------------------------------
    @property
    def provider_name(self) -> str:
        return self.provider.name

    def is_configured(self) -> bool:
        return self.provider.is_configured()

    # -- migration --------------------------------------------------------
    def migrate_code(
        self,
        source_code: str,
        source_language: str,
        target_language: str,
        analysis: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        source = get_language(source_language)
        target = get_language(target_language)
        analysis_block = ""
        if analysis:
            analysis_block = (
                "\nStatic analysis of the source program (for context):\n"
                + json.dumps(analysis, indent=2)[:4000]
            )

        prompt = f"""Migrate the following {source.label} program to {target.label}.

Requirements:
- Preserve behavior exactly, including stdout formatting and stdin parsing.
- The program must be runnable as a standalone file ({target.source_filename}).
- Read input from stdin when the original does; do not print extra prompts.
- Use only the {target.label} standard library.
{"- The Java entry class must be named Main." if target.key == "java" else ""}
{"- Go code must be package main with a func main()." if target.key == "go" else ""}
{analysis_block}

Source ({source.label}):
```{source.monaco_id}
{source_code}
```

Respond with the migrated {target.label} program in a single fenced code block, followed by a short
"### Notes" section explaining non-obvious translation decisions."""

        raw = self.provider.complete(MIGRATION_SYSTEM_PROMPT, prompt)
        code = extract_code(raw)
        if not code:
            raise AIProviderError("The AI did not return any migrated code.")
        notes = ""
        if "### Notes" in raw:
            notes = raw.split("### Notes", 1)[1].strip()
        return {"code": code, "explanation": notes}

    # -- test generation --------------------------------------------------
    def generate_test_cases(
        self,
        source_code: str,
        source_language: str,
        count: int = 8,
        analysis: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, str]]:
        source = get_language(source_language)
        analysis_block = (
            "\nStatic analysis:\n" + json.dumps(analysis, indent=2)[:3000] if analysis else ""
        )
        prompt = f"""Design up to {count} test cases for the following {source.label} program.

Each test case is a stdin payload that will be piped into the program.
If the program reads no input, use an empty string for "input".
Cover: normal cases, boundary cases, zero values, negative values, empty input where
applicable, large values, and edge cases.
{analysis_block}

Program:
```{source.monaco_id}
{source_code}
```

Respond with ONLY a JSON array, no prose, using this shape:
[
  {{"input": "5\\n10\\n", "expected_behavior": "prints the sum 15", "description": "normal case", "category": "normal"}}
]
Use "\\n" escapes for newlines inside the input string. category must be one of:
normal, boundary, zero, negative, empty, large, edge."""

        raw = self.provider.complete(TEST_SYSTEM_PROMPT, prompt, temperature=0.4)
        data = extract_json(raw)
        if isinstance(data, dict):
            data = data.get("test_cases") or data.get("tests") or []
        if not isinstance(data, list):
            raise AIProviderError("The AI did not return a list of test cases.")

        cases: List[Dict[str, str]] = []
        for item in data[:count]:
            if not isinstance(item, dict):
                continue
            raw_input = item.get("input", "")
            if isinstance(raw_input, (list, tuple)):
                raw_input = "\n".join(str(part) for part in raw_input)
            cases.append(
                {
                    "input": str(raw_input),
                    "expected_behavior": str(item.get("expected_behavior", "")).strip(),
                    "description": str(item.get("description", "")).strip() or "AI generated case",
                    "category": str(item.get("category", "normal")).strip().lower(),
                }
            )
        if not cases:
            raise AIProviderError("The AI returned an empty test-case list.")
        return cases

    # -- error analysis / correction --------------------------------------
    def analyze_failure(self, report: Dict[str, Any]) -> str:
        prompt = (
            "Explain, in at most four sentences, why the migrated program behaves differently "
            "from the original given this verification report:\n"
            + json.dumps(report, indent=2)[:6000]
        )
        return self.provider.complete(FIX_SYSTEM_PROMPT, prompt, temperature=0.2)

    def correct_code(
        self,
        source_code: str,
        source_language: str,
        migrated_code: str,
        target_language: str,
        failure_report: Dict[str, Any],
    ) -> Dict[str, str]:
        source = get_language(source_language)
        target = get_language(target_language)
        prompt = f"""The migrated program below does not reproduce the behavior of the original.

Original ({source.label}):
```{source.monaco_id}
{source_code}
```

Current migration ({target.label}):
```{target.monaco_id}
{migrated_code}
```

Verification evidence (produced by actually executing both programs in a sandbox):
```json
{json.dumps(failure_report, indent=2)[:6000]}
```

Fix the {target.label} program so that, for every listed input, its stdout matches the original's
stdout exactly. Keep the same stdin parsing contract.
{"The Java entry class must be named Main." if target.key == "java" else ""}

Respond with the corrected {target.label} program in a single fenced code block, followed by a
"### Reason" section of at most three sentences describing the root cause you fixed."""

        raw = self.provider.complete(FIX_SYSTEM_PROMPT, prompt, temperature=0.1)
        code = extract_code(raw)
        if not code:
            raise AIProviderError("The AI did not return corrected code.")
        reason = ""
        if "### Reason" in raw:
            reason = raw.split("### Reason", 1)[1].strip()
        return {"code": code, "reason": reason or "AI correction attempt."}


def get_ai_service() -> AIService:
    return AIService()
