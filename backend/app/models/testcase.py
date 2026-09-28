from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.connection import Base


class TestCase(Base):
    __tablename__ = "test_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    migration_id: Mapped[int] = mapped_column(
        ForeignKey("migrations.id", ondelete="CASCADE"), index=True
    )
    input: Mapped[str] = mapped_column(Text, default="")
    expected_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_behavior: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reference_status: Mapped[str | None] = mapped_column(String(32), nullable=True)

    migration = relationship("Migration", back_populates="test_cases")
