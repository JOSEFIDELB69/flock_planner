"""Pruebas del motor de planificación real (sin mocks)."""

from datetime import date

import pytest

from app.planning.compare import compare, suggest_team_variants
from app.planning.engine import (
    Absence,
    EngineStory,
    EngineTask,
    MemberConfig,
    PlanningError,
    PlanningParameters,
    ProfileConfig,
    schedule,
)

MONDAY = date(2026, 10, 5)


def params(**kw):
    base = dict(start_date=MONDAY, review_overhead_pct=0, rework_pct=0, coordination_overhead_pct=0)
    base.update(kw)
    return PlanningParameters(**base)


def team(fe=1, be=1, qa=1, hours=8.0):
    return [
        ProfileConfig("frontend", "Desarrollador Frontend", fe, hours),
        ProfileConfig("backend", "Desarrollador Backend", be, hours),
        ProfileConfig("qa", "QA Engineer", qa, hours, is_qa=True),
    ]


def task(tid, profile, hours, story="S1", deps=(), confidence="medium"):
    return EngineTask(id=tid, title=tid, profile_key=profile, hours=hours, story_id=story, story_title=story,
                      epic_id="E1", epic_title="Épica", depends_on=list(deps), confidence=confidence)


def by_id(result):
    return {s["task_id"]: s for s in result["schedule"]}


def test_single_task_duration_and_dates():
    r = schedule([task("T1", "backend", 16)], [EngineStory("S1")], team(), params())
    assert r["duration_working_days"] == 2
    assert r["completion_date"] == "2026-10-06"
    assert r["base_effort_hours"] == 16


def test_weekend_is_skipped():
    # 40 h a 8 h/día desde el jueves: jue, vie, lun, mar, mié
    r = schedule([task("T1", "backend", 40)], [EngineStory("S1")], team(),
                 params(start_date=date(2026, 10, 8)))
    assert r["completion_date"] == "2026-10-14"
    assert r["duration_working_days"] == 5


def test_holidays_are_skipped():
    r = schedule([task("T1", "backend", 16)], [EngineStory("S1")], team(),
                 params(holidays=[date(2026, 10, 6)]))
    assert r["completion_date"] == "2026-10-07"
    assert r["duration_working_days"] == 2


def test_dependencies_are_respected():
    tasks = [task("A", "backend", 8), task("B", "frontend", 8, deps=["A"])]
    r = schedule(tasks, [EngineStory("S1")], team(), params())
    s = by_id(r)
    assert s["B"]["start"] >= s["A"]["finish"] - 1e-9
    assert r["duration_working_days"] == 2


def test_independent_tasks_run_in_parallel_on_different_profiles():
    tasks = [task("A", "backend", 8), task("B", "frontend", 8)]
    r = schedule(tasks, [EngineStory("S1")], team(), params())
    assert r["duration_working_days"] == 1


def test_qa_waits_for_development_of_story():
    tasks = [task("DEV", "backend", 16), task("QA", "qa", 8)]
    r = schedule(tasks, [EngineStory("S1")], team(), params())
    s = by_id(r)
    assert s["QA"]["start"] >= s["DEV"]["finish"] - 1e-9
    assert r["duration_working_days"] == 3


def test_story_dependencies_are_respected():
    tasks = [task("A", "backend", 8, story="S1"), task("B", "frontend", 8, story="S2")]
    stories = [EngineStory("S1"), EngineStory("S2", depends_on=["S1"])]
    r = schedule(tasks, stories, team(), params())
    assert by_id(r)["B"]["start"] >= by_id(r)["A"]["finish"] - 1e-9


def test_no_person_is_double_booked():
    tasks = [task(f"T{i}", "backend", 6 + i, story=f"S{i}") for i in range(8)]
    r = schedule(tasks, [EngineStory(f"S{i}") for i in range(8)], team(be=2), params())
    per_member = {}
    for s in r["schedule"]:
        per_member.setdefault(s["member_id"], []).append((s["start"], s["finish"]))
    for intervals in per_member.values():
        intervals.sort()
        for (a1, b1), (a2, _b2) in zip(intervals, intervals[1:]):
            assert a2 >= b1 - 1e-9


def test_duration_is_not_total_hours_divided_by_people():
    # cadena estricta: más gente no acorta
    tasks = [task("A", "backend", 8), task("B", "backend", 8, deps=["A"]), task("C", "backend", 8, deps=["B"])]
    one = schedule(tasks, [EngineStory("S1")], team(be=1), params())
    three = schedule(tasks, [EngineStory("S1")], team(be=3), params())
    assert one["duration_working_days"] == three["duration_working_days"] == 3


def test_more_people_reduce_duration_when_parallelizable():
    tasks = [task(f"T{i}", "backend", 8, story=f"S{i}") for i in range(4)]
    stories = [EngineStory(f"S{i}") for i in range(4)]
    one = schedule(tasks, stories, team(be=1), params())
    two = schedule(tasks, stories, team(be=2), params())
    assert one["duration_working_days"] == 4
    assert two["duration_working_days"] == 2


def test_coordination_overhead_gives_diminishing_returns():
    tasks = [task(f"T{i}", "backend", 8, story=f"S{i}") for i in range(4)]
    stories = [EngineStory(f"S{i}") for i in range(4)]
    two = schedule(tasks, stories, team(be=2), params(coordination_overhead_pct=10))
    assert two["duration_working_days"] > 2


def test_overheads_are_applied_to_non_qa_tasks_only():
    tasks = [task("DEV", "backend", 10), task("QA", "qa", 10)]
    r = schedule(tasks, [EngineStory("S1")], team(), params(review_overhead_pct=10, rework_pct=10))
    assert r["base_effort_hours"] == 20
    assert r["planned_effort_hours"] == pytest.approx(22)


def test_dedication_and_availability_reduce_capacity():
    p = team(hours=8)
    p[1].dedication_percentage = 50
    r = schedule([task("T1", "backend", 16)], [EngineStory("S1")], p, params())
    assert r["duration_working_days"] == 4
    p[1].dedication_percentage = 100
    p[1].members = [MemberConfig(name="Ana", availability_percentage=50)]
    r2 = schedule([task("T1", "backend", 16)], [EngineStory("S1")], p, params())
    assert r2["duration_working_days"] == 4
    assert r2["schedule"][0]["member_name"] == "Ana"


def test_absences_delay_work():
    p = team()
    p[1].members = [MemberConfig(name="Beto", absences=[Absence(MONDAY, date(2026, 10, 6))])]
    r = schedule([task("T1", "backend", 8)], [EngineStory("S1")], p, params())
    assert r["schedule"][0]["start_date"] == "2026-10-07"


def test_cycle_detection():
    tasks = [task("A", "backend", 8, deps=["B"]), task("B", "backend", 8, deps=["A"])]
    with pytest.raises(PlanningError) as exc:
        schedule(tasks, [EngineStory("S1")], team(), params())
    assert "circulares" in exc.value.message


def test_missing_profile_is_reported():
    with pytest.raises(PlanningError) as exc:
        schedule([task("A", "devops", 8)], [EngineStory("S1")], team(), params())
    assert exc.value.details["missing_profiles"] == ["devops"]


def test_profile_without_capacity_is_reported():
    with pytest.raises(PlanningError):
        schedule([task("A", "qa", 8)], [EngineStory("S1")], team(qa=0), params())


def test_critical_path_and_bottleneck():
    tasks = [task("B1", "backend", 40), task("F1", "frontend", 8), task("Q1", "qa", 8)]
    r = schedule(tasks, [EngineStory("S1")], team(), params())
    ids = [c["task_id"] for c in r["critical_path"]]
    assert ids == ["B1", "Q1"]
    assert r["main_bottleneck"] == "backend"


def test_costs_when_rates_configured():
    p = team()
    for prof in p:
        prof.hourly_rate = 10
    r = schedule([task("A", "backend", 8), task("Q", "qa", 2)], [EngineStory("S1")], p, params())
    assert r["total_cost"] == pytest.approx(100)


def test_staffing_cost_grows_with_idle_people():
    p1, p2 = team(), team(be=2)
    for prof in p1 + p2:
        prof.hourly_rate = 10
    tasks = [task("A", "backend", 8), task("B", "backend", 8, deps=["A"])]  # cadena: el 2.º backend no ayuda
    one = schedule(tasks, [EngineStory("S1")], p1, params())
    two = schedule(tasks, [EngineStory("S1")], p2, params())
    assert one["duration_working_days"] == two["duration_working_days"]
    assert one["total_cost"] == two["total_cost"]  # horas asignadas × tarifa: igual
    assert two["total_staffing_cost"] > one["total_staffing_cost"]  # capacidad pagada: mayor


def test_contingency_gap_adds_working_days_after_last_task():
    tasks = [task("A", "backend", 80)]  # 10 días laborables a 8 h
    base = schedule(tasks, [EngineStory("S1")], team(), params())
    gap = schedule(tasks, [EngineStory("S1")], team(), params(contingency_pct=15))
    assert base["duration_working_days"] == 10 and base["contingency_days"] == 0
    assert gap["work_duration_days"] == 10
    assert gap["contingency_days"] == 2  # ceil(10 × 15 %) = 2
    assert gap["duration_working_days"] == 12
    assert gap["work_completion_date"] == base["completion_date"] == "2026-10-16"
    assert gap["completion_date"] == "2026-10-20"  # lun 19 y mar 20 (salta el fin de semana)
    assert gap["schedule"] == base["schedule"]  # la reserva no altera las tareas
    assert gap["planned_effort_hours"] == base["planned_effort_hours"]
    assert any(m["type"] == "work" for m in gap["milestones"])
    assert any("Reserva por imprevistos" in a for a in gap["assumptions"])


def test_contingency_skips_holidays_and_raises_staffing_cost():
    p = team()
    for prof in p:
        prof.hourly_rate = 10
    tasks = [task("A", "backend", 16)]  # lun 5 y mar 6
    gap = schedule(tasks, [EngineStory("S1")], p, params(contingency_pct=50, holidays=[date(2026, 10, 7)]))
    assert gap["contingency_days"] == 1 and gap["completion_date"] == "2026-10-08"
    base = schedule(tasks, [EngineStory("S1")], p, params())
    assert gap["total_cost"] == base["total_cost"]  # horas asignadas iguales
    assert gap["total_staffing_cost"] > base["total_staffing_cost"]  # el equipo sigue asignado en la reserva


def test_target_date_risk():
    r = schedule([task("A", "backend", 80)], [EngineStory("S1")], team(), params(), target_date=date(2026, 10, 7))
    assert r["meets_target"] is False
    assert any("fecha objetivo" in x["title"] for x in r["risks"])


def test_deterministic_results():
    tasks = [task(f"T{i}", ["backend", "frontend", "qa"][i % 3], 3 + i, story=f"S{i % 4}") for i in range(20)]
    stories = [EngineStory(f"S{i}") for i in range(4)]
    a = schedule(tasks, stories, team(), params())
    b = schedule(tasks, stories, team(), params())
    assert a == b


def test_compare_formulas():
    tasks = [task(f"T{i}", "backend", 8, story=f"S{i}") for i in range(4)]
    stories = [EngineStory(f"S{i}") for i in range(4)]
    base_team = [{"profile_key": "backend", "quantity": 1}]
    sc_team = [{"profile_key": "backend", "quantity": 2}]
    base = schedule(tasks, stories, team(be=1), params())
    sc = schedule(tasks, stories, team(be=2), params())
    c = compare(base, sc, base_team, sc_team)
    assert c["baseline_duration"] == 4 and c["scenario_duration"] == 2
    assert c["time_savings_days"] == 2
    assert c["variation_pct"] == -50.0


def test_suggested_variants_only_for_profiles_with_work():
    tasks = [task("A", "backend", 8)]
    base = schedule(tasks, [EngineStory("S1")], team(), params())
    t = [{"profile_key": k, "profile_name": k, "quantity": 1, "dedication_percentage": 100}
         for k in ("frontend", "backend", "qa")]
    variants = suggest_team_variants(t, base)
    assert [v["single_profile"] for v in variants] == ["backend"]


# --------------------------------------------------------------------------- seniority


def test_seniority_changes_task_time_by_configured_percentage():
    p = params(seniority_factors={"sr": -25.0, "ssr": 0.0, "jr": 50.0})
    jr = [ProfileConfig("backend", "Backend", 1, 8.0, members=[MemberConfig(seniority="jr")])]
    sr = [ProfileConfig("backend", "Backend", 1, 8.0, members=[MemberConfig(seniority="sr")])]
    r_jr = schedule([task("T1", "backend", 16)], [EngineStory("S1")], jr, p)
    r_sr = schedule([task("T1", "backend", 16)], [EngineStory("S1")], sr, p)
    assert r_jr["planned_effort_hours"] == 24 and r_jr["duration_working_days"] == 3
    assert r_sr["planned_effort_hours"] == 12 and r_sr["duration_working_days"] == 2
    assert by_id(r_jr)["T1"]["seniority"] == "jr" and by_id(r_jr)["T1"]["seniority_pct"] == 50
    assert r_jr["base_effort_hours"] == 16  # la estimación base no cambia


def test_without_seniority_there_is_no_adjustment():
    r = schedule([task("T1", "backend", 16)], [EngineStory("S1")], team(), params())
    assert r["planned_effort_hours"] == 16
    assert not any("Seniority" in a for a in r["assumptions"])


def test_seniority_applies_to_qa_and_scheduler_prefers_the_faster_person():
    p = params(seniority_factors={"sr": -50.0, "ssr": 0.0, "jr": 100.0})
    qa = ProfileConfig("qa", "QA", 2, 8.0, is_qa=True,
                       members=[MemberConfig(name="Ana", seniority="jr"), MemberConfig(name="Bea", seniority="sr")])
    r = schedule([task("T1", "qa", 8)], [EngineStory("S1")], [qa], p)
    assert by_id(r)["T1"]["member_name"] == "Bea"
    assert r["planned_effort_hours"] == 4
    assert any("Seniority" in a for a in r["assumptions"])
    assert any("1 SR, 1 JR" in a for a in r["assumptions"])


def test_seniority_mix_is_mapped_to_people_in_order():
    from app.planning.adapters import member_seniorities, parameters_from_dict, profiles_from_config
    assert member_seniorities(4, {"sr": 1, "jr": 2}) == ["sr", "jr", "jr", None]
    assert member_seniorities(2, {"sr": 1, "ssr": 1, "jr": 1}) == ["sr", "ssr"]
    prof = profiles_from_config([{"profile_key": "backend", "quantity": 2, "availability_configuration": {
        "members": [{"name": "Juan"}], "seniority": {"sr": 0, "ssr": 1, "jr": 1}}}])[0]
    assert [(m.name, m.seniority) for m in prof.members] == [("Juan", "ssr"), ("", "jr")]
    pp = parameters_from_dict({"start_date": "2026-10-05"})
    assert pp.seniority_factors == {"sr": -15.0, "ssr": 0.0, "jr": 30.0}
    pp = parameters_from_dict({"start_date": "2026-10-05", "seniority_factors": {"jr": 40}})
    assert pp.seniority_factors["jr"] == 40 and pp.seniority_factors["sr"] == -15


# --------------------------------------------------------------------------- pronóstico Monte Carlo


def _forecast(tasks, prof=None, p=None, target=None, runs=300):
    from app.planning.forecast import forecast
    prof = prof or team()
    p = p or params()
    r = schedule(tasks, [EngineStory("S1")], prof, p, target)
    return r, forecast(tasks, [EngineStory("S1")], prof, p, r, target, runs=runs)


def test_forecast_is_reproducible_and_ordered():
    tasks = [task(f"T{i}", "backend", 16) for i in range(6)]
    r, f1 = _forecast(tasks)
    _, f2 = _forecast(tasks)
    assert f1 == f2  # semilla fija
    assert f1["p50"]["working_days"] <= f1["p80"]["working_days"] <= f1["p90"]["working_days"]
    assert f1["min_working_days"] <= r["work_duration_days"] < f1["max_working_days"]
    # rangos asimétricos hacia arriba: la mediana supera al plan determinista
    assert f1["p50"]["working_days"] >= r["work_duration_days"]
    assert f1["curve"][-1]["probability"] == 1.0
    assert 0 < f1["probability_work_only"] < 0.6


def test_confidence_widens_the_forecast():
    high = [task(f"T{i}", "backend", 16, confidence="high") for i in range(6)]
    low = [task(f"T{i}", "backend", 16, confidence="low") for i in range(6)]
    _, fh = _forecast(high)
    _, fl = _forecast(low)
    assert fl["p90"]["working_days"] > fh["p90"]["working_days"]
    assert fl["contingency_for_p80_pct"] > fh["contingency_for_p80_pct"]


def test_own_task_range_overrides_confidence_and_reserve_raises_probability():
    tight = [EngineTask(id=f"T{i}", title="t", profile_key="backend", hours=16, story_id="S1",
                        confidence="low", min_hours=15, max_hours=17) for i in range(5)]
    r, f = _forecast(tight)
    assert f["tasks_with_own_range"] == 5
    assert f["p90"]["working_days"] <= r["work_duration_days"] + 1
    loose = [task(f"T{i}", "backend", 16, confidence="low") for i in range(5)]
    _, without = _forecast(loose)
    _, with_reserve = _forecast(loose, p=params(contingency_pct=60))
    assert with_reserve["probability_plan"] > without["probability_plan"]


def test_forecast_target_probability_and_plan_integration():
    from app.planning.adapters import run_plan
    snap = {"epics": [{"id": 1, "title": "E", "stories": [{"id": 1, "title": "S", "estimate_confidence": "medium", "tasks": [
        {"id": 1, "title": "API", "profile_key": "backend", "estimated_hours": 40,
         "optimistic_hours": 30, "pessimistic_hours": 80},
        {"id": 2, "title": "QA", "profile_key": "qa", "estimated_hours": 8}]}]}]}
    team_cfg = [{"profile_key": "backend", "quantity": 1, "available_hours_per_day": 8},
                {"profile_key": "qa", "quantity": 1, "available_hours_per_day": 8, "is_qa": True}]
    r = run_plan(snap, team_cfg, {"start_date": "2026-10-05", "review_overhead_pct": 0, "rework_pct": 0},
                 date(2026, 10, 30))
    f = r["forecast"]
    assert f["tasks_with_own_range"] == 1 and f["base_hours_range"] == [36.8, 48.0, 92.0]
    assert f["probability_target"] == 1.0
    assert any("Monte Carlo" in a for a in r["assumptions"])
