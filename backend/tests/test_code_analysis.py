from app.services.code_analysis_service import code_analysis_service

PY = """import sys
from math import sqrt

TOTAL = 10


class Calculator:
    def add(self, a, b):
        return a + b


def main():
    for line in sys.stdin:
        if line.strip():
            print(Calculator().add(1, 2))


main()
"""


def test_python_analysis_extracts_structure():
    analysis = code_analysis_service.analyze(PY, "python")
    assert analysis["language"] == "python"
    assert "main" in [fn["name"] for fn in analysis["functions"]]
    assert "Calculator" in [cls["name"] for cls in analysis["classes"]]
    assert "sys" in analysis["imports"]
    assert "TOTAL" in analysis["variables"]
    assert analysis["control_flow"]["for"] >= 1
    assert analysis["control_flow"]["if"] >= 1
    assert analysis["reads_stdin"] is True


def test_python_function_signatures_are_captured():
    analysis = code_analysis_service.analyze(PY, "python")
    add = next(fn for fn in analysis["functions"] if fn["name"] == "add")
    assert add["parameters"] == ["self", "a", "b"]


def test_java_analysis_finds_class_and_method():
    java = (
        "public class Main {\n"
        "  static int twice(int x) { return 2 * x; }\n"
        "  public static void main(String[] args) { System.out.println(twice(2)); }\n"
        "}\n"
    )
    analysis = code_analysis_service.analyze(java, "java")
    assert "Main" in [cls["name"] for cls in analysis["classes"]]
    assert "twice" in [fn["name"] for fn in analysis["functions"]]


def test_analysis_of_broken_code_does_not_raise():
    analysis = code_analysis_service.analyze("def broken(:\n", "python")
    assert analysis["language"] == "python"
    assert analysis["line_count"] >= 1
