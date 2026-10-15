"""Observaciones (supuestos y advertencias) de la generación del backlog y su revisión por el usuario."""

from __future__ import annotations

import re

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import BacklogObservation, Requirement

CODE_RE = re.compile(r"\b(REQ|US|TK|EP)-\d+\b", re.IGNORECASE)
LINK_TYPES = {"REQ": "requirement", "US": "story", "TK": "task", "EP": "epic"}


def _links(db: Session, project_id: int, text: str) -> list[dict]:
    """Detecta códigos (REQ-012, US-003…) mencionados en el texto para poder ir directo a corregirlos."""
    codes = list(dict.fromkeys(m.group(0).upper() for m in CODE_RE.finditer(text)))
    if not codes:
        return []
    reqs = {r.code.upper(): r.id for r in db.scalars(select(Requirement).where(
        Requirement.project_id == project_id, Requirement.code.in_(codes))).all()}
    out = []
    for code in codes:
        kind = LINK_TYPES[code.split("-")[0]]
        if kind == "requirement":
            if code in reqs:
                out.append({"type": kind, "id": reqs[code], "code": code})
        else:
            out.append({"type": kind, "code": code})
    return out


def previous_feedback(db: Session, project_id: int) -> str:
    """Texto con las decisiones del usuario sobre la generación anterior, para enviarlo al agente."""
    rows = db.scalars(select(BacklogObservation).where(BacklogObservation.project_id == project_id)
                      .order_by(BacklogObservation.position)).all()
    corrected = [r for r in rows if r.status == "correction" and r.correction.strip()]
    accepted = [r for r in rows if r.status == "accepted" and r.kind == "assumption"]
    if not corrected and not accepted:
        return ""
    parts = []
    if corrected:
        parts.append("Correcciones del usuario a supuestos de la generación anterior (usalas como información "
                     "confirmada y no vuelvas a suponer lo contrario):\n"
                     + "\n".join(f"- Antes se supuso: {r.text} → Lo correcto es: {r.correction.strip()}"
                                  for r in corrected))
    if accepted:
        parts.append("Supuestos que el usuario revisó y aceptó (mantenelos):\n"
                     + "\n".join(f"- {r.text}" for r in accepted))
    return "\n".join(parts)


def replace_observations(db: Session, project_id: int, warnings: list[str], assumptions: list[str]) -> None:
    db.execute(delete(BacklogObservation).where(BacklogObservation.project_id == project_id))
    items = [("warning", w) for w in warnings] + [("assumption", a) for a in assumptions]
    seen = set()
    for i, (kind, text) in enumerate(items):
        text = (text or "").strip()
        if not text or (kind, text) in seen:
            continue
        seen.add((kind, text))
        db.add(BacklogObservation(project_id=project_id, kind=kind, text=text[:4000], position=i,
                                  links=_links(db, project_id, text)))
    db.flush()
