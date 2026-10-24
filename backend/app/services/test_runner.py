"""Custom Test Runner: the behavioral verification engine.

The runner never assumes that "it compiled" means "it behaves the same". For
every test case it executes the ORIGINAL program and the MIGRATED program in
isolated Docker containers, captures stdout/stderr/exit codes and compares the
observed behavior.

The original program is the behavioral reference. Two rules follow from that and
are enforced here:

1. If the original program cannot be compiled or cannot run a given input
   successfully, that test has **no valid reference**. It is reported as ERROR
   (a property of the harness/reference, not of the migration) and is never
   counted as a behavioral match - not even when the migrated program fails in
   the exact same way.
2. Expected outputs invented by the AI are never ground truth; only the bytes
   actually printed by the original program are.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.logging_config import get_logger
from app.services.docker_executor import DockerExecutor, ExecutionResult, docker_executor
from app.services.output_comparator import compare_outputs

logger = get_logger(__name__)

PASS = "PASS"
FAIL = "FAIL"
PARTIAL = "PARTIAL"
ERROR = "ERROR"

# -- per-test failure classification -------------------------------------------
#: The original program produced no usable reference for this input.
REASON_ORIGINAL_COMPILE_ERROR = "ORIGINAL_COMPILE_ERROR"
REASON_ORIGINAL_RUNTIME_ERROR = "ORIGINAL_RUNTIME_ERROR"
REASON_ORIGINAL_TIMEOUT = "ORIGINAL_TIMEOUT"
#: The migrated program's own failures.
REASON_MIGRATED_COMPILE_ERROR = "MIGRATED_COMPILE_ERROR"
REASON_MIGRATED_RUNTIME_ERROR = "MIGRATED_RUNTIME_ERROR"
REASON_MIGRATED_TIMEOUT = "MIGRATED_TIMEOUT"
#: Both ran; the observable output differs.
REASON_OUTPUT_MISMATCH = "OUTPUT_MISMATCH"
#: Exit codes differ while outputs happened to match.
REASON_EXIT_CODE_MISMATCH = "EXIT_CODE_MISMATCH"


@dataclass
class TestCaseSpec:
    input: str = ""
    description: str = ""
    expected_behavior: str = ""
    category: str = "normal"
    test_case_id: Optional[int] = None


@dataclass
class TestOutcome:
    test_number: int
    test_case_id: Optional[int]
    description: str
    input: str
    original_output: str
    migrated_output: str
    original_stderr: str
    migrated_stderr: str
    original_exit_code: int
    migrated_exit_code: int
    original_time_ms: float
    migrated_time_ms: float
    status: str
    difference: Optional[str] = None
    #: Machine readable classification, e.g. MIGRATED_RUNTIME_ERROR.
    failure_reason: Optional[str] = None
    #: False when the original program could not provide a reference output.
    reference_valid: bool = True


@dataclass
class VerificationReport:
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    error_tests: int = 0
    behavior_match_percentage: float = 0.0
    compilation_status: str = "UNKNOWN"
    runtime_status: str = "UNKNOWN"
    overall_status: str = "UNKNOWN"
    compiler_error: Optional[str] = None
    infrastructure_error: Optional[str] = None
    test_results: List[TestOutcome] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["test_results"] = [asdict(result) for result in self.test_results]
        return data

    def failure_payload(self, limit: int = 5) -> Dict[str, Any]:
        """Compact evidence bundle handed to the AI correction loop."""
        failures = [r for r in self.test_results if r.status != PASS][:limit]
        return {
            "compilation_status": self.compilation_status,
            "compiler_error": self.compiler_error,
            "runtime_status": self.runtime_status,
            "infrastructure_error": self.infrastructure_error,
            "behavior_match_percentage": self.behavior_match_percentage,
            "failed_tests": [
                {
                    "input": failure.input,
                    "original_output": failure.original_output,
                    "migrated_output": failure.migrated_output,
                    "original_stderr": (failure.original_stderr or "")[:2000],
                    "migrated_stderr": (failure.migrated_stderr or "")[:2000],
                    "original_exit_code": failure.original_exit_code,
                    "migrated_exit_code": failure.migrated_exit_code,
                    "reference_valid": failure.reference_valid,
                    "failure_reason": failure.failure_reason,
                    "difference": failure.difference,
                }
                for failure in failures
            ],
        }


class CustomTestRunner:
    """Runs both programs against every test case and produces a verification report."""

    def __init__(self, executor: Optional[DockerExecutor] = None):
        self.executor = executor or docker_executor

    def run(
        self,
        source_code: str,
        source_language: str,
        migrated_code: str,
        target_language: str,
        test_cases: List[TestCaseSpec],
    ) -> VerificationReport:
        report = VerificationReport(total_tests=len(test_cases))
        if not test_cases:
            report.overall_status = ERROR
            report.compiler_error = "No test cases available. Generate test cases first."
            return report

        original = self.executor.prepare(source_language, source_code)
        migrated = None
        try:
            if not original.compilation.success:
                report.compilation_status = ERROR
                report.runtime_status = ERROR
                report.overall_status = ERROR
                report.compiler_error = (
                    "The ORIGINAL program failed to compile, so it cannot act as the "
                    f"behavioral reference:\n{original.compilation.error_message}"
                )
                return report

            migrated = self.executor.prepare(target_language, migrated_code)
            if not migrated.compilation.success:
                report.compilation_status = FAIL
                report.runtime_status = FAIL
                report.overall_status = FAIL
                report.compiler_error = migrated.compilation.error_message
                report.failed_tests = report.total_tests
                report.behavior_match_percentage = 0.0
                return report

            report.compilation_status = PASS

            for index, case in enumerate(test_cases, start=1):
                try:
                    original_run = self.executor.run(original, case.input)
                    migrated_run = self.executor.run(migrated, case.input)
                except Exception as exc:  # infrastructure failure mid-run
                    report.infrastructure_error = str(exc)
                    report.test_results.append(
                        self._infrastructure_outcome(index, case, exc)
                    )
                    break
                report.test_results.append(
                    self._compare_run(index, case, original_run, migrated_run)
                )

            self._summarize(report)
            return report
        finally:
            original.cleanup()
            if migrated is not None:
                migrated.cleanup()

    # -- comparison ---------------------------------------------------------
    def _compare_run(
        self,
        index: int,
        case: TestCaseSpec,
        original_run: ExecutionResult,
        migrated_run: ExecutionResult,
    ) -> TestOutcome:
        reference_valid = True
        failure_reason: Optional[str] = None
        difference: Optional[str] = None

        if original_run.timed_out:
            status = ERROR
            reference_valid = False
            failure_reason = REASON_ORIGINAL_TIMEOUT
            difference = (
                "The ORIGINAL program timed out for this input, so there is no reference "
                "behavior to compare against."
            )
        elif original_run.exit_code != 0:
            status = ERROR
            reference_valid = False
            failure_reason = REASON_ORIGINAL_RUNTIME_ERROR
            difference = (
                f"The ORIGINAL program exited with code {original_run.exit_code} for this "
                "input, so it produced no valid reference output. This test is not counted "
                "as a behavioral match."
            )
        elif migrated_run.timed_out:
            status = FAIL
            failure_reason = REASON_MIGRATED_TIMEOUT
            difference = "The migrated program timed out."
        elif migrated_run.exit_code != 0:
            status = FAIL
            failure_reason = REASON_MIGRATED_RUNTIME_ERROR
            difference = (
                f"The migrated program exited with code {migrated_run.exit_code} while the "
                f"original succeeded (exit code {original_run.exit_code})."
            )
        else:
            comparison = compare_outputs(
                original_run.stdout,
                migrated_run.stdout,
                numeric_tolerance=settings.verification_numeric_tolerance,
                rel_tolerance=settings.verification_numeric_rel_tolerance,
                abs_tolerance=settings.verification_numeric_abs_tolerance,
            )
            if comparison.matches:
                status = PASS
            else:
                status = FAIL
                failure_reason = REASON_OUTPUT_MISMATCH
                difference = comparison.difference

        return TestOutcome(
            test_number=index,
            test_case_id=case.test_case_id,
            description=case.description,
            input=case.input,
            original_output=original_run.stdout,
            migrated_output=migrated_run.stdout,
            original_stderr=original_run.stderr,
            migrated_stderr=migrated_run.stderr,
            original_exit_code=original_run.exit_code,
            migrated_exit_code=migrated_run.exit_code,
            original_time_ms=original_run.execution_time_ms,
            migrated_time_ms=migrated_run.execution_time_ms,
            status=status,
            difference=difference,
            failure_reason=failure_reason,
            reference_valid=reference_valid,
        )

    def _infrastructure_outcome(
        self, index: int, case: TestCaseSpec, exc: Exception
    ) -> TestOutcome:
        return TestOutcome(
            test_number=index,
            test_case_id=case.test_case_id,
            description=case.description,
            input=case.input,
            original_output="",
            migrated_output="",
            original_stderr="",
            migrated_stderr="",
            original_exit_code=0,
            migrated_exit_code=0,
            original_time_ms=0.0,
            migrated_time_ms=0.0,
            status=ERROR,
            difference=f"The execution sandbox failed: {exc}",
            failure_reason="INFRASTRUCTURE_ERROR",
            reference_valid=False,
        )

    # -- aggregation --------------------------------------------------------
    def _summarize(self, report: VerificationReport) -> None:
        executed = len(report.test_results)
        report.passed_tests = sum(1 for r in report.test_results if r.status == PASS)
        report.error_tests = sum(1 for r in report.test_results if r.status == ERROR)
        report.failed_tests = executed - report.passed_tests - report.error_tests
        report.total_tests = report.total_tests or executed

        # The denominator is every requested test: a test that could not run is
        # not a match, and silently shrinking the denominator would overstate the
        # migration's equivalence.
        if report.total_tests:
            report.behavior_match_percentage = round(
                100.0 * report.passed_tests / report.total_tests, 2
            )

        migrated_failures = [
            r
            for r in report.test_results
            if r.failure_reason
            in {
                REASON_MIGRATED_RUNTIME_ERROR,
                REASON_MIGRATED_TIMEOUT,
                REASON_MIGRATED_COMPILE_ERROR,
            }
        ]
        if report.infrastructure_error:
            report.runtime_status = ERROR
        elif migrated_failures:
            report.runtime_status = FAIL
        elif report.compilation_status == PASS:
            report.runtime_status = PASS
        else:
            report.runtime_status = "UNKNOWN"

        report.overall_status = self._overall_status(report)

    def _overall_status(self, report: VerificationReport) -> str:
        if report.infrastructure_error or report.error_tests:
            return ERROR
        if report.total_tests and report.passed_tests == report.total_tests:
            return PASS
        if report.passed_tests == 0:
            return FAIL
        return PARTIAL


custom_test_runner = CustomTestRunner()
