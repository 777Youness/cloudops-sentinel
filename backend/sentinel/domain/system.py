"""Sync runs and system status: how Sentinel reports on its own data sources."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel

CollectorName = Literal["simulator", "ec2", "cloudwatch_metrics", "cloudwatch_logs", "alarms"]
CollectorState = Literal["ok", "degraded", "failed", "disabled"]
SyncStatus = Literal["success", "partial", "failed"]
Mode = Literal["local", "aws"]


class CollectorError(BaseModel):
    code: str
    message: str
    hint: str | None = None


class CollectorStatus(BaseModel):
    name: CollectorName
    state: CollectorState
    last_success_at: AwareDatetime | None = None
    error: CollectorError | None = None


class SyncRun(BaseModel):
    id: str
    started_at: AwareDatetime
    finished_at: AwareDatetime
    status: SyncStatus
    collectors: list[CollectorStatus]
    resources_evaluated: int
    rules_evaluated: int
    incidents_opened: int
    incidents_updated: int
    incidents_resolved: int


class LlmStatus(BaseModel):
    provider: str | None
    model: str | None
    configured: bool


class SystemStatus(BaseModel):
    version: str
    contract_version: str
    mode: Mode
    environment: str
    region: str
    llm: LlmStatus
    last_sync: SyncRun | None = None


class Health(BaseModel):
    status: Literal["ok"] = "ok"
