from typing import Annotated

from fastapi import APIRouter, Depends

from sentinel.api.deps import Container, container
from sentinel.domain.overview import Overview

router = APIRouter(tags=["overview"])


@router.get("/overview", response_model=Overview)
def overview(c: Annotated[Container, Depends(container)]) -> Overview:
    """Open incidents by severity, the most important ones, data trust and resource health.
    Reads stored data only."""
    return c.incidents.overview()
