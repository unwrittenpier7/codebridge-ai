"""Application configuration loaded from environment variables."""
from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Secret values that must never be used outside local development.
INSECURE_JWT_SECRETS = {
    "",
    "change-me-in-production",
    "replace-with-a-long-random-string",
    "secret",
    "changeme",
}
MIN_JWT_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "CodeBridge AI"
    api_prefix: str = "/api"

    #: "development" relaxes the production secret checks; anything else is
    #: treated as a deployed environment and validated strictly.
    environment: str = "development"

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
    #: "uid:gid" the sandbox runs as. Empty means "current user on POSIX,
    #: 1000:1000 on Windows".
    docker_container_user: str = ""
    max_execution_time: int = 10
    max_memory_mb: int = 256
    max_code_size_kb: int = 500
    max_output_chars: int = 20000
    max_processes: int = 128

    max_correction_attempts: int = 3
    max_generated_test_cases: int = 10

    #: Numeric tolerance for output comparison. Off by default: a migration that
    #: changes `3.0` into `3` has changed observable behavior. Enable it only for
    #: targets where float formatting genuinely differs.
    verification_numeric_tolerance: bool = False
    verification_numeric_rel_tolerance: float = 1e-9
    verification_numeric_abs_tolerance: float = 1e-9

    #: Explicit CORS allow-list. The localhost regex is only added outside
    #: production so a deployed instance cannot be called from any localhost page.
    cors_origins: List[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    #: Simple in-process rate limit for authentication endpoints.
    auth_rate_limit_requests: int = 20
    auth_rate_limit_window_seconds: int = 60
    rate_limit_enabled: bool = True
    #: Only enable behind a proxy you control that overwrites X-Forwarded-For.
    trust_proxy_headers: bool = False

    log_level: str = "INFO"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value):
        """Accept a JSON array (compose) or a comma separated string (shell)."""
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return []
            if raw.startswith("["):
                import json

                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    pass
            return [item.strip() for item in raw.split(",") if item.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() in {"production", "prod", "staging"}

    @model_validator(mode="after")
    def _validate_production_secrets(self):
        """Refuse to start a deployed instance with placeholder credentials."""
        if not self.is_production:
            return self
        problems = []
        if self.jwt_secret.strip() in INSECURE_JWT_SECRETS:
            problems.append("JWT_SECRET is still the example placeholder")
        elif len(self.jwt_secret.strip()) < MIN_JWT_SECRET_LENGTH:
            problems.append(
                f"JWT_SECRET must be at least {MIN_JWT_SECRET_LENGTH} characters in production"
            )
        if not self.cors_origins:
            problems.append("CORS_ORIGINS must list the deployed frontend origin(s)")
        if self.jwt_algorithm.strip().upper().startswith("HS") is False:
            # Asymmetric algorithms are fine, but a misconfigured value is not.
            if self.jwt_algorithm.strip().upper() not in {"RS256", "ES256"}:
                problems.append(f"JWT_ALGORITHM '{self.jwt_algorithm}' is not a supported algorithm")
        if problems:
            raise ValueError(
                "Refusing to start with an unsafe production configuration: "
                + "; ".join(problems)
            )
        return self

    @property
    def max_code_size_bytes(self) -> int:
        return self.max_code_size_kb * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

