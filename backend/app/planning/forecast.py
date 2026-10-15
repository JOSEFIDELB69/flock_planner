"""Pronóstico probabilístico del plazo por simulación Monte Carlo sobre el motor real.

Cada tarea tiene un rango de horas (optimista, probable, pesimista). Si la tarea no trae rango propio,
se deriva de la confianza de su historia (por defecto alta −10 %/+25 %, media −15 %/+50 %,
baja −25 %/+100 %). En cada corrida se sortean las horas de todas las tareas con una distribución
triangular y se vuelve a calcular el cronograma completo con el mismo motor (dependencias, capacidad,
seniority, calendario). El resultado es la distribución de la fecha de fin del trabajo: P50, P80, P90
y la probabilidad de cumplir la fecha del plan y la fecha objetivo.

* Los errores de estimación de un mismo proyecto no son independientes (suelen desviarse todos en el
  mismo sentido): se usa una cópula gaussiana con correlación 0,3 entre tareas.
* La semilla es fija: mismos datos → mismo resultado (el pronóstico es reproducible y auditable).
"""

from __future__ import annotations

import math
import random
from dataclasses import replace
from datetime import date, timedelta
from typing import Any

from app.planning.engine import EPS, EngineStory, EngineTask, PlanningParameters, ProfileConfig, \
    project_working_days, schedule

RUNS = 500
SEED = 20261009
CORRELATION = 0.3
CONFIDENCE_LEVELS = ("high", "medium", "low")
# % sobre las horas probables: [optimista, pesimista]
DEFAULT_UNCERTAINTY = {"high": [-10.0, 25.0], "medium": [-15.0, 50.0], "low": [-25.0, 100.0]}


def uncertainty_from(data: dict[str, Any] | None) -> dict[str, list[float]]:
    out = {}
    for level in CONFIDENCE_LEVELS:
        lo, hi = (data or {}).get(level) or DEFAULT_UNCERTAINTY[level]
        lo, hi = max(-95.0, min(0.0, float(lo))), max(0.0, float(hi))
        out[level] = [lo, hi]
    return out


def task_range(task: EngineTask, uncertainty: dict[str, list[float]]) -> tuple[float, float, float]:
    """(optimista, probable, pesimista) en horas de esfuerzo base."""
    m = task.hours
    if task.min_hours is not None and task.max_hours is not None and task.min_hours <= m + EPS \
            and task.max_hours >= m - EPS and task.max_hours > task.min_hours:
        return task.min_hours, m, task.max_hours
    lo, hi = uncertainty.get(task.confidence, uncertainty["medium"])
    return m * (1 + lo / 100.0), m, m * (1 + hi / 100.0)


def _triangular(u: float, a: float, m: float, b: float) -> float:
    if b - a <= EPS:
        return m
    fc = (m - a) / (b - a)
    if u < fc:
        return a + math.sqrt(u * (b - a) * (m - a))
    return b - math.sqrt((1 - u) * (b - a) * (b - m))


def _phi(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def forecast(tasks: list[EngineTask], stories: list[EngineStory], profiles: list[ProfileConfig],
             params: PlanningParameters, result: dict[str, Any], target_date: date | None = None,
             runs: int = RUNS) -> dict[str, Any] | None:
    if not tasks or result.get("work_duration_days", 0) <= 0:
        return None
    uncertainty = uncertainty_from(params.uncertainty)
    ranges = [task_range(t, uncertainty) for t in tasks]
    rng = random.Random(SEED)
    rho_g, rho_e = math.sqrt(CORRELATION), math.sqrt(1.0 - CORRELATION)
    samples: list[tuple[int, int]] = []  # (días laborables de trabajo, índice del último día)
    for _ in range(runs):
        g = rng.gauss(0.0, 1.0)
        sampled = [replace(t, hours=_triangular(_phi(rho_g * g + rho_e * rng.gauss(0.0, 1.0)), *r))
                   for t, r in zip(tasks, ranges)]
        finish = schedule(sampled, stories, profiles, params, metrics=False)["finish"]
        last_day = max(0, math.floor(finish - EPS))
        samples.append((project_working_days(params, 0, last_day), last_day))
    samples.sort()

    def pct(p: float) -> dict[str, Any]:
        days, last_day = samples[min(len(samples) - 1, max(0, math.ceil(p * len(samples)) - 1))]
        return {"working_days": days, "date": (params.start_date + timedelta(days=last_day)).isoformat()}

    def prob(max_days: int) -> float:
        return round(sum(1 for d, _ in samples if d <= max_days) / len(samples), 4)

    work_days = result["work_duration_days"]
    plan_days = result["duration_working_days"]
    p80 = pct(0.8)["working_days"]
    curve, seen = [], set()
    for i, (d, last_day) in enumerate(samples):
        if d in seen:
            continue
        seen.add(d)
        n = sum(1 for x, _ in samples if x <= d)
        curve.append({"working_days": d, "date": (params.start_date + timedelta(days=last_day)).isoformat(),
                      "probability": round(n / len(samples), 4)})
    target_probability = None
    if target_date:
        target_probability = round(
            sum(1 for _, ld in samples if params.start_date + timedelta(days=ld) <= target_date) / len(samples), 4)
    base = sum(t.hours for t in tasks)
    return {
        "method": "monte_carlo",
        "runs": runs,
        "seed": SEED,
        "correlation": CORRELATION,
        "uncertainty": uncertainty,
        "tasks_with_own_range": sum(1 for t in tasks if t.min_hours is not None and t.max_hours is not None),
        "base_hours_range": [round(sum(r[0] for r in ranges), 1), round(base, 1), round(sum(r[2] for r in ranges), 1)],
        "p50": pct(0.5),
        "p80": pct(0.8),
        "p90": pct(0.9),
        "min_working_days": samples[0][0],
        "max_working_days": samples[-1][0],
        "mean_working_days": round(sum(d for d, _ in samples) / len(samples), 1),
        "probability_work_only": prob(work_days),
        "probability_plan": prob(plan_days),
        "probability_target": target_probability,
        "contingency_for_p80_pct": max(0, math.ceil((p80 / work_days - 1) * 100 - EPS)) if work_days else 0,
        "curve": curve,
    }


def forecast_assumption(f: dict[str, Any]) -> str:
    u = f["uncertainty"]
    return (f"Probabilidad de cumplimiento: simulación Monte Carlo de {f['runs']} escenarios sobre el mismo motor. "
            f"Cada tarea usa su rango optimista–pesimista o, si no lo tiene, el de la confianza de su historia "
            f"(alta {u['high'][0]:g}/+{u['high'][1]:g} %, media {u['medium'][0]:g}/+{u['medium'][1]:g} %, "
            f"baja {u['low'][0]:g}/+{u['low'][1]:g} %), con distribución triangular y correlación "
            f"{str(f['correlation']).replace('.', ',')} entre tareas. Semilla fija: el resultado es reproducible.")


def forecast_risk(f: dict[str, Any]) -> dict[str, Any] | None:
    p = f["probability_plan"]
    if p >= 0.7:
        return None
    return {
        "title": "Baja probabilidad de cumplir la fecha del plan",
        "severity": "high" if p < 0.5 else "medium",
        "detail": (f"Según la simulación, la fecha del plan se cumple en el {round(p * 100)} % de los escenarios. "
                   f"Con 80 % de confianza el trabajo termina el "
                   f"{date.fromisoformat(f['p80']['date']).strftime('%d/%m/%Y')} ({f['p80']['working_days']} días "
                   f"laborables); para cubrirlo hace falta una reserva por imprevistos de al menos "
                   f"{f['contingency_for_p80_pct']} %."),
        "source": "engine",
    }
