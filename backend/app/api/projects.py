from collections import Counter

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_actor, get_project
from app.errors import AppError, NotFound
from app.models import AuditLog, Epic, Export, PlanVersion, Project, Requirement, Scenario, Task, UserStory
from app.schemas import ProjectBulkDelete, ProjectCreate, ProjectOut, ProjectSummary, ProjectUpdate
from app.services import audit
from app.services.plans import add_default_team, baseline_of

router = APIRouter(tags=["Proyectos"])

PROJECT_FIELDS = ["name", "description", "business_objective", "owner", "target_date", "timezone",
                  "calendar_configuration", "mode", "currency", "status"]


def _summary(db: Session, p: Project) -> dict:
    data = ProjectOut.model_validate(p).model_dump()
    data["requirement_count"] = db.scalar(select(func.count()).select_from(Requirement)
                                          .where(Requirement.project_id == p.id)) or 0
    data["epic_count"] = db.scalar(select(func.count()).select_from(Epic).where(Epic.project_id == p.id)) or 0
    data["story_count"] = db.scalar(select(func.count()).select_from(UserStory)
                                    .where(UserStory.project_id == p.id)) or 0
    data["task_count"] = db.scalar(select(func.count()).select_from(Task).where(Task.project_id == p.id)) or 0
    data["total_hours"] = round(db.scalar(select(func.coalesce(func.sum(Task.estimated_hours), 0))
                                          .where(Task.project_id == p.id)) or 0, 2)
    data["has_baseline"] = baseline_of(db, p.id) is not None
    data["export_count"] = db.scalar(select(func.count()).select_from(Export).where(Export.project_id == p.id)) or 0
    if p.active_plan_version_id:
        v = db.get(PlanVersion, p.active_plan_version_id)
        if v:
            data["active_version_number"] = v.version_number
            data["estimated_completion_date"] = v.estimated_completion_date
            data["estimated_duration"] = v.estimated_duration
    return data


@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(get_db), actor: str = Depends(get_actor)):
    data = body.model_dump()
    data["calendar_configuration"] = body.calendar_configuration.model_dump(mode="json")
    project = Project(**data)
    db.add(project)
    db.flush()
    add_default_team(db, project)
    audit.record(db, project_id=project.id, entity_type="project", entity_id=project.id, action="create",
                 actor=actor, after=audit.snapshot(project, PROJECT_FIELDS))
    db.commit()
    db.refresh(project)
    return project


@router.get("/projects", response_model=list[ProjectSummary])
def list_projects(include_archived: bool = False, db: Session = Depends(get_db)):
    q = select(Project).order_by(Project.updated_at.desc())
    if not include_archived:
        q = q.where(Project.status != "archived")
    return [_summary(db, p) for p in db.scalars(q).all()]


@router.get("/projects/{project_id}", response_model=ProjectSummary)
def get_project_detail(project: Project = Depends(get_project), db: Session = Depends(get_db)):
    return _summary(db, project)


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(body: ProjectUpdate, project: Project = Depends(get_project), db: Session = Depends(get_db),
                   actor: str = Depends(get_actor)):
    before = audit.snapshot(project, PROJECT_FIELDS)
    changes = body.model_dump(exclude_unset=True, mode="json")
    for k, v in changes.items():
        if k == "target_date":
            from datetime import date
            v = date.fromisoformat(v) if v else None
        setattr(project, k, v)
    audit.record(db, project_id=project.id, entity_type="project", entity_id=project.id, action="update",
                 actor=actor, before=before, after=audit.snapshot(project, PROJECT_FIELDS))
    db.commit()
    db.refresh(project)
    return project


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project: Project = Depends(get_project), db: Session = Depends(get_db),
                   confirm: bool = Query(False, description="Debe ser true para confirmar la eliminación"),
                   actor: str = Depends(get_actor)):
    if not confirm:
        raise AppError("Confirmá la eliminación del proyecto (confirm=true). Esta acción no se puede deshacer.",
                       code="confirmation_required", status_code=422)
    _delete_project(db, project, actor)
    db.commit()
    return Response(status_code=204)


def _delete_project(db: Session, project: Project, actor: str, reason: str = "") -> None:
    # la auditoría del proyecto se borra en cascada: el registro de la eliminación queda como global
    audit.record(db, project_id=None, entity_type="project", entity_id=project.id, action="delete", actor=actor,
                 before={"name": project.name, "status": project.status, "owner": project.owner}, reason=reason)
    project.active_plan_version_id = None
    db.flush()
    db.delete(project)


@router.post("/projects/delete")
def delete_projects(body: ProjectBulkDelete, db: Session = Depends(get_db), actor: str = Depends(get_actor)):
    """Elimina varios proyectos en una sola transacción (todos o ninguno). Exige escribir ELIMINAR."""
    if not body.confirm or body.confirmation_text.strip().upper() != "ELIMINAR":
        raise AppError("Para eliminar varios proyectos escribí ELIMINAR y confirmá.", code="confirmation_required",
                       status_code=422)
    ids = list(dict.fromkeys(body.ids))
    rows = db.scalars(select(Project).where(Project.id.in_(ids))).all()
    missing = sorted(set(ids) - {p.id for p in rows})
    if missing:
        raise NotFound("Algunos proyectos no existen.", {"ids": missing})
    for p in rows:
        _delete_project(db, p, actor, reason="eliminación múltiple")
    db.commit()
    return {"deleted": len(rows)}


@router.get("/projects/{project_id}/audit")
def project_audit(project: Project = Depends(get_project), db: Session = Depends(get_db),
                  entity_type: str | None = None, entity_id: int | None = None, limit: int = Query(100, le=500)):
    q = select(AuditLog).where(AuditLog.project_id == project.id)
    if entity_type:
        q = q.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        q = q.where(AuditLog.entity_id == entity_id)
    rows = db.scalars(q.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit)).all()
    return [{"id": r.id, "entity_type": r.entity_type, "entity_id": r.entity_id, "action": r.action,
             "before": r.before, "after": r.after, "reason": r.reason, "actor": r.actor,
             "created_at": r.created_at} for r in rows]


@router.get("/dashboard")
def global_dashboard(db: Session = Depends(get_db)):
    projects = db.scalars(select(Project).where(Project.status != "archived")).all()
    status_counts = Counter(p.status for p in projects)
    items = [_summary(db, p) for p in projects]
    return {
        "active_projects": status_counts.get("active", 0),
        "draft_projects": status_counts.get("draft", 0),
        "total_projects": len(projects),
        "total_hours": round(sum(i["total_hours"] for i in items), 2),
        "projects": items,
    }


@router.get("/projects/{project_id}/dashboard")
def project_dashboard(project: Project = Depends(get_project), db: Session = Depends(get_db)):
    """Indicadores del proyecto calculados a partir de datos persistidos (versión activa y backlog)."""
    summary = _summary(db, project)
    active = db.get(PlanVersion, project.active_plan_version_id) if project.active_plan_version_id else None
    baseline = baseline_of(db, project.id)
    versions = db.scalars(select(PlanVersion).where(PlanVersion.project_id == project.id)
                          .order_by(PlanVersion.version_number)).all()
    scenarios = db.scalars(select(Scenario).where(Scenario.project_id == project.id,
                                                  Scenario.status.in_(["simulated", "applied"]))
                           .order_by(Scenario.id)).all()
    epic_hours = [
        {"code": e.code, "title": e.title,
         "hours": round(sum(t.estimated_hours for s in e.stories for t in s.tasks), 2)}
        for e in db.scalars(select(Epic).where(Epic.project_id == project.id).order_by(Epic.order_index)).all()
    ]
    hours_by_profile: dict[str, float] = {}
    for key, hours in db.execute(select(Task.profile_key, func.sum(Task.estimated_hours))
                                 .where(Task.project_id == project.id).group_by(Task.profile_key)).all():
        hours_by_profile[key] = round(hours or 0, 2)
    out = {
        "project": summary,
        "backlog": {"hours_by_profile": hours_by_profile, "epic_hours": epic_hours},
        "active_version": None,
        "baseline": None,
        "versions_trend": [{"version_number": v.version_number, "label": v.label, "duration": v.estimated_duration,
                            "effort": v.estimated_effort, "is_baseline": v.is_baseline,
                            "completion_date": v.estimated_completion_date} for v in versions],
        "scenarios": [{"id": s.id, "name": s.name, "status": s.status, "duration": s.estimated_duration,
                       "completion_date": s.estimated_completion_date,
                       "variation_pct": (s.comparison_metrics or {}).get("variation_pct"),
                       "time_savings_days": (s.comparison_metrics or {}).get("time_savings_days")}
                      for s in scenarios],
    }
    if active:
        m = active.metrics or {}
        out["active_version"] = {
            "id": active.id, "version_number": active.version_number, "label": active.label,
            "is_baseline": active.is_baseline, "duration": active.estimated_duration,
            "completion_date": active.estimated_completion_date, "start_date": active.start_date,
            "planned_effort": active.estimated_effort, "base_effort": m.get("base_effort_hours"),
            "by_profile": m.get("by_profile", []), "by_epic": m.get("by_epic", []),
            "main_bottleneck": m.get("main_bottleneck"), "bottlenecks": m.get("bottlenecks", []),
            "risks": active.risks[:5], "milestones": m.get("milestones", []), "total_cost": m.get("total_cost"),
            "total_daily_capacity": round(sum(p.get("daily_capacity", 0) for p in m.get("by_profile", [])), 2),
            "meets_target": m.get("meets_target"),
        }
    if baseline:
        out["baseline"] = {"id": baseline.id, "version_number": baseline.version_number,
                           "duration": baseline.estimated_duration,
                           "completion_date": baseline.estimated_completion_date}
        if active and active.id != baseline.id and baseline.estimated_duration:
            out["active_version"]["delta_vs_baseline_days"] = active.estimated_duration - baseline.estimated_duration
            out["active_version"]["delta_vs_baseline_pct"] = round(
                (active.estimated_duration - baseline.estimated_duration) / baseline.estimated_duration * 100, 2)
    return out
