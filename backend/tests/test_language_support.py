"""Regression tests for language support and migration guidance (Priority 5).

Verifies the language registry (including the newly added C support), that C is
kept distinct from C++, that aliases resolve, and that per-language semantic
guidance and analysis are present.
"""
import pytest

from app.core.errors import UnsupportedLanguageError
from app.core.languages import ALIASES, LANGUAGES, get_language, supported_languages
from app.services.code_analysis_service import code_analysis_service

C_PROGRAM = """#include <stdio.h>
#include <stdlib.h>

int add(int a, int b) {
    return a + b;
}

int main(void) {
    int a, b;
    if (scanf("%d %d", &a, &b) != 2) {
        return 1;
    }
    printf("%d\\n", add(a, b));
    return 0;
}
"""


# -- registry ------------------------------------------------------------------
def test_all_expected_languages_are_supported():
    assert set(LANGUAGES) >= {"python", "javascript", "java", "cpp", "c", "go"}


def test_c_is_a_supported_language():
    language = get_language("c")
    assert language.key == "c"
    assert language.label == "C"


def test_c_and_cpp_are_distinct():
    c = get_language("c")
    cpp = get_language("cpp")
    assert c.key != cpp.key
    assert c.extension != cpp.extension
    assert c.extension == "c"
    assert cpp.extension in {"cpp", "cc", "cxx"}


def test_c_has_a_compiler_image_and_commands():
    language = get_language("c")
    assert language.image
    assert language.compile_command
    assert language.run_command
    assert language.source_filename.endswith(".c")


def test_c_uses_a_c_compiler_not_a_cpp_one():
    """The whole point: C must not be compiled as C++."""
    compile_command = " ".join(get_language("c").compile_command or [])
    assert "gcc" in compile_command or "clang" in compile_command
    assert "g++" not in compile_command


def test_c_aliases_resolve():
    for alias in ("c", "C", "ansi-c", "c99", "c11"):
        assert get_language(alias).key == "c"


def test_cpp_aliases_still_resolve():
    for alias in ("cpp", "c++", "cplusplus"):
        assert get_language(alias).key == "cpp"


def test_ambiguous_cc_alias_is_left_unsupported():
    """`cc` means the C compiler to make(1) and a C++ extension to compilers.

    Guessing either way could silently compile a program with the wrong
    language's semantics, so the alias is deliberately not mapped.
    """
    assert "cc" not in ALIASES
    with pytest.raises(UnsupportedLanguageError):
        get_language("cc")


def test_alias_table_does_not_conflate_c_and_cpp():
    assert ALIASES.get("c++") == "cpp"
    assert ALIASES.get("ansi-c") == "c"
    assert get_language("c").key != get_language("c++").key


def test_unknown_language_raises_an_unsupported_language_error():
    with pytest.raises(UnsupportedLanguageError):
        get_language("cobol")


def test_every_language_has_migration_guidance():
    for language in supported_languages():
        assert language.migration_guidance, f"{language.key} has no migration guidance"


def test_every_language_declares_a_source_filename():
    for language in supported_languages():
        assert language.source_filename
        assert language.run_command, f"{language.key} has no run command"


def test_stdin_based_languages_are_detected():
    assert code_analysis_service.analyze(C_PROGRAM, "c")["reads_stdin"] is True
    assert code_analysis_service.analyze("print(1)", "python")["reads_stdin"] is False


# -- analysis ------------------------------------------------------------------
def test_c_analysis_extracts_structure():
    analysis = code_analysis_service.analyze(C_PROGRAM, "c")
    assert analysis["language"] == "c"
    assert "add" in [fn["name"] for fn in analysis["functions"]]
    assert analysis["reads_stdin"] is True
    assert "stdio.h" in analysis["imports"]


def test_c_analysis_detects_pointer_and_memory_usage():
    """C-specific semantics must be surfaced so the migration prompt can warn."""
    analysis = code_analysis_service.analyze(C_PROGRAM, "c")
    signals = analysis["semantic_signals"]
    assert signals, "C analysis must report language-specific semantic signals"
    assert any(
        key in signals for key in ("pointers", "memory", "arrays", "integer_types")
    ), signals


def test_c_analysis_flags_unsafe_string_functions():
    analysis = code_analysis_service.analyze('#include <string.h>\nchar b[8]; strcpy(b, s);\n', "c")
    assert "unsafe_strings" in analysis["semantic_signals"]


def test_analysis_marks_itself_best_effort():
    """Regex/parser analysis is not a proof of equivalence and must say so."""
    analysis = code_analysis_service.analyze(C_PROGRAM, "c")
    assert analysis["analyzer"] in {"tree-sitter", "regex-fallback", "python-ast"}
    assert analysis["semantic_equivalence_proven"] is False


def test_analysis_reports_a_confidence_level():
    analysis = code_analysis_service.analyze(C_PROGRAM, "c")
    assert analysis["analysis_confidence"] in {"exact", "approximate", "heuristic"}


def test_java_analysis_flags_overflow_and_null_signals():
    code = (
        "public class Main {\n"
        "  public static void main(String[] a) {\n"
        "    Integer x = null;\n"
        "    System.out.println(Integer.MAX_VALUE);\n"
        "  }\n"
        "}\n"
    )
    signals = code_analysis_service.analyze(code, "java")["semantic_signals"]
    assert "integer_overflow" in signals
    assert "null_handling" in signals


def test_analysis_for_each_supported_language_does_not_crash():
    samples = {
        "python": "print(1)\n",
        "javascript": "console.log(1);\n",
        "java": "public class Main { public static void main(String[] a) {} }\n",
        "cpp": "int main(){return 0;}\n",
        "c": "int main(void){return 0;}\n",
        "go": "package main\nfunc main(){}\n",
    }
    for key, code in samples.items():
        analysis = code_analysis_service.analyze(code, key)
        assert analysis["language"] == key
        assert isinstance(analysis["semantic_signals"], dict)

