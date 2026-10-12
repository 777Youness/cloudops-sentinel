"""Access to the service container from routes."""

from dataclasses import dataclass

from fastapi import Request

from sentinel.clock import Clock
from sentinel.config import Settings
from sentinel.services.incidents import IncidentService
from sentinel.services.investigation import InvestigationService
from sentinel.services.sync import SyncService
from sentinel.services.system import SystemService
from sentinel.store.base import Store


@dataclass
class Container:
    settings: Settings
    clock: Clock
    # Held so the app can close it; routes use the services below, never the store.
    store: Store
    sync: SyncService
    incidents: IncidentService
    investigations: InvestigationService
    system: SystemService


def container(request: Request) -> Container:
    return request.app.state.container
