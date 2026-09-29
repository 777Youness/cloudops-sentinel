from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from sentinel.api.deps import Container, container
from sentinel.domain.incidents import SEVERITY_ORDER, IncidentList, IncidentSummary

router = APIRouter(tags=["incidents"])


@router.get("/incidents", response_model=IncidentList)
def list_incidents(
    c: Annotated[Container, Depends(container)],
    status: Annotated[Literal["open", "resolved", "all"], Query()] = "open",
) -> IncidentList:
    """Incidents sorted by severity (highest first), then most recent first."""
    incidents = c.store.list_incidents(None if status == "all" else status)
    incidents.sort(key=lambda i: i.first_detected_at, reverse=True)
    incidents.sort(key=lambda i: SEVERITY_ORDER[i.severity], reverse=True)
    items = [IncidentSummary.from_incident(i) for i in incidents]
    return IncidentList(items=items, total=len(items))
