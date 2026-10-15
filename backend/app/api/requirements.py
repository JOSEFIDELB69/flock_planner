import re

from fastapi import APIRouter, Depends, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.ai.provider import get_ai_provider
from app.db import get_db
from app.deps import ai_rate_limit, get_actor, get_project
from app.errors import AppError, Conflict, NotFound
from app.models import Project, Requirement, RequirementAnalysis, RequirementLink
from app.schemas import (
    AcceptSuggestions,
    AnalysisAnswers,
    AnalysisOut,
    RequirementBulkDelete,
    RequirementBulkStatus,
    RequirementBulkText,
    RequirementCreate,
    RequirementOut,
    RequirementUpdate,
)
from app.services import audit
from app.services.ai_calls import run_ai
from app.services.backlog import next_code
from app.services.documents import split_free_text

router = APIRouter(tags=["Requisitos"])

REQ_FIELDS = ["code", "title", "description", "type", "priority", "source", "status", "group_name", "assumptions",
              "risks", "duplicate_of_id"]


def _links(db: Session, req_id: int) -> tuple[list[int], list[int]]:
    links = db.scalars(select(RequirementLink).where(RequirementLink.requirement_id == req_id)).all()
    return ([l.related_id for l in links if l.relation_type == "relates_to"],
            [l.related_id for l in links if l.relation_type == "depends_on"])


def _out(db: Session, r: Requirement) -> dict:
    related, depends = _links(db, r.id)
    data = {f: getattr(r, f) for f in REQ_FIELDS}
    return {**data, "id": r.id, "project_id": r.project_id, "related_ids": related, "depends_on_ids": depends,
            "source_document_id": r.source_document_id, "created_at": r.created_at, "updated_at": r.updated_at}


def _get_req(db: Session, requirement_id: int) -> Requirement:
    r = db.get(Requirement, requirement_id)
    if r is None:
        raise NotFound("No encontramos el requisito.")
    return r


def _create(db: Session, project: Project, body: RequirementCreate, actor: str) -> Requirement:
    r = Requirement(project_id=project.id, code=next_code(db, Requirement, project.id, "REQ"), **body.model_dump())
    db.add(r)
    db.flush()
    audit.record(db, project_id=project.id, entity_type="requirement", entity_id=r.id, action="create", actor=actor,
                 after=audit.snapshot(r, REQ_FIELDS))
    return r


@router.post("/projects/{project_id}/requirements", response_model=RequirementOut, status_code=201)
def create_requirement(body: RequirementCreate, project: Project = Depends(get_project),
                       db: Session = Depends(get_db), actor: str = Depends(get_actor)):
    r = _create(db, project, body, actor)
    db.commit()
    return _out(db, r)


@router.post("/projects/{project_id}/requirements/bulk", response_model=list[RequirementOut], status_code=201)
def create_from_text(body: RequirementBulkText, project: Project = Depends(get_project),
                     db: Session = Depends(get_db), actor: str = Depends(get_actor)):
    items = split_free_text(body.text)
    if not items:
        raise AppError("No encontramos requisitos en el texto.", status_code=422)
    created = []
    for item in items[:200]:
        title = re.split(r"(?<=[.!?])\s", item, maxsplit=1)[0][:300]
        created.append(_create(db, project, RequirementCreate(title=title, description=item, source=body.source),
                               actor))
    db.commit()
    return [_out(db, r) for r in created]


@router.get("/projects/{project_id}/requirements", response_model=list[RequirementOut])
def list_requirements(project: Project = Depends(get_project), db: Session = Depends(get_db),
                      status: str | None = None, type: str | None = None, q: str | None = None):
    query = select(Requirement).where(Requirement.project_id == project.id)
    if status:
        query = query.where(Requirement.status == status)
    if type:
        query = query.where(Requirement.type == type)
    if q:
        like = f"%{q}%"
        query = query.where(or_(Requirement.title.ilike(like), Requirement.description.ilike(like),
                                Requirement.code.ilike(like)))
    return [_out(db, r) for r in db.scalars(query.order_by(Requirement.id)).all()]


def _set_links(db: Session, r: Requirement, ids: list[int], relation: str) -> None:
    for l in db.scalars(select(RequirementLink).where(RequirementLink.requirement_id == r.id,
                                                      RequirementLink.relation_type == relation)).all():
        db.delete(l)
    db.flush()
    for rid in dict.fromkeys(ids):
        other = db.get(Requirement, rid)
        if other is None or other.project_id != r.project_id or other.id == r.id:
            raise Conflict(f"El requisito {rid} no es válido para relacionar.")
        exists = db.scalars(select(RequirementLink).where(RequirementLink.requirement_id == r.id,
                                                          RequirementLink.related_id == rid)).first()
        if exists:
            exists.relation_type = relation
        else:
            db.add(RequirementLink(requirement_id=r.id, related_id=rid, relation_type=relation))


@router.patch("/requirements/{requirement_id}", response_model=RequirementOut)
def update_requirement(requirement_id: int, body: RequirementUpdate, db: Session = Depends(get_db),
                       actor: str = Depends(get_actor)):
    r = _get_req(db, requirement_id)
    before = {**audit.snapshot(r, REQ_FIELDS), "links": _links(db, r.id)}
    changes = body.model_dump(exclude_unset=True)
    related = changes.pop("related_ids", None)
    depends = changes.pop("depends_on_ids", None)
    if "duplicate_of_id" in changes and changes["duplicate_of_id"] is not None:
        dup = db.get(Requirement, changes["duplicate_of_id"])
        if dup is None or dup.project_id != r.project_id or dup.id == r.id:
            raise Conflict("El requisito original indicado no es válido.")
        changes["status"] = "duplicate"
    for k, v in changes.items():
        setattr(r, k, v)
    if related is not None:
        _set_links(db, r, related, "relates_to")
    if depends is not None:
        _set_links(db, r, depends, "depends_on")
    db.flush()
    audit.record(db, project_id=r.project_id, entity_type="requirement", entity_id=r.id, action="update", actor=actor,
                 before=before, after={**audit.snapshot(r, REQ_FIELDS), "links": _links(db, r.id)})
    db.commit()
    return _out(db, r)


@router.delete("/requirements/{requirement_id}", status_code=204)
def delete_requirement(requirement_id: int, db: Session = Depends(get_db), actor: str = Depends(get_actor)):
    r = _get_req(db, requirement_id)
    audit.record(db, project_id=r.project_id, entity_type="requirement", entity_id=r.id, action="delete", actor=actor,
                 before=audit.snapshot(r, REQ_FIELDS))
    db.delete(r)
    db.commit()
    return Response(status_code=204)


@router.post("/projects/{project_id}/requirements/status")
def set_requirements_status(body: RequirementBulkStatus, project: Project = Depends(get_project),
                            db: Session = Depends(get_db), actor: str = Depends(get_actor)):
    """Confirma o rechaza varios requisitos a la vez (p. ej. las sugerencias que el agente extrajo de un documento)."""
    ids = list(dict.fromkeys(body.ids))
    rows = db.scalars(select(Requirement).where(Requirement.project_id == project.id,
                                                Requirement.id.in_(ids))).all()
    missing = sorted(set(ids) - {r.id for r in rows})
    if missing:
        raise NotFound("Algunos requisitos no existen o no pertenecen a este proyecto.", {"ids": missing})
    for r in rows:
        if r.status != body.status:
            audit.record(db, project_id=project.id, entity_type="requirement", entity_id=r.id, action="update",
                         actor=actor, before={"status": r.status}, after={"status": body.status},
                         reason="cambio de estado múltiple")
            r.status = body.status
    db.commit()
    return {"updated": len(rows), "status": body.status}


@router.post("/projects/{project_id}/requirements/delete")
def delete_requirements(body: RequirementBulkDelete, project: Project = Depends(get_project),
                        db: Session = Depends(get_db), actor: str = Depends(get_actor)):
    """Elimina varios requisitos del proyecto en una sola transacción (todos o ninguno), con auditoría."""
    if not body.confirm:
        raise AppError("Confirmá la eliminación de los requisitos seleccionados.", code="confirmation_required",
                       status_code=422)
    ids = list(dict.fromkeys(body.ids))
    rows = db.scalars(select(Requirement).where(Requirement.project_id == project.id,
                                                Requirement.id.in_(ids))).all()
    found = {r.id for r in rows}
    missing = [i for i in ids if i not in found]
    if missing:
        raise NotFound("Algunos requisitos no existen o no pertenecen a este proyecto.", {"ids": missing})
    for r in rows:
        audit.record(db, project_id=project.id, entity_type="requirement", entity_id=r.id, action="delete",
                     actor=actor, before=audit.snapshot(r, REQ_FIELDS), reason="eliminación múltiple")
        db.delete(r)
    db.commit()
    return {"deleted": len(rows)}


@router.get("/requirements/{requirement_id}/history")
def requirement_history(requirement_id: int, db: Session = Depends(get_db)):
    from app.models import AuditLog

    rows = db.scalars(select(AuditLog).where(AuditLog.entity_type == "requirement",
                                             AuditLog.entity_id == requirement_id)
                      .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())).all()
    return [{"id": a.id, "action": a.action, "before": a.before, "after": a.after, "actor": a.actor,
             "created_at": a.created_at, "reason": a.reason} for a in rows]


# --------------------------------------------------------------------------- análisis con IA


def project_context(project: Project) -> dict:
    return {"name": project.name, "description": project.description,
            "business_objective": project.business_objective,
            "target_date": project.target_date.isoformat() if project.target_date else None}


def requirement_context(db: Session, project: Project) -> list[dict]:
    reqs = db.scalars(select(Requirement).where(Requirement.project_id == project.id,
                                                Requirement.status.notin_(["rejected", "duplicate", "suggested"]))
                      .order_by(Requirement.id)).all()
    return [{"code": r.code, "title": r.title, "description": r.description, "type": r.type,
             "priority": r.priority, "status": r.status, "group_name": r.group_name,
             "assumptions": r.assumptions} for r in reqs]


@router.post("/projects/{project_id}/requirements/analyze", response_model=AnalysisOut, status_code=201,
             dependencies=[Depends(ai_rate_limit)])
def analyze_requirements(project: Project = Depends(get_project), db: Session = Depends(get_db),
                         actor: str = Depends(get_actor)):
    reqs = requirement_context(db, project)
    if not reqs:
        raise AppError("Cargá al menos un requisito antes de analizarlos.", code="no_requirements", status_code=422)
    provider = get_ai_provider()
    result = run_ai(db, provider, project.id, "analyze_requirements",
                    lambda: provider.analyze_requirements(project_context(project), reqs))
    analysis = RequirementAnalysis(project_id=project.id, result=result.model_dump(), answers={},
                                   is_simulated=provider.is_simulated, model=provider.model, created_by=actor)
    db.add(analysis)
    db.flush()
    audit.record(db, project_id=project.id, entity_type="analysis", entity_id=analysis.id, action="create",
                 actor=actor, after={"model": provider.model, "simulated": provider.is_simulated,
                                     "questions": len(result.clarification_questions)})
    db.commit()
    return analysis


@router.get("/projects/{project_id}/requirements/analyses", response_model=list[AnalysisOut])
def list_analyses(project: Project = Depends(get_project), db: Session = Depends(get_db)):
    return db.scalars(select(RequirementAnalysis).where(RequirementAnalysis.project_id == project.id)
                      .order_by(RequirementAnalysis.id.desc())).all()


def _get_analysis(db: Session, analysis_id: int) -> RequirementAnalysis:
    a = db.get(RequirementAnalysis, analysis_id)
    if a is None:
        raise NotFound("No encontramos el análisis.")
    return a


@router.put("/analyses/{analysis_id}/answers", response_model=AnalysisOut)
def save_answers(analysis_id: int, body: AnalysisAnswers, db: Session = Depends(get_db),
                 actor: str = Depends(get_actor)):
    a = _get_analysis(db, analysis_id)
    a.answers = {k: v.strip() for k, v in body.answers.items() if v and v.strip()}
    a.proceed_with_assumptions = body.proceed_with_assumptions
    audit.record(db, project_id=a.project_id, entity_type="analysis", entity_id=a.id, action="answers", actor=actor,
                 after={"answered": len(a.answers), "proceed_with_assumptions": a.proceed_with_assumptions})
    db.commit()
    return a


@router.post("/analyses/{analysis_id}/accept-suggestions", response_model=list[RequirementOut])
def accept_suggestions(analysis_id: int, body: AcceptSuggestions, db: Session = Depends(get_db),
                       actor: str = Depends(get_actor)):
    """El usuario confirma qué requisitos sugeridos por la IA se incorporan (nada se agrega sin revisión)."""
    a = _get_analysis(db, analysis_id)
    project = db.get(Project, a.project_id)
    suggestions = a.result.get("suggested_requirements", [])
    created = []
    for idx in sorted(set(body.indexes)):
        if idx < 0 or idx >= len(suggestions):
            raise AppError(f"La sugerencia {idx} no existe.", status_code=422)
        s = suggestions[idx]
        source = "sugerencia IA (simulada)" if a.is_simulated else "sugerencia IA"
        created.append(_create(db, project, RequirementCreate(
            title=s["title"][:300], description=s.get("description", ""), type=s.get("type", "functional"),
            priority=s.get("priority", "medium"), source=source, status="confirmed",
            assumptions=s.get("rationale", "")), actor))
    db.commit()
    return [_out(db, r) for r in created]
