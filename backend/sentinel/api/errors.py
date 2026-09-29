"""The one place where errors become HTTP responses with the standard envelope:

{"error": {"code": "...", "message": "...", "hint": "..."}}
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from sentinel.domain.errors import (
    ErrorBody,
    ErrorResponse,
    NotFoundError,
    SentinelError,
    SyncInProgressError,
)

log = logging.getLogger("sentinel.api")

HTTP_STATUS: dict[type[SentinelError], int] = {
    NotFoundError: 404,
    SyncInProgressError: 409,
}

# Documented error responses, reused in route declarations so they appear in OpenAPI.
ERROR_RESPONSES = {"model": ErrorResponse}


def _envelope(status: int, code: str, message: str, hint: str | None = None) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message, hint=hint))
    return JSONResponse(status_code=status, content=body.model_dump())


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(SentinelError)
    async def sentinel_error(_: Request, exc: SentinelError) -> JSONResponse:
        return _envelope(HTTP_STATUS.get(type(exc), 500), exc.code, exc.message, exc.hint)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", []))
        return _envelope(422, "VALIDATION_ERROR", f"Invalid request at {where}: {first.get('msg')}")

    @app.exception_handler(Exception)
    async def unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        log.exception("Unhandled error")
        return _envelope(500, "INTERNAL", "Unexpected server error. See the backend log.")
