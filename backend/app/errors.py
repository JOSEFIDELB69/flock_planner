"""Gestión centralizada de errores: todas las respuestas de error tienen la forma
{"error": {"code": str, "message": str, "details": {...}}}."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.models import ImmutablePlanError
from app.planning.engine import PlanningError

log = logging.getLogger("pm_agent")


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, details: dict[str, Any] | None = None, status_code: int | None = None,
                 code: str | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        if status_code:
            self.status_code = status_code
        if code:
            self.code = code


class NotFound(AppError):
    status_code = 404
    code = "not_found"


class Conflict(AppError):
    status_code = 409
    code = "conflict"


class AIUnavailable(AppError):
    status_code = 503
    code = "ai_unavailable"


class Forbidden(AppError):
    status_code = 403
    code = "forbidden"


def _body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_req: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content=_body(exc.code, exc.message, exc.details))

    @app.exception_handler(PlanningError)
    async def _planning_error(_req: Request, exc: PlanningError):
        return JSONResponse(status_code=422, content=_body("planning_error", exc.message, exc.details))

    @app.exception_handler(ImmutablePlanError)
    async def _immutable(_req: Request, exc: ImmutablePlanError):
        return JSONResponse(status_code=409, content=_body("immutable_plan", str(exc)))

    @app.exception_handler(RequestValidationError)
    async def _validation(_req: Request, exc: RequestValidationError):
        errors = [
            {"field": ".".join(str(p) for p in e.get("loc", []) if p != "body"), "message": e.get("msg", "")}
            for e in exc.errors()
        ]
        return JSONResponse(status_code=422, content=_body("validation_error", "Revisá los datos enviados.",
                                                           {"errors": errors}))

    @app.exception_handler(StarletteHTTPException)
    async def _http(_req: Request, exc: StarletteHTTPException):
        message = exc.detail if isinstance(exc.detail, str) else "Error en la solicitud."
        return JSONResponse(status_code=exc.status_code, content=_body("http_error", message))

    @app.exception_handler(Exception)
    async def _unhandled(_req: Request, exc: Exception):
        log.exception("Error no controlado: %s", type(exc).__name__)
        return JSONResponse(status_code=500, content=_body(
            "internal_error", "Ocurrió un error inesperado. Los datos guardados no se perdieron; probá de nuevo."))
