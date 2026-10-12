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
from sentinel.domain.system import LlmStatus
from sentinel.investigation.providers.base import LlmProvider
from sentinel.investigation.providers.mock import MockProvider
from sentinel.investigation.providers.openai_compatible import OpenAICompatibleProvider
from sentinel.services.incidents import IncidentService
from sentinel.services.investigation import InvestigationService
from sentinel.services.sync import SyncService
from sentinel.services.system import SystemService
from sentinel.store.sqlite import SqliteStore

API_PREFIX = "/api/v1"


def build_provider(settings: Settings) -> tuple[LlmProvider | None, LlmStatus]:
    """The configured provider, or None if it is selected but incomplete. An incomplete
    provider never stops the app: only the investigation endpoint reports it (503)."""
    if settings.llm_provider == "mock":
        mock = MockProvider()
        return mock, LlmStatus(provider=mock.name, model=mock.model, configured=True)
    status = LlmStatus(provider="openai_compatible", model=settings.llm_model, configured=False)
    if not settings.llm_base_url or not settings.llm_model:
        return None, status
    key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else None
    provider = OpenAICompatibleProvider(
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        api_key=key or None,
        timeout_seconds=settings.llm_timeout_seconds,
        max_tokens=settings.llm_max_tokens,
    )
    return provider, status.model_copy(update={"configured": True})


def build_container(
    settings: Settings, clock: Clock, llm_provider: LlmProvider | None = None
) -> Container:
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
    if llm_provider is not None:  # injected by tests
        provider: LlmProvider | None = llm_provider
        llm = LlmStatus(provider=llm_provider.name, model=llm_provider.model, configured=True)
    else:
        provider, llm = build_provider(settings)
    return Container(
        settings=settings,
        clock=clock,
        store=store,
        sync=sync,
        incidents=IncidentService(store, settings.mode),
        investigations=InvestigationService(store, provider, llm, clock),
        system=SystemService(store, settings, llm),
    )


def create_app(
    settings: Settings | None = None,
    clock: Clock | None = None,
    llm_provider: LlmProvider | None = None,
) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(
        title="CloudOps Sentinel API",
        version=VERSION,
        description="Evidence-based incident investigation for AWS workloads.",
    )
    app.state.container = build_container(settings, clock or SystemClock(), llm_provider)
    install_error_handlers(app)
    for module in (system, sync, overview, incidents):
        app.include_router(module.router, prefix=API_PREFIX)
    return app


app = create_app()
