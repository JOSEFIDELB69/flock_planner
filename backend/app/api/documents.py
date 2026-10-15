"""Documentos adjuntos al proyecto. El archivo se guarda tal cual y se le entrega al agente de IA, que extrae
los requisitos; estos quedan como «sugeridos» vinculados al documento hasta que el usuario los confirme."""

import hashlib
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ai.provider import get_ai_provider
from app.api.requirements import project_context
from app.config import get_settings
from app.db import get_db
from app.deps import ai_rate_limit, get_actor, get_project
from app.errors import AppError, NotFound
from app.models import Project, ProjectDocument, Requirement, utcnow
from app.services import audit
from app.services.ai_calls import run_ai
from app.services.backlog import CodeAllocator
from app.services.documents import CONTENT_TYPES, validate_document

router = APIRouter(tags=["Documentos"])


def _out(d: ProjectDocument) -> dict:
    return {
        "id": d.id, "project_id": d.project_id, "filename": d.filename, "kind": d.kind, "size_bytes": d.size_bytes,
        "status": d.status, "error": d.error, "summary": d.summary, "requirements_created": d.requirements_created,
        "ai_model": d.ai_model, "is_simulated": d.is_simulated, "created_at": d.created_at,
        "created_by": d.created_by, "processed_at": d.processed_at,
    }


def _get(db: Session, document_id: int) -> ProjectDocument:
    d = db.get(ProjectDocument, document_id)
    if d is None:
        raise NotFound("No encontramos el documento.")
    return d


@router.post("/projects/{project_id}/documents", status_code=201)
async def upload_document(project: Project = Depends(get_project), file: UploadFile = File(...),
                          db: Session = Depends(get_db), actor: str = Depends(get_actor)):
    """Adjunta el archivo original (sin transformarlo) después de validar que sea seguro."""
    limit = get_settings().max_document_bytes
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise AppError(f"El archivo supera el máximo de {limit / 1_000_000:g} MB.", code="file_too_large",
                       status_code=413)
    if not data:
        raise AppError("El archivo está vacío.", code="unreadable_file", status_code=422)
    name = (file.filename or "documento").replace("\\", "/").split("/")[-1][:255]
    kind = await run_in_threadpool(validate_document, name, data)
    doc = ProjectDocument(project_id=project.id, filename=name, kind=kind, content_type=CONTENT_TYPES[kind],
                          size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), content=data,
                          status="pending", created_by=actor)
    db.add(doc)
    db.flush()
    audit.record(db, project_id=project.id, entity_type="document", entity_id=doc.id, action="upload", actor=actor,
                 after={"filename": name, "kind": kind, "bytes": len(data)})
    db.commit()
    return _out(doc)


@router.get("/projects/{project_id}/documents")
def list_documents(project: Project = Depends(get_project), db: Session = Depends(get_db)):
    rows = db.scalars(select(ProjectDocument).where(ProjectDocument.project_id == project.id)
                      .order_by(ProjectDocument.id.desc())).all()
    return [_out(d) for d in rows]


@router.get("/documents/{document_id}/download")
def download_document(document_id: int, db: Session = Depends(get_db)):
    d = _get(db, document_id)
    safe = d.filename.replace('"', "")
    return Response(content=d.content, media_type=d.content_type, headers={
        "Content-Disposition": f'attachment; filename="{safe.encode("ascii", "replace").decode()}"; '
                               f"filename*=UTF-8''{quote(safe)}",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store",
    })


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: int, db: Session = Depends(get_db), actor: str = Depends(get_actor)):
    """Quita el adjunto. Los requisitos ya extraídos se conservan (pierden el vínculo con el documento)."""
    d = _get(db, document_id)
    audit.record(db, project_id=d.project_id, entity_type="document", entity_id=d.id, action="delete", actor=actor,
                 before={"filename": d.filename, "requirements_created": d.requirements_created})
    db.delete(d)
    db.commit()
    return Response(status_code=204)


@router.post("/documents/{document_id}/extract", dependencies=[Depends(ai_rate_limit)])
def extract_requirements(document_id: int, db: Session = Depends(get_db), actor: str = Depends(get_actor)):
    """El agente lee el documento y propone requisitos («sugeridos»). Reprocesar reemplaza solo las sugerencias
    de este documento que todavía no se confirmaron ni editaron."""
    d = _get(db, document_id)
    project = db.get(Project, d.project_id)
    provider = get_ai_provider()
    d.status = "processing"
    db.commit()
    try:
        result = run_ai(db, provider, project.id, "extract_requirements_from_document",
                        lambda: provider.extract_requirements_from_document(project_context(project), d.filename,
                                                                            d.kind, d.content))
    except AppError as exc:
        d.status = "error"
        d.error = exc.message
        db.commit()
        raise
    # reemplaza sugerencias previas de este documento que siguen sin revisar
    db.execute(delete(Requirement).where(Requirement.source_document_id == d.id, Requirement.status == "suggested"))
    codes = CodeAllocator(db, project.id)
    source = f"documento {d.filename}" + (" (simulado)" if provider.is_simulated else "")
    created = []
    for item in result.requirements:
        ref = f" ({item.source_reference})" if item.source_reference else ""
        r = Requirement(project_id=project.id, code=codes.next("REQ"), title=item.title[:300],
                        description=item.description, type=item.type, priority=item.priority,
                        source=(source + ref)[:200], status="suggested", assumptions=item.assumptions,
                        source_document_id=d.id)
        db.add(r)
        created.append(r)
    db.flush()
    d.status = "processed"
    d.error = ""
    d.summary = result.summary + ("\n\nObservaciones:\n- " + "\n- ".join(result.observations)
                                  if result.observations else "")
    d.requirements_created = len(created)
    d.ai_model = provider.model
    d.is_simulated = provider.is_simulated
    d.processed_at = utcnow()
    audit.record(db, project_id=project.id, entity_type="document", entity_id=d.id, action="extract", actor=actor,
                 after={"requirements": len(created), "model": provider.model, "simulated": provider.is_simulated})
    db.commit()
    return {**_out(d), "requirement_ids": [r.id for r in created]}
