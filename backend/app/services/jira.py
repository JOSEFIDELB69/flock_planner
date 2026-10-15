"""Integración opcional con JIRA Cloud (REST API v3, autenticación con API token).

La configuración guarda solo la conexión (sitio, email, token cifrado). El proyecto de JIRA destino y los
tipos de incidencia NO son configuración: se leen del JIRA conectado en el momento de publicar.

Reglas de seguridad:
* desactivada por defecto; nunca se usa para escribir en modo autónomo;
* solo escribe después de una vista previa y una confirmación explícita (se escribe la clave del proyecto
  destino y se envía la huella de la vista previa revisada);
* antes de publicar se verifica en JIRA que los tipos de incidencia elegidos existan en ese proyecto;
* evita duplicados con la tabla jira_issue_links (unicidad por elemento local);
* el token se guarda cifrado y nunca se devuelve ni se registra.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError, Forbidden
from app.models import IntegrationConfiguration, JiraIssueLink, JiraPublishRun, Project, utcnow
from app.services import audit
from app.services.backlog import load_epics
from app.services.crypto import read_secret

# Permite inyectar un transporte simulado en las pruebas automatizadas.
TRANSPORT: httpx.BaseTransport | None = None
KINDS = ("epic", "story", "task")


def get_config(db: Session, project: Project) -> IntegrationConfiguration:
    cfg = db.scalars(select(IntegrationConfiguration).where(
        IntegrationConfiguration.project_id == project.id, IntegrationConfiguration.provider == "jira")).first()
    if cfg is None:
        cfg = IntegrationConfiguration(project_id=project.id, provider="jira", enabled=False,
                                       configuration_status="not_configured", issue_type_mapping={})
        db.add(cfg)
        db.flush()
    return cfg


def config_out(cfg: IntegrationConfiguration, project: Project) -> dict[str, Any]:
    return {
        "project_id": project.id, "enabled": cfg.enabled, "configuration_status": cfg.configuration_status,
        "site_url": cfg.site_url, "auth_method": cfg.auth_method, "account_email": cfg.account_email,
        "has_secret": bool(cfg.secret_reference), "last_validated_at": cfg.last_validated_at,
        "last_error": cfg.last_error, "project_mode": project.mode,
    }


class JiraClient:
    def __init__(self, site_url: str, email: str, token: str):
        site_url = f"https://{urlsplit(site_url).netloc}"  # solo el sitio, aunque se haya guardado una URL de tablero
        self._client = httpx.Client(base_url=site_url, auth=(email, token), timeout=20.0, transport=TRANSPORT,
                                    headers={"Accept": "application/json"})

    def _req(self, method: str, path: str, **kw) -> Any:
        try:
            r = self._client.request(method, path, **kw)
        except httpx.HTTPError:
            raise AppError("No pudimos conectar con JIRA. Revisá la URL del sitio y la conexión.",
                           code="jira_unreachable", status_code=502)
        if r.status_code in (401, 403):
            raise AppError("JIRA rechazó las credenciales o faltan permisos en el proyecto.", code="jira_auth",
                           status_code=502)
        if r.status_code == 404:
            raise AppError("JIRA no encontró el recurso (revisá el proyecto elegido y tus permisos).",
                           code="jira_not_found", status_code=502)
        if r.status_code >= 400:
            detail = ""
            try:
                body = r.json()
                detail = "; ".join(body.get("errorMessages", []) + [f"{k}: {v}" for k, v in
                                                                     (body.get("errors") or {}).items()])
            except ValueError:
                pass
            raise AppError(f"JIRA respondió {r.status_code}. {detail}".strip(), code="jira_error", status_code=502,
                           details={"status": r.status_code})
        return r.json() if r.content else {}

    def myself(self) -> dict:
        return self._req("GET", "/rest/api/3/myself")

    def list_projects(self, limit: int = 500) -> list[dict]:
        out: list[dict] = []
        start = 0
        while len(out) < limit:
            data = self._req("GET", "/rest/api/3/project/search",
                             params={"startAt": start, "maxResults": 100, "orderBy": "name"})
            values = data.get("values", [])
            out.extend(values)
            if data.get("isLast", True) or not values:
                break
            start += len(values)
        return out[:limit]

    def issue_types(self, key: str) -> list[dict]:
        data = self._req("GET", f"/rest/api/3/issue/createmeta/{key}/issuetypes")
        return data.get("issueTypes") or data.get("values") or []

    def search_labeled(self, key: str, label: str) -> list[dict]:
        jql = f'project = "{key}" AND labels = "{label}"'
        data = self._req("GET", "/rest/api/3/search/jql", params={"jql": jql, "fields": "summary,labels",
                                                                    "maxResults": 100})
        return data.get("issues", [])

    def create_issue(self, fields: dict) -> dict:
        return self._req("POST", "/rest/api/3/issue", json={"fields": fields})


def _client(db: Session, cfg: IntegrationConfiguration) -> JiraClient:
    token = read_secret(db, cfg.secret_reference)
    if not (cfg.site_url and cfg.account_email and token):
        raise AppError("Completá la URL del sitio, el email y el API token de JIRA y guardá la configuración.",
                       code="jira_incomplete", status_code=422)
    return JiraClient(cfg.site_url, cfg.account_email, token)


def check_connection(db: Session, project: Project, actor: str) -> dict[str, Any]:
    """Valida solo las credenciales y el acceso al sitio (no hay proyecto ni tipos en la configuración)."""
    cfg = get_config(db, project)
    try:
        client = _client(db, cfg)
        me = client.myself()
        count = len(client.list_projects(limit=100))
    except AppError as exc:
        cfg.configuration_status = "error"
        cfg.last_error = exc.message
        audit.record(db, project_id=project.id, entity_type="integration", entity_id=cfg.id, action="test_failed",
                     actor=actor, after={"error": exc.message})
        db.commit()
        raise
    cfg.configuration_status = "validated"
    cfg.last_error = ""
    cfg.last_validated_at = utcnow()
    audit.record(db, project_id=project.id, entity_type="integration", entity_id=cfg.id, action="test_ok",
                 actor=actor)
    return {"ok": True, "account": me.get("displayName", ""), "visible_projects": count}


# --------------------------------------------------------------------------- descubrimiento (solo lectura)


def discover_projects(db: Session, project: Project) -> list[dict[str, Any]]:
    """Proyectos de JIRA visibles para la cuenta configurada."""
    projects = _client(db, get_config(db, project)).list_projects()
    return [{"key": p.get("key"), "name": p.get("name"), "type": p.get("projectTypeKey", ""),
             "style": p.get("style", "")} for p in projects if p.get("key")]


def _normalize_types(raw: list[dict]) -> list[dict[str, Any]]:
    types = []
    for t in raw:
        if not t.get("name"):
            continue
        level = t.get("hierarchyLevel")
        if level is None:
            level = -1 if t.get("subtask") else 0
        types.append({"id": str(t.get("id", "")), "name": t["name"], "subtask": bool(t.get("subtask")),
                      "hierarchy_level": int(level)})
    return types


def _pick(types: list[dict], level: int, preferred: tuple[str, ...]) -> str:
    candidates = [t for t in types if t["hierarchy_level"] == level]
    for name in preferred:
        for t in candidates:
            if t["name"].lower() == name:
                return t["name"]
    return candidates[0]["name"] if candidates else ""


def suggest_mapping(types: list[dict]) -> dict[str, str]:
    """Mapeo sugerido por jerarquía de JIRA: 1 = épica, 0 = estándar, -1 = subtarea."""
    return {
        "epic": _pick(types, 1, ("epic", "épica", "epica")),
        "story": _pick(types, 0, ("story", "historia", "user story", "historia de usuario", "task", "tarea")),
        "task": _pick(types, -1, ("subtask", "sub-task", "subtarea", "sub-tarea")),
    }


def discover_issue_types(db: Session, project: Project, key: str) -> dict[str, Any]:
    """Tipos de incidencia del proyecto de JIRA indicado y el mapeo sugerido."""
    types = _normalize_types(_client(db, get_config(db, project)).issue_types(key))
    return {"project_key": key, "issue_types": types, "suggested_mapping": suggest_mapping(types)}


# --------------------------------------------------------------------------- vista previa y publicación


def _adf(text: str) -> dict:
    paragraphs = [p for p in text.split("\n") if p.strip()] or [" "]
    return {"type": "doc", "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": p[:30000]}]} for p in paragraphs]}


def _label(project: Project) -> str:
    return f"pm-agent-p{project.id}"


def _local_items(db: Session, project: Project, links: dict) -> list[dict[str, Any]]:
    def existing(kind: str, local_id: int) -> str | None:
        link = links.get((kind, local_id))
        return link.jira_key if link else None

    items: list[dict[str, Any]] = []
    for e in load_epics(db, project.id):
        items.append({"local_type": "epic", "local_id": e.id, "code": e.code, "summary": e.title,
                      "description": e.description, "parent_code": None, "existing_key": existing("epic", e.id)})
        for s in e.stories:
            ac = "\n".join(f"Dado {c.get('given')}, cuando {c.get('when')}, entonces {c.get('then')}."
                           for c in s.acceptance_criteria or [])
            hours = sum(t.estimated_hours for t in s.tasks)
            deps = ", ".join(d.code for d in s.depends_on)
            desc = s.description + (f"\n\nCriterios de aceptación:\n{ac}" if ac else "") + \
                f"\n\nEstimación: {hours:g} h" + (f"\nDepende de: {deps}" if deps else "")
            items.append({"local_type": "story", "local_id": s.id, "code": s.code, "summary": s.title,
                          "description": desc, "parent_code": e.code, "estimated_hours": hours,
                          "existing_key": existing("story", s.id)})
            for t in s.tasks:
                items.append({"local_type": "task", "local_id": t.id, "code": t.code, "summary": t.title,
                              "description": f"{t.description}\n\nPerfil: {t.profile_key}\nHoras: "
                                             f"{t.estimated_hours:g}\nCriterio de finalización: {t.done_criteria}",
                              "parent_code": s.code, "estimated_hours": t.estimated_hours,
                              "existing_key": existing("task", t.id)})
    return items


def _fingerprint(target_key: str, mapping: dict[str, str], to_create: list[dict]) -> str:
    payload = [target_key, [mapping.get(k, "") for k in KINDS],
               [(i["local_type"], i["local_id"], i["summary"], i["description"]) for i in to_create]]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()[:16]


def build_preview(db: Session, project: Project, target_key: str, mapping: dict[str, str],
                  check_remote: bool = True) -> dict[str, Any]:
    cfg = get_config(db, project)
    target_key = (target_key or "").strip().upper()
    mapping = {k: (mapping or {}).get(k, "").strip() for k in KINDS}
    links = {(l.local_type, l.local_id): l for l in db.scalars(
        select(JiraIssueLink).where(JiraIssueLink.project_id == project.id)).all()}
    items = _local_items(db, project, links)
    pending: list[str] = []
    if not target_key:
        pending.append("Elegí el proyecto de JIRA destino")
    labels = {"epic": "épicas", "story": "historias", "task": "subtareas"}
    for k in KINDS:
        if not mapping[k]:
            pending.append(f"Elegí el tipo de incidencia para {labels[k]}")
    remote_duplicates: list[dict[str, Any]] = []
    if check_remote and target_key and cfg.configuration_status == "validated":
        try:
            client = _client(db, cfg)
            available = {t["name"] for t in _normalize_types(client.issue_types(target_key))}
            missing = [v for v in mapping.values() if v and v not in available]
            if missing:
                pending.append("Estos tipos no existen en " + target_key + ": " + ", ".join(missing))
            known = {l.jira_key for l in links.values()}
            for issue in client.search_labeled(target_key, _label(project)):
                if issue.get("key") not in known:
                    remote_duplicates.append({"key": issue.get("key"),
                                              "summary": (issue.get("fields") or {}).get("summary", "")})
        except AppError as exc:
            pending.append(f"No se pudo consultar JIRA: {exc.message}")
    to_create = [i for i in items if not i["existing_key"]]
    return {
        "project_key": target_key,
        "issue_type_mapping": mapping,
        "items": items,
        "counts": {k: sum(1 for i in to_create if i["local_type"] == k) for k in KINDS},
        "already_published": sum(1 for i in items if i["existing_key"]),
        "pending_fields": pending,
        "remote_duplicates": remote_duplicates,
        "fingerprint": _fingerprint(target_key, mapping, to_create),
        "can_publish": project.mode == "jira" and cfg.enabled and cfg.configuration_status == "validated"
        and not pending,
    }


def publish(db: Session, project: Project, *, target_key: str, mapping: dict[str, str], confirm: bool,
            confirmation_text: str, fingerprint: str, actor: str) -> JiraPublishRun:
    if project.mode != "jira":
        raise Forbidden("El proyecto está en modo autónomo: no se publica nada en JIRA.", code="standalone_mode")
    cfg = get_config(db, project)
    if not cfg.enabled or cfg.configuration_status != "validated":
        raise Forbidden("La integración con JIRA no está habilitada o no fue validada.", code="jira_not_ready")
    target_key = (target_key or "").strip().upper()
    if not confirm or not target_key or confirmation_text.strip().upper() != target_key:
        raise Forbidden("Falta la confirmación explícita: escribí la clave del proyecto de JIRA para publicar.",
                        code="confirmation_required")
    # verificación remota de tipos incluida: no se supone que existan en todos los proyectos
    preview = build_preview(db, project, target_key, mapping, check_remote=True)
    if preview["pending_fields"]:
        raise AppError("No se puede publicar todavía: " + "; ".join(preview["pending_fields"]),
                       code="jira_incomplete", status_code=422)
    if fingerprint != preview["fingerprint"]:
        raise AppError("El backlog o el destino cambiaron desde la vista previa. Generá la vista previa de nuevo "
                       "antes de publicar.", code="stale_preview", status_code=409)
    mapping = preview["issue_type_mapping"]
    client = _client(db, cfg)
    run = JiraPublishRun(project_id=project.id, status="running", requested_by=actor)
    db.add(run)
    db.flush()
    keys = {i["code"]: i["existing_key"] for i in preview["items"] if i["existing_key"]}
    results: list[dict[str, Any]] = []
    label = _label(project)
    for item in preview["items"]:
        if item["existing_key"]:
            results.append({"code": item["code"], "status": "skipped", "key": item["existing_key"],
                            "message": "Ya publicado anteriormente"})
            continue
        fields: dict[str, Any] = {
            "project": {"key": target_key},
            "summary": f"{item['summary']}"[:250],
            "issuetype": {"name": mapping[item["local_type"]]},
            "description": _adf(item["description"] + f"\n\nReferencia Flock Planner: {item['code']}"),
            "labels": ["pm_agent", label],
        }
        parent = item.get("parent_code")
        if parent:
            if parent not in keys:
                results.append({"code": item["code"], "status": "error", "key": None,
                                "message": f"No se creó porque falló el elemento padre {parent}"})
                continue
            fields["parent"] = {"key": keys[parent]}
        try:
            created = client.create_issue(fields)
        except AppError as exc:
            results.append({"code": item["code"], "status": "error", "key": None, "message": exc.message})
            continue
        keys[item["code"]] = created["key"]
        db.add(JiraIssueLink(project_id=project.id, local_type=item["local_type"], local_id=item["local_id"],
                             jira_key=created["key"], jira_id=str(created.get("id", "")), publish_run_id=run.id))
        db.flush()
        results.append({"code": item["code"], "status": "created", "key": created["key"], "message": ""})
    errors = sum(1 for r in results if r["status"] == "error")
    created_n = sum(1 for r in results if r["status"] == "created")
    run.status = "completed" if errors == 0 else ("partial" if created_n else "failed")
    run.results = results
    run.summary = {"created": created_n, "skipped": sum(1 for r in results if r["status"] == "skipped"),
                   "errors": errors, "project_key": target_key}
    audit.record(db, project_id=project.id, entity_type="jira_publish", entity_id=run.id, action="publish",
                 actor=actor, after={**run.summary, "issue_type_mapping": mapping})
    db.flush()
    return run
