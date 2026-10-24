"""Verification, validation and AI correction endpoints."""
from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.errors import ValidationError
from app.database.connection import get_db
from app.models import User
from app.schemas.migration import FixRequest, VerificationResultOut, VerifyRequest
from app.schemas.verification import FixRunOut, VerificationRunOut
from app.services.docker_executor import docker_executor
from app.services.migration_service import MigrationService
from app.services.verification_service import VerificationService

router = APIRouter(prefix="/migrations", tags=["verification"])


def _result_out(result, migration) -> VerificationResultOut:
    payload = VerificationResultOut.model_validate(result)
    payload.stale = result.is_stale_for(
        migration.source_code,
        migration.migrated_code,
        migration.source_language,
        migration.target_language,
    )
    return payload


@router.post("/{migration_id}/validate")
def validate_migrated_code(
    migration_id: int,
    payload: Optional[VerifyRequest] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Compile/syntax-check the migrated code inside the sandbox without running tests."""
    payload = payload or VerifyRequest()
    migration = MigrationService(db).get_for_user(user, migration_id)
    code = payload.migrated_code or migration.migrated_code or ""
    if not code.strip():
        raise ValidationError("There is no migrated code to validate.")

    program = docker_executor.prepare(migration.target_language, code)
    try:
        compilation = program.compilation
        if compilation.success and migration.target_language in {"python", "javascript"}:
            # Interpreted languages have no compile step: do a syntax-only check.
            syntax_check = {
                "python": "python -m py_compile main.py",
                "javascript": "node --check main.js",
            }[migration.target_language]
            result = docker_executor.run_shell(
                image=program.language.image,
                workdir=program.workdir,
                shell_command=syntax_check,
                timeout=30,
            )
            return {
                "compilation_status": "PASS" if result.exit_code == 0 else "FAIL",
                "error": result.stderr if result.exit_code != 0 else None,
            }
        return {
            "compilation_status": "PASS" if compilation.success else "FAIL",
            "error": compilation.error_message or None,
        }
    finally:
        program.cleanup()


@router.post("/{migration_id}/verify", response_model=VerificationRunOut)
def verify(
    migration_id: int,
    payload: Optional[VerifyRequest] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> VerificationRunOut:
    payload = payload or VerifyRequest()
    migration = MigrationService(db).get_for_user(user, migration_id)
    result = VerificationService(db).verify(migration, migrated_code=payload.migrated_code)
    return VerificationRunOut(
        migration_id=migration.id,
        migration_status=migration.status,
        result=_result_out(result, migration),
    )


@router.post("/{migration_id}/fix", response_model=FixRunOut)
def fix_with_ai(
    migration_id: int,
    payload: Optional[FixRequest] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FixRunOut:
    payload = payload or FixRequest()
    service = MigrationService(db)
    migration = service.get_for_user(user, migration_id)
    corrections, results = VerificationService(db).fix_with_ai(
        migration, max_attempts=payload.max_attempts
    )
    db.refresh(migration)
    serialized = [_result_out(result, migration) for result in results]
    return FixRunOut(
        migration_id=migration.id,
        migration_status=migration.status,
        migrated_code=migration.migrated_code,
        attempts_used=len(corrections),
        corrections=corrections,
        results=serialized,
        final_result=serialized[-1] if serialized else None,
    )


@router.get("/{migration_id}/results", response_model=List[VerificationResultOut])
def get_results(
    migration_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[VerificationResultOut]:
    migration = MigrationService(db).get_for_user(user, migration_id)
    return [
        _result_out(result, migration)
        for result in sorted(migration.verification_results, key=lambda r: r.id)
    ]

