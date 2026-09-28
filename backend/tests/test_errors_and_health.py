from app.core.errors import (
    AIProviderError,
    CodeBridgeError,
    ConfigurationError,
    ExecutionServiceError,
    NotFoundError,
    UnsupportedLanguageError,
    ValidationError,
)


def test_health_endpoint_reports_dependencies(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert set(["ai_configured", "docker_available", "ai_provider"]) <= set(body)


def test_languages_endpoint_lists_supported_languages(client):
    keys = {item["key"] for item in client.get("/api/languages").json()}
    assert {"python", "javascript", "java", "cpp", "go"} <= keys


def test_error_status_codes_are_distinct():
    assert NotFoundError("x").status_code == 404
    assert ValidationError("x").status_code == 400
    assert ConfigurationError("x").status_code == 503
    assert AIProviderError("x").status_code == 502
    assert ExecutionServiceError("x").status_code == 503
    assert UnsupportedLanguageError("x").status_code == 400
    assert CodeBridgeError("x").status_code == 500
    assert isinstance(ValidationError("x"), CodeBridgeError)


def test_domain_errors_are_translated_to_json(client, auth_headers):
    response = client.get("/api/migrations/424242", headers=auth_headers)
    assert response.status_code == 404
    assert "detail" in response.json()


def test_unknown_route_returns_404(client):
    assert client.get("/api/does-not-exist").status_code == 404
