"""The collector interface. Every data source implements it.

Detection receives an ObservationSnapshot and cannot tell which source produced it.
"""

from datetime import datetime
from typing import Protocol

from sentinel.domain.observations import DataOrigin, ObservationSnapshot
from sentinel.domain.system import CollectorName


class TelemetrySource(Protocol):
    name: CollectorName
    data_origin: DataOrigin

    def collect(self, window_start: datetime, window_end: datetime) -> ObservationSnapshot:
        """Return normalized observations for [window_start, window_end].

        Raises an exception if the source is unreachable; the sync service turns it into a
        CollectorStatus instead of crashing.
        """
        ...
