"""Application configuration loaded from environment variables."""
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "CodeBridge AI"
    api_prefix: str = "/api"

    database_url: str = "sqlite:///./codebridge.db"

    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24

    ai_provider: str = "openai"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"
    ai_request_timeout: int = 120

    docker_execution_enabled: bool = True
    max_execution_time: int = 10
    max_memory_mb: int = 256
    max_code_size_kb: int = 500
    max_output_chars: int = 20000
    max_processes: int = 128

    max_correction_attempts: int = 3
    max_generated_test_cases: int = 10

    cors_origins: List[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
