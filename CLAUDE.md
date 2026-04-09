# AICoderBench — CLAUDE.md

Automated evaluation platform for benchmarking LLM coding capabilities on C system programming problems.

## Architecture Overview

```
AICoderBench/
├── backend/          # Python 3.12 + FastAPI + SQLite
├── frontend/         # Next.js 14 + Tailwind CSS (dark theme)
├── problems/         # 10 C programming challenge definitions
├── sandbox/          # Docker-based evaluation scripts (eval.sh)
├── docs/             # Architecture and design docs
├── docker-compose.yml
├── run_single.py     # Single-problem evaluation script
├── run_agent_all.py  # Full benchmark runner across all models/problems
└── run_glm_thinking.py  # GLM extended-thinking mode runner
```

## Development Workflows

### Local Development (no Docker)

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --port 8000 --reload

# Frontend (separate terminal)
cd frontend
npm install
npm run dev        # runs on port 3000
```

### Docker Deployment

```bash
docker-compose up --build
# Backend: http://localhost:8000
# Frontend: http://localhost:3000
```

### Running Evaluations

```bash
# Sync evaluation (blocks until done)
curl -X POST http://localhost:8000/api/rounds/sync \
  -H 'Content-Type: application/json' \
  -d '{"name":"test","problem_ids":["06-memory-pool"],"model_ids":["<model-uuid>"]}'

# From scripts
python run_single.py       # evaluate one problem with all enabled models
python run_agent_all.py    # full benchmark
```

## Backend (`backend/`)

**Stack**: FastAPI, aiosqlite (SQLite), httpx, pydantic v2, Docker SDK

**Entry point**: `app/main.py` — FastAPI app with CORS middleware, calls `db.init_db()` on startup.

**Key modules**:

| Module | Path | Purpose |
|--------|------|---------|
| Config | `app/config.py` | All constants: paths, Docker limits, timeouts, model params |
| Routes | `app/api/routes.py` | All REST endpoints (problems, models, rounds, results) |
| Database | `app/database.py` | SQLite schema, async CRUD, migrations |
| Evaluator | `app/evaluator/engine.py` | `EvalResult` dataclass, `compute_scores()`, `run_eval_in_sandbox()` |
| Providers | `app/providers/model_provider.py` | Model API integrations (GLM, Kimi, MiniMax, OpenRouter) |
| Agent Runner | `app/scheduler/agent_runner.py` | Multi-turn code generation loop |
| Scheduler | `app/scheduler/engine.py` | Benchmark orchestration, dual-queue system |
| Problem Model | `app/models/problem.py` | Problem loading from disk |

**Start script**: `backend/run.sh` (dev server with auto-reload)

### API Endpoints (prefix: `/api`)

```
GET  /health
GET/POST       /problems
GET/PUT/DELETE /problems/{id}
POST           /problems/{id}/test-file

GET/POST       /model-configs
PUT/DELETE     /model-configs/{uuid}
GET            /models                    # enabled models only
GET            /model-stats/{uuid}

POST /rounds                              # async round
POST /rounds/sync                         # blocking round
GET  /rounds, /rounds/{id}

GET  /global-leaderboard
GET  /problem-leaderboard/{id}
GET  /leaderboard/{round_id}
GET  /submissions/{round_id}/{problem_id}/{model_uuid}
```

### Database Schema

SQLite via aiosqlite. Tables: `problems`, `models`, `rounds`, `submissions`.
Database file: `/app/data/aicoderbench.db` (configurable via `DATABASE_URL` env var).

### Evaluation Pipeline

1. **Agent loop** (`agent_runner.py`): model calls `write_file` → `compile` → `run_tests` → iterates on errors → `submit`. Max 50 rounds, 2-hour total timeout.
2. **Sandbox eval** (`evaluator/engine.py` + `sandbox/eval.sh`): Docker container runs:
   - Static analysis: cppcheck, lizard (cyclomatic complexity), cloc
   - Compilation: normal + TSan + ASan variants
   - Functional tests (normal binary)
   - Concurrency check (TSan binary, 60s timeout)
   - Memory safety check (ASan binary, 60s timeout)
3. **Scoring** (`compute_scores()`): 100-point system (see below).

### Scoring Weights

| Dimension | Points | Deduction Rules |
|-----------|--------|-----------------|
| Compile | 10 | Failure → 0 total; 1pt/warning (max 5) |
| Functional tests | 25 | Pass rate × 25 |
| Concurrency safety | 25 | 5pts/TSan issue; non-concurrent problems exempt |
| Memory safety | 15 | 3pts/ASan issue |
| Code quality | 15 | 3pts/cppcheck error, 1pt/warning; cyclomatic > 20 tiered deduction |
| Performance | 10 | Baseline comparison |

**Compile failure sets the entire score to 0.**

### Docker Sandbox Limits

- Image: `aicoderbench-eval`
- Memory: 128MB, CPU: 1 core, Timeout: 120s
- Concurrency: controlled by `SANDBOX_CONCURRENCY` env var (default: 1)

### Model Providers

Supported: GLM (智谱), Kimi (Moonshot), MiniMax, OpenRouter.
- All providers extend `ModelProvider` base class
- Temperature: 0 (deterministic), max tokens: 8192 (generation: up to 65536)
- Code extraction: tool calling (`write_file`) preferred; regex fallback for ````c` blocks
- Rate-limit (429) handling: checkpoint + exponential backoff

### Agent Tools Available to Models

- `write_file(command, path, ...)` — create or edit files (`create` / `str_replace`)
- `read_file(path, ...)` — read file contents (supports line range)
- `list_files()` — list files in working directory
- `compile()` — compile `solution.c`
- `run_tests()` — link `solution.o` + `test_self.c` and run
- `submit()` — signal completion

## Frontend (`frontend/`)

**Stack**: Next.js 14 App Router, React 18, TypeScript 5, Tailwind CSS 3.4

**Important**: Read `node_modules/next/dist/docs/` before writing Next.js code — this version may have breaking API changes from training data. See `frontend/AGENTS.md`.

**Commands**:
```bash
npm run dev      # development (port 3000)
npm run build    # production build
npm run start    # production server (port 3000)
```

### Page Routes

| Route | Page | Purpose |
|-------|------|---------|
| `/` | `app/page.tsx` | Global leaderboard |
| `/problems` | `app/problems/page.tsx` | Problem browser |
| `/problems/[id]` | `app/problems/[id]/page.tsx` | Problem details |
| `/problems/new` | `app/problems/new/page.tsx` | Create problem |
| `/problems/[id]/edit` | `app/problems/[id]/edit/page.tsx` | Edit problem |
| `/models` | `app/models/page.tsx` | Model management |
| `/models/[modelId]` | `app/models/[modelId]/page.tsx` | Model statistics |
| `/rounds` | `app/rounds/page.tsx` | Evaluation history |
| `/rounds/[id]` | `app/rounds/[id]/page.tsx` | Round details + leaderboard |
| `/new-round` | `app/new-round/page.tsx` | Create evaluation round |
| `/submission/[roundId]/[problemId]/[modelId]` | `app/submission/.../page.tsx` | Detailed results |

**Shared components**: `src/components/nav.tsx`, `src/components/model-badge.tsx`

**API client**: `src/lib/api.ts` — unified fetch-based client with TypeScript interfaces for all types. Uses `NEXT_PUBLIC_API_URL` env var.

**Styling conventions**: dark theme (`bg-gray-900`), accent colors `cyan-400` / `purple-500`, max-width containers (`max-w-7xl`), responsive layout.

## Problems (`problems/`)

10 C system programming challenges. Each problem directory contains:

```
problems/{id}-{name}/
├── problem.json    # metadata: scoring weights, compile flags, difficulty
├── problem.md      # full problem description (Chinese)
├── solution.h      # interface/header definitions the model must implement
├── test.c          # test suite
└── test_framework.h
```

**Problem IDs**: `01-rate-limiter` through `10-event-loop`

**C compilation flags**: `-std=c11 -D_DEFAULT_SOURCE -Wall -Wextra -O2 -lpthread`

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | `sqlite:///data/aicoderbench.db` | SQLite path |
| `SANDBOX_CONCURRENCY` | `1` | Parallel sandbox evaluations |
| `MINIMAX_API_KEY` | — | MiniMax API key |
| `GLM_API_KEY` | — | Zhipu (GLM) API key |
| `KIMI_API_KEY` | — | Moonshot (Kimi) API key |
| `NEXT_PUBLIC_API_URL` | — | Frontend → backend URL |

## Key Conventions

### Python (Backend)
- Python 3.12+, async/await throughout (FastAPI + aiosqlite)
- Pydantic v2 for request/response validation
- Dataclasses for internal data structures (`EvalResult`, agent state)
- No explicit linting config — follow existing patterns (no black/isort enforced)
- Logging: `logging.getLogger(__name__)` in each module

### TypeScript (Frontend)
- Next.js App Router (not Pages Router)
- All API calls go through `src/lib/api.ts` — do not use raw fetch elsewhere
- Tailwind for all styling — no CSS modules or styled-components
- ESLint configured via `next/core-web-vitals` + TypeScript rules

### General
- No GitHub Actions CI currently configured
- Tests are manual scripts in `backend/test_*.py` (not pytest)
- Models identified by UUID in the database (not provider name)
- All user-facing text is in Chinese; code/identifiers are in English
