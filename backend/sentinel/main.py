"""Application factory: builds the service container and the FastAPI app.

Run with:  uv run uvicorn sentinel.main:app --reload --host 127.0.0.1 --port 8000
"""

from datetime import timedelta

from fastapi import FastAPI

from sentinel.api.deps import Container
from sentinel.api.errors import install_error_handlers
from sentinel.api.routes import incidents, overview, sync, system
from sentinel.clock import Clock, SystemClock
from sentinel.collectors.simulated import SimulatedSource, load_scenarios
from sentinel.config import VERSION, Settings
from sentinel.services.incidents import IncidentService
from sentinel.services.sync import SyncService
from sentinel.services.system import SystemService
from sentinel.store.sqlite import SqliteStore

API_PREFIX = "/api/v1"


def build_container(settings: Settings, clock: Clock) -> Container:
    if settings.mode == "aws":
        # Honest failure instead of a half-working mode. AWS collectors arrive on Day 5.
        raise RuntimeError("SENTINEL_MODE=aws is not implemented yet. Use SENTINEL_MODE=local.")
    source = SimulatedSource(
        load_scenarios(settings.scenarios_dir),
        clock=clock,
        region=settings.region,
        latency_seconds=settings.simulated_latency_seconds,
    )
    store = SqliteStore(settings.resolved_db_path())
    sync = SyncService(source, store, clock, window=timedelta(minutes=settings.sync_window_minutes))
    return Container(
        settings=settings,
        clock=clock,
        store=store,
        sync=sync,
        incidents=IncidentService(store, settings.mode),
        system=SystemService(store, settings),
    )


def create_app(settings: Settings | None = None, clock: Clock | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(
        title="CloudOps Sentinel API",
        version=VERSION,
        description="Evidence-based incident investigation for AWS workloads.",
    )
    app.state.container = build_container(settings, clock or SystemClock())
    install_error_handlers(app)
    for module in (system, sync, overview, incidents):
        app.include_router(module.router, prefix=API_PREFIX)
    return app


app = create_app()
