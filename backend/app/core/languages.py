"""Supported languages and their per-language execution configuration.

Each entry carries everything needed to (a) write the source file, (b) compile
it, (c) run it, and (d) give the migration model language-specific semantic
guidance. C is a first-class language here: it is *not* treated as C++.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.core.errors import UnsupportedLanguageError


@dataclass(frozen=True)
class LanguageConfig:
    """Everything needed to compile and run a program for one language."""

    key: str
    label: str
    monaco_id: str
    extension: str
    image: str
    source_filename: str
    run_command: List[str] = field(default_factory=list)
    compile_command: Optional[List[str]] = None
    #: Language-specific semantics appended to the migration prompt.
    migration_guidance: str = ""


JAVA_GUIDANCE = "- The Java entry class must be named Main."
GO_GUIDANCE = "- Go code must be package main with a func main()."

CPP_GUIDANCE = (
    "- C++ specifics: preserve integer widths (int vs long long) and overflow behavior; "
    "std::endl flushes and emits exactly one newline; std::cin >> skips whitespace, so a "
    "migrated program must consume input the same way; uninitialized locals must not become "
    "defined values; use the standard library only (no Boost)."
)

C_GUIDANCE = (
    "- C specifics: main must return int; use only the C standard library (stdio.h, stdlib.h, "
    "string.h, math.h); preserve integer widths and signed overflow behavior; scanf/fgets skip "
    "and split input exactly as written; printf formatting (e.g. %d, %lld, %.6f) determines the "
    "exact stdout, so reproduce it character for character; there are no exceptions, so error "
    "paths must return exit codes instead; arrays are not bounds-checked, so do not introduce "
    "undefined behavior."
)

JAVASCRIPT_GUIDANCE = (
    "- JavaScript specifics: read stdin synchronously from file descriptor 0; numbers are "
    "IEEE-754 doubles, so integer division must be floored explicitly and large 64-bit values "
    "may lose precision; use only the Node.js standard library; console.log adds a trailing "
    "newline."
)

PYTHON_GUIDANCE = (
    "- Python specifics: sys.stdin.read() vs input() changes whitespace handling; integer "
    "division differs from C-like languages; print() adds a newline; floats print with repr "
    "precision."
)

GO_GUIDANCE_FULL = (
    GO_GUIDANCE + " Preserve integer widths (int is 64-bit on most platforms); use only the Go "
    "standard library; fmt.Println adds a newline."
)


LANGUAGES: Dict[str, LanguageConfig] = {
    "python": LanguageConfig(
        key="python",
        label="Python",
        monaco_id="python",
        extension="py",
        image="python:3.11-alpine",
        source_filename="main.py",
        run_command=["python", "main.py"],
        migration_guidance=PYTHON_GUIDANCE,
    ),
    "javascript": LanguageConfig(
        key="javascript",
        label="JavaScript",
        monaco_id="javascript",
        extension="js",
        image="node:20-alpine",
        source_filename="main.js",
        run_command=["node", "main.js"],
        migration_guidance=JAVASCRIPT_GUIDANCE,
    ),
    "java": LanguageConfig(
        key="java",
        label="Java",
        monaco_id="java",
        extension="java",
        image="eclipse-temurin:21-jdk-alpine",
        source_filename="Main.java",
        compile_command=["javac", "Main.java"],
        run_command=["java", "Main"],
        migration_guidance=JAVA_GUIDANCE,
    ),
    "cpp": LanguageConfig(
        key="cpp",
        label="C++",
        monaco_id="cpp",
        extension="cpp",
        image="gcc:13",
        source_filename="main.cpp",
        compile_command=["g++", "-O2", "-std=c++17", "-o", "main", "main.cpp"],
        run_command=["./main"],
        migration_guidance=CPP_GUIDANCE,
    ),
    "c": LanguageConfig(
        key="c",
        label="C",
        monaco_id="c",
        extension="c",
        image="gcc:13",
        source_filename="main.c",
        compile_command=["gcc", "-O2", "-std=c11", "-o", "main", "main.c"],
        run_command=["./main"],
        migration_guidance=C_GUIDANCE,
    ),
    "go": LanguageConfig(
        key="go",
        label="Go",
        monaco_id="go",
        extension="go",
        image="golang:1.22-alpine",
        source_filename="main.go",
        compile_command=["go", "build", "-o", "main", "main.go"],
        run_command=["./main"],
        migration_guidance=GO_GUIDANCE_FULL,
    ),
}

ALIASES = {
    "c++": "cpp",
    "cplusplus": "cpp",
    "js": "javascript",
    "node": "javascript",
    "nodejs": "javascript",
    "py": "python",
    "python3": "python",
    "golang": "go",
    "ansi-c": "c",
    "c99": "c",
    "c11": "c",
}


def get_language(key: str) -> LanguageConfig:
    normalized = (key or "").strip().lower()
    normalized = ALIASES.get(normalized, normalized)
    if normalized not in LANGUAGES:
        raise UnsupportedLanguageError(
            f"Unsupported language '{key}'. Supported: {', '.join(sorted(LANGUAGES))}"
        )
    return LANGUAGES[normalized]


def supported_languages() -> List[LanguageConfig]:
    return list(LANGUAGES.values())
