"""Integración JIRA con un transporte HTTP SIMULADO (no hay conexión real con Atlassian)."""

import json

import httpx
import pytest

from app.services import jira as jira_service

API = "/api/v1"
TARGET = {"project_key": "PMA", "issue_type_mapping": {"epic": "Epic", "story": "Story", "task": "Subtask"}}


class FakeJira:
    def __init__(self):
        self.created: list[dict] = []
        self.requests: list[tuple[str, str]] = []
        self.fail_summary: str | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append((request.method, request.url.path))
        path = request.url.path
        if path == "/rest/api/3/myself":
            return httpx.Response(200, json={"displayName": "Bot"})
        if path == "/rest/api/3/project/search":
            return httpx.Response(200, json={"isLast": True, "values": [
                {"key": "PMA", "name": "PM Agent", "projectTypeKey": "software", "style": "next-gen"},
                {"key": "OPS", "name": "Operaciones", "projectTypeKey": "business"}]})
        if path == "/rest/api/3/issue/createmeta/PMA/issuetypes":
            return httpx.Response(200, json={"issueTypes": [
                {"id": "1", "name": "Task", "hierarchyLevel": 0}, {"id": "2", "name": "Epic", "hierarchyLevel": 1},
                {"id": "3", "name": "Story", "hierarchyLevel": 0},
                {"id": "4", "name": "Subtask", "hierarchyLevel": -1, "subtask": True}]})
        if path == "/rest/api/3/search/jql":
            return httpx.Response(200, json={"issues": []})
        if path == "/rest/api/3/issue" and request.method == "POST":
            fields = json.loads(request.content)["fields"]
            if self.fail_summary and fields["summary"] == self.fail_summary:
                return httpx.Response(400, json={"errors": {"summary": "inválido"}})
            n = len(self.created) + 1
            self.created.append(fields)
            return httpx.Response(201, json={"id": str(1000 + n), "key": f"PMA-{n}"})
        return httpx.Response(404, json={})


@pytest.fixture()
def fake_jira():
    fake = FakeJira()
    jira_service.TRANSPORT = httpx.MockTransport(fake.handler)
    yield fake
    jira_service.TRANSPORT = None


def _configure(client, pid, enabled=True):
    return client.put(f"{API}/projects/{pid}/integrations/jira/configuration", json={
        "enabled": enabled, "site_url": "https://acme.atlassian.net", "account_email": "bot@acme.com",
        "api_token": "token-de-prueba"})


def _publish(client, pid, fingerprint, text="PMA", target=TARGET):
    return client.post(f"{API}/projects/{pid}/integrations/jira/publish", json={
        **target, "confirm": True, "confirmation_text": text, "preview_fingerprint": fingerprint})


def test_configuration_has_only_connection_data(client, project, fake_jira):
    out = _configure(client, project["id"]).json()
    assert "external_project_reference" not in out and "issue_type_mapping" not in out
    assert out["site_url"] == "https://acme.atlassian.net"


def test_projects_and_issue_types_are_discovered_from_jira(client, project, fake_jira):
    pid = project["id"]
    _configure(client, pid)
    projects = client.get(f"{API}/projects/{pid}/integrations/jira/remote-projects").json()
    assert [p["key"] for p in projects] == ["PMA", "OPS"]
    types = client.get(f"{API}/projects/{pid}/integrations/jira/remote-issue-types?key=pma").json()
    assert [t["name"] for t in types["issue_types"]] == ["Task", "Epic", "Story", "Subtask"]
    assert types["suggested_mapping"] == {"epic": "Epic", "story": "Story", "task": "Subtask"}
    assert not any(m == "POST" for m, _ in fake_jira.requests)  # descubrir es solo lectura


def test_suggest_mapping_falls_back_by_hierarchy():
    types = [{"name": "Épica", "hierarchy_level": 1}, {"name": "Tarea", "hierarchy_level": 0},
             {"name": "Subtarea", "hierarchy_level": -1}]
    assert jira_service.suggest_mapping(types) == {"epic": "Épica", "story": "Tarea", "task": "Subtarea"}


def test_disabled_by_default_and_standalone_never_publishes(client, planned_project, fake_jira):
    pid = planned_project["project"]["id"]
    cfg = client.get(f"{API}/projects/{pid}/integrations/jira/configuration").json()
    assert cfg["enabled"] is False and cfg["configuration_status"] == "not_configured"
    _configure(client, pid)
    assert client.post(f"{API}/projects/{pid}/integrations/jira/test").status_code == 200  # solo lectura
    prev = client.post(f"{API}/projects/{pid}/integrations/jira/preview", json=TARGET).json()
    assert prev["can_publish"] is False
    r = _publish(client, pid, prev["fingerprint"])
    assert r.status_code == 403 and r.json()["error"]["code"] == "standalone_mode"
    assert not any(m == "POST" for m, _ in fake_jira.requests)


def test_token_is_encrypted_and_never_returned(client, planned_project, fake_jira):
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import AuditLog, StoredSecret

    pid = planned_project["project"]["id"]
    out = _configure(client, pid).json()
    assert out["has_secret"] is True and "api_token" not in out
    assert "token-de-prueba" not in json.dumps(out)
    with SessionLocal() as db:
        secrets = db.scalars(select(StoredSecret)).all()
        assert secrets and all("token-de-prueba" not in s.ciphertext for s in secrets)
        logs = db.scalars(select(AuditLog).where(AuditLog.project_id == pid)).all()
        assert all("token-de-prueba" not in json.dumps(l.after or {}) for l in logs)


def test_site_url_is_normalized_to_site_root(client, project):
    r = client.put(f"{API}/projects/{project['id']}/integrations/jira/configuration", json={
        "site_url": "https://acme.atlassian.net/jira/software/projects/SCRUM/boards/1?filter=&groupBy=none"})
    assert r.json()["site_url"] == "https://acme.atlassian.net"


def test_enabling_keeps_validation_when_only_site_path_differs(client, project, fake_jira):
    from app.db import SessionLocal
    from app.models import IntegrationConfiguration

    pid = project["id"]
    _configure(client, pid, enabled=False)
    client.post(f"{API}/projects/{pid}/integrations/jira/test")
    with SessionLocal() as db:  # simula una URL guardada antes con la ruta del tablero
        cfg = db.query(IntegrationConfiguration).filter_by(project_id=pid).one()
        cfg.site_url = "https://acme.atlassian.net/jira/software/projects/SCRUM/boards/1"
        db.commit()
    out = client.put(f"{API}/projects/{pid}/integrations/jira/configuration", json={
        "enabled": True, "site_url": "https://acme.atlassian.net", "account_email": "bot@acme.com"}).json()
    assert out["enabled"] is True and out["configuration_status"] == "validated"


def test_preview_requires_target_and_existing_types(client, planned_project, fake_jira):
    pid = planned_project["project"]["id"]
    client.patch(f"{API}/projects/{pid}", json={"mode": "jira"})
    _configure(client, pid)
    client.post(f"{API}/projects/{pid}/integrations/jira/test")
    empty = client.post(f"{API}/projects/{pid}/integrations/jira/preview").json()
    assert empty["can_publish"] is False and any("proyecto de JIRA" in p for p in empty["pending_fields"])
    wrong = {"project_key": "PMA", "issue_type_mapping": {"epic": "Epic", "story": "Story", "task": "Sub-task"}}
    bad = client.post(f"{API}/projects/{pid}/integrations/jira/preview", json=wrong).json()
    assert bad["can_publish"] is False and any("Sub-task" in p for p in bad["pending_fields"])


def test_publish_requires_validation_confirmation_and_prevents_duplicates(client, planned_project, fake_jira):
    pid = planned_project["project"]["id"]
    client.patch(f"{API}/projects/{pid}", json={"mode": "jira"})
    _configure(client, pid)
    prev = client.post(f"{API}/projects/{pid}/integrations/jira/preview", json=TARGET).json()
    # sin validar la conexión
    r = _publish(client, pid, prev["fingerprint"])
    assert r.status_code == 403 and r.json()["error"]["code"] == "jira_not_ready"
    t = client.post(f"{API}/projects/{pid}/integrations/jira/test")
    assert t.status_code == 200 and t.json()["visible_projects"] == 2
    prev = client.post(f"{API}/projects/{pid}/integrations/jira/preview", json=TARGET).json()
    assert prev["counts"] == {"epic": 2, "story": 3, "task": 9} and prev["can_publish"] is True
    # sin confirmación explícita
    r = _publish(client, pid, prev["fingerprint"], text="")
    assert r.status_code == 403 and r.json()["error"]["code"] == "confirmation_required"
    # vista previa desactualizada (o destino distinto al revisado)
    assert _publish(client, pid, "otra").status_code == 409
    other = {**TARGET, "issue_type_mapping": {"epic": "Epic", "story": "Task", "task": "Subtask"}}
    assert _publish(client, pid, prev["fingerprint"], target=other).status_code == 409
    assert fake_jira.created == []
    # publicación con fallo parcial
    fake_jira.fail_summary = "Perfil"
    run = _publish(client, pid, prev["fingerprint"]).json()
    assert run["status"] == "partial"
    assert run["summary"]["errors"] == 4  # la historia y sus 3 subtareas
    assert len(fake_jira.created) == 10
    story_fields = next(f for f in fake_jira.created if f["summary"] == "Login")
    assert story_fields["parent"]["key"].startswith("PMA-") and "pm-agent-p" + str(pid) in story_fields["labels"]
    sub = next(f for f in fake_jira.created if f["summary"] == "API de login")
    assert sub["issuetype"]["name"] == "Subtask"
    # reintento: solo crea lo que falló, sin duplicar
    fake_jira.fail_summary = None
    prev2 = client.post(f"{API}/projects/{pid}/integrations/jira/preview", json=TARGET).json()
    assert prev2["already_published"] == 10 and sum(prev2["counts"].values()) == 4
    r2 = _publish(client, pid, prev2["fingerprint"]).json()
    assert r2["status"] == "completed" and r2["summary"]["created"] == 4 and r2["summary"]["skipped"] == 10
    assert len(fake_jira.created) == 14
    summaries = [f["summary"] for f in fake_jira.created]
    assert len(summaries) == len(set(summaries))


def test_core_flow_never_contacts_jira(client, planned_project, fake_jira):
    """Planificación, escenarios y PDF funcionan sin ninguna llamada a JIRA."""
    pid = planned_project["project"]["id"]
    base = planned_project["baseline"]
    client.post(f"{API}/projects/{pid}/scenarios/suggest", json={})
    client.post(f"{API}/plans/{base['id']}/exports/pdf", json={"report_type": "full"})
    assert fake_jira.requests == []
