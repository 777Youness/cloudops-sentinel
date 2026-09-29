"""In-memory store. Everything is lost when the process restarts (Day 1 only)."""

import threading

from sentinel.domain.incidents import Incident, IncidentStatus
from sentinel.domain.observations import ObservationSnapshot
from sentinel.domain.system import SyncRun


class MemoryStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()  # API requests run in a thread pool
        self._incidents: dict[str, Incident] = {}
        self._snapshot: ObservationSnapshot | None = None
        self._syncs: list[SyncRun] = []
        self._incident_seq = 0
        self._sync_seq = 0

    def next_incident_id(self) -> str:
        with self._lock:
            self._incident_seq += 1
            return f"INC-{self._incident_seq:04d}"

    def next_sync_id(self) -> str:
        with self._lock:
            self._sync_seq += 1
            return f"SYNC-{self._sync_seq:04d}"

    def add_incident(self, incident: Incident) -> None:
        with self._lock:
            self._incidents[incident.id] = incident

    def list_incidents(self, status: IncidentStatus | None = None) -> list[Incident]:
        with self._lock:
            items = list(self._incidents.values())
        return [i for i in items if status is None or i.status == status]

    def open_fingerprints(self) -> set[str]:
        return {i.fingerprint for i in self.list_incidents("open")}

    def save_snapshot(self, snapshot: ObservationSnapshot) -> None:
        with self._lock:
            self._snapshot = snapshot

    def latest_snapshot(self) -> ObservationSnapshot | None:
        return self._snapshot

    def record_sync(self, run: SyncRun) -> None:
        with self._lock:
            self._syncs.append(run)

    def last_sync(self) -> SyncRun | None:
        return self._syncs[-1] if self._syncs else None
