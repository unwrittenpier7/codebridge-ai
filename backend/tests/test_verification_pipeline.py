"""End-to-end verification tests. These run real programs inside Docker."""
import pytest

from app.models import Migration, User
from app.services.test_generation_service import TestGenerationService
from app.services.verification_service import VerificationService
from tests.stubs import (
    PYTHON_ADDER,
    PYTHON_ADDER_BROKEN,
    ScriptedProvider,
    fenced,
    build_tests_payload,
)
from app.services.ai_service import AIService

pytestmark = pytest.mark.docker

PY_SOURCE_ADDER = PYTHON_ADDER


@pytest.fixture()
def migration(db_session):
    user = User(name="V", email="v@example.com", password_hash="x")
    db_session.add(user)
    db_session.flush()
    migration = Migration(
        user_id=user.id,
        title="adder",
        source_language="python",
        target_language="python",
        source_code=PY_SOURCE_ADDER,
    )
    db_session.add(migration)
    db_session.commit()
    return migration


def _skip_without_docker(docker_available):
    if not docker_available:
        pytest.skip("Docker daemon is not available in this environment")


def test_generated_tests_use_real_program_output(db_session, migration, docker_available):
    _skip_without_docker(docker_available)
    ai = AIService(provider=ScriptedProvider(tests=build_tests_payload(["5\n10\n", "0\n0\n"])))
    cases = TestGenerationService(db_session, ai_service=ai).generate(migration, count=2)

    assert [case.expected_output.strip() for case in cases] == ["15", "0"]
    assert all(case.reference_status == "OK" for case in cases)


def test_equivalent_migration_passes(db_session, migration, docker_available):
    _skip_without_docker(docker_available)
    ai = AIService(provider=ScriptedProvider(tests=build_tests_payload(["5\n10\n", "-3\n3\n"])))
    TestGenerationService(db_session, ai_service=ai).generate(migration, count=2)

    result = VerificationService(db_session).verify(migration, migrated_code=PYTHON_ADDER)
    assert result.overall_status == "PASS"
    assert result.passed_tests == result.total_tests == 2
    assert result.behavior_match_percentage == 100.0


def test_compiling_but_wrong_program_is_not_equivalent(db_session, migration, docker_available):
    _skip_without_docker(docker_available)
    ai = AIService(provider=ScriptedProvider(tests=build_tests_payload(["5\n10\n", "2\n2\n"])))
    TestGenerationService(db_session, ai_service=ai).generate(migration, count=2)

    result = VerificationService(db_session).verify(migration, migrated_code=PYTHON_ADDER_BROKEN)
    assert result.compilation_status == "PASS"
    assert result.overall_status in {"FAIL", "PARTIAL"}
    assert result.failed_tests >= 1
    assert any(tr.difference for tr in result.test_results if tr.status == "FAIL")


def test_runtime_error_in_migration_is_reported(db_session, migration, docker_available):
    _skip_without_docker(docker_available)
    ai = AIService(provider=ScriptedProvider(tests=build_tests_payload(["5\n10\n"])))
    TestGenerationService(db_session, ai_service=ai).generate(migration, count=1)

    result = VerificationService(db_session).verify(
        migration, migrated_code="raise SystemExit('boom')\n"
    )
    assert result.overall_status in {"FAIL", "ERROR"}
    assert result.test_results[0].migrated_exit_code != 0


def test_correction_loop_repairs_and_is_bounded(db_session, migration, docker_available):
    _skip_without_docker(docker_available)
    provider = ScriptedProvider(
        tests=build_tests_payload(["5\n10\n"]),
        corrections=[fenced(PYTHON_ADDER, section="### Reason\nused + instead of -")],
    )
    ai = AIService(provider=provider)
    TestGenerationService(db_session, ai_service=ai).generate(migration, count=1)
    service = VerificationService(db_session, ai_service=ai)
    service.verify(migration, migrated_code=PYTHON_ADDER_BROKEN)

    corrections, results = service.fix_with_ai(migration)
    assert len(corrections) == 1
    assert corrections[0].behavior_match_after == 100.0
    assert results[-1].overall_status == "PASS"
    assert migration.migrated_code.strip() == PYTHON_ADDER.strip()


def test_correction_loop_stops_at_the_configured_maximum(db_session, migration, docker_available):
    _skip_without_docker(docker_available)
    from app.core.config import settings

    broken = fenced(PYTHON_ADDER_BROKEN, section="### Reason\nstill broken")
    provider = ScriptedProvider(
        tests=build_tests_payload(["5\n10\n"]), corrections=[broken] * 10
    )
    ai = AIService(provider=provider)
    TestGenerationService(db_session, ai_service=ai).generate(migration, count=1)
    service = VerificationService(db_session, ai_service=ai)
    service.verify(migration, migrated_code=PYTHON_ADDER_BROKEN)

    corrections, _ = service.fix_with_ai(migration, max_attempts=99)
    assert len(corrections) == settings.max_correction_attempts
