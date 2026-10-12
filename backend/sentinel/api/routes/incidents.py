from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from sentinel.api.deps import Container, container
from sentinel.api.errors import ERROR_RESPONSES
from sentinel.domain.incidents import Incident, IncidentList
from sentinel.domain.investigation import InvestigationResult

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


@router.post(
    "/incidents/{incident_id}/investigation",
    response_model=InvestigationResult,
    responses={404: ERROR_RESPONSES, 409: ERROR_RESPONSES, 503: ERROR_RESPONSES},
)
def run_investigation(
    incident_id: str, c: Annotated[Container, Depends(container)]
) -> InvestigationResult:
    """The only endpoint that calls an LLM provider. Returns 200 with status "failed" when
    the provider or the validator rejected the run: the status describes the outcome.
    404 unknown incident, 409 already running, 503 provider not configured."""
    return c.investigations.run(incident_id)


@router.get(
    "/incidents/{incident_id}/investigation",
    response_model=InvestigationResult,
    responses={404: ERROR_RESPONSES},
)
def latest_investigation(
    incident_id: str, c: Annotated[Container, Depends(container)]
) -> InvestigationResult:
    """The latest saved run, with `outdated` computed now. Never calls a provider.
    404 if the incident is unknown or has never been investigated."""
    return c.investigations.latest(incident_id)
