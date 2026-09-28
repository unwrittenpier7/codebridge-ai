"""Sandboxed code execution using Docker containers.

User supplied code is never executed on the FastAPI host. Every compilation and
every program run happens inside a throwaway container with:

* no network access
* a CPU quota and a memory limit
* a PID limit
* a wall-clock timeout
* a temporary working directory mounted read/write for that run only
* a non-root user
* automatic container removal
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from app.core.config import settings
from app.core.errors import ExecutionServiceError
from app.core.languages import LanguageConfig, get_language
from app.core.logging_config import get_logger

logger = get_logger(__name__)

try:  # pragma: no cover - import guard
    import docker
    from docker.errors import DockerException, ImageNotFound, NotFound
except Exception:  # pragma: no cover
    docker = None

    class DockerException(Exception):
        pass

    class ImageNotFound(Exception):
        pass

    class NotFound(Exception):
        pass


JAVA_PUBLIC_CLASS = re.compile(r"public\s+(?:final\s+|abstract\s+)?class\s+([A-Za-z_]\w*)")


@dataclass
class ExecutionResult:
    """Outcome of running one program once."""

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    execution_time_ms: float = 0.0
    timed_out: bool = False

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


@dataclass
class CompilationResult:
    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    timed_out: bool = False

    @property
    def error_message(self) -> str:
        if self.success:
            return ""
        if self.timed_out:
            return "Compilation timed out."
        return (self.stderr or self.stdout or "Compilation failed.").strip()


@dataclass
class PreparedProgram:
    """A workspace on the host holding sources (and build output) for a program."""

    language: LanguageConfig
    workdir: str
    run_command: List[str]
    compilation: CompilationResult = field(
        default_factory=lambda: CompilationResult(success=True)
    )

    def cleanup(self) -> None:
        shutil.rmtree(self.workdir, ignore_errors=True)


def _truncate(text: str) -> str:
    limit = settings.max_output_chars
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [output truncated at {limit} characters]"


def _shell_quote(parts: List[str]) -> str:
    return " ".join(f"'{p}'" if " " in p else p for p in parts)


class DockerExecutor:
    """Thin, safe wrapper around the Docker Engine API."""

    def __init__(self) -> None:
        self._client = None

    # -- availability -----------------------------------------------------
    @property
    def client(self):
        if self._client is None:
            if not settings.docker_execution_enabled:
                raise ExecutionServiceError(
                    "Docker execution is disabled (DOCKER_EXECUTION_ENABLED=false). "
                    "Enable it to run behavioral verification."
                )
            if docker is None:
                raise ExecutionServiceError(
                    "The 'docker' Python package is not installed on the backend host."
                )
            try:
                self._client = docker.from_env()
                self._client.ping()
            except DockerException as exc:
                raise ExecutionServiceError(
                    f"Execution service unavailable: cannot reach the Docker daemon ({exc})."
                ) from exc
        return self._client

    def availability(self) -> Tuple[bool, str]:
        try:
            self.client
        except ExecutionServiceError as exc:
            return False, exc.message
        return True, "Docker daemon reachable"

    def ensure_image(self, image: str) -> None:
        try:
            self.client.images.get(image)
        except ImageNotFound:
            logger.info("Pulling execution image %s", image)
            try:
                self.client.images.pull(image)
            except DockerException as exc:
                raise ExecutionServiceError(
                    f"Execution service error: could not pull image '{image}' ({exc})."
                ) from exc
        except DockerException as exc:
            raise ExecutionServiceError(f"Execution service error: {exc}") from exc

    # -- program preparation ----------------------------------------------
    def prepare(self, language_key: str, code: str) -> PreparedProgram:
        """Write sources to a temp workspace and compile them if the language needs it."""
        language = get_language(language_key)
        self._validate_code_size(code)
        self.ensure_image(language.image)

        workdir = tempfile.mkdtemp(prefix="codebridge-")
        os.chmod(workdir, 0o777)

        source_filename = language.source_filename
        run_command = list(language.run_command)
        compile_command = list(language.compile_command) if language.compile_command else None

        if language.key == "java":
            match = JAVA_PUBLIC_CLASS.search(code)
            class_name = match.group(1) if match else "Main"
            source_filename = f"{class_name}.java"
            compile_command = ["javac", source_filename]
            run_command = ["java", class_name]

        with open(os.path.join(workdir, source_filename), "w", encoding="utf-8") as handle:
            handle.write(code)

        program = PreparedProgram(language=language, workdir=workdir, run_command=run_command)

        if compile_command:
            program.compilation = self._compile(language, workdir, compile_command)
        return program

    def _compile(
        self, language: LanguageConfig, workdir: str, compile_command: List[str]
    ) -> CompilationResult:
        result = self._run_in_container(
            image=language.image,
            workdir=workdir,
            shell_command=_shell_quote(compile_command),
            timeout=max(settings.max_execution_time * 3, 30),
            env=self._language_env(language),
        )
        return CompilationResult(
            success=result.exit_code == 0 and not result.timed_out,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
            timed_out=result.timed_out,
        )

    # -- execution ---------------------------------------------------------
    def run(
        self,
        program: PreparedProgram,
        stdin_data: str = "",
        timeout: Optional[int] = None,
    ) -> ExecutionResult:
        """Execute a prepared program once with the given stdin."""
        if not program.compilation.success:
            return ExecutionResult(
                stderr=program.compilation.error_message,
                exit_code=program.compilation.exit_code or 1,
            )

        input_path = os.path.join(program.workdir, "__stdin.txt")
        with open(input_path, "w", encoding="utf-8") as handle:
            handle.write(stdin_data or "")

        command = f"{_shell_quote(program.run_command)} < __stdin.txt"
        return self._run_in_container(
            image=program.language.image,
            workdir=program.workdir,
            shell_command=command,
            timeout=timeout or settings.max_execution_time,
            env=self._language_env(program.language),
        )

    def execute_once(
        self, language_key: str, code: str, stdin_data: str = ""
    ) -> Tuple[CompilationResult, ExecutionResult]:
        """Convenience helper: prepare, run once and clean up."""
        program = self.prepare(language_key, code)
        try:
            return program.compilation, self.run(program, stdin_data)
        finally:
            program.cleanup()

    # -- internals ---------------------------------------------------------
    def _language_env(self, language: LanguageConfig) -> dict:
        env = {"HOME": "/workspace"}
        if language.key == "go":
            env.update(
                {
                    "GOCACHE": "/workspace/.cache",
                    "GOPATH": "/workspace/.gopath",
                    "GO111MODULE": "off",
                    "CGO_ENABLED": "0",
                }
            )
        return env

    def _validate_code_size(self, code: str) -> None:
        max_bytes = settings.max_code_size_kb * 1024
        if len(code.encode("utf-8")) > max_bytes:
            raise ExecutionServiceError(
                f"Source code exceeds the maximum allowed size of {settings.max_code_size_kb} KB."
            )

    def _run_in_container(
        self,
        image: str,
        workdir: str,
        shell_command: str,
        timeout: int,
        env: Optional[dict] = None,
    ) -> ExecutionResult:
        container = None
        started = time.perf_counter()
        try:
            container = self.client.containers.create(
                image=image,
                command=["/bin/sh", "-c", shell_command],
                working_dir="/workspace",
                volumes={workdir: {"bind": "/workspace", "mode": "rw"}},
                network_disabled=True,
                network_mode="none",
                mem_limit=f"{settings.max_memory_mb}m",
                memswap_limit=f"{settings.max_memory_mb}m",
                nano_cpus=1_000_000_000,  # 1 CPU
                pids_limit=settings.max_processes,
                user=f"{os.getuid()}:{os.getgid()}",
                environment=env or {},
                stdin_open=False,
                tty=False,
                detach=True,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges"],
            )
            container.start()
            timed_out = False
            exit_code = 0
            try:
                status = container.wait(timeout=timeout)
                exit_code = int(status.get("StatusCode", 0))
            except Exception:
                timed_out = True
                exit_code = 124
                try:
                    container.kill()
                except Exception:  # pragma: no cover - best effort
                    pass

            elapsed_ms = (time.perf_counter() - started) * 1000
            stdout = container.logs(stdout=True, stderr=False).decode("utf-8", "replace")
            stderr = container.logs(stdout=False, stderr=True).decode("utf-8", "replace")
            if timed_out:
                stderr = (
                    stderr + f"\nExecution timed out after {timeout}s."
                ).strip()
            return ExecutionResult(
                stdout=_truncate(stdout),
                stderr=_truncate(stderr),
                exit_code=exit_code,
                execution_time_ms=round(elapsed_ms, 2),
                timed_out=timed_out,
            )
        except ExecutionServiceError:
            raise
        except DockerException as exc:
            raise ExecutionServiceError(f"Execution service error: {exc}") from exc
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except (NotFound, DockerException):  # pragma: no cover - best effort
                    pass


docker_executor = DockerExecutor()
