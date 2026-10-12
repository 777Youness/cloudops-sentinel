"""Read side for incidents and the Overview. Routes call this; they never touch the store."""

from sentinel.detection.health import resource_health
from sentinel.domain.errors import NotFoundError
from sentinel.domain.incidents import (
    SEVERITY_ORDER,
    Incident,
    IncidentList,
    IncidentStatus,
    IncidentSummary,
)
from sentinel.domain.overview import Overview, SeverityCounts
from sentinel.domain.system import Mode
from sentinel.services.investigation import summary_status
from sentinel.store.base import Store

TOP_OPEN_INCIDENTS = 5

# Overview order: what needs attention first. Unknown ranks above ok: no data is not good news.
HEALTH_ORDER = {"crit": 0, "warn": 1, "unknown": 2, "ok": 3}


def by_importance(incidents: list[Incident]) -> list[Incident]:
    """Severity first (highest first), then most recently detected first."""
    return sorted(
        incidents,
        key=lambda i: (SEVERITY_ORDER[i.severity], i.first_detected_at),
        reverse=True,
    )


class IncidentService:
    def __init__(self, store: Store, mode: Mode) -> None:
        self._store = store
        self._mode = mode

    def _summaries(self, incidents: list[Incident]) -> list[IncidentSummary]:
        latest = self._store.latest_investigations()
        return [
            IncidentSummary.from_incident(i, summary_status(latest.get(i.id), i)) for i in incidents
        ]

    def list(self, status: IncidentStatus | None) -> IncidentList:
        items = self._summaries(by_importance(self._store.list_incidents(status)))
        return IncidentList(items=items, total=len(items))

    def get(self, incident_id: str) -> Incident:
        incident = self._store.get_incident(incident_id)
        if incident is None:
            raise NotFoundError(
                f"Incident {incident_id} not found.",
                hint="There is no incident with this ID in the local history.",
            )
        return incident

    def overview(self) -> Overview:
        open_incidents = by_importance(self._store.open_incidents())
        counts = SeverityCounts()
        for incident in open_incidents:
            setattr(counts, incident.severity, getattr(counts, incident.severity) + 1)

        snapshot = self._store.latest_snapshot()
        resources = []
        if snapshot is not None:
            open_by_resource = {i.fingerprint: i for i in open_incidents}
            resources = sorted(
                (
                    resource_health(r, snapshot.series, open_by_resource.get(r.id))
                    for r in snapshot.resources
                ),
                key=lambda h: (HEALTH_ORDER[h.health], h.resource_name),
            )
        last_success = self._store.last_successful_sync()
        return Overview(
            mode=self._mode,
            data_origin=snapshot.data_origin if snapshot else None,
            last_sync=self._store.last_sync(),
            data_as_of=last_success.finished_at if last_success else None,
            open_total=len(open_incidents),
            open_by_severity=counts,
            top_open_incidents=self._summaries(open_incidents[:TOP_OPEN_INCIDENTS]),
            resources=resources,
        )
