# CodeBridge AI

**AI-assisted multi-language source code migration with behavioral verification.**

Most "AI code translators" stop at producing plausible code. CodeBridge AI goes further:
it *runs* the original and the migrated program inside isolated Docker containers with the
same stdin, compares their real stdout, and only then tells you whether the migration is
behaviorally equivalent. Compilation success is never treated as correctness.

---

## Table of contents

- [Features](#features)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Installation](#installation)
- [Environment configuration](#environment-configuration)
- [Running the backend](#running-the-backend)
- [Running the frontend](#running-the-frontend)
- [Docker setup](#docker-setup)
- [Database setup](#database-setup)
- [API reference](#api-reference)
- [Example migration](#example-migration)
- [Verification workflow](#verification-workflow)
- [Testing](#testing)
- [Security considerations](#security-considerations)

---

## Features

- **Real AI migration** between Python, Java, C++, JavaScript and Go (OpenAI or Gemini,
  selected with `AI_PROVIDER`). No mocked or canned migration output anywhere in the system.
- **Static analysis** of the source program (functions, classes, variables, imports,
  control flow, signatures, stdin usage) via Python `ast` and Tree-sitter, fed to the model
  as migration context.
- **AI test generation** that proposes stdin payloads covering normal, boundary, zero,
  negative, empty, large and edge cases. Expected outputs are **not** taken from the model:
  they are produced by executing the original program.
- **Sandboxed execution** of every program in a throwaway Docker container with CPU, memory,
  PID, output-size and wall-clock limits, no network, dropped capabilities and automatic cleanup.
- **Behavioral comparison** of actual stdout, tolerant of line-ending and trailing-whitespace
  noise and float formatting, strict about anything that changes observable behavior.
- **Bounded AI correction loop** (max 3 attempts, configurable): failed tests, both programs'
  outputs and compiler/runtime errors are sent back to the model, the corrected program is
  re-verified, and every attempt is stored with before/after match percentages.
- **Persistent history**: users, projects, migrations, test cases, verification results,
  per-test results and correction attempts.
- **JWT authentication** with bcrypt password hashing and per-user data isolation.
- **Dark developer-tool UI**: sidebar navigation, dual Monaco editors, status badges,
  progress bars, per-test diff view and correction history.

## Architecture

```mermaid
flowchart TD
    subgraph Client["React + Vite frontend"]
        UI["Workspace<br/>dual Monaco editors"]
        RES["Verification dashboard"]
    end

    subgraph API["FastAPI backend"]
        AUTH["Auth (JWT + bcrypt)"]
        MIG["Migration service"]
        ANA["Code analysis service<br/>ast / tree-sitter"]
        GEN["Test generation service"]
        VER["Verification service"]
        FIX["Correction loop (max 3)"]
    end

    subgraph AIL["AI layer"]
        PROV["LLMProvider abstraction"]
        OAI["OpenAI"]
        GEM["Gemini"]
    end

    subgraph SANDBOX["Execution sandbox"]
        RUN["Custom test runner"]
        DOCK["Docker executor<br/>no network · cpu/mem/pid limits · timeout"]
        CMP["Output comparator"]
    end

    DB[("PostgreSQL / SQLite")]

    UI -->|REST + JWT| API
    RES --> API
    MIG --> ANA
    MIG --> PROV
    GEN --> PROV
    FIX --> PROV
    PROV --> OAI
    PROV --> GEM
    GEN --> DOCK
    VER --> RUN
    FIX --> VER
    RUN --> DOCK
    RUN --> CMP
    API --> DB
```

Key boundary: **submitted code never executes in the FastAPI process**. The backend only
talks to the Docker daemon; the frontend has no Docker access at all.

Layout:

```
backend/
  app/api/          REST routes (auth, migrations, verification)
  app/services/     ai_providers, ai_service, code_analysis, docker_executor,
                    output_comparator, test_runner, migration, test_generation, verification
  app/models/       SQLAlchemy entities
  app/schemas/      Pydantic request/response models
  app/core/         config, security, languages, errors, logging
  tests/            pytest suite (unit + real-Docker integration)
frontend/
  src/pages/        Landing, Login, Register, Dashboard, Workspace, MigrationDetails,
                    VerificationResults, History
  src/components/   editors, status badges, result tables, layout
examples/           sample programs and reference migrations
```

## Tech stack

| Layer | Technology |
| --- | --- |
| Frontend | React 18, Vite, JavaScript, Tailwind CSS, Monaco Editor, Axios, React Router DOM |
| Backend | Python 3.10+, FastAPI, Pydantic v2, SQLAlchemy 2, python-jose (JWT), passlib/bcrypt |
| AI | OpenAI and Gemini behind an `LLMProvider` abstraction |
| Execution | Docker SDK for Python; per-language official images |
| Database | PostgreSQL (SQLite by default for local development) |
| Tests | pytest, Vitest + React Testing Library |

## Installation

```bash
git clone <this-repo>
cd codebridge-ai
cp .env.example .env    # then edit .env

# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install
```

Requirements: Python 3.10+, Node 18+, a running Docker daemon, and an API key for the
chosen AI provider.

## Environment configuration

All configuration comes from environment variables (see `.env.example`); **no API key is
ever hard-coded and `.env` is git-ignored**. The most important settings:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./codebridge.db` | Set to a `postgresql+psycopg2://…` URL in production |
| `JWT_SECRET` | `change-me-in-production` | Signing key for access tokens |
| `AI_PROVIDER` | `openai` | `openai` or `gemini` |
| `OPENAI_API_KEY` / `GEMINI_API_KEY` | empty | Key for the selected provider |
| `MAX_EXECUTION_TIME` | `10` | Per-run wall-clock limit (seconds) |
| `MAX_MEMORY_MB` | `256` | Container memory limit |
| `MAX_CODE_SIZE_KB` | `500` | Largest accepted program |
| `MAX_OUTPUT_CHARS` | `20000` | Captured stdout/stderr cap |
| `MAX_PROCESSES` | `128` | Container PID limit |
| `MAX_CORRECTION_ATTEMPTS` | `3` | Hard ceiling on the AI fix loop |
| `MAX_GENERATED_TEST_CASES` | `10` | Test generation cap |

If no API key is configured the app still runs: AI endpoints return
`503 AI provider 'openai' is not configured`, and the header health indicator shows the
missing dependency. Nothing is faked.

## Running the backend

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

- Health: <http://localhost:8000/api/health>
- Interactive docs: <http://localhost:8000/docs>

## Running the frontend

```bash
cd frontend
npm run dev        # http://localhost:5173, proxies /api to localhost:8000
```

## Docker setup

Two independent uses of Docker:

1. **Code execution (required).** The backend pulls and runs these images on demand:
   `python:3.11-alpine`, `node:20-alpine`, `eclipse-temurin:21-jdk-alpine`, `gcc:13`,
   `golang:1.22-alpine`. Pre-pull them for a faster first run:

   ```bash
   docker pull python:3.11-alpine && docker pull node:20-alpine \
     && docker pull eclipse-temurin:21-jdk-alpine && docker pull gcc:13 \
     && docker pull golang:1.22-alpine
   ```

2. **Running the app itself (optional).**

   ```bash
   OPENAI_API_KEY=sk-... docker compose up --build
   # frontend http://localhost:8080, backend http://localhost:8000, PostgreSQL :5432
   ```

   The backend container mounts `/var/run/docker.sock` so it can launch *sibling* containers
   for execution. That socket is a privileged resource: never expose it beyond the backend.

## Database setup

SQLite is used automatically when `DATABASE_URL` is unset — nothing to install. For
PostgreSQL:

```bash
createdb codebridge
export DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/codebridge
```

Tables are created on startup. Entities: `users`, `projects`, `migrations`, `test_cases`,
`verification_results`, `test_results`, `correction_attempts`.

## API reference

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/health` | Service status, AI configuration and Docker availability |
| `GET` | `/api/languages` | Supported languages and their editor ids |
| `POST` | `/api/auth/register` | Create an account, returns a JWT |
| `POST` | `/api/auth/login` | Authenticate, returns a JWT |
| `POST` | `/api/auth/logout` | Stateless logout |
| `GET` | `/api/auth/me` | Current user |
| `POST` | `/api/migrations` | Create a migration |
| `GET` | `/api/migrations` | List the current user's migrations |
| `GET` | `/api/migrations/stats` | Dashboard statistics |
| `GET` | `/api/migrations/{id}` | Full migration with tests, results and corrections |
| `PATCH` | `/api/migrations/{id}` | Update title, code or languages |
| `DELETE` | `/api/migrations/{id}` | Delete a migration |
| `POST` | `/api/migrations/{id}/analyze` | Static analysis of the source program |
| `POST` | `/api/migrations/{id}/migrate` | AI migration |
| `POST` | `/api/migrations/{id}/generate-tests` | AI test inputs + real reference outputs |
| `POST` | `/api/migrations/{id}/validate` | Compile/syntax-check the migrated code |
| `POST` | `/api/migrations/{id}/verify` | Execute both programs and compare behavior |
| `POST` | `/api/migrations/{id}/fix` | Bounded AI correction loop with re-verification |
| `GET` | `/api/migrations/{id}/results` | All verification runs |

All `/api/migrations/*` routes require `Authorization: Bearer <token>`.

## Example migration

Source (Java, `examples/addition.java`):

```java
import java.util.Scanner;

public class Main {
    static int add(int a, int b) { return a + b; }

    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        System.out.println(add(scanner.nextInt(), scanner.nextInt()));
    }
}
```

Migrated to Python by the AI:

```python
import sys


def add(a, b):
    return a + b


def main():
    data = sys.stdin.read().split()
    print(add(int(data[0]), int(data[1])))


main()
```

Verification output for the generated inputs:

| Test | Input | Original stdout | Migrated stdout | Status |
| --- | --- | --- | --- | --- |
| 1 | `5 10` | `15` | `15` | PASS |
| 2 | `0 0` | `0` | `0` | PASS |
| 3 | `-7 7` | `0` | `0` | PASS |

Overall: `PASS`, behavioral match 100%.

## Verification workflow

1. Write or load the source program and pick source/target languages.
2. **Migrate** — static analysis runs, then the LLM produces the migrated program.
3. **Generate tests** — the LLM proposes stdin payloads; each is piped into the *original*
   program in Docker and the real stdout is stored as the expected output.
4. **Run verification** — the migrated program is compiled (if applicable) and executed
   against every input in its own container; stdout is captured and compared.
5. Results are classified:
   - `PASS` — every test matched
   - `PARTIAL` — some tests matched
   - `FAIL` — no test matched, or the program failed to compile/run
   - `ERROR` — the sandbox itself could not complete the run
6. **Fix with AI** — failed inputs with both outputs, exit codes and error text are sent
   back to the model; the corrected program is re-verified. At most
   `MAX_CORRECTION_ATTEMPTS` (default 3) iterations, each stored in the correction history.

## Testing

```bash
# Backend: unit tests only (no Docker required)
cd backend && .venv/bin/python -m pytest -m "not docker"

# Backend: full suite, including real container execution in all five languages
.venv/bin/python -m pytest

# Frontend
cd frontend && npm run lint && npm run test && npm run build
```

The Docker-marked tests assert real behavior: each language compiles and runs, runtime
errors surface exit codes and stderr, infinite loops time out, the sandbox has no network,
oversized sources are rejected, output is truncated, a behaviorally-wrong-but-compiling
program is reported as not equivalent, and the correction loop respects its maximum.

## Security considerations

- Submitted code runs **only** inside short-lived Docker containers — never in the API process.
- Containers run with `network_disabled`/`network_mode=none`, memory and swap limits, a
  1-CPU quota, a PID limit, `cap_drop: ALL`, `no-new-privileges`, a temporary working
  directory and guaranteed removal, plus a hard wall-clock timeout.
- Source size and captured output size are bounded, so a program cannot exhaust disk or memory.
- The Docker socket is reachable by the backend only; it is never exposed to the frontend.
- Passwords are bcrypt-hashed; API access uses signed, expiring JWTs; every migration query
  is scoped to the authenticated user.
- API keys are read from environment variables only, and `.env` is git-ignored.
- Compilation success is explicitly *not* treated as behavioral equivalence, and AI-claimed
  expected outputs are never trusted — only real execution of the original program is.
