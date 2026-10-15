"""Dependencias comunes de los endpoints."""

import re
import threading
import time
from collections import defaultdict, deque

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.errors import AppError, NotFound
from app.models import Project


def get_actor(x_pm_user: str | None = Header(default=None)) -> str:
    """Usuario responsable para auditoría. Sin autenticación multiusuario en v1 (ver README)."""
    if x_pm_user:
        clean = re.sub(r"[^\w .@\-áéíóúñÁÉÍÓÚÑ]", "", x_pm_user)[:120].strip()
        if clean:
            return clean
    return get_settings().default_user


def get_project(project_id: int, db: Session = Depends(get_db)) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise NotFound("No encontramos el proyecto.")
    return project


class RateLimiter:
    """Límite simple en memoria por IP para operaciones costosas (IA)."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def __call__(self, request: Request) -> None:
        limit = get_settings().ai_rate_limit_per_minute
        if limit <= 0:
            return
        key = request.client.host if request.client else "anon"
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= limit:
                raise AppError("Demasiadas solicitudes de IA en poco tiempo. Esperá un minuto y probá de nuevo.",
                               status_code=429, code="rate_limited")
            q.append(now)


ai_rate_limit = RateLimiter()
