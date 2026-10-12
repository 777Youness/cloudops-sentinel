# Architecture

CloudOps Sentinel reads operational telemetry, detects incidents with deterministic rules,
and (from Day 3) asks an LLM to write an evidence-based investigation. Humans remediate.

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
| Investigation (Day 3) | `investigation/` | Hypotheses citing facts, checks, remediation options | Validated interpretation |

## Backend packages and dependency rules

```
collectors ──► domain ◄── detection
                 ▲
investigation ───┘            (Day 3)
services  → collectors, detection, investigation, store
api       → services only
```

- `domain/`: pydantic + stdlib only.
- `detection/`: `domain/` + stdlib only. No I/O, no clock (time is passed in).
- boto3 only in `collectors/aws/` (Day 5); sqlite3 only in `store/` (Day 2);
  LLM HTTP calls only in `investigation/providers/` (Day 3); FastAPI only in `api/`.
- Enforced by `backend/tests/test_architecture.py`.

## Runtime rules

- Only `POST /api/v1/sync` collects telemetry (and, from Day 5, calls AWS).
- Only `POST /api/v1/incidents/{id}/investigation` will call an LLM (Day 3).
- All GET endpoints read stored data. The UI always shows when data was last synced.
- HTTP status describes the API call; `SyncRun.status` describes the outcome.

## Sync flow (Day 1)

```
POST /api/v1/sync
  1. SyncService acquires its lock (409 SYNC_IN_PROGRESS if already held)
  2. TelemetrySource.collect(now - 3h, now)       → ObservationSnapshot
  3. detection.engine.evaluate(snapshot, open_fingerprints, now)
                                                  → incidents to open
  4. store: save snapshot, add incidents, record SyncRun
  5. return SyncRun (success | failed, per-collector status)
```

## Incident lifecycle

- Day 1 / 2a: the rules that trigger on a resource without an open incident open one
  incident (one per resource, all its triggered rules); a resource that already has an
  open incident is left unchanged (no duplicates).
- Day 2 (2b): one open incident per resource; new breaches merge into it; severity is the peak
  while open; resolution after ≥ 10 minutes of clean data; a later breach opens a new one.

## Milestones

| Day | Milestone | Status |
|---|---|---|
| 1 | Thin slice: scenario → R-CPU-SAT → memory store → API → generated types → Incidents page | Built; automated checks pass; manual break exercises deferred |
| 2a | All V1 rules, `within_normal` / `data_gap` facts, one scenario per rule | Built; automated checks pass |
| 2b | Full lifecycle (merge, peak severity, resolution), SQLite, deployment events | Not started |
| 2c | `GET /incidents/{id}`, `GET /overview`, Overview page, Investigation workspace (no AI) | Not started |
| 3 | Investigation engine: evidence bundle, provider interface, mock + one real provider, validation | Not started |
| 4 | Terraform: bootstrap + dev env, workload, CloudWatch agent, SSM scripts | Not started |
| 5 | AWS mode: Boto3 collectors, Resources pages | Not started |
| 6 | Docker Compose, CI hardening, all UI states | Not started |
| 7 | Demo, documentation, review, `v0.1.0` | Not started |

Each milestone stops for review before the next one starts.
