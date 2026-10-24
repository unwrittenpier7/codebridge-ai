"""Verification orchestration and the bounded AI correction loop.

Docker execution lives in `docker_executor`, output comparison in
`output_comparator`, and the run/compare pipeline in `test_runner`. This service
only wires those together with persistence.

Two invariants it protects:

* A migration never stays stuck in an intermediate status. `verify` and
  `fix_with_ai` restore a terminal status on every exit path, including when the
  sandbox raises.
* Every stored `VerificationResult` records the exact code version it tested, so
  a later edit cannot be mistaken for a verified version.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ValidationError
from app.core.logging_config import get_logger
from app.models import (
    CorrectionAttempt,
    Migration,
    MigrationStatus,
    TestResult,
    VerificationResult,
    content_hash,
    test_cases_hash,
)
from app.services.ai_service import AIService, get_ai_service
from app.services.test_runner import (
    CustomTestRunner,
    TestCaseSpec,
    VerificationReport,
    custom_test_runner,
)

logger = get_logger(__name__)

STATUS_TO_MIGRATION_STATUS = {
    "PASS": MigrationStatus.VERIFIED.value,
    "PARTIAL": MigrationStatus.PARTIAL.value,
    "FAIL": MigrationStatus.FAILED.value,
    "ERROR": MigrationStatus.ERROR.value,
}


class VerificationService:
    def __init__(
        self,
        db: Session,
        runner: Optional[CustomTestRunner] = None,
        ai_service: Optional[AIService] = None,
    ):
        self.db = db
        self.runner = runner or custom_test_runner
        self._ai_service = ai_service

    @property
    def ai(self) -> AIService:
        if self._ai_service is None:
            self._ai_service = get_ai_service()
        return self._ai_service

    # -- verification -------------------------------------------------------
    def verify(
        self, migration: Migration, migrated_code: Optional[str] = None
    ) -> VerificationResult:
        if migrated_code:
            migration.migrated_code = migrated_code
        if not (migration.migrated_code or "").strip():
            raise ValidationError("There is no migrated code to verify. Run the migration first.")
        if not migration.test_cases:
            raise ValidationError("No test cases exist for this migration. Generate tests first.")

        migration.status = MigrationStatus.VERIFYING.value
        self.db.commit()
        specs = [
            TestCaseSpec(
                input=case.input or "",
                description=case.description or "",
                expected_behavior=case.expected_behavior or "",
                category=case.category or "normal",
                test_case_id=case.id,
            )
            for case in migration.test_cases
        ]

        attempt_number = len(migration.verification_results)
        try:
            report = self.runner.run(
                source_code=migration.source_code,
                source_language=migration.source_language,
                migrated_code=migration.migrated_code,
                target_language=migration.target_language,
                test_cases=specs,
            )
        except Exception as exc:
            # Infrastructure failure: never leave the record mid-flight.
            logger.exception("Verification crashed for migration %s", migration.id)
            self.db.rollback()
            migration.status = MigrationStatus.ERROR.value
            self.db.commit()
            raise ValidationError(f"Verification could not complete: {exc}") from exc

        try:
            return self._persist_report(migration, report, attempt_number)
        except Exception as exc:
            # A crash while writing the report must not strand the migration in
            # VERIFYING; roll back the partial write and record an error state.
            logger.exception("Storing the verification report failed for migration %s", migration.id)
            self.db.rollback()
            migration.status = MigrationStatus.ERROR.value
            self.db.commit()
            raise ValidationError(f"Verification results could not be stored: {exc}") from exc

    def _persist_report(
        self, migration: Migration, report: VerificationReport, attempt_number: int
    ) -> VerificationResult:
        result = VerificationResult(
            migration_id=migration.id,
            attempt_number=attempt_number,
            total_tests=report.total_tests,
            passed_tests=report.passed_tests,
            failed_tests=report.failed_tests,
            error_tests=report.error_tests,
            behavior_match_percentage=report.behavior_match_percentage,
            compilation_status=report.compilation_status,
            runtime_status=report.runtime_status,
            overall_status=report.overall_status,
            compiler_error=report.compiler_error,
            infrastructure_error=report.infrastructure_error,
            verified_code=migration.migrated_code,
            source_code_hash=content_hash(migration.source_code),
            migrated_code_hash=content_hash(migration.migrated_code),
            test_cases_hash=test_cases_hash(migration.test_cases),
            source_language=migration.source_language,
            target_language=migration.target_language,
        )
        self.db.add(result)
        self.db.flush()

        for outcome in report.test_results:
            self.db.add(
                TestResult(
                    verification_result_id=result.id,
                    test_case_id=outcome.test_case_id,
                    test_number=outcome.test_number,
                    description=outcome.description,
                    input=outcome.input,
                    original_output=outcome.original_output,
                    migrated_output=outcome.migrated_output,
                    original_stderr=outcome.original_stderr,
                    migrated_stderr=outcome.migrated_stderr,
                    original_exit_code=outcome.original_exit_code,
                    migrated_exit_code=outcome.migrated_exit_code,
                    original_time_ms=outcome.original_time_ms,
                    migrated_time_ms=outcome.migrated_time_ms,
                    status=outcome.status,
                    difference=outcome.difference,
                    failure_reason=outcome.failure_reason,
                    reference_valid=outcome.reference_valid,
                )
            )

        migration.status = STATUS_TO_MIGRATION_STATUS.get(
            report.overall_status, MigrationStatus.ERROR.value
        )
        self.db.commit()
        self.db.refresh(result)
        logger.info(
            "Verification for migration %s: %s (%s/%s passed, %s errored)",
            migration.id,
            report.overall_status,
            report.passed_tests,
            report.total_tests,
            report.error_tests,
        )
        return result

    # -- AI correction loop -------------------------------------------------
    def fix_with_ai(
        self, migration: Migration, max_attempts: Optional[int] = None
    ) -> Tuple[List[CorrectionAttempt], List[VerificationResult]]:
        """Iteratively ask the AI to repair the migration, re-verifying each time.

        The loop stops as soon as verification passes, or after at most
        `MAX_CORRECTION_ATTEMPTS` attempts, so it can never run forever.
        """
        limit = min(max_attempts or settings.max_correction_attempts,
                    settings.max_correction_attempts)

        latest = self._latest_result(migration)
        if latest is None:
            latest = self.verify(migration)
        if latest.overall_status == "PASS":
            return [], [latest]

        corrections: List[CorrectionAttempt] = []
        results: List[VerificationResult] = [latest]
        previous_attempts = len(migration.correction_attempts)

        for offset in range(limit):
            attempt_number = previous_attempts + offset + 1
            report_payload = self._failure_payload(latest)
            try:
                correction = self.ai.correct_code(
                    source_code=migration.source_code,
                    source_language=migration.source_language,
                    migrated_code=migration.migrated_code or "",
                    target_language=migration.target_language,
                    failure_report=report_payload,
                )
            except Exception:
                # A failed correction must not strand the migration in a
                # non-terminal state; keep the last known verification verdict.
                self.db.rollback()
                migration.status = STATUS_TO_MIGRATION_STATUS.get(
                    latest.overall_status, MigrationStatus.ERROR.value
                )
                self.db.commit()
                logger.warning(
                    "AI correction attempt failed for migration %s", migration.id, exc_info=True
                )
                raise

            attempt = CorrectionAttempt(
                migration_id=migration.id,
                attempt_number=attempt_number,
                previous_code=migration.migrated_code or "",
                corrected_code=correction["code"],
                reason=correction.get("reason"),
                behavior_match_before=latest.behavior_match_percentage,
            )
            self.db.add(attempt)
            migration.migrated_code = correction["code"]
            self.db.commit()

            latest = self.verify(migration)
            attempt.behavior_match_after = latest.behavior_match_percentage
            self.db.commit()
            self.db.refresh(attempt)

            corrections.append(attempt)
            results.append(latest)

            if latest.overall_status == "PASS":
                break

        return corrections, results

    def _latest_result(self, migration: Migration) -> Optional[VerificationResult]:
        if not migration.verification_results:
            return None
        return sorted(migration.verification_results, key=lambda r: r.id)[-1]

    def _failure_payload(self, result: VerificationResult, limit: int = 5) -> dict:
        failures = [r for r in result.test_results if r.status != "PASS"][:limit]
        return {
            "compilation_status": result.compilation_status,
            "compiler_error": result.compiler_error,
            "runtime_status": result.runtime_status,
            "infrastructure_error": result.infrastructure_error,
            "behavior_match_percentage": result.behavior_match_percentage,
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
