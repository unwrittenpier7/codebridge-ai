"""Custom Test Runner: the behavioral verification engine.

The runner never assumes that "it compiled" means "it behaves the same". For every
test case it executes the ORIGINAL program and the MIGRATED program in isolated
Docker containers, captures stdout/stderr/exit codes and compares the observed
behavior. The original program is the behavioral reference: AI supplied expected
outputs are only used as documentation, never as ground truth.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from app.core.logging_config import get_logger
from app.services.docker_executor import DockerExecutor, ExecutionResult, docker_executor
from app.services.output_comparator import compare_outputs

logger = get_logger(__name__)

PASS = "PASS"
FAIL = "FAIL"
PARTIAL = "PARTIAL"
ERROR = "ERROR"


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


@dataclass
class VerificationReport:
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    behavior_match_percentage: float = 0.0
    compilation_status: str = "UNKNOWN"
    runtime_status: str = "UNKNOWN"
    overall_status: str = "UNKNOWN"
    compiler_error: Optional[str] = None
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
            "behavior_match_percentage": self.behavior_match_percentage,
            "failed_tests": [
                {
                    "input": failure.input,
                    "original_output": failure.original_output,
                    "migrated_output": failure.migrated_output,
                    "migrated_stderr": failure.migrated_stderr[:2000],
                    "migrated_exit_code": failure.migrated_exit_code,
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
            runtime_ok = True

            for index, case in enumerate(test_cases, start=1):
                original_run = self.executor.run(original, case.input)
                migrated_run = self.executor.run(migrated, case.input)
                outcome = self._compare_run(index, case, original_run, migrated_run)
                if migrated_run.exit_code != 0 or migrated_run.timed_out:
                    runtime_ok = False
                report.test_results.append(outcome)

            report.passed_tests = sum(1 for r in report.test_results if r.status == PASS)
            report.failed_tests = report.total_tests - report.passed_tests
            report.behavior_match_percentage = round(
                100.0 * report.passed_tests / report.total_tests, 2
            )
            report.runtime_status = PASS if runtime_ok else FAIL
            report.overall_status = self._overall_status(report)
            return report
        finally:
            original.cleanup()
            if migrated is not None:
                migrated.cleanup()

    def _compare_run(
        self,
        index: int,
        case: TestCaseSpec,
        original_run: ExecutionResult,
        migrated_run: ExecutionResult,
    ) -> TestOutcome:
        if original_run.timed_out:
            status, difference = ERROR, "The original program timed out; no reference behavior."
        elif migrated_run.timed_out:
            status, difference = FAIL, "The migrated program timed out."
        elif original_run.exit_code != migrated_run.exit_code:
            status = FAIL
            difference = (
                f"Exit code differs: original {original_run.exit_code}, "
                f"migrated {migrated_run.exit_code}."
            )
        else:
            comparison = compare_outputs(original_run.stdout, migrated_run.stdout)
            status = PASS if comparison.matches else FAIL
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
        )

    def _overall_status(self, report: VerificationReport) -> str:
        if any(result.status == ERROR for result in report.test_results):
            return ERROR
        if report.passed_tests == report.total_tests:
            return PASS
        if report.passed_tests == 0:
            return FAIL
        return PARTIAL


custom_test_runner = CustomTestRunner()
