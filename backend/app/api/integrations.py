from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_actor, get_project
from app.models import JiraPublishRun, Project
from app.schemas import JiraConfigIn, JiraConfigOut, JiraPublishRequest, JiraTarget
from app.services import audit, jira
from app.services.crypto import store_secret

router = APIRouter(tags=["Integraciones"])


@router.get("/projects/{project_id}/integrations/jira/configuration", response_model=JiraConfigOut)
def get_configuration(project: Project = Depends(get_project), db: Session = Depends(get_db)):
    cfg = jira.get_config(db, project)
    db.commit()
    return jira.config_out(cfg, project)


@router.put("/projects/{project_id}/integrations/jira/configuration", response_model=JiraConfigOut)
def put_configuration(body: JiraConfigIn, project: Project = Depends(get_project), db: Session = Depends(get_db),
                      actor: str = Depends(get_actor)):
    """Solo la conexión: sitio, email y token. El proyecto destino y los tipos se eligen al publicar."""
    cfg = jira.get_config(db, project)
    # se compara solo el sitio: una URL guardada con ruta (tablero) no cuenta como cambio de conexión
    stored_site = f"https://{urlsplit(cfg.site_url).netloc}" if cfg.site_url else ""
    changed_connection = body.site_url != stored_site or body.account_email != cfg.account_email or bool(body.api_token)
    if body.api_token:
        cfg.secret_reference = store_secret(db, body.api_token, cfg.secret_reference)
    cfg.enabled = body.enabled
    cfg.site_url = body.site_url
    cfg.account_email = body.account_email
    if changed_connection or cfg.configuration_status == "not_configured":
        cfg.configuration_status = "configured" if cfg.site_url and cfg.secret_reference else "not_configured"
        cfg.last_validated_at = None
    audit.record(db, project_id=project.id, entity_type="integration", entity_id=cfg.id, action="configure",
                 actor=actor, after={"enabled": cfg.enabled, "site_url": cfg.site_url,
                                     "token_updated": bool(body.api_token)})
    db.commit()
    return jira.config_out(cfg, project)


@router.post("/projects/{project_id}/integrations/jira/test")
def test_connection(project: Project = Depends(get_project), db: Session = Depends(get_db),
                    actor: str = Depends(get_actor)):
    """Valida credenciales y acceso al sitio. Solo lectura: se permite también en modo autónomo."""
    result = jira.check_connection(db, project, actor)
    db.commit()
    return result


@router.get("/projects/{project_id}/integrations/jira/remote-projects")
def remote_projects(project: Project = Depends(get_project), db: Session = Depends(get_db)):
    """Proyectos del JIRA conectado (solo lectura)."""
    return jira.discover_projects(db, project)


@router.get("/projects/{project_id}/integrations/jira/remote-issue-types")
def remote_issue_types(key: str = Query(min_length=1, max_length=50, pattern=r"^[A-Za-z][A-Za-z0-9_]*$"),
                       project: Project = Depends(get_project), db: Session = Depends(get_db)):
    """Tipos de incidencia del proyecto de JIRA indicado y mapeo sugerido (solo lectura)."""
    return jira.discover_issue_types(db, project, key.upper())


@router.post("/projects/{project_id}/integrations/jira/preview")
def preview(body: JiraTarget | None = None, project: Project = Depends(get_project), db: Session = Depends(get_db)):
    """Vista previa de lo que se crearía en el proyecto destino. No escribe nada en JIRA."""
    target = body or JiraTarget()
    result = jira.build_preview(db, project, target.project_key, target.issue_type_mapping.model_dump())
    db.commit()
    return result


@router.post("/projects/{project_id}/integrations/jira/publish")
def publish(body: JiraPublishRequest, project: Project = Depends(get_project), db: Session = Depends(get_db),
            actor: str = Depends(get_actor)):
    run = jira.publish(db, project, target_key=body.project_key, mapping=body.issue_type_mapping.model_dump(),
                       confirm=body.confirm, confirmation_text=body.confirmation_text,
                       fingerprint=body.preview_fingerprint, actor=actor)
    db.commit()
    return {"id": run.id, "status": run.status, "summary": run.summary, "results": run.results}


@router.get("/projects/{project_id}/integrations/jira/runs")
def runs(project: Project = Depends(get_project), db: Session = Depends(get_db)):
    rows = db.scalars(select(JiraPublishRun).where(JiraPublishRun.project_id == project.id)
                      .order_by(JiraPublishRun.id.desc())).all()
    return [{"id": r.id, "status": r.status, "summary": r.summary, "results": r.results,
             "requested_by": r.requested_by, "created_at": r.created_at} for r in rows]
