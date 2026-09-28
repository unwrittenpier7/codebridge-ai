"""Docker sandbox tests: real containers, real compilers."""
import pytest

from app.core.errors import ExecutionServiceError
from app.core.languages import get_language, supported_languages
from app.services.docker_executor import docker_executor

pytestmark = pytest.mark.docker

ADDERS = {
    "python": "import sys\na,b=[int(x) for x in sys.stdin.read().split()[:2]]\nprint(a+b)\n",
    "javascript": (
        "const d=require('fs').readFileSync(0,'utf8').trim().split(/\\s+/);\n"
        "console.log(parseInt(d[0])+parseInt(d[1]));\n"
    ),
    "java": (
        "import java.util.Scanner;\npublic class Main{public static void main(String[] a){"
        "Scanner s=new Scanner(System.in);System.out.println(s.nextInt()+s.nextInt());}}\n"
    ),
    "cpp": "#include <iostream>\nint main(){int a,b;std::cin>>a>>b;std::cout<<a+b<<std::endl;}\n",
    "go": (
        "package main\nimport \"fmt\"\nfunc main(){var a,b int;fmt.Scan(&a,&b);fmt.Println(a+b)}\n"
    ),
}


@pytest.fixture(autouse=True)
def _require_docker(docker_available):
    if not docker_available:
        pytest.skip("Docker daemon is not available in this environment")


def test_language_registry_covers_the_required_languages():
    keys = {language.key for language in supported_languages()}
    assert {"python", "javascript", "java", "cpp", "go"} <= keys
    assert get_language("c++").key == "cpp"
    assert get_language("PY").key == "python"


@pytest.mark.parametrize("language", sorted(ADDERS))
def test_each_language_runs_and_returns_real_output(language):
    compilation, result = docker_executor.execute_once(language, ADDERS[language], "5\n10\n")
    assert compilation.success, compilation.error_message
    assert result.stdout.strip() == "15"
    assert result.exit_code == 0
    assert result.execution_time_ms >= 0


def test_compilation_failure_is_reported_not_raised():
    program = docker_executor.prepare("cpp", "int main(){ this is not c++ }")
    try:
        assert not program.compilation.success
        assert program.compilation.error_message
    finally:
        program.cleanup()


def test_runtime_error_exit_code_and_stderr_are_captured():
    _, result = docker_executor.execute_once("python", "raise ValueError('nope')\n")
    assert result.exit_code != 0
    assert "ValueError" in result.stderr


def test_infinite_loop_times_out():
    _, result = docker_executor.execute_once("python", "while True:\n    pass\n")
    assert result.timed_out
    assert result.exit_code != 0


def test_network_is_disabled_inside_the_sandbox():
    code = (
        "import socket\n"
        "try:\n"
        "    socket.create_connection(('1.1.1.1', 80), timeout=3)\n"
        "    print('NETWORK')\n"
        "except Exception:\n"
        "    print('NO-NETWORK')\n"
    )
    _, result = docker_executor.execute_once("python", code)
    assert result.stdout.strip() == "NO-NETWORK"


def test_oversized_source_is_rejected():
    from app.core.config import settings

    huge = "# padding\n" * (settings.max_code_size_kb * 200)
    with pytest.raises(ExecutionServiceError):
        docker_executor.prepare("python", huge)


def test_output_is_truncated_rather_than_unbounded():
    from app.core.config import settings

    _, result = docker_executor.execute_once(
        "python", "print('x' * 10_000_000)\n"
    )
    assert len(result.stdout) <= settings.max_output_chars + 200
