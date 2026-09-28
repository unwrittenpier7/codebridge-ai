"""Migration business logic: CRUD plus the analyze -> migrate step."""
from __future__ import annotations

import json
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import NotFoundError, ValidationError
from app.core.config import settings
from app.core.languages import get_language
from app.core.logging_config import get_logger
from app.models import Migration, MigrationStatus, User
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
            raise NotFoundError(f"Migration {migration_id} was not found.")
        return migration

    def update(self, user: User, migration_id: int, payload: MigrationUpdate) -> Migration:
        migration = self.get_for_user(user, migration_id)
        if payload.title is not None:
            migration.title = payload.title
        if payload.source_code is not None:
            self._validate_code_size(payload.source_code)
            migration.source_code = payload.source_code
        if payload.migrated_code is not None:
            self._validate_code_size(payload.migrated_code)
            migration.migrated_code = payload.migrated_code
        if payload.source_language is not None:
            migration.source_language = get_language(payload.source_language).key
        if payload.target_language is not None:
            migration.target_language = get_language(payload.target_language).key
        self.db.commit()
        self.db.refresh(migration)
        return migration

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
        max_bytes = settings.max_code_size_kb * 1024
        if len(code.encode("utf-8")) > max_bytes:
            raise ValidationError(
                f"Source code exceeds the maximum size of {settings.max_code_size_kb} KB."
            )
