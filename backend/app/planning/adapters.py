"""Conversión entre las estructuras persistidas (snapshots JSON) y los objetos del motor."""

from __future__ import annotations

from datetime import date
from typing import Any

from app.planning.forecast import forecast, forecast_assumption, forecast_risk, uncertainty_from
from app.planning.engine import (
    Absence,
    EngineStory,
    EngineTask,
    MemberConfig,
    DEFAULT_SENIORITY_FACTORS,
    SENIORITY_LEVELS,
    PlanningParameters,
    ProfileConfig,
    schedule,
)

DEFAULT_PARAMETERS = {
    "working_days": [0, 1, 2, 3, 4],
    "holidays": [],
    "review_overhead_pct": 10.0,
    "rework_pct": 10.0,
    "coordination_overhead_pct": 5.0,
    "qa_after_dev": True,
    "contingency_pct": 0.0,
    "seniority_factors": dict(DEFAULT_SENIORITY_FACTORS),
}


def _d(value: Any) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def parameters_from_dict(data: dict[str, Any]) -> PlanningParameters:
    merged = {**DEFAULT_PARAMETERS, **{k: v for k, v in data.items() if v is not None}}
    return PlanningParameters(
        start_date=_d(merged["start_date"]),
        working_days=[int(x) for x in merged["working_days"]],
        holidays=[_d(h) for h in merged.get("holidays", [])],
        review_overhead_pct=float(merged["review_overhead_pct"]),
        rework_pct=float(merged["rework_pct"]),
        coordination_overhead_pct=float(merged["coordination_overhead_pct"]),
        qa_after_dev=bool(merged["qa_after_dev"]),
        contingency_pct=float(merged.get("contingency_pct") or 0.0),
        seniority_factors=seniority_factors(merged.get("seniority_factors")),
        uncertainty=uncertainty_from(merged.get("uncertainty")),
    )


def seniority_factors(data: dict[str, Any] | None) -> dict[str, float]:
    given = data or {}
    return {k: float(given.get(k, DEFAULT_SENIORITY_FACTORS[k]) or 0.0) for k in SENIORITY_LEVELS}


def member_seniorities(quantity: int, mix: dict[str, Any] | None) -> list[str | None]:
    """Asigna la seniority a cada persona del perfil según la composición (SR, luego SSR, luego JR)."""
    out: list[str | None] = []
    for level in SENIORITY_LEVELS:
        out.extend([level] * max(0, int((mix or {}).get(level, 0) or 0)))
    out = out[:max(0, quantity)]
    return out + [None] * (max(0, quantity) - len(out))


def profiles_from_config(team: list[dict[str, Any]]) -> list[ProfileConfig]:
    out = []
    for p in team:
        conf = p.get("availability_configuration") or {}
        quantity = int(p.get("quantity", 0))
        given = conf.get("members", []) or []
        members = []
        for i, level in enumerate(member_seniorities(quantity, conf.get("seniority"))):
            m = given[i] if i < len(given) else {}
            members.append(MemberConfig(
                name=m.get("name") or "",
                availability_percentage=float(m.get("availability_percentage", 100) or 0),
                hours_per_day=float(m["hours_per_day"]) if m.get("hours_per_day") else None,
                absences=[Absence(_d(a["start"]), _d(a["end"])) for a in m.get("absences", []) or []],
                seniority=level,
            ))
        out.append(ProfileConfig(
            profile_key=p["profile_key"],
            profile_name=p.get("profile_name") or p["profile_key"],
            quantity=quantity,
            hours_per_day=float(p.get("available_hours_per_day", 6)),
            dedication_percentage=float(p.get("dedication_percentage", 100)),
            hourly_rate=float(p["hourly_rate"]) if p.get("hourly_rate") is not None else None,
            is_qa=bool(p.get("is_qa", False)),
            members=members,
        ))
    return out


def engine_inputs_from_snapshot(snapshot: dict[str, Any]) -> tuple[list[EngineTask], list[EngineStory]]:
    tasks: list[EngineTask] = []
    stories: list[EngineStory] = []
    order = 0
    for epic in snapshot.get("epics", []):
        for story in epic.get("stories", []):
            stories.append(EngineStory(id=str(story["id"]), depends_on=[str(x) for x in story.get("depends_on", [])]))
            for task in story.get("tasks", []):
                order += 1
                tasks.append(EngineTask(
                    id=str(task["id"]),
                    title=f"{task.get('code', '')} {task['title']}".strip(),
                    profile_key=task["profile_key"],
                    hours=float(task.get("estimated_hours", 0) or 0),
                    story_id=str(story["id"]),
                    story_title=f"{story.get('code', '')} {story['title']}".strip(),
                    epic_id=str(epic["id"]),
                    epic_title=f"{epic.get('code', '')} {epic['title']}".strip(),
                    priority=story.get("priority", "medium"),
                    confidence=story.get("estimate_confidence", "medium"),
                    depends_on=[str(x) for x in task.get("depends_on", [])],
                    order=order,
                    min_hours=_opt_float(task.get("optimistic_hours")),
                    max_hours=_opt_float(task.get("pessimistic_hours")),
                ))
    return tasks, stories


def _opt_float(v: Any) -> float | None:
    return float(v) if v is not None and v != "" else None


def run_plan(snapshot: dict[str, Any], team: list[dict[str, Any]], parameters: dict[str, Any],
             target_date: date | None = None) -> dict[str, Any]:
    tasks, stories = engine_inputs_from_snapshot(snapshot)
    profiles, params = profiles_from_config(team), parameters_from_dict(parameters)
    result = schedule(tasks, stories, profiles, params, target_date)
    f = forecast(tasks, stories, profiles, params, result, target_date)
    result["forecast"] = f
    if f:
        result["assumptions"].append(forecast_assumption(f))
        risk = forecast_risk(f)
        if risk:
            result["risks"].append(risk)
    return result
