"""SQLite store: domain models saved as JSON documents, plus a few indexed columns.

Why documents and not one table per model: the pydantic models are the source of truth
and are always read whole (an incident with its facts and timeline). Columns exist only
for what queries filter or sort on. No ORM: a handful of explicit SQL statements.

Concurrency: one connection shared by the API's worker threads, guarded by a re-entrant
lock (a transaction and the writes inside it run on the same thread).
"""

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sentinel.domain.incidents import Incident, IncidentStatus
from sentinel.domain.observations import ObservationSnapshot
from sentinel.domain.system import SyncRun

# Bump when the schema changes, and add a step to MIGRATIONS.
SCHEMA_VERSION = 1

MIGRATIONS: dict[int, str] = {
    1: """
        CREATE TABLE incidents (
            id                TEXT PRIMARY KEY,
            fingerprint       TEXT NOT NULL,
            status            TEXT NOT NULL,
            first_detected_at TEXT NOT NULL,
            body              TEXT NOT NULL
        );
        CREATE INDEX incidents_by_status ON incidents (status, fingerprint);
        CREATE TABLE sync_runs (
            id         TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            body       TEXT NOT NULL
        );
        -- Only the latest snapshot is kept: incidents carry their own evidence.
        CREATE TABLE latest_snapshot (
            id   INTEGER PRIMARY KEY CHECK (id = 1),
            body TEXT NOT NULL
        );
        CREATE TABLE counters (
            name  TEXT PRIMARY KEY,
            value INTEGER NOT NULL
        );
    """,
}


class SqliteStore:
    def __init__(self, path: str | Path) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        # isolation_level=None: autocommit, except inside transaction() where we BEGIN ourselves.
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._lock = threading.RLock()
        self._in_transaction = False
        try:
            self._migrate()
        except Exception:
            self._db.close()
            raise

    def _migrate(self) -> None:
        with self._lock:
            (version,) = self._db.execute("PRAGMA user_version").fetchone()
            if version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"Database schema v{version} is newer than this code (v{SCHEMA_VERSION})."
                )
            for step in range(version + 1, SCHEMA_VERSION + 1):
                self._db.executescript(
                    f"BEGIN; {MIGRATIONS[step]} PRAGMA user_version = {step}; COMMIT;"
                )

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._lock:
            if self._in_transaction:  # nested: the outer transaction decides
                yield
                return
            self._db.execute("BEGIN")
            self._in_transaction = True
            try:
                yield
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            else:
                self._db.execute("COMMIT")
            finally:
                self._in_transaction = False

    def _next(self, counter: str) -> int:
        with self.transaction():
            self._db.execute(
                "INSERT INTO counters (name, value) VALUES (?, 1) "
                "ON CONFLICT (name) DO UPDATE SET value = value + 1",
                (counter,),
            )
            (value,) = self._db.execute(
                "SELECT value FROM counters WHERE name = ?", (counter,)
            ).fetchone()
        return value

    def next_incident_id(self) -> str:
        return f"INC-{self._next('incident'):04d}"

    def next_sync_id(self) -> str:
        return f"SYNC-{self._next('sync'):04d}"

    def add_incident(self, incident: Incident) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO incidents (id, fingerprint, status, first_detected_at, body) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    incident.id,
                    incident.fingerprint,
                    incident.status,
                    incident.first_detected_at.isoformat(),
                    incident.model_dump_json(),
                ),
            )

    def update_incident(self, incident: Incident) -> None:
        with self._lock:
            cursor = self._db.execute(
                "UPDATE incidents SET status = ?, body = ? WHERE id = ?",
                (incident.status, incident.model_dump_json(), incident.id),
            )
            if cursor.rowcount != 1:
                raise KeyError(f"Incident {incident.id} does not exist")

    def get_incident(self, incident_id: str) -> Incident | None:
        with self._lock:
            row = self._db.execute(
                "SELECT body FROM incidents WHERE id = ?", (incident_id,)
            ).fetchone()
        return Incident.model_validate_json(row[0]) if row else None

    def list_incidents(self, status: IncidentStatus | None = None) -> list[Incident]:
        with self._lock:
            if status is None:
                rows = self._db.execute("SELECT body FROM incidents ORDER BY id").fetchall()
            else:
                rows = self._db.execute(
                    "SELECT body FROM incidents WHERE status = ? ORDER BY id", (status,)
                ).fetchall()
        return [Incident.model_validate_json(body) for (body,) in rows]

    def open_incidents(self) -> list[Incident]:
        return self.list_incidents("open")

    def save_snapshot(self, snapshot: ObservationSnapshot) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO latest_snapshot (id, body) VALUES (1, ?) "
                "ON CONFLICT (id) DO UPDATE SET body = excluded.body",
                (snapshot.model_dump_json(),),
            )

    def latest_snapshot(self) -> ObservationSnapshot | None:
        with self._lock:
            row = self._db.execute("SELECT body FROM latest_snapshot WHERE id = 1").fetchone()
        return ObservationSnapshot.model_validate_json(row[0]) if row else None

    def record_sync(self, run: SyncRun) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO sync_runs (id, started_at, body) VALUES (?, ?, ?)",
                (run.id, run.started_at.isoformat(), run.model_dump_json()),
            )

    def last_sync(self) -> SyncRun | None:
        with self._lock:
            row = self._db.execute(
                "SELECT body FROM sync_runs ORDER BY started_at DESC, id DESC LIMIT 1"
            ).fetchone()
        return SyncRun.model_validate_json(row[0]) if row else None

    def last_successful_sync(self) -> SyncRun | None:
        """The newest sync whose data was stored. json_extract reads inside the JSON body,
        so this needs no extra column (and no schema migration)."""
        with self._lock:
            row = self._db.execute(
                "SELECT body FROM sync_runs WHERE json_extract(body, '$.status') = 'success' "
                "ORDER BY started_at DESC, id DESC LIMIT 1"
            ).fetchone()
        return SyncRun.model_validate_json(row[0]) if row else None

    def close(self) -> None:
        with self._lock:
            self._db.close()
