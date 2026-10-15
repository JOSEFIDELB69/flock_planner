import hashlib

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_actor, get_project
from app.errors import NotFound
from app.models import Export, Project, Scenario
from app.pdf.reports import build_pdf, safe_filename
from app.schemas import ExportOut, ExportRequest
from app.services import audit
from app.services.plans import baseline_of, get_version

router = APIRouter(tags=["Exportaciones"])


@router.post("/plans/{plan_id}/exports/pdf", response_model=ExportOut, status_code=201)
def create_pdf(plan_id: int, body: ExportRequest, db: Session = Depends(get_db), actor: str = Depends(get_actor)):
    version = get_version(db, plan_id)
    project = db.get(Project, version.project_id)
    scenarios = db.scalars(select(Scenario).where(Scenario.project_id == project.id).order_by(Scenario.id)).all()
    numbers = {v.id: v.version_number for v in project.plan_versions}
    content = build_pdf(project, version, body.report_type, scenarios=scenarios, baseline=baseline_of(db, project.id),
                        version_numbers=numbers)
    export = Export(project_id=project.id, plan_version_id=version.id, report_type=body.report_type,
                    filename=safe_filename(project.name, body.report_type, version.version_number), content=content,
                    size_bytes=len(content), sha256=hashlib.sha256(content).hexdigest(), created_by=actor)
    db.add(export)
    db.flush()
    audit.record(db, project_id=project.id, entity_type="export", entity_id=export.id, action="create", actor=actor,
                 after={"report_type": body.report_type, "version": version.version_number, "bytes": len(content)})
    db.commit()
    return export


@router.get("/exports/{export_id}")
def download(export_id: int, db: Session = Depends(get_db)):
    export = db.get(Export, export_id)
    if export is None:
        raise NotFound("No encontramos la exportación.")
    return Response(content=export.content, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{export.filename}"',
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store",
    })


@router.get("/projects/{project_id}/exports", response_model=list[ExportOut])
def list_exports(project: Project = Depends(get_project), db: Session = Depends(get_db)):
    return db.scalars(select(Export).where(Export.project_id == project.id).order_by(Export.id.desc())).all()
