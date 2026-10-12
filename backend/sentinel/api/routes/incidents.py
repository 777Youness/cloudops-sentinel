from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from sentinel.api.deps import Container, container
from sentinel.api.errors import ERROR_RESPONSES
from sentinel.domain.incidents import Incident, IncidentList

router = APIRouter(tags=["incidents"])


@router.get("/incidents", response_model=IncidentList)
def list_incidents(
    c: Annotated[Container, Depends(container)],
    status: Annotated[Literal["open", "resolved", "all"], Query()] = "open",
) -> IncidentList:
    """Incidents sorted by severity (highest first), then most recent first."""
    return c.incidents.list(None if status == "all" else status)


@router.get("/incidents/{incident_id}", response_model=Incident, responses={404: ERROR_RESPONSES})
def get_incident(incident_id: str, c: Annotated[Container, Depends(container)]) -> Incident:
    """One incident with everything stored for it: facts, timeline, evidence series,
    rule ids and evidence hash. 404 NOT_FOUND if the id is unknown."""
    return c.incidents.get(incident_id)
