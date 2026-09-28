from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.connection import Base
from app.models.user import utcnow


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
    behavior_match_percentage: Mapped[float] = mapped_column(Float, default=0.0)
    compilation_status: Mapped[str] = mapped_column(String(16), default="UNKNOWN")
    runtime_status: Mapped[str] = mapped_column(String(16), default="UNKNOWN")
    overall_status: Mapped[str] = mapped_column(String(16), default="UNKNOWN")
    compiler_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    migration = relationship("Migration", back_populates="verification_results")
    test_results = relationship(
        "TestResult", back_populates="verification_result", cascade="all, delete-orphan",
        order_by="TestResult.id",
    )


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
