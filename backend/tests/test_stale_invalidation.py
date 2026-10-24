"""Regression tests for stale test/verification invalidation (Priority 4).

The bug this covers: editing source code (or switching languages) left the old
verification PASS visible as if it still described the edited program.

These tests use stubbed verification so no Docker is required: what is under test
is the *invalidation bookkeeping*, not the sandbox.
"""
import pytest

from app.models import Migration, TestCase, User, content_hash
from app.schemas.migration import MigrationUpdate
from app.services.migration_service import MigrationService
from app.services.verification_service import VerificationService
from app.services.test_runner import VerificationReport, TestOutcome


SOURCE_V1 = "print(1)\n"
SOURCE_V2 = "print(2)\n"


@pytest.fixture()
def user(db_session):
    account = User(name="Owner", email="owner@example.com", password_hash="x")
    db_session.add(account)
    db_session.commit()
    return account


@pytest.fixture()
def migration(db_session, user):
    record = Migration(
        user_id=user.id,
        title="m",
        source_language="python",
        target_language="python",
        source_code=SOURCE_V1,
        migrated_code="print(1)\n",
    )
    db_session.add(record)
    db_session.commit()
    return record


class StubRunner:
    """Returns a fixed PASS report so persistence can be tested without Docker."""

    def __init__(self, status="PASS"):
        self.status = status

    def run(self, source_code, source_language, migrated_code, target_language, test_cases):
        outcomes = [
            TestOutcome(
                test_number=index,
                test_case_id=case.test_case_id,
                description=case.description,
                input=case.input,
                original_output="1\n",
                migrated_output="1\n",
                original_stderr="",
                migrated_stderr="",
                original_exit_code=0,
                migrated_exit_code=0,
                original_time_ms=1.0,
                migrated_time_ms=1.0,
                status=self.status,
            )
            for index, case in enumerate(test_cases, start=1)
        ]
        report = VerificationReport(
            total_tests=len(test_cases),
            passed_tests=len(test_cases) if self.status == "PASS" else 0,
            failed_tests=0 if self.status == "PASS" else len(test_cases),
            behavior_match_percentage=100.0 if self.status == "PASS" else 0.0,
            compilation_status="PASS",
            runtime_status="PASS",
            overall_status=self.status,
            test_results=outcomes,
        )
        return report


def add_tests(db_session, migration, inputs=("1\n",)):
    for value in inputs:
        db_session.add(
            TestCase(
                migration_id=migration.id,
                input=value,
                expected_output="1\n",
                source_code_hash=content_hash(migration.source_code),
                source_language=migration.source_language,
            )
        )
    db_session.commit()


# -- results record the code version they tested -------------------------------
def test_result_records_the_hashes_of_the_code_it_tested(db_session, migration):
    add_tests(db_session, migration)
    result = VerificationService(db_session, runner=StubRunner()).verify(migration)
    assert result.source_code_hash == content_hash(SOURCE_V1)
    assert result.migrated_code_hash == content_hash("print(1)\n")
    assert result.source_language == "python"
    assert result.test_cases_hash


def test_result_is_not_stale_immediately_after_verification(db_session, migration):
    add_tests(db_session, migration)
    result = VerificationService(db_session, runner=StubRunner()).verify(migration)
    assert result.is_stale_for(migration.source_code, migration.migrated_code) is False


def test_result_becomes_stale_after_the_source_code_changes(db_session, migration):
    add_tests(db_session, migration)
    result = VerificationService(db_session, runner=StubRunner()).verify(migration)
    assert result.is_stale_for(SOURCE_V2, migration.migrated_code) is True


def test_result_becomes_stale_after_the_migrated_code_changes(db_session, migration):
    add_tests(db_session, migration)
    result = VerificationService(db_session, runner=StubRunner()).verify(migration)
    assert result.is_stale_for(migration.source_code, "print(999)\n") is True


def test_result_becomes_stale_after_a_language_change(db_session, migration):
    add_tests(db_session, migration)
    result = VerificationService(db_session, runner=StubRunner()).verify(migration)
    assert result.is_stale_for(migration.source_code, migration.migrated_code, "java") is True


# -- update() marks downstream artifacts stale ---------------------------------
def test_editing_source_code_marks_the_previous_result_stale(db_session, user, migration):
    add_tests(db_session, migration)
    result = VerificationService(db_session, runner=StubRunner()).verify(migration)
    assert result.overall_status == "PASS"

    MigrationService(db_session).update(user, migration.id, MigrationUpdate(source_code=SOURCE_V2))

    db_session.refresh(result)
    assert result.is_stale_for(migration.source_code, migration.migrated_code) is True


def test_editing_code_does_not_delete_history(db_session, user, migration):
    """History is preserved and labelled, not silently discarded."""
    add_tests(db_session, migration)
    VerificationService(db_session, runner=StubRunner()).verify(migration)
    MigrationService(db_session).update(user, migration.id, MigrationUpdate(source_code=SOURCE_V2))
    db_session.refresh(migration)
    assert len(migration.verification_results) == 1


def test_switching_target_language_marks_results_stale(db_session, user, migration):
    add_tests(db_session, migration)
    result = VerificationService(db_session, runner=StubRunner()).verify(migration)
    MigrationService(db_session).update(user, migration.id, MigrationUpdate(target_language="javascript"))
    db_session.refresh(result)
    assert result.is_stale_for(migration.source_code, migration.migrated_code, None, "javascript")


def test_no_change_leaves_results_fresh(db_session, user, migration):
    add_tests(db_session, migration)
    result = VerificationService(db_session, runner=StubRunner()).verify(migration)
    MigrationService(db_session).update(user, migration.id, MigrationUpdate(title="renamed"))
    db_session.refresh(result)
    assert result.is_stale_for(migration.source_code, migration.migrated_code) is False


def test_editing_code_resets_a_non_terminal_status(db_session, user, migration):
    migration.status = "verifying"
    db_session.commit()
    MigrationService(db_session).update(user, migration.id, MigrationUpdate(source_code=SOURCE_V2))
    db_session.refresh(migration)
    assert migration.status == "draft"


# -- test cases carry their own version ----------------------------------------
def test_test_cases_record_the_source_hash_they_came_from(db_session, migration):
    add_tests(db_session, migration)
    case = migration.test_cases[0]
    assert case.source_code_hash == content_hash(SOURCE_V1)
    assert case.source_language == "python"


# -- failed verification must not strand the record ----------------------------
def test_verification_restores_a_terminal_status_when_the_sandbox_raises(db_session, migration):
    add_tests(db_session, migration)

    class ExplodingRunner:
        def run(self, **kwargs):
            raise RuntimeError("docker exploded")

    with pytest.raises(Exception):
        VerificationService(db_session, runner=ExplodingRunner()).verify(migration)

    db_session.refresh(migration)
    assert migration.status == "error"
    assert migration.status != "verifying"


def test_a_crash_while_storing_the_report_does_not_strand_the_migration(
    db_session, migration, monkeypatch
):
    """A failure inside report persistence must roll back and record an error."""
    add_tests(db_session, migration)
    service = VerificationService(db_session, runner=StubRunner())

    def explode(*args, **kwargs):
        raise RuntimeError("database write failed")

    monkeypatch.setattr(service, "_persist_report", explode)
    with pytest.raises(Exception):
        service.verify(migration)

    db_session.refresh(migration)
    assert migration.status == "error"
    assert migration.status != "verifying"


def test_failed_ai_correction_restores_a_terminal_status(db_session, migration):
    add_tests(db_session, migration)
    service = VerificationService(db_session, runner=StubRunner(status="FAIL"))
    service.verify(migration)

    class ExplodingAI:
        provider_name = "exploding"

        def correct_code(self, **kwargs):
            raise RuntimeError("model unavailable")

    service._ai_service = ExplodingAI()
    with pytest.raises(RuntimeError):
        service.fix_with_ai(migration)

    db_session.refresh(migration)
    assert migration.status in {"failed", "error"}
    assert migration.status != "verifying"
