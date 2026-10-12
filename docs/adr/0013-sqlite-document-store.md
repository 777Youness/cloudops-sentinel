# ADR 0013 — SQLite with JSON documents, one database file per mode

- Status: accepted
- Date: 2026-10-12

## Context
Incidents now live across syncs (merge, resolve, reopen), so they must survive a backend
restart. Sentinel runs locally for one operator (ADR 0001). The pydantic models are the
source of truth and are always read whole: an incident with its facts, timeline and evidence.

## Decision
- SQLite through the standard library `sqlite3`, only inside `store/`. No ORM.
- Each model is stored as its pydantic JSON in a `body` column; only the fields queries
  filter or sort on get their own columns (incident `status`, `fingerprint`,
  `first_detected_at`; sync `started_at`).
- Schema version in `PRAGMA user_version`, with numbered migration steps. A database newer
  than the code is refused rather than misread.
- A sync's evaluation and writes run in one transaction: stored whole or not at all.
  One connection, guarded by a re-entrant lock, shared by the API worker threads.
- One file per mode: `backend/data/sentinel-local.db` and `sentinel-aws.db`. Simulated and
  AWS incidents can never meet in the same history (principle 6).
- The in-memory store is removed; tests use SQLite with `":memory:"`, so production and
  tests run the same storage code.

## Alternatives considered
- One table per model (facts, timeline entries, series points): normalized, but every read
  would reassemble an incident from many joins, for no query that needs it.
- An ORM (SQLAlchemy): forbidden by the dependency policy, and hides the SQL that is the
  point of this exercise.
- Keeping the in-memory store next to SQLite: two implementations of one contract to keep
  in sync, and tests that do not exercise the real one.
- One file with a `data_origin` column: keeping origins apart would then depend on every
  query remembering the filter.

## Consequences
- Easy: restart-safe history, readable SQL, `sqlite3 backend/data/sentinel-local.db` to inspect.
- Harder: changing a model's shape needs care, because old JSON must still validate;
  add a migration step when that happens.
- Watch: a single connection serializes requests. Fine for one local operator; a hosted
  multi-user Sentinel (not planned for V1) would need a different design.
