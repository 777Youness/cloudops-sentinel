"""The collector interface. Every data source implements it.

Detection receives an ObservationSnapshot and cannot tell which source produced it.
"""

from datetime import datetime
from typing import Protocol

from sentinel.domain.observations import DataOrigin, ObservationSnapshot
from sentinel.domain.system import CollectorError, CollectorName


class TelemetrySource(Protocol):
    name: CollectorName
    data_origin: DataOrigin

    def collect(self, window_start: datetime, window_end: datetime) -> ObservationSnapshot:
        """Return normalized observations for [window_start, window_end].

        A source made of several parts reports a part that failed in
        `snapshot.collector_statuses` and still returns what the other parts collected.
        If nothing usable can be collected it raises (CollectionError when it can explain
        why); the sync service turns that into a failed SyncRun instead of crashing.
        """
        ...


class CollectionError(Exception):
    """The source could not collect anything. Carries a translated, user-facing error."""

    def __init__(self, collector: CollectorName, error: CollectorError) -> None:
        super().__init__(error.message)
        self.collector = collector
        self.error = error
