"""AI-facing operations: migration, test generation, error analysis and correction.

This module owns prompt construction, response parsing and the *single* bounded
retry allowed for a recoverable malformed answer. The transport is delegated to
an `LLMProvider`.

Two completion flavours are kept strictly apart:

* source-code generation (`migrate_code`, `correct_code`) uses free-form text;
* structured generation (`generate_test_cases`) uses the provider's JSON mode and
  the schema validation in `app.services.test_case_schema`.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.core.errors import (
    AIProviderError,
    AITestSchemaError,
    AITruncatedResponseError,
    ValidationError,
)
from app.core.languages import get_language
from app.core.logging_config import get_logger
from app.services.ai_json import extract_json, find_notes_section, strip_code_fence
from app.services.ai_providers import Completion, LLMProvider, get_provider
from app.services.test_case_schema import normalize_test_cases

logger = get_logger(__name__)

#: One retry only: a second malformed answer means the model is not usable here.
MAX_JSON_ATTEMPTS = 2

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
    "and edge cases. You never invent expected outputs that you cannot justify from the code. "
    "You answer with JSON only, exactly in the requested schema."
)

TEST_RETRY_SYSTEM_PROMPT = (
    TEST_SYSTEM_PROMPT
    + " The previous answer could not be parsed. Return ONLY the JSON array, with no "
    "explanation, no Markdown fence and no commentary."
)

FIX_SYSTEM_PROMPT = (
    "You are an expert debugger. Given a source program, a failed migration, and concrete "
    "behavioral differences observed by running both programs, you produce a corrected version "
    "of the migrated program that matches the original's behavior exactly."
)


def extract_code(text: str) -> str:
    """Pull a code block out of an LLM response, tolerating prose around it."""
    return strip_code_fence(text)


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
                "\nStatic analysis of the source program (best-effort context, not a proof of "
                "equivalence):\n" + json.dumps(analysis, indent=2)[:4000]
            )

        prompt = f"""Migrate the following {source.label} program to {target.label}.

Requirements:
- Preserve behavior exactly, including stdout formatting and stdin parsing.
- The program must be runnable as a standalone file ({target.source_filename}).
- Read input from stdin when the original does; do not print extra prompts.
- Use only the {target.label} standard library.
{target.migration_guidance}
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
        return {"code": code, "explanation": find_notes_section(raw, "Notes")}

    # -- test generation --------------------------------------------------
    def generate_test_cases(
        self,
        source_code: str,
        source_language: str,
        count: int = 8,
        analysis: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, str]]:
        """Ask the model for stdin payloads and return validated, normalized cases.

        Exactly one retry is attempted when the first answer is unusable *and*
        the failure is recoverable (malformed JSON, wrong shape, truncation,
        empty answer). Refusals, rate limits and invalid requests are never
        retried because a second identical request cannot succeed.
        """
        source = get_language(source_language)
        analysis_block = (
            "\nStatic analysis (best-effort context):\n"
            + json.dumps(analysis, indent=2)[:3000]
            if analysis
            else ""
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

        last_error: Optional[Exception] = None
        for attempt in range(MAX_JSON_ATTEMPTS):
            system_prompt = TEST_SYSTEM_PROMPT if attempt == 0 else TEST_RETRY_SYSTEM_PROMPT
            try:
                completion = self.provider.complete_json(
                    system_prompt, prompt, temperature=0.4
                )
                return self._parse_test_cases(completion, count)
            except AIProviderError as exc:
                # Only failures that a stricter second request could plausibly fix
                # are retried: unusable/malformed/empty/truncated answers. A
                # refusal, a rate limit or an invalid request is deterministic, so
                # retrying it would just burn another API call.
                last_error = exc
                if not getattr(exc, "retryable", False) or attempt == MAX_JSON_ATTEMPTS - 1:
                    raise
                logger.warning(
                    "Test generation attempt %s/%s failed (%s); retrying once.",
                    attempt + 1,
                    MAX_JSON_ATTEMPTS,
                    type(exc).__name__,
                )

        assert last_error is not None
        raise last_error

    @staticmethod
    def _parse_test_cases(completion: Completion, count: int) -> List[Dict[str, str]]:
        raw = completion.text
        try:
            data = extract_json(raw)
        except AIProviderError as exc:
            if completion.truncated:
                # Distinguish "the model ran out of room" from "the model wrote
                # something unparseable", because the fix is different.
                raise AITruncatedResponseError(
                    "The AI response was cut off at the model's output limit, so the "
                    "test-case list is incomplete. Try requesting fewer test cases."
                ) from exc
            raise
        return normalize_test_cases(data, count)

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
{target.migration_guidance}

Respond with the corrected {target.label} program in a single fenced code block, followed by a
"### Reason" section of at most three sentences describing the root cause you fixed."""

        raw = self.provider.complete(FIX_SYSTEM_PROMPT, prompt, temperature=0.1)
        code = extract_code(raw)
        if not code:
            raise AIProviderError("The AI did not return corrected code.")
        reason = find_notes_section(raw, "Reason")
        return {"code": code, "reason": reason or "AI correction attempt."}


def get_ai_service() -> AIService:
    return AIService()
