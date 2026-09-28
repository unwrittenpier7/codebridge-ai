from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings


class MigrationCreate(BaseModel):
    title: str = Field(default="Untitled migration", max_length=200)
    source_language: str
    target_language: str
    source_code: str = Field(default="")
    project_id: Optional[int] = None


class MigrationUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    source_code: Optional[str] = None
    migrated_code: Optional[str] = None
    source_language: Optional[str] = None
    target_language: Optional[str] = None


class TestCaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    input: str
    expected_output: Optional[str]
    expected_behavior: Optional[str]
    description: Optional[str]
    category: Optional[str]
    reference_status: Optional[str]


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


class VerificationResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    attempt_number: int
    total_tests: int
    passed_tests: int
    failed_tests: int
    behavior_match_percentage: float
    compilation_status: str
    runtime_status: str
    overall_status: str
    compiler_error: Optional[str]
    created_at: datetime
    test_results: List[TestResultOut] = []


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
    source_code: Optional[str] = None
    source_language: Optional[str] = None
    target_language: Optional[str] = None


class GenerateTestsRequest(BaseModel):
    count: int = Field(default=settings.max_generated_test_cases, ge=1, le=20)


class VerifyRequest(BaseModel):
    migrated_code: Optional[str] = None


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
