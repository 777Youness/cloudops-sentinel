from typing import Annotated

from fastapi import APIRouter, Depends

from sentinel.api.deps import Container, container
from sentinel.config import CONTRACT_VERSION, VERSION
from sentinel.domain.system import Health, LlmStatus, SystemStatus

router = APIRouter(tags=["system"])


@router.get("/health", response_model=Health)
def health() -> Health:
    """Liveness only. Never touches AWS or the store."""
    return Health()


@router.get("/system", response_model=SystemStatus)
def system(c: Annotated[Container, Depends(container)]) -> SystemStatus:
    return SystemStatus(
        version=VERSION,
        contract_version=CONTRACT_VERSION,
        mode=c.settings.mode,
        environment=c.settings.environment,
        region=c.settings.region,
        llm=LlmStatus(provider=None, model=None, configured=False),  # Day 3
        last_sync=c.store.last_sync(),
    )
