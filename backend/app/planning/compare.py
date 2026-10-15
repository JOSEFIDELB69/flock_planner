"""Comparación de escenarios contra la línea base y generación de escenarios sugeridos.

Todas las métricas se derivan de resultados calculados por el motor; nada se estima aquí.
"""

from __future__ import annotations

import copy
from datetime import date
from typing import Any


def compare(baseline: dict[str, Any], scenario: dict[str, Any],
            baseline_team: list[dict[str, Any]], scenario_team: list[dict[str, Any]]) -> dict[str, Any]:
    b_dur = baseline["duration_working_days"]
    s_dur = scenario["duration_working_days"]
    variation = ((s_dur - b_dur) / b_dur * 100.0) if b_dur else 0.0
    b_completion = date.fromisoformat(baseline["completion_date"])
    s_completion = date.fromisoformat(scenario["completion_date"])

    b_prof = {p["profile_key"]: p for p in baseline["by_profile"]}
    s_prof = {p["profile_key"]: p for p in scenario["by_profile"]}
    b_team = {p["profile_key"]: p for p in baseline_team}
    s_team = {p["profile_key"]: p for p in scenario_team}
    capacity_changes = []
    for key in sorted(set(b_prof) | set(s_prof)):
        bp, sp = b_prof.get(key, {}), s_prof.get(key, {})
        b_q = int(b_team.get(key, {}).get("quantity", 0))
        s_q = int(s_team.get(key, {}).get("quantity", 0))
        b_cap = float(bp.get("daily_capacity", 0.0))
        s_cap = float(sp.get("daily_capacity", 0.0))
        capacity_changes.append({
            "profile_key": key,
            "profile_name": sp.get("profile_name") or bp.get("profile_name") or key,
            "baseline_quantity": b_q,
            "scenario_quantity": s_q,
            "quantity_delta": s_q - b_q,
            "baseline_daily_capacity": round(b_cap, 2),
            "scenario_daily_capacity": round(s_cap, 2),
            "daily_capacity_delta": round(s_cap - b_cap, 2),
            "baseline_utilization": bp.get("utilization", 0.0),
            "scenario_utilization": sp.get("utilization", 0.0),
        })

    cost_delta = None
    if baseline.get("total_cost") is not None and scenario.get("total_cost") is not None:
        cost_delta = round(scenario["total_cost"] - baseline["total_cost"], 2)

    staffing_delta = None
    if baseline.get("total_staffing_cost") is not None and scenario.get("total_staffing_cost") is not None:
        staffing_delta = round(scenario["total_staffing_cost"] - baseline["total_staffing_cost"], 2)

    return {
        "baseline_staffing_cost": baseline.get("total_staffing_cost"),
        "scenario_staffing_cost": scenario.get("total_staffing_cost"),
        "staffing_cost_delta": staffing_delta,
        "added_people": sum(c["quantity_delta"] for c in capacity_changes),
        "baseline_contingency_pct": baseline.get("contingency_pct", 0.0),
        "scenario_contingency_pct": scenario.get("contingency_pct", 0.0),
        "baseline_contingency_days": baseline.get("contingency_days", 0),
        "scenario_contingency_days": scenario.get("contingency_days", 0),
        "scenario_work_duration": scenario.get("work_duration_days", s_dur),
        "baseline_p80": (baseline.get("forecast") or {}).get("p80"),
        "scenario_p80": (scenario.get("forecast") or {}).get("p80"),
        "baseline_probability_plan": (baseline.get("forecast") or {}).get("probability_plan"),
        "scenario_probability_plan": (scenario.get("forecast") or {}).get("probability_plan"),
        "baseline_duration": b_dur,
        "scenario_duration": s_dur,
        "time_savings_days": b_dur - s_dur,
        "variation_pct": round(variation, 2),
        "baseline_completion_date": baseline["completion_date"],
        "scenario_completion_date": scenario["completion_date"],
        "completion_delta_calendar_days": (s_completion - b_completion).days,
        "baseline_effort": baseline["planned_effort_hours"],
        "scenario_effort": scenario["planned_effort_hours"],
        "effort_delta": round(scenario["planned_effort_hours"] - baseline["planned_effort_hours"], 2),
        "baseline_cost": baseline.get("total_cost"),
        "scenario_cost": scenario.get("total_cost"),
        "cost_delta": cost_delta,
        "capacity_changes": capacity_changes,
        "baseline_main_bottleneck": baseline.get("main_bottleneck"),
        "scenario_main_bottleneck": scenario.get("main_bottleneck"),
    }


def recommendation_key(name: str, metrics: dict[str, Any]) -> tuple:
    """Orden determinista de recomendación: menor duración, luego menor coste de equipo, menos personas, nombre."""
    staffing = metrics.get("staffing_cost_delta")
    return (metrics["scenario_duration"], staffing if staffing is not None else 0.0,
            metrics.get("added_people", 0), name)


def suggest_team_variants(team: list[dict[str, Any]], baseline_result: dict[str, Any]) -> list[dict[str, Any]]:
    """Variantes deterministas: +1 por perfil con trabajo, refuerzo del cuello de botella y dedicación plena."""
    with_work = {p["profile_key"] for p in baseline_result["by_profile"] if p["planned_hours"] > 0}
    names = {p["profile_key"]: p["profile_name"] for p in team}
    variants: list[dict[str, Any]] = []

    for p in team:
        if p["profile_key"] not in with_work:
            continue
        t = copy.deepcopy(team)
        for q in t:
            if q["profile_key"] == p["profile_key"]:
                q["quantity"] = int(q["quantity"]) + 1
        variants.append({
            "name": f"+1 {p['profile_name']}",
            "description": f"Suma una persona al perfil {p['profile_name']} manteniendo el resto del equipo.",
            "team": t,
            "single_profile": p["profile_key"],
        })

    ranked = [b["profile_key"] for b in baseline_result.get("bottlenecks", []) if b["profile_key"] in with_work]
    if len(ranked) >= 2:
        a, b = ranked[0], ranked[1]
        t = copy.deepcopy(team)
        for q in t:
            if q["profile_key"] in (a, b):
                q["quantity"] = int(q["quantity"]) + 1
        variants.append({
            "name": f"Refuerzo de {names[a]} y {names[b]}",
            "description": "Suma una persona en los dos perfiles con mayor peso en el camino crítico y la utilización.",
            "team": t,
            "single_profile": None,
        })

    if any(float(p.get("dedication_percentage", 100)) < 100 for p in team):
        t = copy.deepcopy(team)
        for q in t:
            q["dedication_percentage"] = 100.0
        variants.append({
            "name": "Dedicación plena del equipo actual",
            "description": "Lleva la dedicación de todos los perfiles al 100 % sin sumar personas.",
            "team": t,
            "single_profile": None,
        })
    return variants


def ineffective_profiles(baseline_result: dict[str, Any], variant_results: list[tuple[dict[str, Any], dict[str, Any]]]) -> list[str]:
    """Perfiles cuyo +1 no mejora el plazo (variante de perfil único sin ahorro)."""
    out = []
    for variant, result in variant_results:
        key = variant.get("single_profile")
        if key and result["duration_working_days"] >= baseline_result["duration_working_days"]:
            out.append(key)
    return out
