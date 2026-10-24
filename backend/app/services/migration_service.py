"""Migration business logic: CRUD plus the analyze -> migrate step.

Invalidation contract
---------------------
A stored verification result or test case only describes the exact code version
it was produced from. `update` therefore records the code hashes of the previous
version and marks dependent artifacts stale instead of deleting them: history is
preserved (and clearly labelled) while the API can never present a stale PASS as
if it applied to the edited code.
"""
from __future__ import annotations

import json
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import NotFoundError, ValidationError
from app.core.config import settings
from app.core.languages import get_language
from app.core.logging_config import get_logger
from app.models import Migration, MigrationStatus, User, content_hash
from app.schemas.migration import MigrationCreate, MigrationUpdate
from app.services.ai_service import AIService, get_ai_service
from app.services.code_analysis_service import code_analysis_service

logger = get_logger(__name__)


class MigrationService:
    def __init__(self, db: Session, ai_service: Optional[AIService] = None):
        self.db = db
        self._ai_service = ai_service

    @property
    def ai(self) -> AIService:
        if self._ai_service is None:
            self._ai_service = get_ai_service()
        return self._ai_service

    # -- CRUD ---------------------------------------------------------------
    def create(self, user: User, payload: MigrationCreate) -> Migration:
        self._validate_code_size(payload.source_code)
        source = get_language(payload.source_language)
        target = get_language(payload.target_language)
        migration = Migration(
            user_id=user.id,
            project_id=payload.project_id,
            title=payload.title or "Untitled migration",
            source_language=source.key,
            target_language=target.key,
            source_code=payload.source_code or "",
            status=MigrationStatus.DRAFT.value,
        )
        self.db.add(migration)
        self.db.commit()
        self.db.refresh(migration)
        logger.info("Created migration %s (%s -> %s)", migration.id, source.key, target.key)
        return migration

    def list_for_user(self, user: User, limit: int = 100) -> List[Migration]:
        stmt = (
            select(Migration)
            .where(Migration.user_id == user.id)
            .options(selectinload(Migration.verification_results))
            .order_by(Migration.created_at.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt))

    def get_for_user(self, user: User, migration_id: int) -> Migration:
        stmt = (
            select(Migration)
            .where(Migration.id == migration_id, Migration.user_id == user.id)
            .options(
                selectinload(Migration.test_cases),
                selectinload(Migration.verification_results),
                selectinload(Migration.correction_attempts),
            )
        )
        migration = self.db.scalars(stmt).unique().one_or_none()
        if migration is None:
            # A resource owned by somebody else is indistinguishable from a
            # missing one, so ownership is never leaked through 403 vs 404.
            raise NotFoundError(f"Migration {migration_id} was not found.")
        return migration

    def update(self, user: User, migration_id: int, payload: MigrationUpdate) -> Migration:
        migration = self.get_for_user(user, migration_id)

        code_changed = False
        if payload.title is not None:
            migration.title = payload.title
        if payload.source_code is not None and payload.source_code != migration.source_code:
            self._validate_code_size(payload.source_code)
            migration.source_code = payload.source_code
            code_changed = True
        if payload.migrated_code is not None and payload.migrated_code != migration.migrated_code:
            self._validate_code_size(payload.migrated_code)
            migration.migrated_code = payload.migrated_code
            code_changed = True
        if payload.source_language is not None:
            new_source = get_language(payload.source_language).key
            if new_source != migration.source_language:
                migration.source_language = new_source
                code_changed = True
        if payload.target_language is not None:
            new_target = get_language(payload.target_language).key
            if new_target != migration.target_language:
                migration.target_language = new_target
                code_changed = True

        if code_changed:
            # Results are kept for history, but the API marks them stale because
            # their recorded hashes no longer match the stored code.
            self._invalidate_downstream(migration)

        self.db.commit()
        self.db.refresh(migration)
        return migration

    def _invalidate_downstream(self, migration: Migration) -> None:
        """Return a migration to a stable status after its code changed.

        Stored results and test cases are deliberately *kept*: they are history,
        and the API derives a `stale` flag from their recorded hashes. Only a
        non-terminal status is reset, so the record cannot be left claiming it is
        "verifying" code that no longer exists.
        """
        if migration.status in {
            MigrationStatus.VERIFYING.value,
            MigrationStatus.MIGRATING.value,
        }:
            migration.status = MigrationStatus.DRAFT.value
        logger.info("Code changed for migration %s; prior results are now stale", migration.id)

    def delete(self, user: User, migration_id: int) -> None:
        migration = self.get_for_user(user, migration_id)
        self.db.delete(migration)
        self.db.commit()

    # -- AI migration -------------------------------------------------------
    def analyze(self, migration: Migration) -> dict:
        analysis = code_analysis_service.analyze(migration.source_code, migration.source_language)
        migration.analysis_json = json.dumps(analysis)
        self.db.commit()
        return analysis

    def migrate(self, user: User, migration_id: int, source_code: Optional[str] = None,
                source_language: Optional[str] = None,
                target_language: Optional[str] = None) -> Migration:
        migration = self.get_for_user(user, migration_id)
        if source_code is not None:
            self._validate_code_size(source_code)
            migration.source_code = source_code
        if source_language:
            migration.source_language = get_language(source_language).key
        if target_language:
            migration.target_language = get_language(target_language).key
        if not (migration.source_code or "").strip():
            raise ValidationError("Cannot migrate an empty source program.")

        migration.status = MigrationStatus.MIGRATING.value
        self.db.commit()

        analysis = self.analyze(migration)
        try:
            result = self.ai.migrate_code(
                migration.source_code,
                migration.source_language,
                migration.target_language,
                analysis=analysis,
            )
        except Exception:
            self.db.rollback()
            migration.status = MigrationStatus.ERROR.value
            self.db.commit()
            raise

        migration.migrated_code = result["code"]
        migration.explanation = result.get("explanation") or None
        migration.status = MigrationStatus.MIGRATED.value
        # A new migration invalidates previous verification evidence.
        migration.verification_results.clear()
        migration.correction_attempts.clear()
        self.db.commit()
        self.db.refresh(migration)
        logger.info("Migrated migration %s via %s", migration.id, self.ai.provider_name)
        return migration

    def _validate_code_size(self, code: Optional[str]) -> None:
        if code is None:
            return
        if len(code.encode("utf-8")) > settings.max_code_size_bytes:
            raise ValidationError(
                f"Source code exceeds the maximum size of {settings.max_code_size_kb} KB."
            )
