from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.provider import get_ai_provider
from app.api.requirements import project_context, requirement_context
from app.db import get_db
from app.deps import ai_rate_limit, get_actor, get_project
from app.errors import AppError, Conflict, NotFound
from app.models import BacklogObservation, Epic, Project, RequirementAnalysis, Task, UserStory
from app.schemas import (
    BacklogGenerateRequest,
    EpicCreate,
    EpicUpdate,
    ObservationOut,
    ObservationUpdate,
    StoryCreate,
    StoryUpdate,
    TaskCreate,
    TaskUpdate,
    check_task_range,
)
from app.services import audit
from app.services.ai_calls import run_ai
from app.services.observations import previous_feedback, replace_observations
from app.models import utcnow
from app.services.backlog import (
    apply_generated_backlog,
    backlog_out,
    next_code,
    set_story_dependencies,
    set_task_dependencies,
    story_out,
)
from app.services.plans import team_config

router = APIRouter(tags=["Backlog"])

STORY_FIELDS = ["title", "description", "acceptance_criteria", "priority", "business_value", "assumptions", "risks",
                "estimate_confidence", "estimate_status", "status", "epic_id"]
TASK_FIELDS = ["title", "description", "category", "profile_key", "estimated_hours", "optimistic_hours",
               "pessimistic_hours", "estimate_status", "done_criteria", "risks", "status"]


@router.get("/projects/{project_id}/backlog")
def get_backlog(project: Project = Depends(get_project), db: Session = Depends(get_db)):
    return backlog_out(db, project)


@router.post("/projects/{project_id}/backlog/generate", status_code=201, dependencies=[Depends(ai_rate_limit)])
def generate_backlog(body: BacklogGenerateRequest, project: Project = Depends(get_project),
                     db: Session = Depends(get_db), actor: str = Depends(get_actor)):
    reqs = requirement_context(db, project)
    if not reqs:
        raise AppError("Cargá requisitos antes de generar el backlog.", code="no_requirements", status_code=422)
    existing = db.scalar(select(func.count()).select_from(Epic).where(Epic.project_id == project.id)) or 0
    if existing and not body.replace_existing:
        raise Conflict("El proyecto ya tiene backlog. Confirmá el reemplazo (replace_existing=true) o editalo "
                       "manualmente. Las versiones de plan ya guardadas no se modifican.", code="backlog_exists")
    analysis = None
    if body.analysis_id:
        analysis = db.get(RequirementAnalysis, body.analysis_id)
        if analysis is None or analysis.project_id != project.id:
            raise NotFound("No encontramos el análisis indicado.")
    else:
        analysis = db.scalars(select(RequirementAnalysis).where(RequirementAnalysis.project_id == project.id)
                              .order_by(RequirementAnalysis.id.desc())).first()
    answers = {}
    if analysis:
        questions = analysis.result.get("clarification_questions", [])
        for k, v in (analysis.answers or {}).items():
            idx = int(k) if str(k).isdigit() else -1
            q = questions[idx]["question"] if 0 <= idx < len(questions) else k
            answers[q] = v
        if questions and not answers and not analysis.proceed_with_assumptions:
            raise AppError("Hay preguntas de aclaración sin responder. Respondelas o indicá que querés continuar con "
                           "supuestos explícitos.", code="pending_clarifications", status_code=422)
    provider = get_ai_provider()
    team = team_config(db, project)
    feedback = previous_feedback(db, project.id) if body.apply_observations else ""
    extra = "\n\n".join(x for x in (body.additional_instructions.strip(), feedback) if x)
    generated = run_ai(db, provider, project.id, "generate_backlog", lambda: provider.generate_backlog(
        project_context(project), reqs, analysis.result if analysis else None, answers, team, extra))
    warnings = apply_generated_backlog(db, project, generated, "demo" if provider.is_simulated else "ai",
                                       body.replace_existing)
    replace_observations(db, project.id, warnings, generated.assumptions)
    audit.record(db, project_id=project.id, entity_type="backlog", entity_id=None, action="generate", actor=actor,
                 after={"epics": len(generated.epics), "model": provider.model, "simulated": provider.is_simulated,
                        "replaced": body.replace_existing, "warnings": warnings,
                        "feedback_applied": bool(feedback)})
    db.commit()
    return {**backlog_out(db, project), "warnings": warnings, "assumptions": generated.assumptions,
            "is_simulated": provider.is_simulated, "feedback_applied": bool(feedback)}


@router.get("/projects/{project_id}/backlog/observations", response_model=list[ObservationOut])
def list_observations(project: Project = Depends(get_project), db: Session = Depends(get_db)):
    return db.scalars(select(BacklogObservation).where(BacklogObservation.project_id == project.id)
                      .order_by(BacklogObservation.position)).all()


@router.patch("/backlog-observations/{observation_id}", response_model=ObservationOut)
def update_observation(observation_id: int, body: ObservationUpdate, db: Session = Depends(get_db),
                       actor: str = Depends(get_actor)):
    o = db.get(BacklogObservation, observation_id)
    if o is None:
        raise NotFound("No encontramos la observación.")
    before = {"status": o.status, "correction": o.correction}
    o.status = body.status
    o.correction = body.correction.strip() if body.status == "correction" else ""
    o.resolved_at = None if body.status == "pending" else utcnow()
    o.resolved_by = "" if body.status == "pending" else actor
    audit.record(db, project_id=o.project_id, entity_type="backlog_observation", entity_id=o.id, action="review",
                 actor=actor, before=before, after={"status": o.status, "correction": o.correction})
    db.commit()
    return o


# --------------------------------------------------------------------------- épicas


def _epic(db: Session, epic_id: int) -> Epic:
    e = db.get(Epic, epic_id)
    if e is None:
        raise NotFound("No encontramos la épica.")
    return e


@router.post("/projects/{project_id}/epics", status_code=201)
def create_epic(body: EpicCreate, project: Project = Depends(get_project), db: Session = Depends(get_db),
                actor: str = Depends(get_actor)):
    order = db.scalar(select(func.count()).select_from(Epic).where(Epic.project_id == project.id)) or 0
    e = Epic(project_id=project.id, code=next_code(db, Epic, project.id, "EP", 2), source="manual",
             order_index=order, **body.model_dump())
    db.add(e)
    db.flush()
    audit.record(db, project_id=project.id, entity_type="epic", entity_id=e.id, action="create", actor=actor,
                 after=body.model_dump())
    db.commit()
    return {"id": e.id, "code": e.code}


@router.patch("/epics/{epic_id}")
def update_epic(epic_id: int, body: EpicUpdate, db: Session = Depends(get_db), actor: str = Depends(get_actor)):
    e = _epic(db, epic_id)
    before = audit.snapshot(e, ["title", "description", "priority", "status"])
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(e, k, v)
    audit.record(db, project_id=e.project_id, entity_type="epic", entity_id=e.id, action="update", actor=actor,
                 before=before, after=audit.snapshot(e, ["title", "description", "priority", "status"]))
    db.commit()
    return {"id": e.id}


@router.delete("/epics/{epic_id}", status_code=204)
def delete_epic(epic_id: int, db: Session = Depends(get_db), actor: str = Depends(get_actor)):
    e = _epic(db, epic_id)
    audit.record(db, project_id=e.project_id, entity_type="epic", entity_id=e.id, action="delete", actor=actor,
                 before={"code": e.code, "title": e.title})
    db.delete(e)
    db.commit()
    return Response(status_code=204)


# --------------------------------------------------------------------------- historias


def _story(db: Session, story_id: int) -> UserStory:
    s = db.get(UserStory, story_id)
    if s is None:
        raise NotFound("No encontramos la historia.")
    return s


@router.post("/epics/{epic_id}/stories", status_code=201)
def create_story(epic_id: int, body: StoryCreate, db: Session = Depends(get_db), actor: str = Depends(get_actor)):
    e = _epic(db, epic_id)
    data = body.model_dump()
    data["acceptance_criteria"] = [c.model_dump() for c in body.acceptance_criteria]
    s = UserStory(epic_id=e.id, project_id=e.project_id, code=next_code(db, UserStory, e.project_id, "US"),
                  order_index=len(e.stories), estimate_status="initial", **data)
    db.add(s)
    db.flush()
    audit.record(db, project_id=e.project_id, entity_type="story", entity_id=s.id, action="create", actor=actor,
                 after=data)
    db.commit()
    db.refresh(s)
    return story_out(s)


@router.patch("/stories/{story_id}")
def update_story(story_id: int, body: StoryUpdate, db: Session = Depends(get_db), actor: str = Depends(get_actor)):
    s = _story(db, story_id)
    before = {**audit.snapshot(s, STORY_FIELDS), "depends_on": [d.id for d in s.depends_on]}
    changes = body.model_dump(exclude_unset=True)
    deps = changes.pop("depends_on_ids", None)
    if "epic_id" in changes:
        target = _epic(db, changes["epic_id"])
        if target.project_id != s.project_id:
            raise Conflict("La épica destino pertenece a otro proyecto.")
    if "acceptance_criteria" in changes and changes["acceptance_criteria"] is not None:
        changes["acceptance_criteria"] = [dict(c) for c in changes["acceptance_criteria"]]
    for k, v in changes.items():
        setattr(s, k, v)
    if deps is not None:
        set_story_dependencies(db, s, deps)
    db.flush()
    audit.record(db, project_id=s.project_id, entity_type="story", entity_id=s.id, action="update", actor=actor,
                 before=before, after={**audit.snapshot(s, STORY_FIELDS), "depends_on": [d.id for d in s.depends_on]})
    db.commit()
    db.refresh(s)
    return story_out(s)


@router.delete("/stories/{story_id}", status_code=204)
def delete_story(story_id: int, db: Session = Depends(get_db), actor: str = Depends(get_actor)):
    s = _story(db, story_id)
    audit.record(db, project_id=s.project_id, entity_type="story", entity_id=s.id, action="delete", actor=actor,
                 before={"code": s.code, "title": s.title})
    db.delete(s)
    db.commit()
    return Response(status_code=204)


# --------------------------------------------------------------------------- tareas


def _task(db: Session, task_id: int) -> Task:
    t = db.get(Task, task_id)
    if t is None:
        raise NotFound("No encontramos la tarea.")
    return t


def _task_out(t: Task) -> dict:
    return {**{c: getattr(t, c) for c in ["id", "story_id", "code", "original_estimate_hours", *TASK_FIELDS]},
            "depends_on_ids": [d.id for d in t.depends_on]}


@router.post("/stories/{story_id}/tasks", status_code=201)
def create_task(story_id: int, body: TaskCreate, db: Session = Depends(get_db), actor: str = Depends(get_actor)):
    s = _story(db, story_id)
    data = body.model_dump()
    deps = data.pop("depends_on_ids")
    t = Task(story_id=s.id, project_id=s.project_id, code=next_code(db, Task, s.project_id, "TK"),
             order_index=len(s.tasks), original_estimate_hours=body.estimated_hours, estimate_status="initial", **data)
    db.add(t)
    db.flush()
    if deps:
        set_task_dependencies(db, t, deps)
    audit.record(db, project_id=s.project_id, entity_type="task", entity_id=t.id, action="create", actor=actor,
                 after=body.model_dump())
    db.commit()
    db.refresh(t)
    return _task_out(t)


@router.patch("/tasks/{task_id}")
def update_task(task_id: int, body: TaskUpdate, db: Session = Depends(get_db), actor: str = Depends(get_actor)):
    t = _task(db, task_id)
    before = {**audit.snapshot(t, TASK_FIELDS), "depends_on": [d.id for d in t.depends_on]}
    changes = body.model_dump(exclude_unset=True)
    deps = changes.pop("depends_on_ids", None)
    if "optimistic_hours" in changes or "pessimistic_hours" in changes:
        try:
            check_task_range(changes.get("optimistic_hours", t.optimistic_hours),
                             changes.get("estimated_hours", t.estimated_hours),
                             changes.get("pessimistic_hours", t.pessimistic_hours))
        except ValueError as e:
            raise AppError(str(e), code="invalid_range", status_code=422) from e
    for k, v in changes.items():
        setattr(t, k, v)
    if t.optimistic_hours is not None and t.pessimistic_hours is not None \
            and not (t.optimistic_hours <= t.estimated_hours <= t.pessimistic_hours):
        # las horas nuevas quedaron fuera del rango anterior: se descarta y se usa el de la confianza
        t.optimistic_hours = t.pessimistic_hours = None
    if "estimated_hours" in changes and abs(t.estimated_hours - t.original_estimate_hours) > 1e-9:
        # una estimación ajustada manualmente pasa a "revisada" (también la historia)
        t.estimate_status = "revised"
        t.story.estimate_status = "revised"
    if deps is not None:
        set_task_dependencies(db, t, deps)
    db.flush()
    audit.record(db, project_id=t.project_id, entity_type="task", entity_id=t.id, action="update", actor=actor,
                 before=before, after={**audit.snapshot(t, TASK_FIELDS), "depends_on": [d.id for d in t.depends_on]})
    db.commit()
    db.refresh(t)
    return _task_out(t)


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: int, db: Session = Depends(get_db), actor: str = Depends(get_actor)):
    t = _task(db, task_id)
    audit.record(db, project_id=t.project_id, entity_type="task", entity_id=t.id, action="delete", actor=actor,
                 before={"code": t.code, "title": t.title, "hours": t.estimated_hours})
    db.delete(t)
    db.commit()
    return Response(status_code=204)


@router.post("/projects/{project_id}/estimates/confirm")
def confirm_estimates(project: Project = Depends(get_project), db: Session = Depends(get_db),
                      actor: str = Depends(get_actor)):
    """Marca todas las estimaciones como revisadas por el usuario antes de confirmar la línea base."""
    stories = db.scalars(select(UserStory).where(UserStory.project_id == project.id)).all()
    for s in stories:
        s.estimate_status = "revised"
        for t in s.tasks:
            t.estimate_status = "revised"
    audit.record(db, project_id=project.id, entity_type="estimates", entity_id=None, action="confirm", actor=actor,
                 after={"stories": len(stories)})
    db.commit()
    return {"confirmed_stories": len(stories)}
