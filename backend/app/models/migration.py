from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.connection import Base
from app.models.user import utcnow


class MigrationStatus(str, Enum):
    DRAFT = "draft"
    MIGRATING = "migrating"
    MIGRATED = "migrated"
    TESTS_GENERATED = "tests_generated"
    VERIFYING = "verifying"
    VERIFIED = "verified"
    PARTIAL = "partial"
    FAILED = "failed"
    ERROR = "error"


class Migration(Base):
    __tablename__ = "migrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(200), default="Untitled migration")
    source_language: Mapped[str] = mapped_column(String(32), nullable=False)
    target_language: Mapped[str] = mapped_column(String(32), nullable=False)
    source_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    migrated_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=MigrationStatus.DRAFT.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    user = relationship("User", back_populates="migrations")
    project = relationship("Project", back_populates="migrations")
    test_cases = relationship(
        "TestCase", back_populates="migration", cascade="all, delete-orphan",
        order_by="TestCase.id",
    )
    verification_results = relationship(
        "VerificationResult", back_populates="migration", cascade="all, delete-orphan",
        order_by="VerificationResult.id",
    )
    correction_attempts = relationship(
        "CorrectionAttempt", back_populates="migration", cascade="all, delete-orphan",
        order_by="CorrectionAttempt.attempt_number",
    )
