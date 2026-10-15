"""Motor de planificación determinista de Flock Planner.

La IA propone tareas y horas; este motor calcula la duración calendario respetando:

* dependencias explícitas entre tareas y entre historias,
* QA de una historia después de su desarrollo (configurable),
* capacidad diaria de cada profesional (horas productivas × dedicación × disponibilidad),
* calendario laboral, feriados y ausencias individuales,
* sobrecostos de revisión, retrabajo y coordinación,
* una tarea es ejecutada por una sola persona (la paralelización está limitada por la
  granularidad del backlog; sumar gente no reduce el plazo de forma proporcional).

Algoritmo: list scheduling con prioridad por "rango ascendente" (camino más largo de horas
hasta el final) e inserción en huecos libres de cada recurso. El tiempo se mide en días
fraccionarios desde la fecha de inicio: durante el día d, un recurso trabaja a razón de
capacidad(d) horas por día.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

EPS = 1e-9
MAX_HORIZON_DAYS = 5 * 366
PRIORITY_WEIGHT = {"critical": 4, "high": 3, "medium": 2, "low": 1}


class PlanningError(Exception):
    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


@dataclass
class EngineTask:
    id: str
    title: str
    profile_key: str
    hours: float
    story_id: str = ""
    story_title: str = ""
    epic_id: str = ""
    epic_title: str = ""
    priority: str = "medium"
    confidence: str = "medium"
    depends_on: list[str] = field(default_factory=list)
    order: int = 0
    min_hours: float | None = None  # rango propio (optimista / pesimista) para el pronóstico Monte Carlo
    max_hours: float | None = None


@dataclass
class EngineStory:
    id: str
    depends_on: list[str] = field(default_factory=list)


@dataclass
class Absence:
    start: date
    end: date


SENIORITY_LEVELS = ("sr", "ssr", "jr")
SENIORITY_LABELS = {"sr": "Senior", "ssr": "Semi senior", "jr": "Junior"}
# % que se suma (o resta, si es negativo) al tiempo de cada tarea según la seniority de quien la hace
DEFAULT_SENIORITY_FACTORS = {"sr": -15.0, "ssr": 0.0, "jr": 30.0}


@dataclass
class MemberConfig:
    name: str = ""
    availability_percentage: float = 100.0
    hours_per_day: float | None = None
    absences: list[Absence] = field(default_factory=list)
    seniority: str | None = None  # sr | ssr | jr; None = sin definir (sin ajuste)


@dataclass
class ProfileConfig:
    profile_key: str
    profile_name: str
    quantity: int
    hours_per_day: float = 6.0
    dedication_percentage: float = 100.0
    hourly_rate: float | None = None
    is_qa: bool = False
    members: list[MemberConfig] = field(default_factory=list)


@dataclass
class PlanningParameters:
    start_date: date
    working_days: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4])
    holidays: list[date] = field(default_factory=list)
    review_overhead_pct: float = 10.0
    rework_pct: float = 10.0
    coordination_overhead_pct: float = 5.0
    min_efficiency: float = 0.6
    qa_after_dev: bool = True
    contingency_pct: float = 0.0  # Reserva por imprevistos: % de la duración que se reserva al final
    seniority_factors: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_SENIORITY_FACTORS))
    # rangos por confianza para el pronóstico: {"high": [-10, 25], ...}; None = valores por defecto
    uncertainty: dict[str, list[float]] | None = None

    def seniority_pct(self, seniority: str | None) -> float:
        return float(self.seniority_factors.get(seniority, 0.0)) if seniority else 0.0


# --------------------------------------------------------------------------- recursos


class Member:
    def __init__(self, uid: str, name: str, profile: ProfileConfig, daily_capacity: float, absences: set[date],
                 params: PlanningParameters, efficiency: float = 1.0, seniority: str | None = None):
        self.uid = uid
        self.seniority = seniority
        self.seniority_pct = params.seniority_pct(seniority)
        # multiplicador del tiempo de trabajo (p. ej. JR +30 % → 1,3); nunca menos del 10 % del tiempo base
        self.time_factor = max(0.1, 1.0 + self.seniority_pct / 100.0)
        self.efficiency = efficiency
        self.name = name
        self.profile = profile
        self.daily_capacity = daily_capacity
        self.absences = absences
        self.params = params
        self.intervals: list[tuple[float, float]] = []
        self._holidays = set(params.holidays)
        self._working = set(params.working_days)
        self._cap_cache: dict[int, float] = {}

    def capacity(self, day: int) -> float:
        cached = self._cap_cache.get(day)
        if cached is not None:
            return cached
        d = self.params.start_date + timedelta(days=day)
        cap = 0.0
        if d.weekday() in self._working and d not in self._holidays and d not in self.absences:
            cap = self.daily_capacity
        self._cap_cache[day] = cap
        return cap

    def work(self, start: float, hours: float) -> tuple[float, float]:
        """Devuelve (inicio_real, fin) de `hours` horas de trabajo empezando no antes de `start`."""
        day = math.floor(start + EPS)
        frac = max(0.0, start - day)
        # avanzar hasta el primer momento con capacidad
        while self.capacity(day) <= 0:
            day += 1
            frac = 0.0
            if day > MAX_HORIZON_DAYS:
                raise PlanningError(
                    f"{self.name} no tiene capacidad disponible dentro del horizonte de planificación."
                )
        actual_start = day + frac
        if hours <= EPS:
            return actual_start, actual_start
        remaining = hours
        while True:
            cap = self.capacity(day)
            if cap > 0:
                available = cap * (1.0 - frac)
                if available >= remaining - EPS:
                    return actual_start, day + frac + remaining / cap
                remaining -= available
            day += 1
            frac = 0.0
            if day > MAX_HORIZON_DAYS:
                raise PlanningError(
                    "La planificación excede el horizonte de 5 años. Revisá la capacidad del equipo y las horas."
                )

    def earliest_slot(self, ready: float, hours: float) -> tuple[float, float]:
        candidates = sorted({ready, *[f for (_s, f) in self.intervals if f > ready]})
        for c in candidates:
            if any(s + EPS < c < f - EPS for s, f in self.intervals):
                continue
            a, b = self.work(c, hours)
            if all(f <= a + EPS or s >= b - EPS for s, f in self.intervals):
                return a, b
        raise AssertionError("unreachable: siempre existe un hueco después del último intervalo")

    def book(self, a: float, b: float) -> None:
        self.intervals.append((a, b))
        self.intervals.sort()

    def capacity_between(self, first_day: int, last_day: int) -> float:
        return sum(self.capacity(d) for d in range(first_day, last_day + 1))


def build_members(profiles: list[ProfileConfig], params: PlanningParameters) -> dict[str, list[Member]]:
    by_profile: dict[str, list[Member]] = {}
    for p in profiles:
        n = max(0, int(p.quantity))
        efficiency = max(params.min_efficiency, 1.0 - params.coordination_overhead_pct / 100.0 * max(0, n - 1))
        members: list[Member] = []
        for i in range(n):
            override = p.members[i] if i < len(p.members) else MemberConfig()
            hours = override.hours_per_day if override.hours_per_day else p.hours_per_day
            cap = hours * (p.dedication_percentage / 100.0) * (override.availability_percentage / 100.0) * efficiency
            absences: set[date] = set()
            for ab in override.absences:
                d = ab.start
                while d <= ab.end:
                    absences.add(d)
                    d += timedelta(days=1)
            name = override.name or f"{p.profile_name} {i + 1}"
            if cap > EPS:
                members.append(Member(f"{p.profile_key}-{i + 1}", name, p, cap, absences, params, efficiency,
                                      override.seniority))
        by_profile[p.profile_key] = members
    return by_profile


# --------------------------------------------------------------------------- calendario


def day_to_date(params: PlanningParameters, day_float: float, is_end: bool = False) -> date:
    idx = math.floor(day_float - EPS) if is_end else math.floor(day_float + EPS)
    return params.start_date + timedelta(days=max(0, idx))


def add_working_days(params: PlanningParameters, from_day: int, working_days: int) -> int:
    """Día (índice) que resulta de sumar `working_days` días laborables del proyecto después de `from_day`."""
    holidays = set(params.holidays)
    working = set(params.working_days)
    day, added = from_day, 0
    while added < working_days:
        day += 1
        dt = params.start_date + timedelta(days=day)
        if dt.weekday() in working and dt not in holidays:
            added += 1
        if day - from_day > MAX_HORIZON_DAYS:
            raise PlanningError("La reserva por imprevistos excede el horizonte de planificación.")
    return day


def project_working_days(params: PlanningParameters, first_day: int, last_day: int) -> int:
    holidays = set(params.holidays)
    working = set(params.working_days)
    count = 0
    for d in range(first_day, last_day + 1):
        dt = params.start_date + timedelta(days=d)
        if dt.weekday() in working and dt not in holidays:
            count += 1
    return count


# --------------------------------------------------------------------------- grafo


def effective_hours(task: EngineTask, profile: ProfileConfig | None, params: PlanningParameters) -> float:
    if profile is not None and profile.is_qa:
        return task.hours
    return task.hours * (1.0 + (params.review_overhead_pct + params.rework_pct) / 100.0)


def build_graph(tasks: list[EngineTask], stories: list[EngineStory], qa_profiles: set[str],
                params: PlanningParameters) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    ids = {t.id for t in tasks}
    preds: dict[str, set[str]] = {t.id: set() for t in tasks}
    by_story: dict[str, list[EngineTask]] = defaultdict(list)
    for t in tasks:
        by_story[t.story_id].append(t)
        for dep in t.depends_on:
            if dep in ids and dep != t.id:
                preds[t.id].add(dep)
    for s in stories:
        for dep_story in s.depends_on:
            for t in by_story.get(s.id, []):
                for d in by_story.get(dep_story, []):
                    preds[t.id].add(d.id)
    if params.qa_after_dev:
        for story_tasks in by_story.values():
            dev = [t.id for t in story_tasks if t.profile_key not in qa_profiles]
            for t in story_tasks:
                if t.profile_key in qa_profiles:
                    preds[t.id].update(dev)
    succs: dict[str, set[str]] = {t.id: set() for t in tasks}
    for tid, ps in preds.items():
        for p in ps:
            succs[p].add(tid)
    return preds, succs


def topological_order(preds: dict[str, set[str]], succs: dict[str, set[str]]) -> list[str]:
    indeg = {k: len(v) for k, v in preds.items()}
    queue = sorted(k for k, v in indeg.items() if v == 0)
    order: list[str] = []
    while queue:
        n = queue.pop(0)
        order.append(n)
        for s in sorted(succs[n]):
            indeg[s] -= 1
            if indeg[s] == 0:
                queue.append(s)
    if len(order) != len(preds):
        cyclic = sorted(k for k, v in indeg.items() if v > 0)
        raise PlanningError(
            "Hay dependencias circulares en el backlog. Revisá las dependencias de las tareas indicadas.",
            {"tasks": cyclic},
        )
    return order


# --------------------------------------------------------------------------- motor


def schedule(
    tasks: list[EngineTask],
    stories: list[EngineStory],
    profiles: list[ProfileConfig],
    params: PlanningParameters,
    target_date: date | None = None,
    metrics: bool = True,
) -> dict[str, Any]:
    """Calcula el cronograma. Con metrics=False solo devuelve {"finish": día} (lo usa la simulación)."""
    profile_map = {p.profile_key: p for p in profiles}
    missing = sorted({t.profile_key for t in tasks if t.profile_key not in profile_map})
    if missing:
        raise PlanningError(
            "Hay tareas asignadas a perfiles que no existen en el equipo: " + ", ".join(missing)
            + ". Agregá esos perfiles en Equipo y capacidad o reasigná las tareas.",
            {"missing_profiles": missing},
        )
    members_by_profile = build_members(profiles, params)
    needed = sorted({t.profile_key for t in tasks if t.hours > EPS})
    empty = [k for k in needed if not members_by_profile.get(k)]
    if empty:
        raise PlanningError(
            "Hay perfiles con tareas pero sin capacidad (cantidad 0 o disponibilidad 0): "
            + ", ".join(profile_map[k].profile_name for k in empty) + ".",
            {"profiles_without_capacity": empty},
        )

    qa_profiles = {p.profile_key for p in profiles if p.is_qa}
    preds, succs = build_graph(tasks, stories, qa_profiles, params)
    order = topological_order(preds, succs)
    task_map = {t.id: t for t in tasks}
    eff = {t.id: effective_hours(t, profile_map.get(t.profile_key), params) for t in tasks}

    # rango ascendente en horas, normalizado por la capacidad media del perfil (y su seniority media)
    avg_cap = {}
    for key, ms in members_by_profile.items():
        avg_cap[key] = (sum(m.daily_capacity / m.time_factor for m in ms) / len(ms)) if ms else 1.0
    rank: dict[str, float] = {}
    for tid in reversed(order):
        t = task_map[tid]
        own = eff[tid] / max(avg_cap.get(t.profile_key, 1.0), EPS)
        rank[tid] = own + max((rank[s] for s in succs[tid]), default=0.0)

    scheduled: dict[str, dict[str, Any]] = {}
    remaining_preds = {k: set(v) for k, v in preds.items()}
    ready = [tid for tid in order if not remaining_preds[tid]]

    def sort_key(tid: str) -> tuple:
        t = task_map[tid]
        return (-rank[tid], -PRIORITY_WEIGHT.get(t.priority, 2), t.order, tid)

    while ready:
        ready.sort(key=sort_key)
        tid = ready.pop(0)
        t = task_map[tid]
        ready_time = max((scheduled[p]["finish"] for p in preds[tid]), default=0.0)
        best: tuple[float, float, Member] | None = None
        for m in members_by_profile.get(t.profile_key, []):
            # la seniority de cada persona cambia el tiempo que le lleva la tarea
            a, b = m.earliest_slot(ready_time, eff[tid] * m.time_factor)
            if best is None or b < best[1] - EPS:
                best = (a, b, m)
        seniority, seniority_pct = None, 0.0
        if best is None:  # tarea de 0 h sin capacidad: no consume recursos
            a = b = ready_time
            member_uid, member_name = "", ""
        else:
            a, b, m = best
            m.book(a, b)
            member_uid, member_name = m.uid, m.name
            seniority, seniority_pct = m.seniority, m.seniority_pct
            eff[tid] = eff[tid] * m.time_factor
        scheduled[tid] = {
            "task_id": tid,
            "title": t.title,
            "story_id": t.story_id,
            "story_title": t.story_title,
            "epic_id": t.epic_id,
            "epic_title": t.epic_title,
            "profile_key": t.profile_key,
            "member_id": member_uid,
            "member_name": member_name,
            "seniority": seniority,
            "seniority_pct": seniority_pct,
            "base_hours": round(t.hours, 2),
            "effective_hours": round(eff[tid], 2),
            "ready": ready_time,
            "start": a,
            "finish": b,
            "start_date": day_to_date(params, a).isoformat(),
            "end_date": day_to_date(params, b, is_end=True).isoformat() if b > a else day_to_date(params, a).isoformat(),
            "wait_days": round(max(0.0, a - ready_time), 3),
            "depends_on": sorted(preds[tid]),
        }
        for s in succs[tid]:
            remaining_preds[s].discard(tid)
            if not remaining_preds[s]:
                ready.append(s)

    if not metrics:
        return {"finish": max((s["finish"] for s in scheduled.values()), default=0.0)}
    return _compute_metrics(tasks, profiles, params, members_by_profile, scheduled, preds, eff, target_date)


# --------------------------------------------------------------------------- métricas


def _critical_path(scheduled: dict[str, dict[str, Any]], preds: dict[str, set[str]]) -> list[dict[str, Any]]:
    if not scheduled:
        return []
    by_member: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in scheduled.values():
        if s["member_id"]:
            by_member[s["member_id"]].append(s)
    for lst in by_member.values():
        lst.sort(key=lambda x: x["start"])

    current = max(scheduled.values(), key=lambda s: (s["finish"], s["task_id"]))
    chain: list[dict[str, Any]] = []
    visited: set[str] = set()
    while current and current["task_id"] not in visited:
        visited.add(current["task_id"])
        candidates: list[tuple[float, str, dict[str, Any]]] = []
        for p in preds[current["task_id"]]:
            ps = scheduled[p]
            if ps["finish"] <= current["start"] + 1e-6:
                candidates.append((ps["finish"], "dependency", ps))
        if current["member_id"]:
            prev = [x for x in by_member[current["member_id"]] if x["finish"] <= current["start"] + 1e-6
                    and x["task_id"] != current["task_id"]]
            if prev:
                ps = max(prev, key=lambda x: x["finish"])
                candidates.append((ps["finish"], "resource", ps))
        binding = max(candidates, key=lambda c: (c[0], c[1] == "dependency")) if candidates else None
        chain.append({
            "task_id": current["task_id"],
            "title": current["title"],
            "profile_key": current["profile_key"],
            "member_name": current["member_name"],
            "start_date": current["start_date"],
            "end_date": current["end_date"],
            "effective_hours": current["effective_hours"],
            "constraint": binding[1] if binding else "start",
        })
        current = binding[2] if binding else None
    chain.reverse()
    return chain


def _compute_metrics(tasks, profiles, params, members_by_profile, scheduled, preds, eff, target_date):
    profile_map = {p.profile_key: p for p in profiles}
    finish = max((s["finish"] for s in scheduled.values()), default=0.0)
    last_day = max(0, math.floor(finish - EPS)) if finish > 0 else 0
    work_completion = params.start_date + timedelta(days=last_day)
    work_duration = project_working_days(params, 0, last_day) if scheduled and finish > 0 else 0
    # Reserva por imprevistos: reserva de días laborables después de la última tarea
    contingency_days = math.ceil(work_duration * params.contingency_pct / 100.0 - EPS) \
        if params.contingency_pct > 0 and work_duration > 0 else 0
    final_day = add_working_days(params, last_day, contingency_days)
    completion = params.start_date + timedelta(days=final_day)
    duration = work_duration + contingency_days

    by_profile: dict[str, dict[str, Any]] = {}
    for p in profiles:
        ms = members_by_profile.get(p.profile_key, [])
        capacity = sum(m.capacity_between(0, last_day) for m in ms) if finish > 0 else 0.0
        base = sum(t.hours for t in tasks if t.profile_key == p.profile_key)
        planned = sum(eff[t.id] for t in tasks if t.profile_key == p.profile_key)
        qa_waits = [s["wait_days"] for s in scheduled.values() if s["profile_key"] == p.profile_key]
        cost = planned * p.hourly_rate if p.hourly_rate is not None else None
        # horas pagadas durante el plan, incluida la reserva por imprevistos (capacidad nominal, sin coordinación)
        staffing_hours = sum(m.capacity_between(0, final_day) / m.efficiency for m in ms) if finish > 0 else 0.0
        staffing_cost = staffing_hours * p.hourly_rate if p.hourly_rate is not None else None
        by_profile[p.profile_key] = {
            "profile_key": p.profile_key,
            "profile_name": p.profile_name,
            "is_qa": p.is_qa,
            "members": len(ms),
            "quantity": p.quantity,
            "daily_capacity": round(sum(m.daily_capacity for m in ms), 2),
            "base_hours": round(base, 2),
            "planned_hours": round(planned, 2),
            "available_hours": round(capacity, 2),
            "utilization": round(planned / capacity, 4) if capacity > EPS else 0.0,
            "avg_wait_days": round(sum(qa_waits) / len(qa_waits), 2) if qa_waits else 0.0,
            "max_wait_days": round(max(qa_waits), 2) if qa_waits else 0.0,
            "hourly_rate": p.hourly_rate,
            "cost": round(cost, 2) if cost is not None else None,
            "staffing_hours": round(staffing_hours, 2),
            "staffing_cost": round(staffing_cost, 2) if staffing_cost is not None else None,
        }

    members_out = []
    for key, ms in members_by_profile.items():
        for m in ms:
            assigned = sum(eff[s["task_id"]] for s in scheduled.values() if s["member_id"] == m.uid)
            cap = m.capacity_between(0, last_day) if finish > 0 else 0.0
            members_out.append({
                "member_id": m.uid,
                "name": m.name,
                "profile_key": key,
                "seniority": m.seniority,
                "seniority_pct": m.seniority_pct,
                "daily_capacity": round(m.daily_capacity, 2),
                "assigned_hours": round(assigned, 2),
                "available_hours": round(cap, 2),
                "utilization": round(assigned / cap, 4) if cap > EPS else 0.0,
            })

    by_epic: dict[str, dict[str, Any]] = {}
    for t in tasks:
        e = by_epic.setdefault(t.epic_id, {"epic_id": t.epic_id, "title": t.epic_title, "base_hours": 0.0,
                                           "planned_hours": 0.0, "end": 0.0, "start": math.inf})
        e["base_hours"] += t.hours
        e["planned_hours"] += eff[t.id]
        e["end"] = max(e["end"], scheduled[t.id]["finish"])
        e["start"] = min(e["start"], scheduled[t.id]["start"])
    epics_out = []
    for e in by_epic.values():
        epics_out.append({
            "epic_id": e["epic_id"],
            "title": e["title"],
            "base_hours": round(e["base_hours"], 2),
            "planned_hours": round(e["planned_hours"], 2),
            "start_date": day_to_date(params, e["start"]).isoformat() if e["start"] != math.inf else None,
            "end_date": day_to_date(params, e["end"], is_end=True).isoformat(),
        })

    critical = _critical_path(scheduled, preds)
    critical_hours: dict[str, float] = defaultdict(float)
    for c in critical:
        critical_hours[c["profile_key"]] += c["effective_hours"]

    qa_keys = {p.profile_key for p in profiles if p.is_qa}
    dev_finish = max((s["finish"] for s in scheduled.values() if s["profile_key"] not in qa_keys), default=0.0)
    milestones = [
        {"name": f"Fin de la épica: {e['title']}", "date": e["end_date"], "type": "epic"} for e in epics_out
    ]
    if dev_finish > 0:
        milestones.append({"name": "Fin del desarrollo", "date": day_to_date(params, dev_finish, True).isoformat(),
                           "type": "development"})
    if finish > 0 and contingency_days:
        milestones.append({"name": "Fin del trabajo planificado (QA incluido)", "date": work_completion.isoformat(),
                           "type": "work"})
        milestones.append({"name": f"Entrega estimada con reserva por imprevistos ({params.contingency_pct:g} %)",
                           "date": completion.isoformat(), "type": "delivery"})
    elif finish > 0:
        milestones.append({"name": "Fin de QA y entrega estimada", "date": completion.isoformat(), "type": "delivery"})
    milestones.sort(key=lambda m: m["date"])

    bottlenecks = _bottlenecks(by_profile, critical_hours, profile_map, tasks, scheduled, qa_keys)
    base_total = sum(t.hours for t in tasks)
    planned_total = sum(eff.values())
    costs = [v["cost"] for v in by_profile.values() if v["planned_hours"] > 0]
    total_cost = round(sum(c for c in costs if c is not None), 2) if costs and all(c is not None for c in costs) else None
    staffing = [v["staffing_cost"] for v in by_profile.values() if v["members"] > 0]
    total_staffing_cost = (round(sum(staffing), 2) if staffing and all(c is not None for c in staffing)
                           else None)

    schedule_out = sorted(scheduled.values(), key=lambda s: (s["start"], s["task_id"]))
    for s in schedule_out:
        s["start"] = round(s["start"], 4)
        s["finish"] = round(s["finish"], 4)
        s["ready"] = round(s["ready"], 4)

    assumptions = _assumptions(params, profiles)
    risks = _risks(bottlenecks, tasks, by_profile, completion, target_date, base_total)

    return {
        "start_date": params.start_date.isoformat(),
        "completion_date": completion.isoformat(),
        "duration_working_days": duration,
        "calendar_days": (final_day + 1) if finish > 0 else 0,
        "work_duration_days": work_duration,
        "work_completion_date": work_completion.isoformat(),
        "contingency_pct": params.contingency_pct,
        "contingency_days": contingency_days,
        "base_effort_hours": round(base_total, 2),
        "planned_effort_hours": round(planned_total, 2),
        "total_cost": total_cost,
        "total_staffing_cost": total_staffing_cost,
        "by_profile": list(by_profile.values()),
        "by_member": members_out,
        "by_epic": epics_out,
        "critical_path": critical,
        "critical_hours_by_profile": {k: round(v, 2) for k, v in critical_hours.items()},
        "milestones": milestones,
        "bottlenecks": bottlenecks,
        "main_bottleneck": bottlenecks[0]["profile_key"] if bottlenecks else None,
        "schedule": schedule_out,
        "assumptions": assumptions,
        "risks": risks,
        "target_date": target_date.isoformat() if target_date else None,
        "meets_target": (completion <= target_date) if target_date else None,
    }


def _bottlenecks(by_profile, critical_hours, profile_map, tasks, scheduled, qa_keys) -> list[dict[str, Any]]:
    total_critical = sum(critical_hours.values()) or 1.0
    out = []
    for key, v in by_profile.items():
        if v["planned_hours"] <= 0:
            continue
        share = critical_hours.get(key, 0.0) / total_critical
        score = share * 0.6 + min(v["utilization"], 1.5) * 0.4
        reasons = []
        if share >= 0.3:
            reasons.append(f"{round(share * 100)} % del camino crítico")
        if v["utilization"] >= 0.85:
            reasons.append(f"utilización {round(v['utilization'] * 100)} %")
        if key in qa_keys and v["avg_wait_days"] >= 1:
            reasons.append(f"las pruebas esperan {v['avg_wait_days']} días en promedio")
        if v["members"] == 1 and v["planned_hours"] > 0:
            reasons.append("una sola persona concentra el conocimiento")
        out.append({
            "profile_key": key,
            "profile_name": v["profile_name"],
            "critical_share": round(share, 4),
            "utilization": v["utilization"],
            "score": round(score, 4),
            "reasons": reasons,
        })
    out.sort(key=lambda b: (-b["score"], b["profile_key"]))
    return out


def _assumptions(params: PlanningParameters, profiles: list[ProfileConfig]) -> list[str]:
    days = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    wd = ", ".join(days[d] for d in sorted(params.working_days))
    out = [
        f"Inicio de la planificación: {params.start_date.strftime('%d/%m/%Y')}.",
        f"Días laborables: {wd}. Feriados considerados: {len(params.holidays)}.",
        f"Se suma un {params.review_overhead_pct:g} % por revisión de código y un {params.rework_pct:g} % por "
        "retrabajo a las tareas que no son de QA.",
        f"Coordinación: cada persona adicional en un mismo perfil reduce un {params.coordination_overhead_pct:g} % "
        f"la eficiencia individual (mínimo {round(params.min_efficiency * 100)} %).",
        "Cada tarea la ejecuta una sola persona; no se reparte entre varias.",
    ]
    if params.qa_after_dev:
        out.append("Las tareas de QA de una historia empiezan cuando termina su desarrollo.")
    if params.contingency_pct > 0:
        out.append(f"Reserva por imprevistos: se reserva un {params.contingency_pct:g} % de la duración del trabajo "
                   "(redondeado hacia arriba en días laborables) después de la última tarea.")
    with_seniority = [p for p in profiles if any(m.seniority for m in p.members[:p.quantity])]
    if with_seniority:
        f = params.seniority_factors
        out.append(
            "Seniority: el tiempo de cada tarea se ajusta según quién la hace — "
            + ", ".join(f"{SENIORITY_LABELS[k]} {_signed(f.get(k, 0.0))}" for k in SENIORITY_LEVELS)
            + ". Las personas sin seniority definida no tienen ajuste."
        )
    for p in profiles:
        line = (f"{p.profile_name}: {p.quantity} persona(s), {p.hours_per_day:g} h productivas/día al "
                f"{p.dedication_percentage:g} % de dedicación")
        counts = {k: sum(1 for m in p.members[:p.quantity] if m.seniority == k) for k in SENIORITY_LEVELS}
        if any(counts.values()):
            line += " (" + ", ".join(f"{n} {k.upper()}" for k, n in counts.items() if n) + ")"
        out.append(line + ".")
    return out


def _signed(pct: float) -> str:
    return f"{pct:+g} %" if pct else "sin ajuste"


def _risks(bottlenecks, tasks, by_profile, completion, target_date, base_total) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    if bottlenecks and bottlenecks[0]["score"] >= 0.5:
        b = bottlenecks[0]
        risks.append({
            "title": f"Cuello de botella en {b['profile_name']}",
            "severity": "high",
            "detail": "; ".join(b["reasons"]) or "Concentra la mayor parte del trabajo crítico.",
            "source": "engine",
        })
    for v in by_profile.values():
        if v["members"] == 1 and base_total > 0 and v["base_hours"] / base_total >= 0.25:
            risks.append({
                "title": f"Concentración de conocimiento en {v['profile_name']}",
                "severity": "medium",
                "detail": f"Una sola persona tiene el {round(v['base_hours'] / base_total * 100)} % del esfuerzo.",
                "source": "engine",
            })
    low = [t for t in tasks if t.confidence == "low"]
    if low:
        hours = sum(t.hours for t in low)
        risks.append({
            "title": "Estimaciones con confianza baja",
            "severity": "medium" if hours / max(base_total, EPS) < 0.3 else "high",
            "detail": f"{len(low)} tareas ({round(hours)} h) pertenecen a historias con confianza baja.",
            "source": "engine",
        })
    if target_date and completion > target_date:
        risks.append({
            "title": "La fecha objetivo no se cumple",
            "severity": "high",
            "detail": f"Fin estimado {completion.strftime('%d/%m/%Y')} vs. objetivo {target_date.strftime('%d/%m/%Y')}.",
            "source": "engine",
        })
    return risks
