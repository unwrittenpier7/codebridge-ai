"""Supported languages and their per-language execution configuration."""
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
    compile_command: Optional[List[str]] = None
    run_command: List[str] = field(default_factory=list)


LANGUAGES: Dict[str, LanguageConfig] = {
    "python": LanguageConfig(
        key="python",
        label="Python",
        monaco_id="python",
        extension="py",
        image="python:3.11-alpine",
        source_filename="main.py",
        run_command=["python", "main.py"],
    ),
    "javascript": LanguageConfig(
        key="javascript",
        label="JavaScript",
        monaco_id="javascript",
        extension="js",
        image="node:20-alpine",
        source_filename="main.js",
        run_command=["node", "main.js"],
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
    ),
}


def get_language(key: str) -> LanguageConfig:
    normalized = (key or "").strip().lower()
    aliases = {"c++": "cpp", "js": "javascript", "node": "javascript", "py": "python", "golang": "go"}
    normalized = aliases.get(normalized, normalized)
    if normalized not in LANGUAGES:
        raise UnsupportedLanguageError(
            f"Unsupported language '{key}'. Supported: {', '.join(sorted(LANGUAGES))}"
        )
    return LANGUAGES[normalized]


def supported_languages() -> List[LanguageConfig]:
    return list(LANGUAGES.values())
