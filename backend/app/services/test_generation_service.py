"""Test case generation.

Generation is intentionally separate from execution. The AI proposes stdin
payloads; the expected output is then obtained by running the ORIGINAL program in
the sandbox, so AI-invented outputs are never trusted as ground truth.

The previous test cases are only replaced *after* the AI has produced a usable
list, so a failed generation attempt leaves the existing (clearly versioned)
cases in place instead of destroying evidence.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ValidationError
from app.core.logging_config import get_logger
from app.models import Migration, MigrationStatus, TestCase, content_hash
from app.services.ai_service import AIService, get_ai_service
from app.services.code_analysis_service import code_analysis_service
from app.services.docker_executor import DockerExecutor, docker_executor

logger = get_logger(__name__)


class TestGenerationService:
    def __init__(
        self,
        db: Session,
        ai_service: Optional[AIService] = None,
        executor: Optional[DockerExecutor] = None,
    ):
        self.db = db
        self._ai_service = ai_service
        self.executor = executor or docker_executor

    @property
    def ai(self) -> AIService:
        if self._ai_service is None:
            self._ai_service = get_ai_service()
        return self._ai_service

    def generate(self, migration: Migration, count: Optional[int] = None) -> List[TestCase]:
        if not (migration.source_code or "").strip():
            raise ValidationError("Cannot generate tests for an empty source program.")
        count = count or settings.max_generated_test_cases

        analysis = code_analysis_service.analyze(migration.source_code, migration.source_language)
        # This call is the only step that can fail on the model's output. It runs
        # before any destructive database work.
        specs = self.ai.generate_test_cases(
            migration.source_code, migration.source_language, count=count, analysis=analysis
        )

        source_hash = content_hash(migration.source_code)
        reference = self.executor.prepare(migration.source_language, migration.source_code)
        created: List[TestCase] = []
        try:
            if not reference.compilation.success:
                raise ValidationError(
                    "The original program does not compile, so reference outputs cannot be "
                    f"produced:\n{reference.compilation.error_message}"
                )
            for spec in specs:
                run = self.executor.run(reference, spec["input"])
                status = "OK"
                if run.timed_out:
                    status = "TIMEOUT"
                elif run.exit_code != 0:
                    status = "RUNTIME_ERROR"
                created.append(
                    TestCase(
                        migration_id=migration.id,
                        input=spec["input"],
                        expected_output=run.stdout,
                        expected_behavior=spec.get("expected_behavior"),
                        description=spec.get("description"),
                        category=spec.get("category"),
                        reference_status=status,
                        source_code_hash=source_hash,
                        source_language=migration.source_language,
                    )
                )
        finally:
            reference.cleanup()

        if not created:
            raise ValidationError(
                "Test generation produced no test cases; the previous cases were kept."
            )

        # Replace previous cases only now: they describe an older program version.
        for existing in list(migration.test_cases):
            self.db.delete(existing)
        self.db.flush()
        for test_case in created:
            self.db.add(test_case)

        migration.status = MigrationStatus.TESTS_GENERATED.value
        self.db.commit()
        for test_case in created:
            self.db.refresh(test_case)
        logger.info("Generated %s test cases for migration %s", len(created), migration.id)
        return created

