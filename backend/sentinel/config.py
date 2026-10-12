"""Configuration from environment variables (prefix SENTINEL_). See .env.example."""

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SENTINEL_", env_file=".env", extra="ignore")

    mode: Literal["local", "aws"] = "local"
    environment: str = "dev"
    region: str = "eu-west-3"
    scenarios_dir: Path = BACKEND_DIR / "scenarios"
    # Collection window per sync. Long enough for a 60-minute baseline plus the incident.
    sync_window_minutes: int = 180
    # Dev aid: makes the simulated collector slow so loading states and the sync lock
    # can be observed. Always 0 outside manual testing.
    simulated_latency_seconds: float = 0.0
    # Where incidents and sync runs are stored. Default: data/sentinel-<mode>.db, one file
    # per mode so simulated and AWS incidents can never mix. ":memory:" keeps nothing.
    db_path: str | None = None

    def resolved_db_path(self) -> str:
        return self.db_path or str(BACKEND_DIR / "data" / f"sentinel-{self.mode}.db")


VERSION = "0.1.0.dev1"
CONTRACT_VERSION = "1"
