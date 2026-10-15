"""Ejecución trazada de operaciones de IA (registra éxito/error sin guardar prompts ni secretos)."""

from collections.abc import Callable
from typing import TypeVar

from sqlalchemy.orm import Session

from app.ai.provider import AIProvider, timed
from app.db import SessionLocal
from app.errors import AppError
from app.models import AIInteraction

T = TypeVar("T")


def run_ai(db: Session, provider: AIProvider, project_id: int | None, operation: str, fn: Callable[[], T]) -> T:
    with timed(operation) as timer:
        try:
            result = fn()
        except AppError as exc:
            _log_error(project_id, provider, operation, exc.message, timer)
            raise
        except Exception as exc:  # noqa: BLE001
            _log_error(project_id, provider, operation, type(exc).__name__, timer)
            raise AppError("La operación de IA falló de forma inesperada. Los datos guardados no se modificaron.",
                           code="ai_error", status_code=502)
    db.add(AIInteraction(project_id=project_id, operation=operation, provider=provider.name, model=provider.model,
                         is_simulated=provider.is_simulated, status="ok", duration_ms=getattr(timer, "ms", 0)))
    return result


def _log_error(project_id, provider, operation, message, timer) -> None:
    # sesión independiente: el error queda registrado aunque la transacción principal se descarte
    with SessionLocal() as s:
        s.add(AIInteraction(project_id=project_id, operation=operation, provider=provider.name,
                            model=provider.model, is_simulated=provider.is_simulated, status="error",
                            error=message[:500], duration_ms=getattr(timer, "ms", 0)))
        s.commit()
