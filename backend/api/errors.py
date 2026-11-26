"""API errors. Every error body has a `detail` message; input errors may also name a `field`."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status_code: int, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.field = field


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        body: dict[str, str] = {"detail": exc.message}
        if exc.field:
            body["field"] = exc.field
        return JSONResponse(status_code=exc.status_code, content=body)
