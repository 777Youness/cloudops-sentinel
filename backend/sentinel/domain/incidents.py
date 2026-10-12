"""Facts and incidents: what detection concludes from observations.

Facts are produced only by code (detection/statements.py), never by an LLM.
"""

from typing import Literal

from pydantic import AwareDatetime, BaseModel

from sentinel.domain.observations import DataOrigin, MetricSeries, SignalName, Unit

Severity = Literal["low", "medium", "high", "critical"]
IncidentStatus = Literal["open", "resolved"]
InvestigationStatus = Literal["not_run", "completed", "failed", "unavailable"]
FactKind = Literal[
    "threshold_breach",
    "baseline_deviation",
    "within_normal",
    "event",
    "alarm_state",
    "log_pattern",
    "data_gap",
]
TimelineKind = Literal[
    "event",
    "breach_start",
    "alarm",
    "incident_opened",
    "incident_updated",
    "incident_resolved",
    "investigation",
]

SEVERITY_ORDER: dict[Severity, int] = {"low": 1, "medium": 2, "high": 3, "critical": 4}


class TimeWindow(BaseModel):
    start: AwareDatetime
    end: AwareDatetime


class Fact(BaseModel):
    id: str  # "F1", unique within its incident
    kind: FactKind
    statement: str
    source: str
    resource_id: str
    observed_at: AwareDatetime
    window: TimeWindow | None = None
    rule_id: str | None = None
    signal: SignalName | None = None
    value: float | None = None
    baseline: float | None = None
    threshold: float | None = None
    unit: Unit | None = None
    event_id: str | None = None  # kind "event" only: the OpsEvent this fact records


class TimelineEntry(BaseModel):
    at: AwareDatetime
    kind: TimelineKind
    label: str
    fact_id: str | None = None


class IncidentEvidence(BaseModel):
    """Snapshot of the data the incident was built from, kept with the incident so
    charts and investigations stay reproducible after the collection window moves on."""

    series: list[MetricSeries]


class KeySignal(BaseModel):
    signal: SignalName
    value: float
    unit: Unit


class Incident(BaseModel):
    id: str  # "INC-0001"
    fingerprint: str  # at most one open incident per fingerprint (= resource id)
    title: str
    severity: Severity
    status: IncidentStatus
    resource_id: str
    resource_name: str
    region: str
    data_origin: DataOrigin
    rule_ids: list[str]
    first_detected_at: AwareDatetime
    last_updated_at: AwareDatetime
    resolved_at: AwareDatetime | None = None
    key_signals: list[KeySignal]
    facts: list[Fact]
    timeline: list[TimelineEntry]
    evidence: IncidentEvidence
    evidence_hash: str


class IncidentSummary(BaseModel):
    id: str
    title: str
    severity: Severity
    status: IncidentStatus
    resource_id: str
    resource_name: str
    data_origin: DataOrigin
    first_detected_at: AwareDatetime
    resolved_at: AwareDatetime | None = None
    key_signals: list[KeySignal]
    investigation_status: InvestigationStatus

    @classmethod
    def from_incident(cls, incident: Incident) -> "IncidentSummary":
        return cls(
            id=incident.id,
            title=incident.title,
            severity=incident.severity,
            status=incident.status,
            resource_id=incident.resource_id,
            resource_name=incident.resource_name,
            data_origin=incident.data_origin,
            first_detected_at=incident.first_detected_at,
            resolved_at=incident.resolved_at,
            key_signals=incident.key_signals,
            investigation_status="not_run",  # investigations arrive on Day 3
        )


class IncidentList(BaseModel):
    items: list[IncidentSummary]
    total: int
