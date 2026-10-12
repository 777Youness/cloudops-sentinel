# CloudOps Sentinel

Evidence-based incident investigation for AWS workloads.

Sentinel collects operational telemetry, detects incidents with deterministic rules, and
(from Day 3) asks an LLM to write an investigation in which every hypothesis must cite facts
the code collected. Severity is rule-based. Humans decide on remediation.

> **Status: V1 in progress — milestone 2a (all detection rules).** Only simulated data
> exists so far. AWS mode, the incident lifecycle, the investigation engine and most
> screens are not built yet. See [docs/architecture.md](docs/architecture.md) for the milestone plan.

## What works today

- Eight simulated scenarios (`backend/scenarios/`) replayed relative to "now": one per
  rule, a healthy instance, and errors on too little traffic (which must not alert).
- All V1 rules (R-CPU-SAT, R-CPU-CREDIT, R-MEM, R-STATUS, R-5XX, R-LAT, C-USER-IMPACT),
  severity from one rule matrix, and facts that also record what was normal and what
  could not be checked. See [docs/detection-rules.md](docs/detection-rules.md).
- API: `GET /api/v1/health`, `GET /api/v1/system`, `POST /api/v1/sync`, `GET /api/v1/incidents`.
- Console: Incidents page (loading, empty, never-synced and unreachable states) and a
  minimal System page, with a persistent simulated-data strip.

## Run locally

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), Node.js 22.

```bash
# terminal 1 — backend on 127.0.0.1:8000
cd backend
uv sync
uv run uvicorn sentinel.main:app --reload --host 127.0.0.1 --port 8000

# terminal 2 — console on http://127.0.0.1:5173 (proxies /api to the backend)
cd frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173, click **Sync now**: six incidents appear.
API docs: http://127.0.0.1:8000/docs

## Checks

```bash
cd backend  && uv run ruff check . && uv run ruff format --check . && uv run pytest -q
cd frontend && npm run gen:api && npm run typecheck && npm run lint && npm test -- --run && npm run build
```

## Repository

```
backend/    FastAPI app, domain models, simulator, detection engine, tests
frontend/   React + TypeScript console
docs/       architecture, domain model, API, rules, design system, ADRs, learning log
CLAUDE.md   rules for AI-assisted development in this repository
```

## Design decisions

See [docs/adr](docs/adr). Key ones: Sentinel runs locally for V1 (0001), a pure detection
core with enforced import rules (0002), only the sync collects data (0003), rule-based
severity (0004), generated API types (0010).

## Acknowledgements

The principle "the deterministic tool detects, the AI interprets" was influenced by
[TerraGuard-AI](https://github.com/vatul16/TerraGuard-AI). CloudOps Sentinel has its own
architecture, code and interface.
