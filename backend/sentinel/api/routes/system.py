from typing import Annotated

from fastapi import APIRouter, Depends

from sentinel.api.deps import Container, container
from sentinel.domain.system import Health, SystemStatus

router = APIRouter(tags=["system"])


@router.get("/health", response_model=Health)
def health() -> Health:
    """Liveness only. Never touches AWS or the store."""
    return Health()


@router.get("/system", response_model=SystemStatus)
def system(c: Annotated[Container, Depends(container)]) -> SystemStatus:
    return c.system.status()
