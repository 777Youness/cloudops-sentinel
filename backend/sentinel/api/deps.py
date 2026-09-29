"""Access to the service container from routes."""

from dataclasses import dataclass

from fastapi import Request

from sentinel.clock import Clock
from sentinel.config import Settings
from sentinel.services.sync import SyncService
from sentinel.store.base import Store


@dataclass
class Container:
    settings: Settings
    clock: Clock
    store: Store
    sync: SyncService


def container(request: Request) -> Container:
    return request.app.state.container
