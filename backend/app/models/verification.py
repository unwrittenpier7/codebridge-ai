from datetime import datetime
import hashlib

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.connection import Base
from app.models.user import utcnow


def content_hash(text: str | None) -> str:
    """Stable hash of a code/text version, used to detect stale results."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def test_cases_hash(test_cases) -> str:
    """Stable hash over the (input, description) pairs of a test-case set."""
    digest = hashlib.sha256()
    for case in test_cases:
        digest.update((case.input or "").encode("utf-8"))
        digest.update(b"\x1f")
        digest.update((case.description or "").encode("utf-8"))
        digest.update(b"\x1e")
    return digest.hexdigest()


class VerificationResult(Base):
    __tablename__ = "verification_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    migration_id: Mapped[int] = mapped_column(
        ForeignKey("migrations.id", ondelete="CASCADE"), index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, default=0)
    total_tests: Mapped[int] = mapped_column(Integer, default=0)
    passed_tests: Mapped[int] = mapped_column(Integer, default=0)
    failed_tests: Mapped[int] = mapped_column(Integer, default=0)
    error_tests: Mapped[int] = mapped_column(Integer, default=0)
    behavior_match_percentage: Mapped[float] = mapped_column(Float, default=0.0)
    compilation_status: Mapped[str] = mapped_column(String(16), default="UNKNOWN")
    runtime_status: Mapped[str] = mapped_column(String(16), default="UNKNOWN")
    overall_status: Mapped[str] = mapped_column(String(16), default="UNKNOWN")
    compiler_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    infrastructure_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    # -- exact code version this run tested -----------------------------------
    # Hashes let the UI and the API tell whether a stored result still describes
    # the code currently in the editor, instead of presenting a stale PASS.
    source_code_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    migrated_code_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    test_cases_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    migration = relationship("Migration", back_populates="verification_results")
    test_results = relationship(
        "TestResult", back_populates="verification_result", cascade="all, delete-orphan",
        order_by="TestResult.id",
    )

    def is_stale_for(
        self,
        source_code: str | None,
        migrated_code: str | None,
        source_language: str | None = None,
        target_language: str | None = None,
    ) -> bool:
        """True when this run no longer describes the given code version."""
        if self.source_code_hash and self.source_code_hash != content_hash(source_code):
            return True
        if self.migrated_code_hash and self.migrated_code_hash != content_hash(migrated_code):
            return True
        if self.source_language and source_language and self.source_language != source_language:
            return True
        if self.target_language and target_language and self.target_language != target_language:
            return True
        return False


class TestResult(Base):
    """Per-test outcome of one verification run."""

    __tablename__ = "test_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    verification_result_id: Mapped[int] = mapped_column(
        ForeignKey("verification_results.id", ondelete="CASCADE"), index=True
    )
    test_case_id: Mapped[int | None] = mapped_column(
        ForeignKey("test_cases.id", ondelete="SET NULL"), nullable=True
    )
    test_number: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    input: Mapped[str] = mapped_column(Text, default="")
    original_output: Mapped[str] = mapped_column(Text, default="")
    migrated_output: Mapped[str] = mapped_column(Text, default="")
    original_stderr: Mapped[str | None] = mapped_column(Text, nullable=True)
    migrated_stderr: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    migrated_exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    original_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    migrated_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="FAIL")
    difference: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Machine readable failure classification (e.g. MIGRATED_RUNTIME_ERROR).
    failure_reason: Mapped[str | None] = mapped_column(String(48), nullable=True)
    #: False when the original program could not supply a reference output.
    reference_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    verification_result = relationship("VerificationResult", back_populates="test_results")


class CorrectionAttempt(Base):
    __tablename__ = "correction_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    migration_id: Mapped[int] = mapped_column(
        ForeignKey("migrations.id", ondelete="CASCADE"), index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    previous_code: Mapped[str] = mapped_column(Text, default="")
    corrected_code: Mapped[str] = mapped_column(Text, default="")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    behavior_match_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    behavior_match_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    migration = relationship("Migration", back_populates="correction_attempts")
