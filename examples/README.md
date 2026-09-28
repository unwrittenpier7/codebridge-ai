# Example programs

Each example is a standalone program that reads stdin and writes stdout, which is
exactly the contract CodeBridge AI verifies. Paste a `source` file into the
workspace, pick the suggested target language, then migrate, generate tests and
verify.

| Example | Suggested migration | Input | Expected stdout |
| --- | --- | --- | --- |
| `addition.java` | Java → Python | `5\n10\n` | `15` |
| `factorial.cpp` | C++ → Java | `5\n` | `120` |
| `fibonacci_prime.py` | Python → JavaScript | `7\n` | `13\nprime` |
| `array_ops.py` | Python → Go | `hello\n3 1 2\n` | `olleh\n6\n3\n1 2 3` |
| `string_reverse.js` | JavaScript → C++ | `codebridge\n` | `egdirbedoc` |

`migrated/` contains reference migrations produced by the pipeline; they are
useful for trying verification without spending AI calls (paste one into the
"migrated code" editor and click *Run verification*).
