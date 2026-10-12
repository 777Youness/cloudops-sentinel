"""System status: what Sentinel is connected to and when its data was last refreshed."""

from sentinel.config import CONTRACT_VERSION, VERSION, Settings
from sentinel.domain.system import LlmStatus, SystemStatus
from sentinel.store.base import Store


class SystemService:
    def __init__(self, store: Store, settings: Settings) -> None:
        self._store = store
        self._settings = settings

    def status(self) -> SystemStatus:
        last_success = self._store.last_successful_sync()
        return SystemStatus(
            version=VERSION,
            contract_version=CONTRACT_VERSION,
            mode=self._settings.mode,
            environment=self._settings.environment,
            region=self._settings.region,
            llm=LlmStatus(provider=None, model=None, configured=False),  # Day 3
            last_sync=self._store.last_sync(),
            data_as_of=last_success.finished_at if last_success else None,
        )
