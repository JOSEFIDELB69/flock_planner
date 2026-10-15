"""Supuestos y advertencias de la generación del backlog: se guardan, se revisan y vuelven al agente."""

API = "/api/v1"


def _generate(client, pid):
    r = client.post(f"{API}/projects/{pid}/backlog/generate", json={"replace_existing": True})
    assert r.status_code == 201, r.text
    return r.json()


def test_observations_are_persisted_with_links(client, planned_project):
    pid = planned_project["project"]["id"]
    obs = client.get(f"{API}/projects/{pid}/backlog/observations").json()
    kinds = {o["kind"] for o in obs}
    assert kinds == {"warning", "assumption"}  # el backlog falso tiene dependencias inválidas
    assert all(o["status"] == "pending" for o in obs)
    login = next(o for o in obs if "REQ-001" in o["text"])
    assert login["links"] == [{"type": "requirement", "id": login["links"][0]["id"], "code": "REQ-001"}]
    warning = next(o for o in obs if o["kind"] == "warning")
    assert any(link["type"] in ("task", "story") for link in warning["links"])


def test_accept_correct_and_feedback_reaches_the_agent(client, planned_project, fake_ai):
    pid = planned_project["project"]["id"]
    obs = client.get(f"{API}/projects/{pid}/backlog/observations").json()
    plain = next(o for o in obs if o["text"] == "Supuesto de prueba")
    login = next(o for o in obs if "REQ-001" in o["text"])

    # corregir exige indicar qué es lo correcto
    assert client.patch(f"{API}/backlog-observations/{login['id']}", json={"status": "correction"}).status_code == 422
    r = client.patch(f"{API}/backlog-observations/{login['id']}",
                     json={"status": "correction", "correction": "El login es con SSO corporativo"})
    assert r.status_code == 200 and r.json()["status"] == "correction" and r.json()["resolved_at"]
    r = client.patch(f"{API}/backlog-observations/{plain['id']}", json={"status": "accepted"})
    assert r.json()["status"] == "accepted"

    out = _generate(client, pid)
    assert out["feedback_applied"] is True
    assert "SSO corporativo" in fake_ai.last_extra and "Supuesto de prueba" in fake_ai.last_extra
    # la nueva generación reemplaza las observaciones y vuelven a quedar pendientes
    fresh = client.get(f"{API}/projects/{pid}/backlog/observations").json()
    assert fresh and all(o["status"] == "pending" for o in fresh)
    assert client.get(f"{API}/projects/{pid}/audit").status_code in (200, 404)


def test_feedback_can_be_skipped_and_reset_to_pending(client, planned_project, fake_ai):
    pid = planned_project["project"]["id"]
    o = client.get(f"{API}/projects/{pid}/backlog/observations").json()[0]
    client.patch(f"{API}/backlog-observations/{o['id']}", json={"status": "correction", "correction": "X"})
    r = client.patch(f"{API}/backlog-observations/{o['id']}", json={"status": "pending", "correction": "ignorado"})
    assert r.json()["status"] == "pending" and r.json()["correction"] == "" and r.json()["resolved_at"] is None
    client.patch(f"{API}/backlog-observations/{o['id']}", json={"status": "correction", "correction": "Otra cosa"})
    r = client.post(f"{API}/projects/{pid}/backlog/generate", json={"replace_existing": True, "apply_observations": False})
    assert r.json()["feedback_applied"] is False and "Otra cosa" not in (fake_ai.last_extra or "")


def test_unknown_observation_returns_404(client):
    assert client.patch(f"{API}/backlog-observations/999999", json={"status": "accepted"}).status_code == 404
