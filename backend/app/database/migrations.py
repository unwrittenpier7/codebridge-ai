"""Additive schema reconciliation for existing installations.

`Base.metadata.create_all()` creates missing *tables* but never alters existing
ones, so a deployment created before this version would lack the new
verification/test-case columns. This module adds only missing, nullable columns
and never drops or rewrites anything, so it is safe to run on every startup and
safe on a populated database.

Alembic remains the tool for anything structural; this is deliberately the
minimum needed for backward-compatible column additions.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.core.logging_config import get_logger

logger = get_logger(__name__)

#: (table, column, DDL type) additions, applied only when absent.
ADDITIVE_COLUMNS: List[Tuple[str, str, str]] = [
    ("verification_results", "error_tests", "INTEGER DEFAULT 0"),
    ("verification_results", "infrastructure_error", "TEXT"),
    ("verification_results", "source_code_hash", "VARCHAR(64)"),
    ("verification_results", "migrated_code_hash", "VARCHAR(64)"),
    ("verification_results", "test_cases_hash", "VARCHAR(64)"),
    ("verification_results", "source_language", "VARCHAR(32)"),
    ("verification_results", "target_language", "VARCHAR(32)"),
    ("test_results", "failure_reason", "VARCHAR(48)"),
    ("test_results", "reference_valid", "BOOLEAN DEFAULT 1"),
    ("test_cases", "source_code_hash", "VARCHAR(64)"),
    ("test_cases", "source_language", "VARCHAR(32)"),
]

#: Indexes worth adding for the query patterns the app actually uses.
ADDITIVE_INDEXES: List[Tuple[str, str, str]] = [
    ("ix_verification_results_source_code_hash", "verification_results", "source_code_hash"),
    ("ix_verification_results_migrated_code_hash", "verification_results", "migrated_code_hash"),
    ("ix_test_cases_source_code_hash", "test_cases", "source_code_hash"),
]

#: SQLite cannot add a column with a non-constant default; these are the
#: portable fallbacks used when the dialect rejects the declared default.
SQLITE_DEFAULTS: Dict[str, str] = {
    "reference_valid": "1",
    "error_tests": "0",
}


def _column_type_for(sqlite: bool, ddl: str) -> str:
    if sqlite:
        return ddl.replace("BOOLEAN", "INTEGER")
    return ddl


def reconcile_schema(engine: Engine) -> List[str]:
    """Add missing columns/indexes. Returns the list of changes applied."""
    applied: List[str] = []
    sqlite = engine.dialect.name == "sqlite"
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as connection:
        for table, column, ddl in ADDITIVE_COLUMNS:
            if table not in existing_tables:
                continue
            columns = {col["name"] for col in inspector.get_columns(table)}
            if column in columns:
                continue
            try:
                connection.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {column} {_column_type_for(sqlite, ddl)}")
                )
            except Exception as exc:  # pragma: no cover - dialect specific
                # A default that the dialect rejects is retried without one;
                # the application always writes these columns explicitly.
                try:
                    bare = _column_type_for(sqlite, ddl).split(" DEFAULT ")[0]
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {bare}"))
                except Exception:
                    logger.warning(
                        "Could not add column %s.%s (%s); continuing without it", table, column, exc
                    )
                    continue
            if sqlite and column in SQLITE_DEFAULTS:
                connection.execute(
                    text(f"UPDATE {table} SET {column} = :value WHERE {column} IS NULL"),
                    {"value": SQLITE_DEFAULTS[column]},
                )
            applied.append(f"{table}.{column}")
            logger.info("Schema migration: added column %s.%s", table, column)

        existing_indexes = {
            index["name"] for table in existing_tables for index in inspector.get_indexes(table)
        }
        for name, table, column in ADDITIVE_INDEXES:
            if table not in existing_tables or name in existing_indexes:
                continue
            try:
                connection.execute(text(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({column})"))
                applied.append(name)
                logger.info("Schema migration: created index %s", name)
            except Exception as exc:  # pragma: no cover - dialect specific
                logger.warning("Could not create index %s (%s); continuing", name, exc)

    return applied
