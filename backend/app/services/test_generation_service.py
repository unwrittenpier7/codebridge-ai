"""Test case generation.

Generation is intentionally separate from execution. The AI proposes stdin
payloads; the expected output is then obtained by running the ORIGINAL program in
the sandbox, so AI-invented outputs are never trusted as ground truth.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ValidationError
from app.core.logging_config import get_logger
from app.models import Migration, MigrationStatus, TestCase
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
        specs = self.ai.generate_test_cases(
            migration.source_code, migration.source_language, count=count, analysis=analysis
        )

        # Replace previous cases: they belong to an older version of the program.
        for existing in list(migration.test_cases):
            self.db.delete(existing)
        self.db.flush()

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
                test_case = TestCase(
                    migration_id=migration.id,
                    input=spec["input"],
                    expected_output=run.stdout,
                    expected_behavior=spec.get("expected_behavior"),
                    description=spec.get("description"),
                    category=spec.get("category"),
                    reference_status=status,
                )
                self.db.add(test_case)
                created.append(test_case)
        finally:
            reference.cleanup()

        migration.status = MigrationStatus.TESTS_GENERATED.value
        self.db.commit()
        for test_case in created:
            self.db.refresh(test_case)
        logger.info("Generated %s test cases for migration %s", len(created), migration.id)
        return created
