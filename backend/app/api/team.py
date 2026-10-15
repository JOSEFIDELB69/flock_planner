from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_actor, get_project
from app.models import Project, TeamProfile
from app.schemas import TeamProfileOut, TeamPut
from app.services import audit
from app.services.plans import PROFILE_CATALOG, team_config

router = APIRouter(tags=["Equipo"])


@router.get("/projects/{project_id}/team", response_model=list[TeamProfileOut])
def get_team(project: Project = Depends(get_project), db: Session = Depends(get_db)):
    return db.scalars(select(TeamProfile).where(TeamProfile.project_id == project.id).order_by(TeamProfile.id)).all()


@router.put("/projects/{project_id}/team", response_model=list[TeamProfileOut])
def put_team(body: TeamPut, project: Project = Depends(get_project), db: Session = Depends(get_db),
             actor: str = Depends(get_actor)):
    """Reemplaza la configuración del equipo. No modifica versiones de plan guardadas (son inmutables)."""
    before = team_config(db, project)
    existing = {p.profile_key: p for p in db.scalars(select(TeamProfile)
                                                     .where(TeamProfile.project_id == project.id)).all()}
    keep = set()
    for p in body.profiles:
        data = p.model_dump(mode="json")
        row = existing.get(p.profile_key)
        if row is None:
            row = TeamProfile(project_id=project.id, profile_key=p.profile_key)
            db.add(row)
        for k, v in data.items():
            setattr(row, k, v)
        keep.add(p.profile_key)
    gone = [k for k in existing if k not in keep]
    if gone:
        db.execute(delete(TeamProfile).where(TeamProfile.project_id == project.id,
                                             TeamProfile.profile_key.in_(gone)))
    db.flush()
    audit.record(db, project_id=project.id, entity_type="team", entity_id=None, action="update", actor=actor,
                 before={"profiles": before}, after={"profiles": team_config(db, project)})
    db.commit()
    return db.scalars(select(TeamProfile).where(TeamProfile.project_id == project.id).order_by(TeamProfile.id)).all()


@router.get("/profile-catalog")
def profile_catalog():
    return PROFILE_CATALOG
