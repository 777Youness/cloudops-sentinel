"""Typed domain errors and the API error envelope.

Each error carries a stable machine-readable code. The mapping to HTTP status codes
lives in one place: api/errors.py.
"""

from pydantic import BaseModel


class SentinelError(Exception):
    code = "INTERNAL"

    def __init__(self, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


class NotFoundError(SentinelError):
    code = "NOT_FOUND"


class SyncInProgressError(SentinelError):
    code = "SYNC_IN_PROGRESS"


class InvestigationInProgressError(SentinelError):
    code = "INVESTIGATION_IN_PROGRESS"


class LlmNotConfiguredError(SentinelError):
    code = "LLM_NOT_CONFIGURED"


class ErrorBody(BaseModel):
    code: str
    message: str
    hint: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
