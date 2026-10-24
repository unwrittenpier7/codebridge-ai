"""Static analysis of submitted source code.

Two strategies are used, best-first:

1. Python sources are parsed with the standard library `ast` module, which gives
   exact function signatures, classes, imports and control-flow counts.
2. Everything else is parsed with Tree-sitter when a grammar is available; if the
   grammar cannot be loaded, a conservative regex scan is used so that analysis
   never blocks a migration.
"""
from __future__ import annotations

import ast
import re
from typing import Any, Dict, List, Optional

from app.core.languages import get_language
from app.core.logging_config import get_logger

logger = get_logger(__name__)

TREE_SITTER_LANGUAGE_NAMES = {
    "python": "python",
    "javascript": "javascript",
    "java": "java",
    "cpp": "cpp",
    "c": "c",
    "go": "go",
}

CONTROL_FLOW_NODE_TYPES = {
    "if_statement",
    "for_statement",
    "while_statement",
    "do_statement",
    "switch_statement",
    "try_statement",
    "for_in_statement",
    "for_range_clause",
    "range_clause",
    "enhanced_for_statement",
}

FUNCTION_NODE_TYPES = {
    "function_definition",
    "function_declaration",
    "method_declaration",
    "method_definition",
    "func_literal",
}

CLASS_NODE_TYPES = {"class_definition", "class_declaration", "class_specifier", "type_declaration"}

IMPORT_NODE_TYPES = {
    "import_statement",
    "import_from_statement",
    "import_declaration",
    "import_spec",
    "preproc_include",
}


def _load_tree_sitter_parser(language_key: str):
    name = TREE_SITTER_LANGUAGE_NAMES.get(language_key)
    if not name:
        return None
    try:  # pragma: no cover - depends on optional native wheels
        from tree_sitter_languages import get_parser

        return get_parser(name)
    except Exception as exc:  # pragma: no cover
        logger.debug("Tree-sitter unavailable for %s: %s", language_key, exc)
        return None


class CodeAnalysisService:
    """Extracts structural information used to guide migration prompts."""

    def analyze(self, code: str, language_key: str) -> Dict[str, Any]:
        language = get_language(language_key)
        code = code or ""
        base: Dict[str, Any] = {
            "language": language.key,
            "line_count": len(code.splitlines()),
            "character_count": len(code),
            "functions": [],
            "classes": [],
            "variables": [],
            "imports": [],
            "control_flow": {},
            "reads_stdin": self._reads_stdin(code, language.key),
            "semantic_signals": self._semantic_signals(code, language.key),
            "analyzer": "none",
            # Static analysis never proves behavioral equivalence; it only lists
            # constructs that deserve attention in the migration prompt.
            "semantic_equivalence_proven": False,
        }

        if language.key == "python":
            python_analysis = self._analyze_python(code)
            if python_analysis is not None:
                base.update(python_analysis)
                base["analyzer"] = "python-ast"
                base["analysis_confidence"] = "exact"
                return base

        tree_sitter_analysis = self._analyze_with_tree_sitter(code, language.key)
        if tree_sitter_analysis is not None:
            base.update(tree_sitter_analysis)
            base["analyzer"] = "tree-sitter"
            # Tree-sitter parses exactly, but an unparsed region downgrades this.
            base["analysis_confidence"] = (
                "approximate" if base.get("has_parse_errors") else "exact"
            )
            return base

        base.update(self._analyze_with_regex(code, language.key))
        base["analyzer"] = "regex-fallback"
        # Regex heuristics can miss or mis-attribute constructs; never present
        # this as a proof of anything.
        base["analysis_confidence"] = "heuristic"
        return base

    # -- python ------------------------------------------------------------
    def _analyze_python(self, code: str) -> Optional[Dict[str, Any]]:
        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            return {
                "syntax_error": f"line {exc.lineno}: {exc.msg}",
                "functions": [],
                "classes": [],
                "variables": [],
                "imports": [],
                "control_flow": {},
            }

        functions: List[Dict[str, Any]] = []
        classes: List[Dict[str, Any]] = []
        imports: List[str] = []
        variables: List[str] = []
        control_flow = {"if": 0, "for": 0, "while": 0, "try": 0, "with": 0, "match": 0}

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(
                    {
                        "name": node.name,
                        "signature": f"{node.name}({', '.join(a.arg for a in node.args.args)})",
                        "parameters": [a.arg for a in node.args.args],
                        "line": node.lineno,
                        "returns": ast.unparse(node.returns) if node.returns else None,
                    }
                )
            elif isinstance(node, ast.ClassDef):
                classes.append(
                    {
                        "name": node.name,
                        "line": node.lineno,
                        "methods": [
                            item.name
                            for item in node.body
                            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                        ],
                    }
                )
            elif isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imports.extend(f"{module}.{alias.name}" for alias in node.names)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        variables.append(target.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                variables.append(node.target.id)
            elif isinstance(node, ast.If):
                control_flow["if"] += 1
            elif isinstance(node, (ast.For, ast.AsyncFor)):
                control_flow["for"] += 1
            elif isinstance(node, ast.While):
                control_flow["while"] += 1
            elif isinstance(node, ast.Try):
                control_flow["try"] += 1
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                control_flow["with"] += 1
            elif hasattr(ast, "Match") and isinstance(node, getattr(ast, "Match")):
                control_flow["match"] += 1

        return {
            "functions": functions,
            "classes": classes,
            "imports": sorted(set(imports)),
            "variables": sorted(set(variables))[:50],
            "control_flow": {k: v for k, v in control_flow.items() if v},
        }

    # -- tree-sitter --------------------------------------------------------
    def _analyze_with_tree_sitter(self, code: str, language_key: str) -> Optional[Dict[str, Any]]:
        parser = _load_tree_sitter_parser(language_key)
        if parser is None:
            return None

        try:  # pragma: no cover - native parsing
            tree = parser.parse(code.encode("utf-8"))
        except Exception as exc:  # pragma: no cover
            logger.debug("Tree-sitter parse failed: %s", exc)
            return None

        functions: List[Dict[str, Any]] = []
        classes: List[Dict[str, Any]] = []
        imports: List[str] = []
        control_flow: Dict[str, int] = {}
        source_bytes = code.encode("utf-8")

        def text(node) -> str:
            return source_bytes[node.start_byte : node.end_byte].decode("utf-8", "replace")

        def named_child_text(node, field: str) -> Optional[str]:
            child = node.child_by_field_name(field)
            return text(child) if child is not None else None

        def walk(node):
            node_type = node.type
            if node_type in FUNCTION_NODE_TYPES:
                name = named_child_text(node, "name") or "<anonymous>"
                params = named_child_text(node, "parameters") or "()"
                functions.append(
                    {
                        "name": name,
                        "signature": f"{name}{params}".replace("\n", " ")[:200],
                        "line": node.start_point[0] + 1,
                    }
                )
            elif node_type in CLASS_NODE_TYPES:
                name = named_child_text(node, "name") or "<anonymous>"
                classes.append({"name": name, "line": node.start_point[0] + 1})
            elif node_type in IMPORT_NODE_TYPES:
                imports.append(text(node).strip().replace("\n", " ")[:120])
            elif node_type in CONTROL_FLOW_NODE_TYPES:
                key = node_type.replace("_statement", "").replace("_clause", "")
                control_flow[key] = control_flow.get(key, 0) + 1
            for child in node.children:
                walk(child)

        walk(tree.root_node)
        return {
            "functions": functions,
            "classes": classes,
            "imports": sorted(set(imports)),
            "variables": [],
            "control_flow": control_flow,
            "has_parse_errors": tree.root_node.has_error,
        }

    # -- regex fallback -----------------------------------------------------
    def _analyze_with_regex(self, code: str, language_key: str) -> Dict[str, Any]:
        patterns = {
            "java": r"(?:public|private|protected|static|\s)+[\w<>\[\]]+\s+(\w+)\s*\(([^)]*)\)\s*\{",
            "cpp": r"[\w:<>\*&\s]+\s+(\w+)\s*\(([^)]*)\)\s*\{",
            "c": r"[\w\*&\s]+\s+(\w+)\s*\(([^)]*)\)\s*\{",
            "go": r"func\s+(\w+)\s*\(([^)]*)\)",
            "javascript": r"function\s+(\w+)\s*\(([^)]*)\)",
            "python": r"def\s+(\w+)\s*\(([^)]*)\)",
        }
        class_patterns = {
            "java": r"class\s+(\w+)",
            "cpp": r"(?:class|struct)\s+(\w+)",
            "c": r"(?:struct|union|enum)\s+(\w+)",
            "go": r"type\s+(\w+)\s+struct",
            "javascript": r"class\s+(\w+)",
            "python": r"class\s+(\w+)",
        }
        import_patterns = {
            "java": r"import\s+([\w\.\*]+);",
            "cpp": r"#include\s*[<\"]([^>\"]+)[>\"]",
            "c": r"#include\s*[<\"]([^>\"]+)[>\"]",
            "go": r'import\s+(?:\(([^)]*)\)|"([^"]+)")',
            "javascript": r'(?:import\s+.*?from\s+[\'"]([^\'"]+)[\'"]|require\([\'"]([^\'"]+)[\'"]\))',
            "python": r"^\s*(?:import|from)\s+([\w\.]+)",
        }

        functions = [
            {"name": m.group(1), "signature": f"{m.group(1)}({m.group(2).strip()})"}
            for m in re.finditer(patterns.get(language_key, patterns["python"]), code, re.MULTILINE)
            if m.group(1) not in {"if", "for", "while", "switch", "catch", "return"}
        ]
        classes = [
            {"name": m.group(1)}
            for m in re.finditer(class_patterns.get(language_key, r"class\s+(\w+)"), code)
        ]
        imports = [
            next(g for g in m.groups() if g)
            for m in re.finditer(
                import_patterns.get(language_key, r"^\s*import\s+(\S+)"), code, re.MULTILINE
            )
            if any(m.groups())
        ]
        control_flow = {
            keyword: len(re.findall(rf"\b{keyword}\b", code))
            for keyword in ("if", "for", "while", "switch", "try")
        }
        return {
            "functions": functions,
            "classes": classes,
            "imports": sorted({i.strip() for i in imports}),
            "variables": [],
            "control_flow": {k: v for k, v in control_flow.items() if v},
        }

    # -- helpers ------------------------------------------------------------
    def _semantic_signals(self, code: str, language_key: str) -> Dict[str, int]:
        """Count language-specific constructs whose semantics differ across languages.

        These counts are best-effort heuristics: they are meant to tell the
        migration prompt which pitfalls are plausible, never to prove that the
        migrated program behaves the same.
        """
        patterns = {
            "c": {
                "pointers": r"\b\w+\s*\*+\s*\w+|\*\s*\w+\s*=|->",
                "memory": r"\b(malloc|calloc|realloc|free|memcpy|memset|strcpy|strdup)\b",
                "arrays": r"\[\s*[^\]]*\]",
                "integer_types": r"\b(int|long|short|unsigned|char|size_t|int8_t|int16_t|int32_t|int64_t)\b",
                "uninitialized_risk": r"\b\w+\s+\w+\s*;",
                "unsafe_strings": r"\b(strcpy|strcat|sprintf|gets)\b",
            },
            "cpp": {
                "pointers": r"\b\w+\s*\*+\s*\w+|->|\bnew\b|\bdelete\b",
                "memory": r"\b(new|delete|malloc|free|unique_ptr|shared_ptr)\b",
                "arrays": r"\[\s*[^\]]*\]",
                "integer_types": r"\b(int|long|short|unsigned|size_t|auto)\b",
                "exceptions": r"\b(try|catch|throw)\b",
            },
            "java": {
                "integer_types": r"\b(int|long|short|byte|char)\b",
                "integer_overflow": r"\b(Integer\.(MAX_VALUE|MIN_VALUE)|Long\.(MAX_VALUE|MIN_VALUE))\b",
                "null_handling": r"\bnull\b|Objects\.requireNonNull",
                "exceptions": r"\b(try|catch|finally|throw|throws)\b",
                "collections": r"\b(ArrayList|HashMap|HashSet|List|Map|Set)\b",
                "strings": r"\b(String|StringBuilder|StringBuffer|charAt|substring)\b",
            },
            "python": {
                "exceptions": r"\b(try|except|finally|raise)\b",
                "collections": r"\b(list|dict|set|tuple|deque|defaultdict)\b",
                "strings": r"\b(str|encode|decode|format|f\")\b",
                "numeric": r"\b(int|float|round|Decimal)\b",
                "null_handling": r"\bNone\b",
            },
            "javascript": {
                "numeric": r"\b(parseInt|parseFloat|Number|Math\.)\b",
                "null_handling": r"\b(null|undefined)\b",
                "exceptions": r"\b(try|catch|finally|throw)\b",
                "collections": r"\b(Array|Map|Set|Object)\b",
                "strings": r"\.(slice|substring|replace|split|toUpperCase)\(",
            },
            "go": {
                "pointers": r"\*|\&",
                "errors": r"\berror\b|errors\.New|fmt\.Errorf",
                "integer_types": r"\b(int|int32|int64|uint|byte|rune)\b",
                "collections": r"\b(map|slice|\[\])\b",
                "strings": r"\b(strings\.|fmt\.Sprintf)\b",
                "concurrency": r"\b(go\s+\w+|chan\b|sync\.)\b",
            },
        }
        return {
            name: len(re.findall(pattern, code))
            for name, pattern in patterns.get(language_key, {}).items()
            if re.search(pattern, code)
        }

    def _reads_stdin(self, code: str, language_key: str) -> bool:
        markers = {
            "python": ["input(", "sys.stdin", "readline"],
            "javascript": ["process.stdin", "readline", "require('fs').readFileSync(0"],
            "java": ["Scanner", "BufferedReader", "System.in"],
            "cpp": ["cin", "scanf", "getline", "fgets"],
            "c": ["scanf", "fgets", "getchar", "getline"],
            "go": ["bufio.NewReader", "fmt.Scan", "os.Stdin"],
        }
        return any(marker in code for marker in markers.get(language_key, []))


code_analysis_service = CodeAnalysisService()
