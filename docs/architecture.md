# Architecture

CloudOps Sentinel reads operational telemetry, detects incidents with deterministic rules,
and asks an LLM (on demand) to write an evidence-based investigation. Humans remediate.

## Principle

AWS and Terraform produce facts → Python collects and normalizes them → deterministic rules
detect incidents → the LLM interprets the evidence → the console presents it → humans decide.

## Deployment (V1)

For V1, Sentinel runs locally and monitors a small disposable AWS workload. Deployment of
Sentinel itself is intentionally deferred until the core product is validated (see ADR 0001).

## Three data layers

| Layer | Produced by | Contains | Nature |
|---|---|---|---|
| Observations | `collectors/` | Resources, metric series (later: events, log samples) | Normalized data, no judgement |
| Facts + incidents | `detection/` | Breaches, facts, incident with rule-based severity | Deterministic judgement |
| Investigation | `investigation/` | Hypotheses citing facts, checks, remediation options | Validated interpretation, saved separately from the incident |

## Backend packages and dependency rules

```
collectors ──► domain ◄── detection
                 ▲
investigation ───┘
services  → collectors, detection, investigation, store
            (sync.py writes; incidents.py and system.py read)
api       → services only (routes never touch the store; tested)
```

- `domain/`: pydantic + stdlib only.
- `detection/`: `domain/` + stdlib only. No I/O, no clock (time is passed in).
- boto3 only in `collectors/aws/` (Day 5); sqlite3 only in `store/` (ADR 0013);
  LLM HTTP calls only in `investigation/providers/`; FastAPI only in `api/`.
- `investigation/` (except `providers/`): `domain/` + stdlib only.
- Enforced by `backend/tests/test_architecture.py`.

## Runtime rules

- Only `POST /api/v1/sync` collects telemetry (and, from Day 5, calls AWS).
- Only `POST /api/v1/incidents/{id}/investigation` calls an LLM provider (tested: sync and
  every GET make zero provider calls).
- All GET endpoints read stored data. The UI always shows when data was last synced.
- HTTP status describes the API call; `SyncRun.status` describes the outcome.

## Sync flow

```
POST /api/v1/sync
  1. SyncService acquires its lock (409 SYNC_IN_PROGRESS if already held)
  2. TelemetrySource.collect(now - 3h, now)       → ObservationSnapshot (series + events)
     (outside the transaction: a slow source never blocks readers)
  3. one store transaction:
       detection.engine.evaluate(snapshot, open incidents, now)
                                                  → opened, updated, resolved
       save snapshot, add / update incidents, record SyncRun
  4. return SyncRun (success | failed, per-collector status, opened/updated/resolved)
```

Storage: SQLite, one file per mode (`backend/data/sentinel-<mode>.db`), models stored as
JSON documents (ADR 0013). Under Docker Compose the file is `/data/sentinel-local.db` in the
named volume `sentinel-data`, separate from the host files.

## Docker Compose (local packaging)

```
browser ── 127.0.0.1:8080 ──► frontend (Nginx, uid 101)
                                ├─ /assets, SPA routes ─► static build (index.html fallback)
                                └─ /api/ ──────────────► backend:8000 (Uvicorn, uid 10001)
                                                            └─ /data/sentinel-local.db (volume)
```

Same code and behaviour as a host run. Differences: the backend listens on 0.0.0.0 inside
the Compose network only (not published); `SENTINEL_MODE=local` is fixed, and no AWS
credentials are mounted. Optional LLM settings come from `.env.docker` at container start.

## Investigation flow (Day 3)

```
POST /api/v1/incidents/{id}/investigation
  1. read the stored incident (404 if unknown); 503 LLM_NOT_CONFIGURED if the selected
     provider is incomplete; 409 if this incident is already being investigated
  2. investigation.bundle   incident -> evidence bundle (facts, timeline, identity, and
                            evidence_scope: what each fact kind means, what was not collected)
  3. investigation.prompt   bundle -> prompt (evidence between markers, declared as data;
                            reasoning rules: correlation is not causation, ...)
  4. provider.complete      prompt -> reply text          (mock by default, ADR 0015)
  5. investigation.validator reply -> findings, or a rejection reason (structural only:
       schema, citations, commands, and "high" confidence that joins breaches of different
       rules or rests on data gaps)
       rejected once -> retry with the reason; rejected twice -> status "failed"
  6. store: save the Investigation (own table, schema v2); the incident is never written
GET /api/v1/incidents/{id}/investigation -> latest run, outdated = hash differs
```

Real-provider behaviour is measured by hand with `backend/evals/investigation_reliability.py`
(cases A-E of `backend/tests/investigation_cases.py`, opt-in, at most 10 calls).

## Incident lifecycle

One open incident per resource (fingerprint = resource id). Implemented in
`detection/engine.py`, which returns new incident versions and never mutates its input.

- **Open:** rules trigger and the resource has no open incident: one incident with every
  triggered rule, plus events from the evidence window.
- **Update:** rules trigger and an incident is open: new rules and new events are appended
  as new facts (`F7`, `F8`, …); existing facts never change, because investigations cite
  them by id. Severity can only rise while open. Re-observing the same situation is not an
  update, so the evidence hash stays stable.
- **Resolve:** nothing triggers and every signal-based condition of the incident has been
  clean for ≥ 10 minutes (data present, not breaching, no gap). One `within_normal` fact
  per condition records the clean window. Missing data never resolves an incident.
- **Reopen:** after resolution, a new breach opens a new incident.
- Not handled in V1: a resource that disappears keeps its incident open (documented limitation).

Simulated mode: a scenario can declare `phases`, advanced one per sync, so updates and
resolution can be shown without waiting (`escalation`, `recovery`). Restarting the backend
restarts the phases.

## Milestones

| Day | Milestone | Status |
|---|---|---|
| 1 | Thin slice: scenario → R-CPU-SAT → memory store → API → generated types → Incidents page | Built; automated checks pass; manual break exercises deferred |
| 2a | All V1 rules, `within_normal` / `data_gap` facts, one scenario per rule | Built; automated checks pass |
| 2b | Full lifecycle (merge, peak severity, resolution), SQLite, deployment events | Built; automated checks pass |
| 2c | `GET /incidents/{id}`, `GET /overview`, Overview page, Investigation workspace (no AI) | Built; automated checks pass; reviewed in a browser (simulated mode) |
| 3 | Investigation engine: evidence bundle, provider interface, mock + one real provider, validation | Built; automated checks pass; real-provider runs with GroqCloud `openai/gpt-oss-20b` on the real AWS incident (prompt v1, then v2 with the confidence check), recorded in `docs/examples/` |
| 4 | Terraform: bootstrap + dev env, workload, CloudWatch agent, SSM scripts | 4a prepared: `infra/` structure, local state (ADR 0016), read-only policy and its test. 4b written and checked locally (ADR 0017): VPC, public subnet, t3.micro with the stdlib workload app (`workload/app.py`), CloudWatch agent (one metric), log group, CPU alarm, operator policy, read-only `scripts/cost-check.sh`, guardrail tests; applied by the owner (first 17, later 19 resources with the read-only role; `/health` 200; destroy to an empty state); **safety timer not yet validated**. Next: termination test, then 4c (SSM fault scripts) |
| 5 | AWS mode: Boto3 collectors, Resources pages | 5a built (ADR 0018): `collectors/aws/` (EC2 discovery, `GetMetricData`, Logs Insights), per-collector status and partial syncs, Sentinel read-only role; **validated once on AWS by the owner** (19 resources, 3 collectors ok, 7/7 signals, no incident on a healthy workload, destroyed). 5b built (ADR 0019): dev-only `/fault/500` route and `scripts/demo_traffic.py`; **run once on AWS**: a real high-severity R-5XX incident (peak 21.1%), then destroyed (19 resources, leftover check clean); resolution on AWS not observed. Not built: Resources pages, deployment events, alarm states |
| 6 | Docker Compose, CI hardening, all UI states | Docker Compose built (2026-11-17): `backend` (FastAPI, non-root, read-only) and `frontend` (Nginx: static build + `/api/` proxy) on `127.0.0.1:8080`, SQLite in a named volume, simulated mode only; smoke and persistence test `scripts/docker_smoke.py`. CI hardening not started |
| 7 | Demo, documentation, review, `v0.1.0` | Portfolio README and documentation done (2026-11-17); screenshots and the `v0.1.0` tag pending |

Each milestone stops for review before the next one starts.
