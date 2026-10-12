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

## Milestone 2a — all detection rules

- Date: 2026-10-12
- Built: six more rules plus a derived one, `within_normal` / `data_gap` facts, eight
  scenarios (each with an expected-outcome test).
- To try later: in `backend/scenarios/low_traffic_errors.yaml` raise `request_rate`
  baseline from 2 to 10 and run `uv run pytest tests/test_scenarios.py` — what fails, and why?
- In my own words, why R-LAT needs two passes:
