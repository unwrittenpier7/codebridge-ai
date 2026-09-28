from typing import List, Optional

from pydantic import BaseModel

from app.schemas.migration import CorrectionAttemptOut, VerificationResultOut


class VerificationRunOut(BaseModel):
    """Response of POST /migrations/{id}/verify."""

    migration_id: int
    migration_status: str
    result: VerificationResultOut


class FixRunOut(BaseModel):
    """Response of POST /migrations/{id}/fix (AI correction loop)."""

    migration_id: int
    migration_status: str
    migrated_code: Optional[str]
    attempts_used: int
    corrections: List[CorrectionAttemptOut]
    results: List[VerificationResultOut]
    final_result: Optional[VerificationResultOut]
