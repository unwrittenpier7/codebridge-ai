"""SQLAlchemy engine/session management."""
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def _engine_kwargs(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {"pool_pre_ping": True}


engine = create_engine(settings.database_url, **_engine_kwargs(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables for all registered models and apply additive column updates."""
    from app import models  # noqa: F401  (ensures models are imported/registered)
    from app.database.migrations import reconcile_schema

    Base.metadata.create_all(bind=engine)
    applied = reconcile_schema(engine)
    if applied:
        from app.core.logging_config import get_logger

        get_logger(__name__).info("Applied %s additive schema change(s)", len(applied))
