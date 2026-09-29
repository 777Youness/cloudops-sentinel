from typing import Annotated

from fastapi import APIRouter, Depends

from sentinel.api.deps import Container, container
from sentinel.api.errors import ERROR_RESPONSES
from sentinel.domain.system import SyncRun

router = APIRouter(tags=["sync"])


@router.post("/sync", response_model=SyncRun, responses={409: ERROR_RESPONSES})
def run_sync(c: Annotated[Container, Depends(container)]) -> SyncRun:
    """Collect telemetry, run detection, store the result.

    Returns 200 even when the sync itself failed: the SyncRun status describes the outcome.
    Returns 409 SYNC_IN_PROGRESS if another sync is running.
    """
    return c.sync.run()
