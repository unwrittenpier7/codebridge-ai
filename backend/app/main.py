"""CodeBridge AI FastAPI application entrypoint."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import auth, migrations, verification
from app.core.config import settings
from app.core.errors import CodeBridgeError, ValidationError
from app.core.languages import supported_languages
from app.core.logging_config import configure_logging, get_logger
from app.core.rate_limit import RateLimitMiddleware
from app.database.connection import init_db
from app.schemas.migration import HealthOut, LanguageOut
from app.services.ai_providers import get_provider
from app.services.docker_executor import docker_executor

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    logger.info(
        "CodeBridge AI started (environment=%s, ai_provider=%s)",
        settings.environment,
        settings.ai_provider,
    )
    yield


app = FastAPI(
    title="CodeBridge AI",
    description="AI-assisted multi-language source code migration and behavioral verification.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS: an explicit allow-list always applies. The permissive localhost regex is
# only added outside production, so a deployed instance cannot be called from an
# arbitrary page served on someone's localhost.
_cors_origin_regex = None
if not settings.is_production:
    _cors_origin_regex = r"https?://(localhost|127\.0\.0\.1)(:\d+)?"

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=_cors_origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Rate limit authentication endpoints (and everything else, generously).
app.add_middleware(RateLimitMiddleware)

#: Requests larger than this are refused before they are parsed. The code-size
#: limit is enforced again per field, but a hard transport ceiling protects the
#: process from a huge body regardless of schema.
MAX_REQUEST_BYTES = max(settings.max_code_size_bytes * 4, 2 * 1024 * 1024)


@app.middleware("http")
async def limit_request_size(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_REQUEST_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": (
                            "Request body is too large. The maximum accepted size is "
                            f"{MAX_REQUEST_BYTES // 1024} KB."
                        ),
                        "error_type": "PayloadTooLargeError",
                    },
                )
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid Content-Length header.", "error_type": "BadRequest"},
            )
    return await call_next(request)


@app.exception_handler(CodeBridgeError)
def handle_domain_error(_: Request, exc: CodeBridgeError) -> JSONResponse:
    logger.warning("%s: %s", type(exc).__name__, exc.message)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "error_type": type(exc).__name__},
    )


@app.exception_handler(RequestValidationError)
def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Return a stable shape for 422s instead of FastAPI's raw error list."""
    return JSONResponse(
        status_code=422,
        content={
            "detail": "The request payload was invalid.",
            "error_type": "ValidationError",
            "errors": [
                {"loc": list(error.get("loc", [])), "msg": error.get("msg", "")}
                for error in exc.errors()
            ],
        },
    )


@app.exception_handler(Exception)
def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
    """Never leak a stack trace or internal detail to the client."""
    logger.exception("Unhandled error: %s", type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An internal error occurred. The failure has been logged.",
            "error_type": "InternalServerError",
        },
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
