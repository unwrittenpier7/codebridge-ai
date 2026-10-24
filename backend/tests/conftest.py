"""Test fixtures: an isolated SQLite database and a FastAPI client with stub services."""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test-codebridge.db")
os.environ.setdefault("JWT_SECRET", "test-secret")

from app.database.connection import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_rate_limiter(monkeypatch):
    """Keep the in-process limiter from leaking state between tests.

    The limiter instance is created once when the app is imported, so without
    this every test in the session would share one counter and unrelated tests
    would start receiving 429s. Rate limiting is off by default here; the tests
    that exercise it turn it back on explicitly.
    """
    from app.core import rate_limit

    monkeypatch.setattr(rate_limit.settings, "rate_limit_enabled", False, raising=False)
    for name in ("_LIMITER", "_SENSITIVE_LIMITER", "_GENERAL_LIMITER"):
        limiter = getattr(rate_limit, name, None)
        if isinstance(limiter, rate_limit.SlidingWindowLimiter):
            limiter.reset()
    yield


@pytest.fixture()
def db_session():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
        os.unlink(path)


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def raw_client(db_session):
    """Like `client`, but surfaces the app's own 500 response instead of re-raising.

    Needed to assert that an unexpected exception is converted into a safe error
    body rather than leaking a traceback.
    """
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(client):
    response = client.post(
        "/api/auth/register",
        json={"name": "Test User", "email": "test@example.com", "password": "supersecret"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture()
def docker_available():
    from app.services.docker_executor import docker_executor

    available, _ = docker_executor.availability()
    return available


@pytest.fixture(autouse=True)
def _skip_docker_tests_without_daemon(request):
    """Skip @docker tests explicitly when no daemon is reachable.

    They are never silently reported as passing: pytest records them as skipped
    with the reason below, so a run without Docker is visibly incomplete.
    """
    if request.node.get_closest_marker("docker") is None:
        return
    from app.services.docker_executor import docker_executor

    available, detail = docker_executor.availability()
    if not available:
        pytest.skip(f"Docker daemon unavailable: {detail}")
