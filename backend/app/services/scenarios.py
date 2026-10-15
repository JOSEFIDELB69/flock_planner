"""Escenarios de optimización: simulan sobre una copia de la configuración, nunca sobre la línea base."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.errors import AppError, Conflict, NotFound
from app.models import PlanVersion, Project, Scenario, TeamProfile, utcnow
from app.planning.compare import compare, ineffective_profiles, suggest_team_variants
from app.planning.engine import PlanningError
from app.services import audit
from app.services.plans import baseline_of, compute, create_version, get_version, resolve_parameters


def get_scenario(db: Session, scenario_id: int) -> Scenario:
    s = db.get(Scenario, scenario_id)
    if s is None:
        raise NotFound("No encontramos el escenario.")
    return s


def base_version_for(db: Session, project: Project, base_version_id: int | None) -> PlanVersion:
    vid = base_version_id or project.active_plan_version_id
    if vid is None:
        raise AppError("Primero confirmá la planificación inicial (línea base) para poder simular escenarios.",
                       code="no_baseline", status_code=422)
    v = get_version(db, vid)
    if v.project_id != project.id:
        raise NotFound("La versión base no pertenece al proyecto.")
    return v


def simulate(db: Session, project: Project, scenario: Scenario) -> Scenario:
    base = get_version(db, scenario.base_version_id)
    baseline = baseline_of(db, project.id) or base
    try:
        result = compute(project, base.backlog_snapshot, scenario.team_configuration, scenario.planning_parameters)
    except PlanningError as exc:
        scenario.status = "error"
        scenario.error_message = exc.message
        scenario.results = None
        scenario.comparison_metrics = None
        db.flush()
        return scenario
    baseline_result = {**baseline.metrics, "schedule": baseline.schedule}
    metrics = compare(baseline_result, result, baseline.team_configuration, scenario.team_configuration)
    metrics["baseline_version_id"] = baseline.id
    metrics["baseline_version_number"] = baseline.version_number
    if base.id != baseline.id:
        vs_base = compare({**base.metrics, "schedule": base.schedule}, result, base.team_configuration,
                          scenario.team_configuration)
        metrics["vs_base_version"] = {"version_id": base.id, "version_number": base.version_number, **vs_base}
    scenario.results = result
    scenario.estimated_effort = result["planned_effort_hours"]
    scenario.estimated_duration = result["duration_working_days"]
    scenario.estimated_completion_date = date.fromisoformat(result["completion_date"])
    scenario.comparison_metrics = metrics
    if scenario.status != "applied":
        scenario.status = "simulated"
    scenario.error_message = ""
    scenario.simulated_at = utcnow()
    db.flush()
    return scenario


def create_scenario(db: Session, project: Project, *, name: str, description: str, base_version_id: int | None,
                    team: list[dict[str, Any]] | None, params: dict[str, Any] | None, source: str,
                    run: bool) -> Scenario:
    base = base_version_for(db, project, base_version_id)
    merged_params = resolve_parameters(project, {**base.planning_parameters, **(params or {})})
    scenario = Scenario(
        project_id=project.id, base_version_id=base.id, name=name, description=description, source=source,
        team_configuration=team if team is not None else [dict(p) for p in base.team_configuration],
        planning_parameters=merged_params, status="draft",
    )
    db.add(scenario)
    db.flush()
    if run:
        simulate(db, project, scenario)
    return scenario


def suggest(db: Session, project: Project, base_version_id: int | None) -> list[Scenario]:
    base = base_version_for(db, project, base_version_id)
    base_result = {**base.metrics, "schedule": base.schedule}
    variants = suggest_team_variants(base.team_configuration, base_result)
    existing = set(db.scalars(select(Scenario.name).where(Scenario.project_id == project.id,
                                                          Scenario.base_version_id == base.id)).all())
    created: list[Scenario] = []
    for v in variants:
        if v["name"] in existing:
            continue
        created.append(create_scenario(db, project, name=v["name"], description=v["description"],
                                       base_version_id=base.id, team=v["team"], params=None, source="suggested",
                                       run=True))
    # perfiles que no mejoran el plazo al sumar capacidad (sobre todas las variantes de perfil único)
    all_s = db.scalars(select(Scenario).where(Scenario.project_id == project.id,
                                              Scenario.base_version_id == base.id,
                                              Scenario.source == "suggested")).all()
    pairs = []
    for s in all_s:
        variant = next((v for v in variants if v["name"] == s.name), None)
        if variant and s.results:
            pairs.append((variant, s.results))
    no_gain = ineffective_profiles(base_result, pairs)
    for s in all_s:
        if s.comparison_metrics is not None:
            s.comparison_metrics = {**s.comparison_metrics, "profiles_without_gain": no_gain}
    db.flush()
    return created


def apply(db: Session, project: Project, scenario: Scenario, actor: str, change_reason: str) -> PlanVersion:
    if scenario.status == "applied":
        raise Conflict("Este escenario ya fue aplicado.", {"applied_version_id": scenario.applied_version_id})
    if scenario.status != "simulated" or not scenario.results:
        raise AppError("Simulá el escenario antes de aplicarlo.", code="not_simulated", status_code=422)
    base = get_version(db, scenario.base_version_id)
    # se recalcula para garantizar que la versión refleja exactamente la configuración guardada
    result = compute(project, base.backlog_snapshot, scenario.team_configuration, scenario.planning_parameters)
    version = create_version(
        db, project, team=scenario.team_configuration, params=scenario.planning_parameters,
        snapshot=base.backlog_snapshot, result=result, actor=actor, label=f"Escenario: {scenario.name}"[:200],
        change_reason=change_reason or f"Aplicación del escenario '{scenario.name}'", source_scenario_id=scenario.id,
    )
    # la configuración del equipo del proyecto pasa a ser la del escenario aplicado
    before_team = [{"profile_key": p.profile_key, "quantity": p.quantity} for p in project.team_profiles]
    db.execute(delete(TeamProfile).where(TeamProfile.project_id == project.id))
    for p in scenario.team_configuration:
        db.add(TeamProfile(project_id=project.id, **{k: p.get(k) for k in (
            "profile_key", "profile_name", "quantity", "available_hours_per_day", "dedication_percentage",
            "hourly_rate", "is_qa")}, availability_configuration=p.get("availability_configuration") or {"members": []}))
    scenario.status = "applied"
    scenario.applied_version_id = version.id
    audit.record(db, project_id=project.id, entity_type="scenario", entity_id=scenario.id, action="apply",
                 actor=actor, before={"team": before_team},
                 after={"applied_version_id": version.id, "team": scenario.team_configuration},
                 reason=version.change_reason)
    db.flush()
    db.expire(project, ["team_profiles"])
    return version
