import pytest

from tests.stubs import PYTHON_ADDER, ScriptedProvider, fenced, patch_ai

JAVA_ADDER = """import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        System.out.println(scanner.nextInt() + scanner.nextInt());
    }
}
"""


def create_migration(client, auth_headers, **overrides):
    payload = {
        "title": "Java adder",
        "source_language": "java",
        "target_language": "python",
        "source_code": JAVA_ADDER,
    }
    payload.update(overrides)
    return client.post("/api/migrations", json=payload, headers=auth_headers)


def test_migration_crud_and_ownership(client, auth_headers):
    created = create_migration(client, auth_headers)
    assert created.status_code == 201
    migration_id = created.json()["id"]

    listed = client.get("/api/migrations", headers=auth_headers)
    assert [m["id"] for m in listed.json()] == [migration_id]

    patched = client.patch(
        f"/api/migrations/{migration_id}", json={"title": "Renamed"}, headers=auth_headers
    )
    assert patched.json()["title"] == "Renamed"

    other = client.post(
        "/api/auth/register",
        json={"name": "Other", "email": "other@example.com", "password": "password123"},
    ).json()
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}
    assert client.get(f"/api/migrations/{migration_id}", headers=other_headers).status_code == 404
    assert client.get("/api/migrations", headers=other_headers).json() == []

    assert client.delete(f"/api/migrations/{migration_id}", headers=auth_headers).status_code == 204
    assert client.get(f"/api/migrations/{migration_id}", headers=auth_headers).status_code == 404


def test_unknown_language_is_rejected(client, auth_headers):
    response = create_migration(client, auth_headers, source_language="cobol")
    assert response.status_code in (400, 422)


def test_analyze_returns_program_structure(client, auth_headers):
    migration_id = create_migration(client, auth_headers).json()["id"]
    response = client.post(f"/api/migrations/{migration_id}/analyze", headers=auth_headers)
    assert response.status_code == 200
    analysis = response.json()
    assert analysis["language"] == "java"
    assert analysis["line_count"] > 0
    assert "functions" in analysis and "classes" in analysis


def test_migrate_uses_the_ai_provider(client, auth_headers, monkeypatch):
    provider = ScriptedProvider(migrations=[fenced(PYTHON_ADDER)])
    patch_ai(monkeypatch, provider)

    migration_id = create_migration(client, auth_headers).json()["id"]
    response = client.post(f"/api/migrations/{migration_id}/migrate", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["migrated_code"].strip() == PYTHON_ADDER.strip()
    assert body["status"] == "migrated"
    assert "migrate" in provider.calls


def test_migrate_without_api_key_returns_a_configuration_error(client, auth_headers, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.openai_api_key", "", raising=False)
    monkeypatch.setattr("app.core.config.settings.gemini_api_key", "", raising=False)
    monkeypatch.setattr("app.core.config.settings.ai_provider", "openai", raising=False)

    migration_id = create_migration(client, auth_headers).json()["id"]
    response = client.post(f"/api/migrations/{migration_id}/migrate", headers=auth_headers)
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"].lower()


def test_dashboard_stats_shape(client, auth_headers):
    create_migration(client, auth_headers)
    stats = client.get("/api/migrations/stats", headers=auth_headers).json()
    assert stats["total_migrations"] == 1
    assert stats["successful_migrations"] == 0
    assert len(stats["recent_migrations"]) == 1


def test_verify_requires_migrated_code_and_tests(client, auth_headers):
    migration_id = create_migration(client, auth_headers).json()["id"]
    response = client.post(f"/api/migrations/{migration_id}/verify", headers=auth_headers)
    assert response.status_code == 400
    assert "migrated code" in response.json()["detail"].lower()
