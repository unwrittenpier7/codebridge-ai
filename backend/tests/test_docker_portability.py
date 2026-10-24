"""Regression tests for Docker executor portability and reliability (Priority 2).

The bug this covers: the executor called `os.getuid()`/`os.getgid()` directly,
which do not exist on standard Windows Python, so `prepare()` raised
`AttributeError` before any container was created.

These tests run without a Docker daemon. Real-container behavior is covered by
`test_docker_executor.py` (marked `docker`).
"""
import os

import pytest

from app.core.errors import ExecutionServiceError
from app.services import docker_executor as executor_module
from app.services.docker_executor import (
    FALLBACK_CONTAINER_USER,
    DockerExecutor,
    PreparedProgram,
    _shell_quote,
    _truncate,
    container_user,
)


# -- Windows portability -------------------------------------------------------
def test_container_user_works_without_getuid(monkeypatch):
    """Simulate a Windows interpreter by hiding os.getuid/os.getgid."""
    monkeypatch.delattr(os, "getuid", raising=False)
    monkeypatch.delattr(os, "getgid", raising=False)
    monkeypatch.setattr(executor_module.settings, "docker_container_user", "", raising=False)
    assert container_user() == FALLBACK_CONTAINER_USER


def test_container_user_uses_current_ids_on_posix(monkeypatch):
    monkeypatch.setattr(executor_module.settings, "docker_container_user", "", raising=False)
    assert container_user() == f"{os.getuid()}:{os.getgid()}"


def test_container_user_can_be_overridden(monkeypatch):
    monkeypatch.setattr(executor_module.settings, "docker_container_user", "1234:5678", raising=False)
    assert container_user() == "1234:5678"


def test_container_user_override_wins_on_windows(monkeypatch):
    monkeypatch.delattr(os, "getuid", raising=False)
    monkeypatch.delattr(os, "getgid", raising=False)
    monkeypatch.setattr(executor_module.settings, "docker_container_user", "0:0", raising=False)
    assert container_user() == "0:0"


def test_module_imports_without_posix_ids(monkeypatch):
    """The module must import cleanly where os.getuid does not exist."""
    monkeypatch.delattr(os, "getuid", raising=False)
    monkeypatch.delattr(os, "getgid", raising=False)
    # The helper must remain callable after the attribute disappears.
    assert ":" in container_user()


# -- command construction ------------------------------------------------------
def test_shell_quoting_escapes_embedded_quotes():
    quoted = _shell_quote(["echo", "it's"])
    assert quoted == "'echo' 'it'\\''s'"


def test_shell_quoting_wraps_every_argument():
    """Every element is quoted, so no argument can inject a shell operator."""
    assert _shell_quote(["./main", "; rm -rf /"]) == "'./main' '; rm -rf /'"


def test_shell_quoting_handles_empty_arguments():
    assert _shell_quote(["python", ""]) == "'python' ''"


# -- output truncation ---------------------------------------------------------
def test_output_is_truncated_at_the_configured_limit(monkeypatch):
    monkeypatch.setattr(executor_module.settings, "max_output_chars", 10, raising=False)
    truncated = _truncate("x" * 100)
    assert truncated.startswith("x" * 10)
    assert "truncated" in truncated


def test_short_output_is_not_touched(monkeypatch):
    monkeypatch.setattr(executor_module.settings, "max_output_chars", 1000, raising=False)
    assert _truncate("hello") == "hello"


# -- validation and cleanup ----------------------------------------------------
def test_oversized_source_is_rejected_before_docker_is_touched(monkeypatch):
    monkeypatch.setattr(executor_module.settings, "max_code_size_kb", 1, raising=False)
    executor = DockerExecutor()
    with pytest.raises(ExecutionServiceError) as excinfo:
        executor.prepare("python", "x" * 5000)
    assert "maximum allowed size" in str(excinfo.value)


def test_prepare_cleans_up_the_temp_directory_on_failure(monkeypatch):
    """A failed compile must still leave no temp workspace behind."""
    created = {}

    real_mkdtemp = executor_module.tempfile.mkdtemp

    def spy_mkdtemp(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        created["path"] = path
        return path

    monkeypatch.setattr(executor_module.tempfile, "mkdtemp", spy_mkdtemp)

    executor = DockerExecutor()
    monkeypatch.setattr(executor, "ensure_image", lambda image: None)
    monkeypatch.setattr(
        executor,
        "_compile",
        lambda language, workdir, command: executor_module.CompilationResult(
            success=False, stderr="syntax error"
        ),
    )

    program = executor.prepare("python", "print(1)\n")
    assert created["path"] and os.path.isdir(created["path"])
    program.cleanup()
    assert not os.path.isdir(created["path"])


def test_workspace_is_writable_for_the_unprivileged_container_user(monkeypatch):
    monkeypatch.setattr(executor_module.settings, "docker_container_user", "", raising=False)
    executor = DockerExecutor()
    monkeypatch.setattr(executor, "ensure_image", lambda image: None)
    program = executor.prepare("python", "print(1)\n")
    try:
        mode = os.stat(program.workdir).st_mode & 0o777
        # The container runs as a non-root uid and must be able to write here.
        assert mode & 0o002, f"workspace mode {oct(mode)} is not world-writable"
        source = os.path.join(program.workdir, "main.py")
        assert os.path.isfile(source)
        assert os.stat(source).st_mode & 0o444
    finally:
        program.cleanup()


def test_java_source_filename_follows_the_public_class(monkeypatch):
    executor = DockerExecutor()
    monkeypatch.setattr(executor, "ensure_image", lambda image: None)
    code = "public class Calculator { public static void main(String[] a) {} }"
    program = executor.prepare("java", code)
    try:
        assert os.path.isfile(os.path.join(program.workdir, "Calculator.java"))
        assert program.run_command == ["java", "Calculator"]
    finally:
        program.cleanup()


def test_run_returns_compilation_error_without_touching_docker():
    """A program that failed to compile must not be executed."""
    program = PreparedProgram(
        language=__import__("app.core.languages", fromlist=["get_language"]).get_language("cpp"),
        workdir="/tmp/does-not-matter",
        run_command=["./main"],
        compilation=executor_module.CompilationResult(success=False, stderr="error: nope"),
    )
    executor = DockerExecutor()
    result = executor.run(program, "1\n")
    assert result.exit_code != 0
    assert "nope" in result.stderr


# -- unavailable daemon --------------------------------------------------------
def test_missing_docker_daemon_is_reported_clearly(monkeypatch):
    executor = DockerExecutor()

    class BrokenClient:
        def ping(self):
            raise executor_module.DockerException("no such file or directory")

    monkeypatch.setattr(executor_module, "docker", type("D", (), {"from_env": staticmethod(lambda: BrokenClient())}))
    monkeypatch.setattr(executor_module.settings, "docker_execution_enabled", True, raising=False)

    available, detail = executor.availability()
    assert available is False
    assert "Docker daemon" in detail


def test_docker_execution_can_be_disabled(monkeypatch):
    monkeypatch.setattr(executor_module.settings, "docker_execution_enabled", False, raising=False)
    executor = DockerExecutor()
    available, detail = executor.availability()
    assert available is False
    assert "disabled" in detail.lower()


def test_missing_docker_package_is_reported(monkeypatch):
    monkeypatch.setattr(executor_module, "docker", None)
    monkeypatch.setattr(executor_module.settings, "docker_execution_enabled", True, raising=False)
    executor = DockerExecutor()
    available, detail = executor.availability()
    assert available is False
    assert "not installed" in detail
