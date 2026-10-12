"""The sync service: the only path that collects telemetry.

    collect (TelemetrySource) -> evaluate (detection engine) -> persist (Store) -> SyncRun

A failing collector does not crash the sync: it is recorded as a failed CollectorStatus and
the SyncRun reports status "failed" (or "partial" once several collectors exist).
"""

import threading
from datetime import timedelta

from sentinel.clock import Clock
from sentinel.collectors.base import TelemetrySource
from sentinel.detection import engine
from sentinel.domain.errors import SyncInProgressError
from sentinel.domain.system import CollectorError, CollectorStatus, SyncRun
from sentinel.store.base import Store


class SyncService:
    def __init__(
        self, source: TelemetrySource, store: Store, clock: Clock, window: timedelta
    ) -> None:
        self._source = source
        self._store = store
        self._clock = clock
        self._window = window
        self._lock = threading.Lock()
        self._last_success_at = None

    def run(self) -> SyncRun:
        # Non-blocking: a second sync while one is running is rejected, not queued.
        if not self._lock.acquire(blocking=False):
            raise SyncInProgressError(
                "A sync is already running.", hint="Wait for it to finish, then retry."
            )
        try:
            return self._run_locked()
        finally:
            self._lock.release()

    def _run_locked(self) -> SyncRun:
        started = self._clock.now()
        try:
            snapshot = self._source.collect(started - self._window, started)
        except Exception as exc:  # any source failure becomes a reported status
            run = SyncRun(
                id=self._store.next_sync_id(),
                started_at=started,
                finished_at=self._clock.now(),
                status="failed",
                collectors=[
                    CollectorStatus(
                        name=self._source.name,
                        state="failed",
                        last_success_at=self._last_success_at,
                        error=CollectorError(code=type(exc).__name__, message=str(exc)),
                    )
                ],
                resources_evaluated=0,
                rules_evaluated=0,
                incidents_opened=0,
                incidents_updated=0,
                incidents_resolved=0,
            )
            self._store.record_sync(run)
            return run

        self._last_success_at = self._clock.now()
        # Evaluation and every write happen in one transaction: a sync is stored whole or
        # not at all, and no other request sees a half-applied sync.
        with self._store.transaction():
            self._store.save_snapshot(snapshot)
            result = engine.evaluate(
                snapshot,
                open_incidents=self._store.open_incidents(),
                now=started,
                allocate_id=self._store.next_incident_id,
            )
            for incident in result.opened:
                self._store.add_incident(incident)
            for incident in result.updated + result.resolved:
                self._store.update_incident(incident)

            run = SyncRun(
                id=self._store.next_sync_id(),
                started_at=started,
                finished_at=self._clock.now(),
                status="success",
                collectors=[
                    CollectorStatus(
                        name=self._source.name, state="ok", last_success_at=self._last_success_at
                    )
                ],
                resources_evaluated=result.resources_evaluated,
                rules_evaluated=result.rules_evaluated,
                incidents_opened=len(result.opened),
                incidents_updated=len(result.updated),
                incidents_resolved=len(result.resolved),
            )
            self._store.record_sync(run)
        return run
