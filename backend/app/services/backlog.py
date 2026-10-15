"""Servicios de backlog: códigos, dependencias sin ciclos, aplicación de backlog generado y snapshots."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai.schemas import GeneratedBacklog
from app.errors import Conflict
from app.models import Epic, Project, Requirement, StoryDependency, Task, TaskDependency, TeamProfile, UserStory


def next_code(db: Session, model, project_id: int, prefix: str, width: int = 3) -> str:
    codes = db.scalars(select(model.code).where(model.project_id == project_id)).all()
    nums = [int(m.group(1)) for c in codes if (m := re.fullmatch(rf"{prefix}-(\d+)", c))]
    return f"{prefix}-{(max(nums) + 1 if nums else 1):0{width}d}"


class CodeAllocator:
    """Asigna códigos correlativos en memoria durante una operación masiva."""

    def __init__(self, db: Session, project_id: int):
        self.counters: dict[str, int] = {}
        for model, prefix in ((Epic, "EP"), (UserStory, "US"), (Task, "TK"), (Requirement, "REQ")):
            codes = db.scalars(select(model.code).where(model.project_id == project_id)).all()
            nums = [int(m.group(1)) for c in codes if (m := re.fullmatch(rf"{prefix}-(\d+)", c))]
            self.counters[prefix] = max(nums) if nums else 0

    def next(self, prefix: str, width: int = 3) -> str:
        self.counters[prefix] += 1
        return f"{prefix}-{self.counters[prefix]:0{width}d}"


def _reachable(graph: dict[Any, set[Any]], start: Any, target: Any) -> bool:
    stack, seen = [start], set()
    while stack:
        n = stack.pop()
        if n == target:
            return True
        if n in seen:
            continue
        seen.add(n)
        stack.extend(graph.get(n, ()))
    return False


def would_create_cycle(edges: list[tuple[Any, Any]], new_from: Any, new_to: Any) -> bool:
    """Arista new_from -> new_to (new_from depende de new_to). Hay ciclo si new_to ya depende de new_from."""
    graph: dict[Any, set[Any]] = defaultdict(set)
    for a, b in edges:
        graph[a].add(b)
    return new_from == new_to or _reachable(graph, new_to, new_from)


def set_story_dependencies(db: Session, story: UserStory, depends_on_ids: list[int]) -> None:
    all_edges = [(d.story_id, d.depends_on_id) for d in db.scalars(
        select(StoryDependency).join(UserStory, UserStory.id == StoryDependency.story_id)
        .where(UserStory.project_id == story.project_id)).all() if d.story_id != story.id]
    targets = []
    for dep_id in dict.fromkeys(depends_on_ids):
        dep = db.get(UserStory, dep_id)
        if dep is None or dep.project_id != story.project_id:
            raise Conflict(f"La historia {dep_id} no pertenece a este proyecto.")
        if would_create_cycle(all_edges, story.id, dep_id):
            raise Conflict(f"La dependencia con {dep.code} crearía una dependencia circular.",
                           code="circular_dependency")
        all_edges.append((story.id, dep_id))
        targets.append(dep)
    story.depends_on = targets


def set_task_dependencies(db: Session, task: Task, depends_on_ids: list[int]) -> None:
    all_edges = [(d.task_id, d.depends_on_id) for d in db.scalars(
        select(TaskDependency).join(Task, Task.id == TaskDependency.task_id)
        .where(Task.project_id == task.project_id)).all() if d.task_id != task.id]
    targets = []
    for dep_id in dict.fromkeys(depends_on_ids):
        dep = db.get(Task, dep_id)
        if dep is None or dep.project_id != task.project_id:
            raise Conflict(f"La tarea {dep_id} no pertenece a este proyecto.")
        if would_create_cycle(all_edges, task.id, dep_id):
            raise Conflict(f"La dependencia con {dep.code} crearía una dependencia circular.",
                           code="circular_dependency")
        all_edges.append((task.id, dep_id))
        targets.append(dep)
    task.depends_on = targets


def load_epics(db: Session, project_id: int) -> list[Epic]:
    return list(db.scalars(
        select(Epic).where(Epic.project_id == project_id).order_by(Epic.order_index, Epic.id)
        .options(selectinload(Epic.stories).selectinload(UserStory.tasks).selectinload(Task.depends_on),
                 selectinload(Epic.stories).selectinload(UserStory.depends_on))
    ).all())


def _generated_range(gt: Any) -> dict[str, float | None]:
    """Rango de tres puntos propuesto por el agente; si es incoherente se descarta (se usa la confianza)."""
    lo, hi, m = gt.optimistic_hours, gt.pessimistic_hours, gt.estimated_hours
    if lo is None or hi is None or not (lo <= m <= hi) or hi <= lo:
        return {"optimistic_hours": None, "pessimistic_hours": None}
    return {"optimistic_hours": round(lo, 2), "pessimistic_hours": round(hi, 2)}


def story_out(story: UserStory) -> dict[str, Any]:
    hours: dict[str, float] = defaultdict(float)
    tasks = []
    for t in story.tasks:
        hours[t.profile_key] += t.estimated_hours
        tasks.append({**{c: getattr(t, c) for c in (
            "id", "story_id", "code", "title", "description", "category", "profile_key", "estimated_hours",
            "optimistic_hours", "pessimistic_hours",
            "original_estimate_hours", "estimate_status", "done_criteria", "risks", "status")},
            "depends_on_ids": [d.id for d in t.depends_on]})
    return {
        **{c: getattr(story, c) for c in (
            "id", "epic_id", "code", "title", "description", "acceptance_criteria", "priority", "business_value",
            "assumptions", "risks", "estimate_confidence", "estimate_status", "status")},
        "depends_on_ids": [d.id for d in story.depends_on],
        "tasks": tasks,
        "hours_by_profile": {k: round(v, 2) for k, v in hours.items()},
        "total_hours": round(sum(hours.values()), 2),
    }


def backlog_out(db: Session, project: Project) -> dict[str, Any]:
    epics = load_epics(db, project.id)
    out_epics, totals = [], defaultdict(float)
    story_count = task_count = 0
    simulated = False
    for e in epics:
        stories = [story_out(s) for s in e.stories]
        for s in stories:
            story_count += 1
            task_count += len(s["tasks"])
            for k, v in s["hours_by_profile"].items():
                totals[k] += v
        simulated = simulated or e.source == "demo"
        out_epics.append({
            **{c: getattr(e, c) for c in ("id", "project_id", "code", "title", "description", "priority", "status",
                                          "source")},
            "stories": stories,
            "total_hours": round(sum(s["total_hours"] for s in stories), 2),
        })
    return {
        "project_id": project.id,
        "epics": out_epics,
        "total_hours": round(sum(totals.values()), 2),
        "hours_by_profile": {k: round(v, 2) for k, v in totals.items()},
        "story_count": story_count,
        "task_count": task_count,
        "is_simulated": simulated,
    }


def backlog_snapshot(db: Session, project: Project) -> dict[str, Any]:
    """Copia completa del backlog que se guarda con cada versión del plan (para PDF y auditoría)."""
    epics = load_epics(db, project.id)
    return {
        "epics": [
            {
                "id": e.id, "code": e.code, "title": e.title, "description": e.description, "priority": e.priority,
                "stories": [
                    {
                        "id": s.id, "code": s.code, "title": s.title, "description": s.description,
                        "priority": s.priority, "business_value": s.business_value,
                        "acceptance_criteria": s.acceptance_criteria, "assumptions": s.assumptions, "risks": s.risks,
                        "estimate_confidence": s.estimate_confidence, "estimate_status": s.estimate_status,
                        "depends_on": [d.id for d in s.depends_on],
                        "tasks": [
                            {
                                "id": t.id, "code": t.code, "title": t.title, "description": t.description,
                                "category": t.category, "profile_key": t.profile_key,
                                "estimated_hours": t.estimated_hours, "estimate_status": t.estimate_status,
                                "optimistic_hours": t.optimistic_hours, "pessimistic_hours": t.pessimistic_hours,
                                "done_criteria": t.done_criteria, "risks": t.risks,
                                "depends_on": [d.id for d in t.depends_on],
                            } for t in s.tasks
                        ],
                    } for s in e.stories
                ],
            } for e in epics
        ],
        "requirements": [
            {"code": r.code, "title": r.title, "type": r.type, "priority": r.priority, "status": r.status,
             "description": r.description}
            for r in db.scalars(select(Requirement).where(Requirement.project_id == project.id)
                                .order_by(Requirement.id)).all()
            if r.status not in ("rejected", "suggested")
        ],
    }


def apply_generated_backlog(db: Session, project: Project, generated: GeneratedBacklog, source: str,
                            replace_existing: bool) -> list[str]:
    """Persiste el backlog generado. Devuelve advertencias (dependencias descartadas, perfiles faltantes)."""
    warnings: list[str] = []
    if replace_existing:
        for e in list(project.epics):
            db.delete(e)
        db.flush()
        db.expire(project, ["epics"])
    codes = CodeAllocator(db, project.id)
    team_keys = set(db.scalars(select(TeamProfile.profile_key).where(TeamProfile.project_id == project.id)).all())
    start_order = len(project.epics) if not replace_existing else 0
    story_by_ref: dict[str, UserStory] = {}
    pending_story_deps: list[tuple[UserStory, list[str]]] = []
    missing_profiles: set[str] = set()

    for ei, ge in enumerate(generated.epics):
        epic = Epic(project_id=project.id, code=codes.next("EP", 2), title=ge.title[:300],
                    description=ge.description, priority=ge.priority, source=source, order_index=start_order + ei,
                    status="draft")
        db.add(epic)
        db.flush()
        for si, gs in enumerate(ge.stories):
            description = gs.description
            if gs.as_a and gs.i_want:
                statement = f"Como {gs.as_a}, quiero {gs.i_want}" + (f", para {gs.so_that}." if gs.so_that else ".")
                description = statement + ("\n\n" + description if description else "")
            story = UserStory(
                epic_id=epic.id, project_id=project.id, code=codes.next("US"), title=gs.title[:300],
                description=description, acceptance_criteria=[c.model_dump() for c in gs.acceptance_criteria],
                priority=gs.priority, business_value=gs.business_value, assumptions=gs.assumptions, risks=gs.risks,
                estimate_confidence=gs.confidence, estimate_status="initial", status="draft", order_index=si,
            )
            db.add(story)
            db.flush()
            if gs.ref:
                story_by_ref[gs.ref] = story
            pending_story_deps.append((story, gs.depends_on))
            task_by_ref: dict[str, Task] = {}
            task_edges: list[tuple[int, int]] = []
            for ti, gt in enumerate(gs.tasks):
                if gt.profile_key not in team_keys:
                    missing_profiles.add(gt.profile_key)
                task = Task(
                    story_id=story.id, project_id=project.id, code=codes.next("TK"), title=gt.title[:300],
                    description=gt.description, category=gt.category[:40], profile_key=gt.profile_key,
                    estimated_hours=round(gt.estimated_hours, 2), original_estimate_hours=round(gt.estimated_hours, 2),
                    **_generated_range(gt),
                    estimate_status="initial", done_criteria=gt.done_criteria, risks=gt.risks, order_index=ti,
                )
                db.add(task)
                db.flush()
                if gt.ref:
                    task_by_ref[gt.ref] = task
                for dep_ref in gt.depends_on:
                    dep = task_by_ref.get(dep_ref)
                    if dep is None:
                        warnings.append(f"{task.code}: dependencia '{dep_ref}' desconocida o posterior; se descartó.")
                        continue
                    if would_create_cycle(task_edges, task.id, dep.id):
                        warnings.append(f"{task.code}: dependencia circular con {dep.code}; se descartó.")
                        continue
                    task_edges.append((task.id, dep.id))
                    db.add(TaskDependency(task_id=task.id, depends_on_id=dep.id))

    story_edges: list[tuple[int, int]] = []
    for story, refs in pending_story_deps:
        for ref in refs:
            dep = story_by_ref.get(ref)
            if dep is None or dep.id == story.id:
                warnings.append(f"{story.code}: dependencia '{ref}' desconocida; se descartó.")
                continue
            if would_create_cycle(story_edges, story.id, dep.id):
                warnings.append(f"{story.code}: dependencia circular con {dep.code}; se descartó.")
                continue
            story_edges.append((story.id, dep.id))
            db.add(StoryDependency(story_id=story.id, depends_on_id=dep.id))

    if missing_profiles:
        warnings.append("Perfiles usados en tareas que no están en el equipo: " + ", ".join(sorted(missing_profiles))
                        + ". Agregalos en Equipo y capacidad antes de planificar.")
    db.flush()
    return warnings
