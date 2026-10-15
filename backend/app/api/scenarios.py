from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.provider import get_ai_provider
from app.api.requirements import project_context
from app.db import get_db
from app.deps import ai_rate_limit, get_actor, get_project
from app.errors import AppError, Conflict
from app.models import Project, Scenario
from app.schemas import (
    ExplainScenariosRequest,
    ScenarioApplyRequest,
    ScenarioCreate,
    ScenarioOut,
    ScenarioUpdate,
    SuggestScenariosRequest,
)
from app.services import audit
from app.services import scenarios as svc
from app.services.ai_calls import run_ai
from app.services.plans import baseline_of, get_version, version_dict

router = APIRouter(tags=["Escenarios"])


def _project(db: Session, s: Scenario) -> Project:
    return db.get(Project, s.project_id)


@router.post("/projects/{project_id}/scenarios", response_model=ScenarioOut, status_code=201)
def create_scenario(body: ScenarioCreate, project: Project = Depends(get_project), db: Session = Depends(get_db),
                    actor: str = Depends(get_actor)):
    team = [p.model_dump(mode="json") for p in body.team_configuration] if body.team_configuration else None
    params = body.planning_parameters.model_dump(mode="json", exclude_none=True) if body.planning_parameters else None
    s = svc.create_scenario(db, project, name=body.name, description=body.description,
                            base_version_id=body.base_version_id, team=team, params=params, source="manual",
                            run=body.simulate)
    audit.record(db, project_id=project.id, entity_type="scenario", entity_id=s.id, action="create", actor=actor,
                 after={"name": s.name, "team": s.team_configuration, "status": s.status})
    db.commit()
    return s


@router.get("/projects/{project_id}/scenarios", response_model=list[ScenarioOut])
def list_scenarios(project: Project = Depends(get_project), db: Session = Depends(get_db)):
    return db.scalars(select(Scenario).where(Scenario.project_id == project.id).order_by(Scenario.id)).all()


@router.get("/scenarios/{scenario_id}", response_model=ScenarioOut)
def get_scenario(scenario_id: int, db: Session = Depends(get_db)):
    return svc.get_scenario(db, scenario_id)


@router.patch("/scenarios/{scenario_id}", response_model=ScenarioOut)
def update_scenario(scenario_id: int, body: ScenarioUpdate, db: Session = Depends(get_db),
                    actor: str = Depends(get_actor)):
    s = svc.get_scenario(db, scenario_id)
    if s.status == "applied":
        raise Conflict("Un escenario aplicado no se modifica. Creá uno nuevo a partir de él.")
    if body.name is not None:
        s.name = body.name
    if body.description is not None:
        s.description = body.description
    if body.team_configuration is not None:
        s.team_configuration = [p.model_dump(mode="json") for p in body.team_configuration]
    if body.planning_parameters is not None:
        s.planning_parameters = {**s.planning_parameters,
                                 **body.planning_parameters.model_dump(mode="json", exclude_none=True)}
    s.status = "draft"
    s.results = None
    s.comparison_metrics = None
    audit.record(db, project_id=s.project_id, entity_type="scenario", entity_id=s.id, action="update", actor=actor,
                 after={"name": s.name, "team": s.team_configuration})
    db.commit()
    return s


@router.delete("/scenarios/{scenario_id}", status_code=204)
def delete_scenario(scenario_id: int, db: Session = Depends(get_db), actor: str = Depends(get_actor)):
    s = svc.get_scenario(db, scenario_id)
    if s.status == "applied":
        raise Conflict("Un escenario aplicado se conserva por trazabilidad y no puede eliminarse.")
    audit.record(db, project_id=s.project_id, entity_type="scenario", entity_id=s.id, action="delete", actor=actor,
                 before={"name": s.name})
    db.delete(s)
    db.commit()
    return Response(status_code=204)


@router.post("/scenarios/{scenario_id}/simulate", response_model=ScenarioOut)
def simulate(scenario_id: int, db: Session = Depends(get_db)):
    s = svc.get_scenario(db, scenario_id)
    svc.simulate(db, _project(db, s), s)
    db.commit()
    return s


@router.post("/projects/{project_id}/scenarios/suggest", response_model=list[ScenarioOut], status_code=201)
def suggest(body: SuggestScenariosRequest, project: Project = Depends(get_project), db: Session = Depends(get_db),
            actor: str = Depends(get_actor)):
    """Escenarios sugeridos de forma determinista (refuerzos por perfil, cuello de botella, dedicación)."""
    created = svc.suggest(db, project, body.base_version_id)
    audit.record(db, project_id=project.id, entity_type="scenario", entity_id=None, action="suggest", actor=actor,
                 after={"created": [s.name for s in created]})
    db.commit()
    return created


@router.get("/scenarios/{scenario_id}/compare")
def compare(scenario_id: int, db: Session = Depends(get_db)):
    s = svc.get_scenario(db, scenario_id)
    if not s.comparison_metrics:
        raise AppError("Simulá el escenario para poder compararlo.", code="not_simulated", status_code=422)
    project = _project(db, s)
    baseline = baseline_of(db, project.id)
    return {
        "scenario": {"id": s.id, "name": s.name, "status": s.status},
        "baseline": {"id": baseline.id, "version_number": baseline.version_number,
                     "duration": baseline.estimated_duration,
                     "completion_date": baseline.estimated_completion_date} if baseline else None,
        "metrics": s.comparison_metrics,
        "scenario_by_profile": (s.results or {}).get("by_profile", []),
        "baseline_by_profile": (baseline.metrics or {}).get("by_profile", []) if baseline else [],
        "scenario_risks": (s.results or {}).get("risks", []),
        "scenario_bottlenecks": (s.results or {}).get("bottlenecks", []),
        "assumptions": (s.results or {}).get("assumptions", []),
    }


@router.post("/scenarios/{scenario_id}/apply", status_code=201)
def apply(scenario_id: int, body: ScenarioApplyRequest, db: Session = Depends(get_db),
          actor: str = Depends(get_actor)):
    """Aplica un escenario: crea una versión nueva (la línea base y las versiones previas se conservan)."""
    s = svc.get_scenario(db, scenario_id)
    project = _project(db, s)
    if not body.confirm:
        base = get_version(db, s.base_version_id)
        return {"requires_confirmation": True, "scenario": ScenarioOut.model_validate(s).model_dump(mode="json"),
                "current_team": base.team_configuration, "new_team": s.team_configuration,
                "comparison": s.comparison_metrics}
    version = svc.apply(db, project, s, actor, body.change_reason)
    db.commit()
    return {"requires_confirmation": False, "version": version_dict(version, project)}


@router.post("/projects/{project_id}/scenarios/explain", dependencies=[Depends(ai_rate_limit)])
def explain(body: ExplainScenariosRequest, project: Project = Depends(get_project), db: Session = Depends(get_db)):
    """La IA explica los resultados ya calculados por el motor; no genera métricas."""
    q = select(Scenario).where(Scenario.project_id == project.id, Scenario.comparison_metrics.is_not(None))
    if body.scenario_ids:
        q = q.where(Scenario.id.in_(body.scenario_ids))
    rows = db.scalars(q).all()
    if not rows:
        raise AppError("No hay escenarios simulados para explicar.", code="no_scenarios", status_code=422)
    comparisons = [{"name": s.name, "description": s.description, "status": s.status,
                    "metrics": {k: v for k, v in (s.comparison_metrics or {}).items() if k != "vs_base_version"},
                    "bottlenecks": (s.results or {}).get("bottlenecks", [])[:3]} for s in rows]
    provider = get_ai_provider()
    result = run_ai(db, provider, project.id, "explain_scenarios",
                    lambda: provider.explain_scenarios(project_context(project), comparisons))
    db.commit()
    return {**result.model_dump(), "is_simulated": provider.is_simulated}
