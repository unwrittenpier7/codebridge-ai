from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings


class MigrationCreate(BaseModel):
    title: str = Field(default="Untitled migration", max_length=200)
    source_language: str = Field(min_length=1, max_length=32)
    target_language: str = Field(min_length=1, max_length=32)
    source_code: str = Field(default="", max_length=settings.max_code_size_bytes)
    project_id: Optional[int] = Field(default=None, ge=1)


class MigrationUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    source_code: Optional[str] = Field(default=None, max_length=settings.max_code_size_bytes)
    migrated_code: Optional[str] = Field(default=None, max_length=settings.max_code_size_bytes)
    source_language: Optional[str] = Field(default=None, max_length=32)
    target_language: Optional[str] = Field(default=None, max_length=32)


class TestCaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    input: str
    expected_output: Optional[str]
    expected_behavior: Optional[str]
    description: Optional[str]
    category: Optional[str]
    reference_status: Optional[str]
    source_code_hash: Optional[str] = None
    source_language: Optional[str] = None
    #: True when these cases were generated from a different source version than
    #: the one currently stored on the migration.
    stale: bool = False


class TestResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    test_number: int
    description: Optional[str]
    input: str
    original_output: str
    migrated_output: str
    original_stderr: Optional[str]
    migrated_stderr: Optional[str]
    original_exit_code: Optional[int]
    migrated_exit_code: Optional[int]
    original_time_ms: Optional[float]
    migrated_time_ms: Optional[float]
    status: str
    difference: Optional[str]
    failure_reason: Optional[str] = None
    reference_valid: bool = True


class VerificationResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    attempt_number: int
    total_tests: int
    passed_tests: int
    failed_tests: int
    error_tests: int = 0
    behavior_match_percentage: float
    compilation_status: str
    runtime_status: str
    overall_status: str
    compiler_error: Optional[str]
    infrastructure_error: Optional[str] = None
    created_at: datetime
    source_code_hash: Optional[str] = None
    migrated_code_hash: Optional[str] = None
    test_cases_hash: Optional[str] = None
    source_language: Optional[str] = None
    target_language: Optional[str] = None
    test_results: List[TestResultOut] = []
    #: True when this run no longer describes the code stored on the migration.
    stale: bool = False


class CorrectionAttemptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    attempt_number: int
    previous_code: str
    corrected_code: str
    reason: Optional[str]
    behavior_match_before: Optional[float]
    behavior_match_after: Optional[float]
    created_at: datetime


class MigrationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    source_language: str
    target_language: str
    status: str
    created_at: datetime
    updated_at: datetime
    latest_behavior_match: Optional[float] = None
    latest_overall_status: Optional[str] = None


class MigrationDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    source_language: str
    target_language: str
    source_code: str
    migrated_code: Optional[str]
    explanation: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime
    analysis: Optional[Dict[str, Any]] = None
    test_cases: List[TestCaseOut] = []
    verification_results: List[VerificationResultOut] = []
    correction_attempts: List[CorrectionAttemptOut] = []


class MigrateRequest(BaseModel):
    source_code: Optional[str] = Field(default=None, max_length=settings.max_code_size_bytes)
    source_language: Optional[str] = Field(default=None, max_length=32)
    target_language: Optional[str] = Field(default=None, max_length=32)


class GenerateTestsRequest(BaseModel):
    count: int = Field(default=settings.max_generated_test_cases, ge=1, le=20)


class VerifyRequest(BaseModel):
    migrated_code: Optional[str] = Field(default=None, max_length=settings.max_code_size_bytes)


class FixRequest(BaseModel):
    max_attempts: int = Field(default=settings.max_correction_attempts, ge=1, le=5)


class DashboardStats(BaseModel):
    total_migrations: int
    successful_migrations: int
    partial_migrations: int
    failed_migrations: int
    average_verification_score: float
    recent_migrations: List[MigrationSummary]


class LanguageOut(BaseModel):
    key: str
    label: str
    monaco_id: str


class HealthOut(BaseModel):
    status: str
    ai_provider: str
    ai_configured: bool
    docker_available: bool
    docker_detail: str
