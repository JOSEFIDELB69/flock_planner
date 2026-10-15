"""Registro de auditoría. Nunca se registran secretos (se filtran claves sensibles)."""

from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog

SENSITIVE_KEYS = {"api_token", "token", "password", "secret", "ciphertext", "authorization", "api_key"}


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("***" if k.lower() in SENSITIVE_KEYS else _scrub(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


def record(db: Session, *, project_id: int | None, entity_type: str, entity_id: int | None, action: str,
           actor: str, before: dict[str, Any] | None = None, after: dict[str, Any] | None = None,
           reason: str = "") -> None:
    db.add(AuditLog(
        project_id=project_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        before=_scrub(before) if before is not None else None,
        after=_scrub(after) if after is not None else None,
        reason=reason,
        actor=actor,
    ))


def snapshot(obj: Any, fields: list[str]) -> dict[str, Any]:
    out = {}
    for f in fields:
        v = getattr(obj, f)
        out[f] = v.isoformat() if hasattr(v, "isoformat") else v
    return out
