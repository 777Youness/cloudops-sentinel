"""The Overview: what is wrong right now, and can the data be trusted?"""

from typing import Literal

from pydantic import AwareDatetime, BaseModel

from sentinel.domain.incidents import IncidentSummary, Severity
from sentinel.domain.observations import DataOrigin, InstanceState, SignalName
from sentinel.domain.system import Mode, SyncRun

HealthState = Literal["ok", "warn", "crit", "unknown"]


class ResourceHealth(BaseModel):
    """Health of one monitored resource, from the latest snapshot and its open incident.

    `signals_missing` lists every expected signal with no datapoint in the latest
    snapshot: missing data is reported, never shown as 0 or as healthy by omission.
    """

    resource_id: str
    resource_name: str
    instance_type: str
    state: InstanceState
    data_origin: DataOrigin
    health: HealthState
    open_incident_id: str | None = None
    open_incident_severity: Severity | None = None
    signals_expected: list[SignalName]
    signals_missing: list[SignalName]
    last_datapoint_at: AwareDatetime | None = None


class SeverityCounts(BaseModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0


class Overview(BaseModel):
    mode: Mode
    # Origin of the stored data; None before the first successful sync.
    data_origin: DataOrigin | None
    last_sync: SyncRun | None
    # When the data on screen was collected: the last *successful* sync. A failed sync
    # does not refresh anything, so it does not make the data fresher.
    data_as_of: AwareDatetime | None
    open_total: int
    open_by_severity: SeverityCounts
    top_open_incidents: list[IncidentSummary]
    resources: list[ResourceHealth]
