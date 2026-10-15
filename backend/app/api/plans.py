from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.provider import get_ai_provider
from app.api.requirements import project_context
from app.db import get_db
from app.deps import ai_rate_limit, get_actor, get_project
from app.errors import NotFound
from app.models import PlanVersion, Project
from app.planning.compare import compare
from app.schemas import (
    PlanGenerateRequest,
    PlanVersionListItem,
    PlanVersionOut,
    RecalculateRequest,
    RestoreRequest,
)
from app.services import audit
from app.services.ai_calls import run_ai
from app.services.backlog import backlog_snapshot
from app.services.plans import (
    compute,
    create_version,
    generate_current,
    get_version,
    resolve_parameters,
    team_config,
    version_dict,
)

router = APIRouter(tags=["Planificación"])


def _project_of(db: Session, v: PlanVersion) -> Project:
    return db.get(Project, v.project_id)


@router.post("/projects/{project_id}/plans/generate")
def generate_plan(body: PlanGenerateRequest, project: Project = Depends(get_project), db: Session = Depends(get_db),
                  actor: str = Depends(get_actor)):
    """Con confirm=false devuelve una vista previa calculada (no se guarda). Con confirm=true guarda una versión;
    la primera versión confirmada del proyecto es la línea base inmutable."""
    team, params, snapshot, result = generate_current(db, project, body.parameters.model_dump(mode="json"))
    if not body.confirm:
        return {"is_preview": True, "team_configuration": team, "planning_parameters": params, "result": result}
    version = create_version(db, project, team=team, params=params, snapshot=snapshot, result=result, actor=actor,
                             label=body.label, change_reason=body.change_reason)
    db.commit()
    return {"is_preview": False, **version_dict(version, project)}


@router.get("/projects/{project_id}/plans", response_model=list[PlanVersionListItem])
def list_plans(project: Project = Depends(get_project), db: Session = Depends(get_db)):
    versions = db.scalars(select(PlanVersion).where(PlanVersion.project_id == project.id)
                          .order_by(PlanVersion.version_number.desc())).all()
    return [version_dict(v, project, full=False) for v in versions]


@router.get("/plans/{plan_id}", response_model=PlanVersionOut)
def get_plan(plan_id: int, db: Session = Depends(get_db)):
    v = get_version(db, plan_id)
    return version_dict(v, _project_of(db, v))


@router.post("/plans/{plan_id}/recalculate", status_code=201)
def recalculate(plan_id: int, body: RecalculateRequest, db: Session = Depends(get_db),
                actor: str = Depends(get_actor)):
    """Crea una versión NUEVA con el backlog actual (la versión de origen no cambia)."""
    v = get_version(db, plan_id)
    project = _project_of(db, v)
    team = team_config(db, project) if body.use_current_team else v.team_configuration
    params = resolve_parameters(project, v.planning_parameters)
    snapshot = backlog_snapshot(db, project)
    result = compute(project, snapshot, team, params)
    new = create_version(db, project, team=team, params=params, snapshot=snapshot, result=result, actor=actor,
                         change_reason=body.change_reason or f"Recalculo desde v{v.version_number}")
    db.commit()
    return version_dict(new, project)


@router.post("/plans/{plan_id}/restore", status_code=201)
def restore(plan_id: int, body: RestoreRequest, db: Session = Depends(get_db), actor: str = Depends(get_actor)):
    """Restaurar = crear una versión nueva con el contenido de una anterior (no se borra historial)."""
    v = get_version(db, plan_id)
    project = _project_of(db, v)
    result = compute(project, v.backlog_snapshot, v.team_configuration, v.planning_parameters)
    new = create_version(db, project, team=v.team_configuration, params=v.planning_parameters,
                         snapshot=v.backlog_snapshot, result=result, actor=actor,
                         label=f"Restauración de v{v.version_number}",
                         change_reason=body.change_reason or f"Restauración del contenido de v{v.version_number}",
                         restored_from_version_id=v.id)
    db.commit()
    return version_dict(new, project)


@router.post("/plans/{plan_id}/summary", dependencies=[Depends(ai_rate_limit)])
def ai_summary(plan_id: int, db: Session = Depends(get_db), actor: str = Depends(get_actor)):
    """Resumen ejecutivo redactado por la IA a partir de las métricas del motor (no altera los cálculos)."""
    v = get_version(db, plan_id)
    project = _project_of(db, v)
    provider = get_ai_provider()
    metrics = {k: v.metrics.get(k) for k in ("start_date", "completion_date", "duration_working_days",
                                              "base_effort_hours", "planned_effort_hours", "by_profile",
                                              "main_bottleneck", "bottlenecks", "milestones", "risks", "total_cost",
                                              "target_date", "meets_target")}
    metrics["team"] = v.team_configuration
    result = run_ai(db, provider, project.id, "executive_summary",
                    lambda: provider.executive_summary(project_context(project), metrics))
    v.executive_summary = result.summary
    v.executive_summary_simulated = provider.is_simulated
    audit.record(db, project_id=project.id, entity_type="plan_version", entity_id=v.id, action="summary",
                 actor=actor, after={"simulated": provider.is_simulated})
    db.commit()
    return {"executive_summary": v.executive_summary, "is_simulated": provider.is_simulated}


@router.get("/plans/{plan_id}/compare/{other_id}")
def compare_versions(plan_id: int, other_id: int, db: Session = Depends(get_db)):
    a, b = get_version(db, plan_id), get_version(db, other_id)
    if a.project_id != b.project_id:
        raise NotFound("Las versiones pertenecen a proyectos distintos.")
    return {
        "from_version": {"id": a.id, "version_number": a.version_number, "label": a.label},
        "to_version": {"id": b.id, "version_number": b.version_number, "label": b.label},
        "metrics": compare({**a.metrics, "schedule": a.schedule}, {**b.metrics, "schedule": b.schedule},
                           a.team_configuration, b.team_configuration),
    }
