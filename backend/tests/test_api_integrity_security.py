"""Regression tests for API/database integrity and application security
(Priorities 6 and 7).

Covers ownership, validation, size limits, transaction rollback, error shape,
rate limiting, production secret validation, password policy and JWT handling.
No Docker and no real AI provider are required.
"""
import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.config import Settings
from app.core.security import (
    PasswordPolicyError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

JAVA_ADDER = "public class Main { public static void main(String[] a) { System.out.println(1); } }"


def auth_headers_for(client, email="trace@example.com"):
    response = client.post(
        "/api/auth/register",
        json={"name": "Trace", "email": email, "password": "supersecret"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_migration(client, headers, **overrides):
    payload = {
        "title": "t",
        "source_language": "java",
        "target_language": "python",
        "source_code": JAVA_ADDER,
    }
    payload.update(overrides)
    return client.post("/api/migrations", json=payload, headers=headers)


# -- ownership -----------------------------------------------------------------
def test_a_migration_belonging_to_another_user_is_a_404(client, auth_headers):
    migration_id = create_migration(client, auth_headers).json()["id"]
    other = client.post(
        "/api/auth/register",
        json={"name": "Other", "email": "other2@example.com", "password": "password123"},
    ).json()
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}

    for method, url in [
        ("get", f"/api/migrations/{migration_id}"),
        ("delete", f"/api/migrations/{migration_id}"),
        ("get", f"/api/migrations/{migration_id}/results"),
    ]:
        response = getattr(client, method)(url, headers=other_headers)
        assert response.status_code == 404, f"{method} {url} leaked ownership"


def test_another_user_cannot_update_a_migration(client, auth_headers):
    migration_id = create_migration(client, auth_headers).json()["id"]
    other = client.post(
        "/api/auth/register",
        json={"name": "Other", "email": "other3@example.com", "password": "password123"},
    ).json()
    response = client.patch(
        f"/api/migrations/{migration_id}",
        json={"title": "hijacked"},
        headers={"Authorization": f"Bearer {other['access_token']}"},
    )
    assert response.status_code == 404


def test_another_user_cannot_run_ai_endpoints(client, auth_headers):
    migration_id = create_migration(client, auth_headers).json()["id"]
    other = client.post(
        "/api/auth/register",
        json={"name": "Other", "email": "other4@example.com", "password": "password123"},
    ).json()
    headers = {"Authorization": f"Bearer {other['access_token']}"}
    for endpoint in ("analyze", "migrate", "generate-tests", "verify", "fix", "validate"):
        response = client.post(f"/api/migrations/{migration_id}/{endpoint}", headers=headers)
        assert response.status_code == 404, f"{endpoint} leaked ownership"


# -- missing records and invalid requests --------------------------------------
def test_missing_migration_returns_404(client, auth_headers):
    assert client.get("/api/migrations/999999", headers=auth_headers).status_code == 404


def test_unauthenticated_access_is_401(client):
    assert client.get("/api/migrations").status_code == 401
    assert client.post("/api/migrations", json={}).status_code == 401


def test_malformed_token_is_401(client):
    assert client.get("/api/migrations", headers={"Authorization": "Bearer not.a.jwt"}).status_code == 401
    assert client.get("/api/migrations", headers={"Authorization": "Bearer "}).status_code == 401


def test_unknown_language_is_rejected(client, auth_headers):
    assert create_migration(client, auth_headers, source_language="cobol").status_code in (400, 422)


def test_empty_language_is_rejected(client, auth_headers):
    assert create_migration(client, auth_headers, source_language="").status_code == 422


def test_oversized_source_code_is_rejected(client, auth_headers):
    from app.core.config import settings

    huge = "x" * (settings.max_code_size_bytes + 100)
    response = create_migration(client, auth_headers, source_code=huge)
    assert response.status_code in (400, 413, 422)


def test_invalid_body_type_is_rejected_cleanly(client, auth_headers):
    response = client.post("/api/migrations", json={"source_language": 42}, headers=auth_headers)
    assert response.status_code == 422
    body = response.json()
    assert body["error_type"] == "ValidationError"
    assert isinstance(body["errors"], list)


def test_generate_tests_count_bounds_are_enforced(client, auth_headers):
    migration_id = create_migration(client, auth_headers).json()["id"]
    response = client.post(
        f"/api/migrations/{migration_id}/generate-tests", json={"count": 999}, headers=auth_headers
    )
    assert response.status_code == 422


def test_fix_max_attempts_bounds_are_enforced(client, auth_headers):
    migration_id = create_migration(client, auth_headers).json()["id"]
    response = client.post(
        f"/api/migrations/{migration_id}/fix", json={"max_attempts": 99}, headers=auth_headers
    )
    assert response.status_code == 422


# -- error shape ---------------------------------------------------------------
def test_domain_errors_have_a_stable_shape(client, auth_headers):
    body = client.get("/api/migrations/999999", headers=auth_headers).json()
    assert "detail" in body
    assert body["error_type"] == "NotFoundError"


def test_internal_errors_do_not_leak_a_stack_trace(raw_client, monkeypatch):
    from app.services.migration_service import MigrationService

    def explode(self, *args, **kwargs):
        raise RuntimeError("super secret internal detail")

    monkeypatch.setattr(MigrationService, "create", explode)
    response = create_migration(raw_client, auth_headers_for(raw_client))
    assert response.status_code == 500
    body = response.json()
    assert "super secret internal detail" not in body["detail"]
    assert "Traceback" not in body["detail"]


def test_unknown_route_is_404(client):
    assert client.get("/api/nope").status_code == 404


# -- AI JSON failures surface as a structured, retryable API error --------------
class _GarbageProvider:
    """Always answers with unparseable text, so generation cannot recover."""

    name = "garbage"
    supports_json_mode = True

    def is_configured(self):
        return True

    def complete(self, *args, **kwargs):
        return "I'm sorry, I can't help with that."

    def complete_json(self, *args, **kwargs):
        from app.services.ai_providers import Completion

        return Completion(text="I'm sorry, I can't help with that.", finish_reason="stop")


def test_unrecoverable_ai_json_returns_a_structured_502(client, auth_headers, monkeypatch):
    """The reported bug: HTTP 200 from OpenAI but the API answered 502 with no detail."""
    from app.services import ai_service as ai_service_module

    migration_id = create_migration(client, auth_headers).json()["id"]

    # Route the endpoint's service through a provider that never returns JSON.
    monkeypatch.setattr(
        ai_service_module, "get_provider", lambda *a, **k: _GarbageProvider()
    )

    response = client.post(
        f"/api/migrations/{migration_id}/generate-tests", json={}, headers=auth_headers
    )
    assert response.status_code == 502
    body = response.json()
    # A structured, actionable error - not an empty body and not a traceback.
    assert body["error_type"] in {"AIJSONParseError", "AITestSchemaError"}
    assert isinstance(body["detail"], str) and body["detail"]
    assert "Traceback" not in body["detail"]


# -- rate limiting -------------------------------------------------------------
def test_login_rate_limit_returns_429(client, monkeypatch):
    """Drive the real middleware: after the configured number of attempts, 429."""
    from app.core import rate_limit

    monkeypatch.setattr(rate_limit.settings, "auth_rate_limit_requests", 3, raising=False)
    monkeypatch.setattr(rate_limit.settings, "rate_limit_enabled", True, raising=False)

    # The limiter lives on the middleware instance; find it by walking the stack.
    middleware = None
    stack = client.app.middleware_stack
    while stack is not None:
        if isinstance(stack, rate_limit.RateLimitMiddleware):
            middleware = stack
            break
        stack = getattr(stack, "app", None)
    assert middleware is not None, "RateLimitMiddleware is not installed"

    middleware.sensitive.reset()
    middleware.sensitive.limit = 3
    payload = {"email": "nobody@example.com", "password": "whatever123"}
    statuses = [client.post("/api/auth/login", json=payload).status_code for _ in range(4)]
    assert statuses[:3] == [401, 401, 401]
    assert statuses[3] == 429


def test_rate_limiter_is_per_key():
    from app.core.rate_limit import SlidingWindowLimiter

    limiter = SlidingWindowLimiter(limit=1, window_seconds=60)
    assert limiter.check("a")[0] is True
    assert limiter.check("a")[0] is False
    assert limiter.check("b")[0] is True


def test_rate_limiter_window_expires(monkeypatch):
    from app.core import rate_limit

    limiter = rate_limit.SlidingWindowLimiter(limit=1, window_seconds=1)
    assert limiter.check("k")[0] is True
    assert limiter.check("k")[0] is False
    # Force the window open by moving the recorded event into the past.
    with limiter._lock:
        limiter._events["k"][0] -= 5
    assert limiter.check("k")[0] is True


# -- production configuration validation --------------------------------------
def test_production_rejects_the_placeholder_jwt_secret():
    with pytest.raises(PydanticValidationError):
        Settings(environment="production", jwt_secret="change-me-in-production")


def test_production_rejects_a_short_jwt_secret():
    with pytest.raises(PydanticValidationError):
        Settings(environment="production", jwt_secret="short", cors_origins=["https://x.test"])


def test_production_requires_cors_origins():
    with pytest.raises(PydanticValidationError):
        Settings(environment="production", jwt_secret="x" * 40, cors_origins=[])


def test_production_accepts_a_strong_configuration():
    settings = Settings(
        environment="production",
        jwt_secret="a" * 40,
        cors_origins=["https://app.example.com"],
    )
    assert settings.is_production is True


def test_development_tolerates_default_secrets():
    settings = Settings(environment="development")
    assert settings.is_production is False


def test_cors_origins_accept_a_comma_separated_string():
    settings = Settings(cors_origins="https://a.test,https://b.test")
    assert settings.cors_origins == ["https://a.test", "https://b.test"]


def test_cors_origins_accept_a_json_array():
    settings = Settings(cors_origins='["https://a.test"]')
    assert settings.cors_origins == ["https://a.test"]


# -- password policy and JWT ---------------------------------------------------
def test_passwords_over_bcrypt_limit_are_rejected():
    with pytest.raises(PasswordPolicyError):
        hash_password("x" * 73)


def test_register_rejects_an_overlong_password(client):
    response = client.post(
        "/api/auth/register",
        json={"name": "Long", "email": "long@example.com", "password": "x" * 73},
    )
    assert response.status_code == 400


def test_password_verification_handles_a_corrupt_hash():
    assert verify_password("whatever", "not-a-bcrypt-hash") is False


def test_password_round_trip():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_jwt_round_trip():
    token = create_access_token("42")
    payload = decode_access_token(token)
    assert payload and payload["sub"] == "42"


def test_tampered_jwt_is_rejected():
    token = create_access_token("42")
    assert decode_access_token(token[:-3] + "aaa") is None


def test_expired_jwt_is_rejected():
    assert decode_access_token(create_access_token("42", expires_minutes=-1)) is None


def test_empty_jwt_is_rejected():
    assert decode_access_token("") is None
    assert decode_access_token("   ") is None


def test_jwt_without_subject_is_rejected(monkeypatch):
    from jose import jwt

    from app.core.config import settings

    token = jwt.encode({"exp": 9999999999}, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    assert decode_access_token(token) is None
