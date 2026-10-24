"""Migration CRUD, AI migration, test generation and dashboard statistics."""
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.connection import get_db
from app.models import Migration, User, content_hash
from app.schemas.migration import (
    DashboardStats,
    GenerateTestsRequest,
    MigrateRequest,
    MigrationCreate,
    MigrationDetail,
    MigrationSummary,
    MigrationUpdate,
    TestCaseOut,
    VerificationResultOut,
)
from app.services.migration_service import MigrationService
from app.services.test_generation_service import TestGenerationService

router = APIRouter(prefix="/migrations", tags=["migrations"])


def _latest_result(migration: Migration):
    if not migration.verification_results:
        return None
    return sorted(migration.verification_results, key=lambda r: r.id)[-1]


def _result_out(result, migration: Migration):
    """Serialize a verification result, flagging whether it still describes the code."""
    payload = VerificationResultOut.model_validate(result)
    payload.stale = result.is_stale_for(
        migration.source_code,
        migration.migrated_code,
        migration.source_language,
        migration.target_language,
    )
    return payload


def to_summary(migration: Migration) -> MigrationSummary:
    latest = _latest_result(migration)
    latest_status = latest.overall_status if latest else None
    latest_score = latest.behavior_match_percentage if latest else None
    # A summary must never advertise a score that no longer matches the code.
    if latest is not None and latest.is_stale_for(
        migration.source_code,
        migration.migrated_code,
        migration.source_language,
        migration.target_language,
    ):
        latest_status = None
        latest_score = None
    return MigrationSummary(
        id=migration.id,
        title=migration.title,
        source_language=migration.source_language,
        target_language=migration.target_language,
        status=migration.status,
        created_at=migration.created_at,
        updated_at=migration.updated_at,
        latest_behavior_match=latest_score,
        latest_overall_status=latest_status,
    )


def to_detail(migration: Migration) -> MigrationDetail:
    detail = MigrationDetail.model_validate(migration)
    if migration.analysis_json:
        try:
            detail.analysis = json.loads(migration.analysis_json)
        except json.JSONDecodeError:
            detail.analysis = None

    current_source_hash = content_hash(migration.source_code)
    for case in detail.test_cases:
        case.stale = bool(case.source_code_hash) and case.source_code_hash != current_source_hash
        if case.source_language and case.source_language != migration.source_language:
            case.stale = True

    detail.verification_results = [
        _result_out(result, migration) for result in detail.verification_results
    ]
    return detail


@router.post("", response_model=MigrationDetail, status_code=201)
def create_migration(
    payload: MigrationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MigrationDetail:
    migration = MigrationService(db).create(user, payload)
    return to_detail(migration)


@router.get("", response_model=List[MigrationSummary])
def list_migrations(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[MigrationSummary]:
    return [to_summary(m) for m in MigrationService(db).list_for_user(user, limit=limit)]


@router.get("/stats", response_model=DashboardStats)
def dashboard_stats(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> DashboardStats:
    migrations = MigrationService(db).list_for_user(user, limit=500)
    summaries = [to_summary(m) for m in migrations]
    scored = [s.latest_behavior_match for s in summaries if s.latest_behavior_match is not None]
    return DashboardStats(
        total_migrations=len(summaries),
        successful_migrations=sum(1 for s in summaries if s.latest_overall_status == "PASS"),
        partial_migrations=sum(1 for s in summaries if s.latest_overall_status == "PARTIAL"),
        failed_migrations=sum(
            1 for s in summaries if s.latest_overall_status in {"FAIL", "ERROR"}
        ),
        average_verification_score=round(sum(scored) / len(scored), 2) if scored else 0.0,
        recent_migrations=summaries[:5],
    )


@router.get("/{migration_id}", response_model=MigrationDetail)
def get_migration(
    migration_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MigrationDetail:
    return to_detail(MigrationService(db).get_for_user(user, migration_id))


@router.patch("/{migration_id}", response_model=MigrationDetail)
def update_migration(
    migration_id: int,
    payload: MigrationUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MigrationDetail:
    return to_detail(MigrationService(db).update(user, migration_id, payload))


@router.delete("/{migration_id}", status_code=204)
def delete_migration(
    migration_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    MigrationService(db).delete(user, migration_id)


@router.post("/{migration_id}/migrate", response_model=MigrationDetail)
def migrate(
    migration_id: int,
    payload: Optional[MigrateRequest] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MigrationDetail:
    payload = payload or MigrateRequest()
    migration = MigrationService(db).migrate(
        user,
        migration_id,
        source_code=payload.source_code,
        source_language=payload.source_language,
        target_language=payload.target_language,
    )
    return to_detail(migration)


@router.post("/{migration_id}/analyze")
def analyze(
    migration_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    service = MigrationService(db)
    migration = service.get_for_user(user, migration_id)
    return service.analyze(migration)


@router.post("/{migration_id}/generate-tests", response_model=List[TestCaseOut])
def generate_tests(
    migration_id: int,
    payload: Optional[GenerateTestsRequest] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[TestCaseOut]:
    payload = payload or GenerateTestsRequest()
    migration = MigrationService(db).get_for_user(user, migration_id)
    cases = TestGenerationService(db).generate(migration, count=payload.count)
    return [TestCaseOut.model_validate(case) for case in cases]
