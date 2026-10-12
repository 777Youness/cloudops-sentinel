# Learning log

One entry per milestone, written by me after running and breaking it myself.
Test: could I explain this without notes?

## Day 1 — thin vertical slice

- Date:
- What I ran:
- What I broke, and what I saw:
  1. Backend stopped →
  2. Peak 85% →
  3. 6-minute breach →
  4. Renamed a contract field →
  5. `import boto3` in detection →
  6. Two concurrent syncs →
- The path of one sync, from YAML to a table row, in my own words:
- Why `detection/` has no I/O:
- What the OpenAPI → TypeScript step guarantees:
- What `data_origin` is for:
- What I still don't fully understand:

Status: break exercises deferred (2026-10-12) to prioritise reaching V1; to do later.

## Concepts to revisit

Maintained as the build goes. Each line: the concept, where it lives, why it matters.

**Day 1**
- Dependency inversion with `typing.Protocol` (`collectors/base.py`, `store/base.py`):
  services depend on an interface, so the simulator and AWS collector are swappable.
- Injectable clock (`clock.py`): tests pin time; detection takes `now` as a parameter.
- HTTP status vs domain status (`SyncRun.status`): a failed AWS sync is a successful API call.
- Contract-first types (OpenAPI → `schema.d.ts`, CI diff check): backend and frontend
  cannot drift silently.
- Non-blocking lock for the sync (`threading.Lock().acquire(blocking=False)` → 409).

**Milestone 2a**
- Trailing-run detection (`detection/rules.py::trailing_run`): why only the ongoing breach
  counts, and why a gap breaks the run.
- Guards (`insufficient_traffic`): 3 errors out of 10 requests is 30%, but means little.
- Baseline vs absolute thresholds (R-LAT): median, the 10-minute exclusion gap, and how
  the "baseline depends on the breach" circle is broken in three steps.
- Severity tiers and derived rules (`severity.py`, C-USER-IMPACT): severity is a table,
  not scattered `if`s.
- Negative evidence: `within_normal` and `data_gap` facts, and why "unknown" must never
  become 0.
- CloudWatch statistics (Average, Maximum, p95) and burstable-instance CPU credits.
- Line endings in Git (`.gitattributes`, `core.autocrlf`).

**Milestone 2b**
- Incident lifecycle as a state machine (open → updated → resolved; reopen = new incident),
  and why the engine returns new versions instead of mutating (`model_copy`).
- Append-only facts: why a fact id must never change once something can cite it.
- Hysteresis: why resolution needs 10 clean minutes, not one good datapoint (flapping).
- Transactions and atomicity (`BEGIN` / `COMMIT` / `ROLLBACK`): a sync is stored whole or
  not at all; why collection happens outside the transaction.
- SQLite as a document store: JSON `body` column plus indexed columns; `PRAGMA user_version`
  for schema migrations (ADR 0013).
- Thread safety: one connection shared by threads, `check_same_thread=False`, `RLock`
  (re-entrant: the same thread takes it again inside a transaction).
- Idempotency: a stable event id makes "the same event seen twice" a no-op.
- Test doubles vs the real thing: tests use SQLite `:memory:`, not a fake store.

**Milestone 2c**
- Read side vs write side: `services/incidents.py` only reads; `services/sync.py` writes.
  Why routes must not touch the store (and the test that enforces it).
- HTTP 404 with an error envelope vs an empty 200: what each tells the client.
- `json_extract` in SQLite: querying inside a JSON column without a schema migration.
- Staleness: "data as of" = last *successful* sync, not last sync.
- Small multiples and a shared time axis: why not one chart with several y-axes.
- Honest charts: `null` breaks a line, 0 lies; counting missing datapoints (`chartData.ts`).
- Server state vs UI state (TanStack Query): keeping data on screen when a refetch fails.
- Code splitting with a lazy route: the chart library loads only in the workspace.
- Peer dependencies (`react-is`) and how to check whether a mismatch actually matters.

## Milestone 2a — all detection rules

- Date: 2026-10-12
- Built: six more rules plus a derived one, `within_normal` / `data_gap` facts, eight
  scenarios (each with an expected-outcome test).
- To try later: in `backend/scenarios/low_traffic_errors.yaml` raise `request_rate`
  baseline from 2 to 10 and run `uv run pytest tests/test_scenarios.py` — what fails, and why?
- In my own words, why R-LAT needs two passes:

## Milestone 2b — lifecycle and storage

- Date: 2026-10-12
- Built: merge / peak severity / resolution / reopen in the engine, deployment events,
  SQLite store (one file per mode), multi-phase scenarios.
- To try later: start the backend, click Sync now twice, stop it, start it again: the
  incidents are still there (SQLite). Then delete `backend/data/sentinel-local.db` and
  restart: empty history.
- In my own words, why missing data never resolves an incident:

## Milestone 2c — Overview and incident workspace

- Date: 2026-10-12
- Built: `GET /incidents/{id}`, `GET /overview`, resource health, the Overview page, the
  incident workspace with charts, stale-data notice.
- Found in browser review and fixed: overlapping chart labels, a clipped marker, a 5xx
  chart flattened by a 0-100% scale, a gap counter that counted the marker margin, and a
  resolved incident whose chart did not show the recovery (engine fix with a test).
- To try later: open a resolved incident and explain why its chart now ends on the
  recovered values (commit "fix(lifecycle): keep the clean window as evidence").
- In my own words, why the UI never decides whether a value breaches:
