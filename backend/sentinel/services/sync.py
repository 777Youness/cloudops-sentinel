"""The sync service: the only path that collects telemetry.

    collect (TelemetrySource) -> evaluate (detection engine) -> persist (Store) -> SyncRun

A source that cannot collect anything does not crash the sync: it is recorded as a failed
CollectorStatus and the SyncRun reports status "failed". A source made of several parts
(AWS) reports each part; if one failed or degraded, the SyncRun is "partial" and the
signals of the failed part are simply absent from the snapshot, so detection treats them
as missing data (never as healthy, never as 0).
"""

import threading
from datetime import datetime, timedelta

from sentinel.clock import Clock
from sentinel.collectors.base import CollectionError, TelemetrySource
from sentinel.detection import engine
from sentinel.domain.errors import SyncInProgressError
from sentinel.domain.system import (
    CollectorError,
    CollectorName,
    CollectorStatus,
    SyncRun,
    SyncStatus,
)
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
        # When each collector last delivered data (shown on the System page).
        self._last_success_at: dict[CollectorName, datetime] = {}

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

    def _failed_run(self, started, collector: CollectorName, error: CollectorError) -> SyncRun:
        run = SyncRun(
            id=self._store.next_sync_id(),
            started_at=started,
            finished_at=self._clock.now(),
            status="failed",
            collectors=[
                CollectorStatus(
                    name=collector,
                    state="failed",
                    last_success_at=self._last_success_at.get(collector),
                    error=error,
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

    def _statuses(self, reported: list[CollectorStatus]) -> list[CollectorStatus]:
        """The source's own report, or one "ok" for single-part sources, with the time
        each collector last delivered data."""
        now = self._clock.now()
        reported = reported or [CollectorStatus(name=self._source.name, state="ok")]
        statuses = []
        for status in reported:
            if status.state in ("ok", "degraded"):
                self._last_success_at[status.name] = now
            statuses.append(
                status.model_copy(
                    update={"last_success_at": self._last_success_at.get(status.name)}
                )
            )
        return statuses

    def _run_locked(self) -> SyncRun:
        started = self._clock.now()
        try:
            snapshot = self._source.collect(started - self._window, started)
        except CollectionError as exc:  # the source explained why (e.g. AccessDenied)
            return self._failed_run(started, exc.collector, exc.error)
        except Exception as exc:  # any other source failure becomes a reported status
            error = CollectorError(code=type(exc).__name__, message=str(exc))
            return self._failed_run(started, self._source.name, error)

        statuses = self._statuses(snapshot.collector_statuses)
        status: SyncStatus = "success" if all(s.state == "ok" for s in statuses) else "partial"
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
                status=status,
                collectors=statuses,
                resources_evaluated=result.resources_evaluated,
                rules_evaluated=result.rules_evaluated,
                incidents_opened=len(result.opened),
                incidents_updated=len(result.updated),
                incidents_resolved=len(result.resolved),
            )
            self._store.record_sync(run)
        return run
