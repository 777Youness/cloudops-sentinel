# CloudOps Sentinel

Evidence-based incident investigation for AWS workloads.

Sentinel collects operational telemetry, detects incidents with deterministic rules, and
asks an LLM (on demand) to write an investigation in which every hypothesis must cite facts
the code collected. Severity is rule-based. Humans decide on remediation.

> **Status: V1 in progress — Day 5b (real-AWS incident demo).** AWS mode ran against a
> real deployment (reported by the owner): 19 resources applied in eu-west-3, the read-only
> role assumed, all three collectors succeeded with 7/7 signals, no incident on a healthy
> workload, then everything destroyed. The demo fault route and traffic script
> ([ADR 0019](docs/adr/0019-dev-fault-injection-for-the-5xx-demo.md)) are tested locally,
> **not yet on AWS**. The EC2 safety timer is **not yet validated**. The Resources pages are
> not built yet. See [docs/architecture.md](docs/architecture.md).

## What works today

- Ten simulated scenarios (`backend/scenarios/`) replayed relative to "now": one per
  rule, a healthy instance, errors on too little traffic (which must not alert), and two
  multi-phase scenarios that advance one step per sync (`escalation`, `recovery`).
- Incident lifecycle: incidents are updated when new rules or deployments appear, keep
  their peak severity, resolve after 10 clean minutes, and a later breach opens a new one.
- SQLite persistence: history survives a restart (`backend/data/sentinel-<mode>.db`;
  delete the file to start over).
- All V1 rules (R-CPU-SAT, R-CPU-CREDIT, R-MEM, R-STATUS, R-5XX, R-LAT, C-USER-IMPACT),
  severity from one rule matrix, and facts that also record what was normal and what
  could not be checked. See [docs/detection-rules.md](docs/detection-rules.md).
- API: `GET /api/v1/health`, `/system`, `/overview`, `/incidents`, `/incidents/{id}`,
  `/incidents/{id}/investigation`; `POST /api/v1/sync`, `/incidents/{id}/investigation`.
- Investigation: on demand, from the incident's stored facts only. Every hypothesis must
  cite existing fact ids; invalid replies are rejected (one retry), never repaired; the
  incident is never changed; outdated runs are flagged. Default provider: a deterministic
  mock (no key, no network). Optional: any OpenAI-compatible endpoint, Ollama recommended
  (see [ADR 0015](docs/adr/0015-investigation-provider.md) and `backend/.env.example`).
- Console:
  - **Overview**: open incidents by severity, the most important ones, data trust (origin,
    data age, sources, what the last sync changed) and the health of every resource, with
    missing signals named.
  - **Incident workspace**: signal charts on one time axis (thresholds, breach windows,
    deployment markers, visible gaps), a timeline linked to facts, and the stored facts
    grouped as observed, checked and normal, and data gaps.
  - Incidents and System pages; a persistent simulated-data strip; a stale-data notice.
- **AWS mode** (`SENTINEL_MODE=aws`, [ADR 0018](docs/adr/0018-aws-telemetry-collector.md)),
  tested with mocked AWS only: the sync discovers instances tagged
  `cloudops-sentinel:monitor=true`, reads CPU, CPU credits, status checks and memory with one
  `GetMetricData` call, and derives request rate, 5xx rate and p95 latency from the workload
  access log with two bounded Logs Insights queries, through a read-only role. Failed or
  partial collection is reported per collector (sync `failed` or `partial`), never treated
  as healthy data. Same detection, lifecycle and storage as simulated mode.

## AWS mode (requires the deployed workload and the read-only role)

```bash
cd backend
SENTINEL_MODE=aws SENTINEL_AWS_PROFILE=sentinel uv run uvicorn sentinel.main:app --host 127.0.0.1 --port 8000
```

Profiles, the role and the one-time setup are in [infra/README.md](infra/README.md).
Credentials always come from the profile (the `sentinel` profile assumes the read-only
role); nothing is stored in `.env`.

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

Open http://127.0.0.1:5173, click **Sync now**: eight incidents appear. Click it again:
one incident is updated (escalation) and one is resolved (recovery, under **Resolved**).
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
severity (0004), generated API types (0010), SQLite document store (0013), investigation
provider (0015), AWS collector (0018), dev-only fault injection for the demo (0019).

## Acknowledgements

The principle "the deterministic tool detects, the AI interprets" was influenced by
[TerraGuard-AI](https://github.com/vatul16/TerraGuard-AI). CloudOps Sentinel has its own
architecture, code and interface.
