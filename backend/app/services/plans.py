"""Servicios de planificación: parámetros, cálculo con el motor y versiones inmutables."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import AppError, NotFound
from app.models import PlanVersion, Project, TeamProfile
from app.planning.adapters import DEFAULT_PARAMETERS, run_plan
from app.services import audit
from app.services.backlog import backlog_snapshot

# Configuración inicial editable (horas productivas, no jornada completa).
DEFAULT_TEAM = [
    {"profile_key": "frontend", "profile_name": "Desarrollador Frontend", "quantity": 1,
     "available_hours_per_day": 6.0, "dedication_percentage": 100.0, "hourly_rate": None, "is_qa": False},
    {"profile_key": "backend", "profile_name": "Desarrollador Backend", "quantity": 1,
     "available_hours_per_day": 6.0, "dedication_percentage": 100.0, "hourly_rate": None, "is_qa": False},
    {"profile_key": "qa", "profile_name": "QA Engineer", "quantity": 1,
     "available_hours_per_day": 6.0, "dedication_percentage": 100.0, "hourly_rate": None, "is_qa": True},
]

PROFILE_CATALOG = [
    *DEFAULT_TEAM,
    {"profile_key": "devops", "profile_name": "DevOps", "is_qa": False},
    {"profile_key": "uxui", "profile_name": "Diseñador UX/UI", "is_qa": False},
    {"profile_key": "architect", "profile_name": "Arquitecto de software", "is_qa": False},
    {"profile_key": "security", "profile_name": "Especialista en seguridad", "is_qa": False},
    {"profile_key": "data", "profile_name": "Data Engineer", "is_qa": False},
]


def add_default_team(db: Session, project: Project) -> None:
    for p in DEFAULT_TEAM:
        db.add(TeamProfile(project_id=project.id, availability_configuration={"members": []}, **p))


def team_config(db: Session, project: Project) -> list[dict[str, Any]]:
    profiles = db.scalars(select(TeamProfile).where(TeamProfile.project_id == project.id)
                          .order_by(TeamProfile.id)).all()
    return [
        {
            "profile_key": p.profile_key,
            "profile_name": p.profile_name,
            "quantity": p.quantity,
            "available_hours_per_day": p.available_hours_per_day,
            "dedication_percentage": p.dedication_percentage,
            "hourly_rate": p.hourly_rate,
            "is_qa": p.is_qa,
            "availability_configuration": p.availability_configuration or {"members": []},
        }
        for p in profiles
    ]


def next_working_day(d: date, working_days: list[int]) -> date:
    for _ in range(14):
        if d.weekday() in working_days:
            return d
        d += timedelta(days=1)
    return d


def resolve_parameters(project: Project, given: dict[str, Any] | None) -> dict[str, Any]:
    given = {k: v for k, v in (given or {}).items() if v is not None}
    cal = project.calendar_configuration or {}
    working = given.get("working_days") or cal.get("working_days") or DEFAULT_PARAMETERS["working_days"]
    holidays = given.get("holidays") if "holidays" in given else cal.get("holidays", [])
    start = given.get("start_date") or next_working_day(date.today(), working)
    params = {
        **DEFAULT_PARAMETERS,
        **given,
        "start_date": start.isoformat() if isinstance(start, date) else str(start),
        "working_days": sorted({int(x) for x in working}),
        "holidays": sorted({h.isoformat() if isinstance(h, date) else str(h) for h in holidays}),
    }
    return params


def compute(project: Project, snapshot: dict[str, Any], team: list[dict[str, Any]],
            params: dict[str, Any]) -> dict[str, Any]:
    if not any(s.get("tasks") for e in snapshot.get("epics", []) for s in e.get("stories", [])):
        raise AppError("El backlog no tiene tareas estimadas. Generá o cargá el backlog antes de planificar.",
                       code="empty_backlog", status_code=422)
    return run_plan(snapshot, team, params, project.target_date)


def get_version(db: Session, plan_id: int) -> PlanVersion:
    v = db.get(PlanVersion, plan_id)
    if v is None:
        raise NotFound("No encontramos la versión del plan.")
    return v


def baseline_of(db: Session, project_id: int) -> PlanVersion | None:
    return db.scalars(select(PlanVersion).where(PlanVersion.project_id == project_id,
                                                PlanVersion.is_baseline.is_(True))).first()


def create_version(db: Session, project: Project, *, team: list[dict[str, Any]], params: dict[str, Any],
                   snapshot: dict[str, Any], result: dict[str, Any], actor: str, label: str = "",
                   change_reason: str = "", source_scenario_id: int | None = None,
                   restored_from_version_id: int | None = None) -> PlanVersion:
    """Crea una versión nueva (nunca modifica otras). La primera de un proyecto es la línea base."""
    current_max = db.scalar(select(func.max(PlanVersion.version_number))
                            .where(PlanVersion.project_id == project.id)) or 0
    is_baseline = baseline_of(db, project.id) is None
    metrics = {k: v for k, v in result.items() if k != "schedule"}
    version = PlanVersion(
        project_id=project.id,
        version_number=current_max + 1,
        label=label or ("Línea base" if is_baseline else f"Versión {current_max + 1}"),
        is_baseline=is_baseline,
        source_scenario_id=source_scenario_id,
        restored_from_version_id=restored_from_version_id,
        team_configuration=team,
        planning_parameters=params,
        backlog_snapshot=snapshot,
        schedule=result["schedule"],
        metrics=metrics,
        estimated_effort=result["planned_effort_hours"],
        estimated_duration=result["duration_working_days"],
        start_date=date.fromisoformat(result["start_date"]),
        estimated_completion_date=date.fromisoformat(result["completion_date"]),
        assumptions=result["assumptions"],
        risks=result["risks"],
        change_reason=change_reason or ("Planificación inicial confirmada" if is_baseline else ""),
        created_by=actor,
    )
    db.add(version)
    db.flush()
    before_active = project.active_plan_version_id
    project.active_plan_version_id = version.id
    if project.status == "draft":
        project.status = "active"
    audit.record(db, project_id=project.id, entity_type="plan_version", entity_id=version.id, action="create",
                 actor=actor, before={"active_plan_version_id": before_active},
                 after={"version_number": version.version_number, "is_baseline": is_baseline,
                        "duration": version.estimated_duration, "effort": version.estimated_effort,
                        "completion": version.estimated_completion_date.isoformat(),
                        "source_scenario_id": source_scenario_id, "team": team},
                 reason=version.change_reason)
    return version


def generate_current(db: Session, project: Project, params_in: dict[str, Any] | None) -> tuple[
        list[dict[str, Any]], dict[str, Any], dict[str, Any], dict[str, Any]]:
    team = team_config(db, project)
    params = resolve_parameters(project, params_in)
    snapshot = backlog_snapshot(db, project)
    result = compute(project, snapshot, team, params)
    return team, params, snapshot, result


def version_dict(v: PlanVersion, project: Project, full: bool = True) -> dict[str, Any]:
    data = {
        "id": v.id, "project_id": v.project_id, "version_number": v.version_number, "label": v.label,
        "is_baseline": v.is_baseline, "is_active": project.active_plan_version_id == v.id,
        "source_scenario_id": v.source_scenario_id, "estimated_effort": v.estimated_effort,
        "estimated_duration": v.estimated_duration, "start_date": v.start_date,
        "estimated_completion_date": v.estimated_completion_date, "change_reason": v.change_reason,
        "created_at": v.created_at, "created_by": v.created_by,
        "main_bottleneck": (v.metrics or {}).get("main_bottleneck"),
        "total_cost": (v.metrics or {}).get("total_cost"),
    }
    if full:
        data.update({
            "restored_from_version_id": v.restored_from_version_id,
            "team_configuration": v.team_configuration, "planning_parameters": v.planning_parameters,
            "metrics": v.metrics, "schedule": v.schedule, "backlog_snapshot": v.backlog_snapshot,
            "assumptions": v.assumptions, "risks": v.risks, "executive_summary": v.executive_summary,
            "executive_summary_simulated": v.executive_summary_simulated,
        })
    return data
