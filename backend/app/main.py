"""CodeBridge AI FastAPI application entrypoint."""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import auth, migrations, verification
from app.core.config import settings
from app.core.errors import CodeBridgeError
from app.core.languages import supported_languages
from app.core.logging_config import configure_logging, get_logger
from app.database.connection import init_db
from app.schemas.migration import HealthOut, LanguageOut
from app.services.ai_providers import get_provider
from app.services.docker_executor import docker_executor

configure_logging()
logger = get_logger(__name__)

app = FastAPI(
    title="CodeBridge AI",
    description="AI-assisted multi-language source code migration and behavioral verification.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    logger.info("CodeBridge AI started (ai_provider=%s)", settings.ai_provider)


@app.exception_handler(CodeBridgeError)
def handle_domain_error(_: Request, exc: CodeBridgeError) -> JSONResponse:
    logger.warning("%s: %s", type(exc).__name__, exc.message)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "error_type": type(exc).__name__},
    )


@app.get("/api/health", response_model=HealthOut, tags=["system"])
def health() -> HealthOut:
    docker_available, docker_detail = (False, "Docker execution disabled")
    if settings.docker_execution_enabled:
        docker_available, docker_detail = docker_executor.availability()
    try:
        provider = get_provider()
        ai_configured = provider.is_configured()
        provider_name = provider.name
    except CodeBridgeError as exc:
        ai_configured, provider_name = False, settings.ai_provider
        docker_detail = f"{docker_detail}; {exc.message}"
    return HealthOut(
        status="ok",
        ai_provider=provider_name,
        ai_configured=ai_configured,
        docker_available=docker_available,
        docker_detail=docker_detail,
    )


@app.get("/api/languages", response_model=list[LanguageOut], tags=["system"])
def languages() -> list[LanguageOut]:
    return [
        LanguageOut(key=lang.key, label=lang.label, monaco_id=lang.monaco_id)
        for lang in supported_languages()
    ]


app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(migrations.router, prefix=settings.api_prefix)
app.include_router(verification.router, prefix=settings.api_prefix)
