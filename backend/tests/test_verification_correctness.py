"""Regression tests for behavioral verification correctness (Priority 3).

These run without Docker: a fake executor returns scripted `ExecutionResult`
objects so every branch of the comparison policy is exercised deterministically.
The real-Docker integration tests live in `test_verification_pipeline.py`.

The core invariant under test: *a migrated program must never be reported as
behaviorally equivalent to an original program that itself failed.*
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pytest

from app.services.docker_executor import CompilationResult, ExecutionResult, PreparedProgram
from app.services.test_runner import (
    ERROR,
    FAIL,
    PARTIAL,
    PASS,
    REASON_MIGRATED_RUNTIME_ERROR,
    REASON_MIGRATED_TIMEOUT,
    REASON_ORIGINAL_RUNTIME_ERROR,
    REASON_ORIGINAL_TIMEOUT,
    REASON_OUTPUT_MISMATCH,
    CustomTestRunner,
    TestCaseSpec,
)


@dataclass
class FakeProgram:
    language: object
    workdir: str = "/tmp/fake"
    run_command: List[str] = field(default_factory=list)
    compilation: CompilationResult = field(
        default_factory=lambda: CompilationResult(success=True)
    )

    def cleanup(self) -> None:
        pass


class FakeExecutor:
    """Returns scripted results keyed by (language, stdin) in order."""

    def __init__(self, original_runs, migrated_runs, original_compiles=True, migrated_compiles=True):
        self.original_runs = list(original_runs)
        self.migrated_runs = list(migrated_runs)
        self.original_compiles = original_compiles
        self.migrated_compiles = migrated_compiles
        self.prepared: List[str] = []

    def prepare(self, language_key: str, code: str) -> FakeProgram:
        self.prepared.append(language_key)
        if language_key == "original":
            success = self.original_compiles
            return FakeProgram(
                language=language_key,
                compilation=CompilationResult(success=success, stderr="" if success else "boom"),
            )
        success = self.migrated_compiles
        return FakeProgram(
            language=language_key,
            compilation=CompilationResult(success=success, stderr="" if success else "boom"),
        )

    def run(self, program, stdin_data="", timeout=None) -> ExecutionResult:
        queue = self.original_runs if program.language == "original" else self.migrated_runs
        if not queue:
            raise AssertionError("executor ran more times than scripted")
        return queue.pop(0)


def runner_for(original_runs, migrated_runs, **kwargs) -> CustomTestRunner:
    return CustomTestRunner(executor=FakeExecutor(original_runs, migrated_runs, **kwargs))


def cases(*inputs) -> List[TestCaseSpec]:
    return [TestCaseSpec(input=value) for value in inputs]


def ok(stdout: str = "15\n", exit_code: int = 0) -> ExecutionResult:
    return ExecutionResult(stdout=stdout, exit_code=exit_code)


def run_ok(**kwargs) -> ExecutionResult:
    return ExecutionResult(exit_code=0, stdout="15\n", **kwargs)


# -- original program failures -------------------------------------------------
def test_original_compilation_failure_is_an_error_not_a_pass():
    report = runner_for([], [], original_compiles=False).run(
        "src", "original", "mig", "migrated", cases("1\n")
    )
    assert report.overall_status == ERROR
    assert report.passed_tests == 0
    assert report.behavior_match_percentage == 0.0
    assert "ORIGINAL" in report.compiler_error


def test_original_runtime_failure_never_counts_as_a_match():
    """The heart of the bug: both programs fail identically -> still not a pass."""
    original = ExecutionResult(stdout="", stderr="error", exit_code=1)
    migrated = ExecutionResult(stdout="", stderr="error", exit_code=1)
    report = runner_for([original], [migrated]).run(
        "src", "original", "mig", "migrated", cases("1\n")
    )
    assert report.passed_tests == 0
    assert report.overall_status == ERROR
    assert report.test_results[0].reference_valid is False
    assert report.test_results[0].failure_reason == REASON_ORIGINAL_RUNTIME_ERROR
    assert report.behavior_match_percentage == 0.0


def test_original_timeout_is_an_error():
    original = ExecutionResult(timed_out=True, exit_code=124)
    migrated = ExecutionResult(stdout="15\n", exit_code=0)
    report = runner_for([original], [migrated]).run(
        "src", "original", "mig", "migrated", cases("1\n")
    )
    assert report.overall_status == ERROR
    assert report.test_results[0].failure_reason == REASON_ORIGINAL_TIMEOUT
    assert report.test_results[0].reference_valid is False


# -- migrated program failures -------------------------------------------------
def test_migrated_compilation_failure_is_reported():
    report = runner_for([], [], migrated_compiles=False).run(
        "src", "original", "mig", "migrated", cases("1\n", "2\n")
    )
    assert report.overall_status == FAIL
    assert report.compilation_status == FAIL
    assert report.failed_tests == 2
    assert report.behavior_match_percentage == 0.0


def test_migrated_runtime_failure_is_distinguished_from_an_output_mismatch():
    report = runner_for(
        [ExecutionResult(stdout="15\n", exit_code=0)],
        [ExecutionResult(stdout="", stderr="Traceback", exit_code=1)],
    ).run("src", "original", "mig", "migrated", cases("1\n"))
    assert report.overall_status == FAIL
    assert report.runtime_status == FAIL
    outcome = report.test_results[0]
    assert outcome.failure_reason == REASON_MIGRATED_RUNTIME_ERROR
    assert outcome.reference_valid is True
    assert "exited with code 1" in outcome.difference


def test_migrated_timeout_is_reported():
    report = runner_for(
        [ExecutionResult(stdout="15\n", exit_code=0)],
        [ExecutionResult(timed_out=True, exit_code=124)],
    ).run("src", "original", "mig", "migrated", cases("1\n"))
    assert report.test_results[0].failure_reason == REASON_MIGRATED_TIMEOUT
    assert report.overall_status == FAIL


# -- exit codes and outputs ----------------------------------------------------
def test_matching_outputs_with_nonzero_original_exit_status_is_not_a_pass():
    report = runner_for(
        [ExecutionResult(stdout="partial\n", exit_code=2)],
        [ExecutionResult(stdout="partial\n", exit_code=2)],
    ).run("src", "original", "mig", "migrated", cases("1\n"))
    assert report.passed_tests == 0
    assert report.overall_status == ERROR


def test_matching_outputs_and_zero_exit_status_is_a_pass():
    report = runner_for(
        [ExecutionResult(stdout="15\n", exit_code=0)],
        [ExecutionResult(stdout="15\n", exit_code=0)],
    ).run("src", "original", "mig", "migrated", cases("1\n"))
    assert report.overall_status == PASS
    assert report.behavior_match_percentage == 100.0


def test_whitespace_only_difference_still_matches():
    report = runner_for(
        [ExecutionResult(stdout="15  \r\n\n", exit_code=0)],
        [ExecutionResult(stdout="15\n", exit_code=0)],
    ).run("src", "original", "mig", "migrated", cases("1\n"))
    assert report.overall_status == PASS


def test_meaningful_string_difference_fails():
    report = runner_for(
        [ExecutionResult(stdout="hello\n", exit_code=0)],
        [ExecutionResult(stdout="Hello\n", exit_code=0)],
    ).run("src", "original", "mig", "migrated", cases("1\n"))
    assert report.overall_status == FAIL
    assert report.test_results[0].failure_reason == REASON_OUTPUT_MISMATCH


def test_float_formatting_difference_fails_by_default():
    report = runner_for(
        [ExecutionResult(stdout="3.0\n", exit_code=0)],
        [ExecutionResult(stdout="3\n", exit_code=0)],
    ).run("src", "original", "mig", "migrated", cases("1\n"))
    assert report.overall_status == FAIL


def test_empty_output_and_empty_input_are_compared():
    report = runner_for(
        [ExecutionResult(stdout="", exit_code=0)],
        [ExecutionResult(stdout="", exit_code=0)],
    ).run("src", "original", "mig", "migrated", cases(""))
    assert report.overall_status == PASS


def test_multiple_input_lines_are_all_executed():
    report = runner_for(
        [ExecutionResult(stdout=str(n), exit_code=0) for n in (1, 2, 3)],
        [ExecutionResult(stdout=str(n), exit_code=0) for n in (1, 2, 3)],
    ).run("src", "original", "mig", "migrated", cases("a\n", "b\n", "c\n"))
    assert report.total_tests == 3
    assert report.passed_tests == 3


def test_large_and_negative_values_are_compared():
    report = runner_for(
        [ExecutionResult(stdout="-9223372036854775808\n", exit_code=0)],
        [ExecutionResult(stdout="-9223372036854775807\n", exit_code=0)],
    ).run("src", "original", "mig", "migrated", cases("-9999999999999999999\n"))
    assert report.overall_status == FAIL


# -- aggregation ---------------------------------------------------------------
def test_partial_match_counts_only_real_matches():
    report = runner_for(
        [ExecutionResult(stdout="1", exit_code=0), ExecutionResult(stdout="2", exit_code=0)],
        [ExecutionResult(stdout="1", exit_code=0), ExecutionResult(stdout="9", exit_code=0)],
    ).run("src", "original", "mig", "migrated", cases("a", "b"))
    assert report.overall_status == PARTIAL
    assert report.passed_tests == 1
    assert report.failed_tests == 1
    assert report.behavior_match_percentage == 50.0


def test_unrunnable_tests_shrink_the_score_not_the_denominator():
    """2 requested, 1 runnable match, 1 original failure -> 50%, not 100%."""
    report = runner_for(
        [ExecutionResult(stdout="1", exit_code=0), ExecutionResult(exit_code=1)],
        [ExecutionResult(stdout="1", exit_code=0), ExecutionResult(exit_code=1)],
    ).run("src", "original", "mig", "migrated", cases("a", "b"))
    assert report.total_tests == 2
    assert report.passed_tests == 1
    assert report.error_tests == 1
    assert report.behavior_match_percentage == 50.0
    assert report.overall_status == ERROR


def test_no_test_cases_is_an_error():
    report = runner_for([], []).run("src", "original", "mig", "migrated", [])
    assert report.overall_status == ERROR
    assert "test cases" in report.compiler_error.lower()


# -- infrastructure failures ---------------------------------------------------
def test_sandbox_failure_is_classified_as_infrastructure_error():
    class ExplodingExecutor(FakeExecutor):
        def run(self, program, stdin_data="", timeout=None):
            raise RuntimeError("docker daemon went away")

    runner = CustomTestRunner(executor=ExplodingExecutor([], []))
    report = runner.run("src", "original", "mig", "migrated", cases("1\n"))
    assert report.overall_status == ERROR
    assert report.infrastructure_error
    assert report.test_results[0].failure_reason == "INFRASTRUCTURE_ERROR"


def test_repeated_runs_are_deterministic():
    def run_once():
        return runner_for(
            [ExecutionResult(stdout="15\n", exit_code=0)] * 2,
            [ExecutionResult(stdout="15\n", exit_code=0)] * 2,
        ).run("src", "original", "mig", "migrated", cases("a", "b"))

    first, second = run_once(), run_once()
    assert first.to_dict() == second.to_dict()


def test_failure_payload_carries_the_classification_for_the_ai():
    report = runner_for(
        [ExecutionResult(stdout="15\n", exit_code=0)],
        [ExecutionResult(stdout="16\n", exit_code=0)],
    ).run("src", "original", "mig", "migrated", cases("1\n"))
    payload = report.failure_payload()
    failure = payload["failed_tests"][0]
    assert failure["failure_reason"] == REASON_OUTPUT_MISMATCH
    assert failure["reference_valid"] is True
    assert failure["original_output"] == "15\n"
