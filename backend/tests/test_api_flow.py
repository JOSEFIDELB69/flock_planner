"""Pruebas de integración del flujo autónomo completo (IA simulada, motor real, base real con migraciones)."""

import io

from pypdf_check import pdf_page_count, pdf_text_sample

API = "/api/v1"


# 1. Crear proyecto ---------------------------------------------------------------------------------------------


def test_create_project_with_default_team(client, project):
    assert project["status"] == "draft"
    assert project["mode"] == "standalone"
    team = client.get(f"{API}/projects/{project['id']}/team").json()
    assert [(p["profile_key"], p["quantity"]) for p in team] == [("frontend", 1), ("backend", 1), ("qa", 1)]
    assert all(p["available_hours_per_day"] < 8 for p in team)  # horas productivas, no jornada completa


def test_project_validation(client):
    r = client.post(f"{API}/projects", json={"name": ""})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


# 2. Requisitos -------------------------------------------------------------------------------------------------


def test_requirements_crud_links_and_history(client, project):
    pid = project["id"]
    a = client.post(f"{API}/projects/{pid}/requirements", json={"title": "Registro", "type": "functional"}).json()
    b = client.post(f"{API}/projects/{pid}/requirements", json={"title": "Registro (dup)"}).json()
    assert a["code"] == "REQ-001" and b["code"] == "REQ-002"
    r = client.patch(f"{API}/requirements/{b['id']}", json={"duplicate_of_id": a["id"], "related_ids": [a["id"]]})
    assert r.json()["status"] == "duplicate" and r.json()["related_ids"] == [a["id"]]
    hist = client.get(f"{API}/requirements/{b['id']}/history").json()
    assert [h["action"] for h in hist] == ["update", "create"]
    assert client.delete(f"{API}/requirements/{a['id']}").status_code == 204


def test_bulk_delete_projects(client, planned_project):
    from app.db import SessionLocal
    from app.models import AuditLog, PlanVersion

    a = planned_project["project"]["id"]  # con línea base, backlog y escenarios
    b = client.post(f"{API}/projects", json={"name": "Borrador"}).json()["id"]
    body = {"ids": [a, b], "confirm": True}
    assert client.post(f"{API}/projects/delete", json={**body, "confirmation_text": "borrar"}).status_code == 422
    assert client.post(f"{API}/projects/delete", json={**body, "ids": [a, 999999], "confirmation_text": "ELIMINAR"}).status_code == 404
    assert client.get(f"{API}/projects/{a}").status_code == 200  # todo o nada
    r = client.post(f"{API}/projects/delete", json={**body, "confirmation_text": "eliminar"})
    assert r.json() == {"deleted": 2}
    assert client.get(f"{API}/projects/{a}").status_code == 404 and client.get(f"{API}/projects/{b}").status_code == 404
    with SessionLocal() as db:
        assert db.query(PlanVersion).filter_by(project_id=a).count() == 0  # cascada
        logs = db.query(AuditLog).filter(AuditLog.project_id.is_(None), AuditLog.entity_type == "project",
                                         AuditLog.entity_id.in_([a, b])).all()
        assert {l.action for l in logs} == {"delete"} and len(logs) == 2  # la eliminación queda registrada


def test_bulk_delete_requirements(client, project):
    pid = project["id"]
    reqs = client.post(f"{API}/projects/{pid}/requirements/bulk",
                       json={"text": "- Uno.\n- Dos.\n- Tres."}).json()
    ids = [r["id"] for r in reqs]
    # sin confirmación no se borra nada
    assert client.post(f"{API}/projects/{pid}/requirements/delete", json={"ids": ids}).status_code == 422
    # ids de otro proyecto: no se borra nada (todo o nada)
    other = client.post(f"{API}/projects", json={"name": "Otro"}).json()
    foreign = client.post(f"{API}/projects/{other['id']}/requirements", json={"title": "Ajeno"}).json()
    r = client.post(f"{API}/projects/{pid}/requirements/delete", json={"ids": [ids[0], foreign["id"]], "confirm": True})
    assert r.status_code == 404
    assert len(client.get(f"{API}/projects/{pid}/requirements").json()) == 3
    r = client.post(f"{API}/projects/{pid}/requirements/delete", json={"ids": ids[:2], "confirm": True})
    assert r.json() == {"deleted": 2}
    left = client.get(f"{API}/projects/{pid}/requirements").json()
    assert [x["id"] for x in left] == [ids[2]]
    log = client.get(f"{API}/projects/{pid}/audit?entity_type=requirement").json()
    assert sum(1 for a in log if a["action"] == "delete") == 2


def test_bulk_text_and_binary_attachment_rejected(client, project):
    pid = project["id"]
    r = client.post(f"{API}/projects/{pid}/requirements/bulk",
                    json={"text": "- El usuario puede registrarse.\n- El admin aprueba cuentas.\n- Exportar a PDF."})
    assert r.status_code == 201 and len(r.json()) == 3
    bad = client.post(f"{API}/projects/{pid}/documents",
                      files={"file": ("malware.exe", io.BytesIO(b"MZ\x00\x00"), "application/octet-stream")})
    assert bad.status_code == 415


# 3-4. Análisis con IA y manejo de indisponibilidad -----------------------------------------------------------------


def test_analyze_requirements_and_accept_suggestion(client, project, fake_ai):
    pid = project["id"]
    client.post(f"{API}/projects/{pid}/requirements", json={"title": "Login rápido"})
    r = client.post(f"{API}/projects/{pid}/requirements/analyze")
    assert r.status_code == 201, r.text
    analysis = r.json()
    assert analysis["result"]["clarification_questions"][0]["impact"] == "high"
    assert analysis["is_simulated"] is False
    acc = client.post(f"{API}/analyses/{analysis['id']}/accept-suggestions", json={"indexes": [0]})
    assert acc.json()[0]["title"] == "Auditoría de acciones"
    assert acc.json()[0]["source"] == "sugerencia IA"


def test_ai_unavailable_keeps_data(client, project, failing_ai):
    pid = project["id"]
    client.post(f"{API}/projects/{pid}/requirements", json={"title": "Algo"})
    r = client.post(f"{API}/projects/{pid}/requirements/analyze")
    assert r.status_code == 503
    assert "Claude Code" in r.json()["error"]["message"]
    assert len(client.get(f"{API}/projects/{pid}/requirements").json()) == 1


def test_ai_not_configured_message(client, project):
    pid = project["id"]
    client.post(f"{API}/projects/{pid}/requirements", json={"title": "Algo"})
    r = client.post(f"{API}/projects/{pid}/requirements/analyze")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "ai_not_configured"
    status = client.get(f"{API}/system/status").json()
    assert status["ai_provider"] is None and status["ai_available"] is False


def test_pending_clarifications_block_generation_until_answered(client, project, fake_ai):
    pid = project["id"]
    client.post(f"{API}/projects/{pid}/requirements", json={"title": "Login"})
    a = client.post(f"{API}/projects/{pid}/requirements/analyze").json()
    r = client.post(f"{API}/projects/{pid}/backlog/generate", json={})
    assert r.status_code == 422 and r.json()["error"]["code"] == "pending_clarifications"
    client.put(f"{API}/analyses/{a['id']}/answers", json={"proceed_with_assumptions": True})
    assert client.post(f"{API}/projects/{pid}/backlog/generate", json={}).status_code == 201


# 5-7. Backlog, subtareas y estimación ----------------------------------------------------------------------------


def test_generated_backlog_structure_and_cycle_cleanup(client, planned_project):
    pid = planned_project["project"]["id"]
    b = client.get(f"{API}/projects/{pid}/backlog").json()
    assert len(b["epics"]) == 2 and b["story_count"] == 3 and b["task_count"] == 9
    assert b["hours_by_profile"] == {"backend": 38, "frontend": 30, "qa": 14}
    login, perfil = b["epics"][0]["stories"]
    assert login["description"].startswith("Como usuario, quiero ingresar")
    assert login["acceptance_criteria"][0]["then"] == "ve su panel"
    assert perfil["depends_on_ids"] == [login["id"]]
    # la auto-dependencia de "Reporte mensual" fue descartada
    assert b["epics"][1]["stories"][0]["depends_on_ids"] == []
    # consistencia de sumas entre niveles
    assert b["total_hours"] == sum(e["total_hours"] for e in b["epics"]) == 82


def test_edit_task_hours_marks_revised(client, planned_project):
    pid = planned_project["project"]["id"]
    b = client.get(f"{API}/projects/{pid}/backlog").json()
    task = b["epics"][0]["stories"][0]["tasks"][0]
    r = client.patch(f"{API}/tasks/{task['id']}", json={"estimated_hours": 20})
    assert r.json()["estimate_status"] == "revised" and r.json()["original_estimate_hours"] == 12
    story = client.get(f"{API}/projects/{pid}/backlog").json()["epics"][0]["stories"][0]
    assert story["estimate_status"] == "revised"


def test_circular_dependency_is_rejected(client, planned_project):
    pid = planned_project["project"]["id"]
    s1, s2 = client.get(f"{API}/projects/{pid}/backlog").json()["epics"][0]["stories"]
    r = client.patch(f"{API}/stories/{s1['id']}", json={"depends_on_ids": [s2["id"]]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "circular_dependency"


def test_manual_backlog_without_ai(client, project):
    pid = project["id"]
    e = client.post(f"{API}/projects/{pid}/epics", json={"title": "Manual"}).json()
    s = client.post(f"{API}/epics/{e['id']}/stories", json={"title": "Historia manual"}).json()
    t1 = client.post(f"{API}/stories/{s['id']}/tasks", json={"title": "API", "profile_key": "backend",
                                                             "estimated_hours": 6}).json()
    t2 = client.post(f"{API}/stories/{s['id']}/tasks", json={"title": "UI", "profile_key": "frontend",
                                                             "estimated_hours": 6, "depends_on_ids": [t1["id"]]}).json()
    assert t2["depends_on_ids"] == [t1["id"]]
    prev = client.post(f"{API}/projects/{pid}/plans/generate", json={"parameters": {"start_date": "2026-10-05"}})
    assert prev.status_code == 200 and prev.json()["is_preview"] is True


# 8-10. Duración, dependencias y línea base ------------------------------------------------------------------------


def test_preview_is_not_persisted(client, planned_project):
    pid = planned_project["project"]["id"]
    before = client.get(f"{API}/projects/{pid}/plans").json()
    client.post(f"{API}/projects/{pid}/plans/generate", json={"parameters": {"start_date": "2026-10-05"}})
    assert client.get(f"{API}/projects/{pid}/plans").json() == before


def test_baseline_metrics_and_dependencies(client, planned_project):
    base = planned_project["baseline"]
    assert base["is_baseline"] is True and base["version_number"] == 1 and base["is_active"] is True
    m = base["metrics"]
    assert m["base_effort_hours"] == 82
    assert m["planned_effort_hours"] == round(68 * 1.2 + 14, 2)  # revisión + retrabajo solo fuera de QA
    assert base["estimated_duration"] > 82 / (3 * 6)  # nunca horas totales / personas
    sched = {s["task_id"]: s for s in base["schedule"]}
    for s in base["schedule"]:
        for dep in s["depends_on"]:
            assert s["start"] >= sched[dep]["finish"] - 1e-6
    assert "2026-10-12" in base["planning_parameters"]["holidays"]
    assert all(s["start_date"] != "2026-10-12" or s["start"] == s["finish"] for s in base["schedule"])


def test_second_confirmation_is_new_version_not_baseline(client, planned_project):
    pid = planned_project["project"]["id"]
    r = client.post(f"{API}/projects/{pid}/plans/generate", json={"confirm": True, "change_reason": "Ajuste"})
    assert r.json()["is_baseline"] is False and r.json()["version_number"] == 2
    plans = client.get(f"{API}/projects/{pid}/plans").json()
    assert sum(1 for p in plans if p["is_baseline"]) == 1


def test_baseline_is_immutable_at_orm_level(planned_project):
    import pytest

    from app.db import SessionLocal
    from app.models import ImmutablePlanError, PlanVersion

    with SessionLocal() as db:
        v = db.get(PlanVersion, planned_project["baseline"]["id"])
        v.estimated_duration = 1
        with pytest.raises(ImmutablePlanError):
            db.commit()


def test_missing_profile_blocks_planning(client, planned_project):
    pid = planned_project["project"]["id"]
    team = client.get(f"{API}/projects/{pid}/team").json()
    team = [p for p in team if p["profile_key"] != "qa"]
    client.put(f"{API}/projects/{pid}/team", json={"profiles": team})
    r = client.post(f"{API}/projects/{pid}/plans/generate", json={})
    assert r.status_code == 422 and r.json()["error"]["details"]["missing_profiles"] == ["qa"]


# 11-17. Escenarios ----------------------------------------------------------------------------------------------


def _team_with(client, pid, **quantities):
    team = client.get(f"{API}/projects/{pid}/team").json()
    for p in team:
        p.pop("id")
        if p["profile_key"] in quantities:
            p["quantity"] = quantities[p["profile_key"]]
    return team


def test_scenarios_simulate_compare_and_apply(client, planned_project):
    pid = planned_project["project"]["id"]
    base = planned_project["baseline"]
    # 11. más desarrolladores
    s_dev = client.post(f"{API}/projects/{pid}/scenarios",
                        json={"name": "B: +1 Backend +1 Frontend", "team_configuration": _team_with(
                            client, pid, backend=2, frontend=2)}).json()
    # 12. más capacidad de QA
    s_qa = client.post(f"{API}/projects/{pid}/scenarios",
                       json={"name": "D: +QA", "team_configuration": _team_with(client, pid, qa=2)}).json()
    assert s_dev["status"] == s_qa["status"] == "simulated"
    c = s_dev["comparison_metrics"]
    assert c["baseline_duration"] == base["estimated_duration"]
    assert c["time_savings_days"] == c["baseline_duration"] - c["scenario_duration"]
    expected = round((c["scenario_duration"] - c["baseline_duration"]) / c["baseline_duration"] * 100, 2)
    assert c["variation_pct"] == expected
    assert c["scenario_duration"] <= c["baseline_duration"]
    changes = {ch["profile_key"]: ch["quantity_delta"] for ch in c["capacity_changes"]}
    assert changes == {"backend": 1, "frontend": 1, "qa": 0}
    # 14. comparar
    cmp = client.get(f"{API}/scenarios/{s_dev['id']}/compare").json()
    assert cmp["baseline"]["version_number"] == 1
    # 15. aplicar: requiere confirmación
    pre = client.post(f"{API}/scenarios/{s_dev['id']}/apply", json={}).json()
    assert pre["requires_confirmation"] is True
    assert len(client.get(f"{API}/projects/{pid}/plans").json()) == 1
    applied = client.post(f"{API}/scenarios/{s_dev['id']}/apply", json={"confirm": True}).json()
    v = applied["version"]
    assert v["version_number"] == 2 and v["is_baseline"] is False and v["is_active"] is True
    assert v["source_scenario_id"] == s_dev["id"]
    assert v["estimated_duration"] == c["scenario_duration"]
    # 16. la línea base se conserva intacta
    b = client.get(f"{API}/plans/{base['id']}").json()
    assert b["is_baseline"] is True and b["estimated_duration"] == base["estimated_duration"]
    assert b["team_configuration"] == base["team_configuration"] and b["schedule"] == base["schedule"]
    # el equipo del proyecto pasa a ser el del escenario; los otros escenarios siguen disponibles
    team = {p["profile_key"]: p["quantity"] for p in client.get(f"{API}/projects/{pid}/team").json()}
    assert team == {"frontend": 2, "backend": 2, "qa": 1}
    statuses = {s["name"]: s["status"] for s in client.get(f"{API}/projects/{pid}/scenarios").json()}
    assert statuses == {"B: +1 Backend +1 Frontend": "applied", "D: +QA": "simulated"}
    # no se puede aplicar dos veces
    assert client.post(f"{API}/scenarios/{s_dev['id']}/apply", json={"confirm": True}).status_code == 409


def test_scenario_with_contingency_gap(client, planned_project):
    pid = planned_project["project"]["id"]
    base = planned_project["baseline"]
    s = client.post(f"{API}/projects/{pid}/scenarios", json={
        "name": "Equipo actual + reserva 20 %", "planning_parameters": {"contingency_pct": 20}}).json()
    c = s["comparison_metrics"]
    work = s["results"]["work_duration_days"]
    assert work == base["estimated_duration"]  # mismas tareas y equipo
    assert c["scenario_contingency_pct"] == 20 and c["scenario_contingency_days"] == -(-work * 20 // 100)
    assert c["scenario_duration"] == work + c["scenario_contingency_days"]
    assert c["time_savings_days"] == -c["scenario_contingency_days"]  # la reserva alarga el plazo
    assert s["results"]["schedule"] == base["schedule"]


def test_suggested_scenarios_and_explanation(client, planned_project, fake_ai):
    pid = planned_project["project"]["id"]
    created = client.post(f"{API}/projects/{pid}/scenarios/suggest", json={}).json()
    names = [s["name"] for s in created]
    assert "+1 Desarrollador Backend" in names and "+1 QA Engineer" in names
    assert all(s["status"] == "simulated" for s in created)
    assert "profiles_without_gain" in created[0]["comparison_metrics"]
    # repetir no duplica
    assert client.post(f"{API}/projects/{pid}/scenarios/suggest", json={}).json() == []
    exp = client.post(f"{API}/projects/{pid}/scenarios/explain", json={}).json()
    assert exp["explanation"] == "Explicación de prueba"


def test_scenario_requires_baseline(client, project):
    r = client.post(f"{API}/projects/{project['id']}/scenarios", json={"name": "X"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "no_baseline"


def test_restore_creates_new_version(client, planned_project):
    pid = planned_project["project"]["id"]
    base = planned_project["baseline"]
    r = client.post(f"{API}/plans/{base['id']}/restore", json={}).json()
    assert r["version_number"] == 2 and r["restored_from_version_id"] == base["id"]
    assert r["estimated_duration"] == base["estimated_duration"]
    assert len(client.get(f"{API}/projects/{pid}/plans").json()) == 2


def test_ai_summary_does_not_change_metrics(client, planned_project, fake_ai):
    base = planned_project["baseline"]
    r = client.post(f"{API}/plans/{base['id']}/summary").json()
    assert r["executive_summary"].startswith("Resumen:")
    after = client.get(f"{API}/plans/{base['id']}").json()
    assert after["metrics"] == base["metrics"] and after["executive_summary"] == r["executive_summary"]


# 18. PDF ----------------------------------------------------------------------------------------------------------


def test_pdf_exports_are_valid_and_downloadable(client, planned_project):
    pid = planned_project["project"]["id"]
    base = planned_project["baseline"]
    for kind in ("full", "executive", "optimization"):
        r = client.post(f"{API}/plans/{base['id']}/exports/pdf", json={"report_type": kind})
        assert r.status_code == 201, r.text
        exp = r.json()
        assert exp["filename"].startswith("Flock_Planner_Portal_de_clientes_") and exp["filename"].endswith("_v1.pdf")
        dl = client.get(f"{API}/exports/{exp['id']}")
        assert dl.status_code == 200 and dl.headers["content-type"] == "application/pdf"
        assert "attachment" in dl.headers["content-disposition"]
        assert dl.content.startswith(b"%PDF") and len(dl.content) == exp["size_bytes"] > 2000
        assert pdf_page_count(dl.content) >= 2
    full = client.get(f"{API}/exports/{client.get(f'{API}/projects/{pid}/exports').json()[-1]['id']}").content
    text = pdf_text_sample(full)
    assert "Portal de clientes" in text


# 19. Persistencia tras reinicio ---------------------------------------------------------------------------------


def test_data_survives_new_app_instance(planned_project):
    """Un engine/sesión nuevos (como tras reiniciar el proceso) leen los datos persistidos."""
    import os

    from sqlalchemy.orm import sessionmaker

    from app.db import make_engine
    from app.models import PlanVersion, Project

    engine = make_engine(os.environ["DATABASE_URL"])
    with sessionmaker(bind=engine)() as db:
        p = db.get(Project, planned_project["project"]["id"])
        assert p is not None and p.active_plan_version_id == planned_project["baseline"]["id"]
        assert db.get(PlanVersion, p.active_plan_version_id).is_baseline
    engine.dispose()


# 23. Seguridad ---------------------------------------------------------------------------------------------------


def test_security_headers_and_error_shape(client):
    r = client.get(f"{API}/projects/999999")
    assert r.status_code == 404
    assert r.json() == {"error": {"code": "not_found", "message": "No encontramos el proyecto.", "details": {}}}
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"


def test_delete_project_requires_confirmation(client, project):
    pid = project["id"]
    assert client.delete(f"{API}/projects/{pid}").status_code == 422
    assert client.delete(f"{API}/projects/{pid}?confirm=true").status_code == 204
    assert client.get(f"{API}/projects/{pid}").status_code == 404


def test_actor_header_is_sanitized_and_audited(client, project):
    pid = project["id"]
    client.post(f"{API}/projects/{pid}/requirements", json={"title": "x"}, headers={"X-PM-User": "Ana <script>"})
    log = client.get(f"{API}/projects/{pid}/audit?entity_type=requirement").json()
    assert log[0]["actor"] == "Ana script"


def test_dashboard_uses_persisted_data(client, planned_project):
    pid = planned_project["project"]["id"]
    d = client.get(f"{API}/projects/{pid}/dashboard").json()
    assert d["active_version"]["duration"] == planned_project["baseline"]["estimated_duration"]
    assert d["backlog"]["hours_by_profile"]["backend"] == 38
    assert d["versions_trend"][0]["is_baseline"] is True
    g = client.get(f"{API}/dashboard").json()
    assert g["active_projects"] >= 1


def test_team_seniority_cannot_exceed_quantity(client):
    pid = client.post("/api/v1/projects", json={"name": "Seniority"}).json()["id"]
    bad = {"profiles": [{"profile_key": "backend", "profile_name": "Backend", "quantity": 1,
                         "availability_configuration": {"members": [], "seniority": {"sr": 1, "jr": 1}}}]}
    assert client.put(f"/api/v1/projects/{pid}/team", json=bad).status_code == 422
    ok = {"profiles": [{"profile_key": "backend", "profile_name": "Backend", "quantity": 2,
                        "availability_configuration": {"members": [], "seniority": {"sr": 1, "jr": 1}}}]}
    r = client.put(f"/api/v1/projects/{pid}/team", json=ok)
    assert r.status_code == 200
    assert r.json()[0]["availability_configuration"]["seniority"] == {"sr": 1, "ssr": 0, "jr": 1}


def test_task_three_point_range_validation(client, planned_project):
    pid = planned_project["project"]["id"]
    task = client.get(f"/api/v1/projects/{pid}/backlog").json()["epics"][0]["stories"][0]["tasks"][0]
    h = task["estimated_hours"]
    url = f"/api/v1/tasks/{task['id']}"
    assert client.patch(url, json={"optimistic_hours": h + 1, "pessimistic_hours": h + 5}).status_code == 422
    assert client.patch(url, json={"optimistic_hours": h - 1}).status_code == 422  # falta el pesimista
    r = client.patch(url, json={"optimistic_hours": h - 2, "pessimistic_hours": h * 2})
    assert r.status_code == 200 and r.json()["pessimistic_hours"] == h * 2
    # horas nuevas fuera del rango → el rango se descarta y vuelve a usarse el de la confianza
    r = client.patch(url, json={"estimated_hours": h * 3})
    assert r.json()["optimistic_hours"] is None and r.json()["pessimistic_hours"] is None
    plan = client.post(f"/api/v1/projects/{pid}/plans/generate",
                       json={"confirm": False, "parameters": {"start_date": "2026-10-05",
                                                              "uncertainty": {"low": [-10, 200]}}}).json()
    f = plan["result"]["forecast"]
    assert f["uncertainty"]["low"] == [-10, 200] and f["p80"]["working_days"] >= plan["result"]["work_duration_days"]
