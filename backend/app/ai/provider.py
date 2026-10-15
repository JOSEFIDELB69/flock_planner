"""Proveedores de IA en tiempo de ejecución.

* ClaudeCodeProvider (app/ai/claude_code.py): proveedor de Flock Planner, la CLI de Claude Code en modo headless.
* DemoProvider: heurísticas locales para demostraciones sin IA (AI_PROVIDER=demo). Todos sus resultados se
  marcan como simulados (is_simulated=True).
"""

from __future__ import annotations

import logging
import re
import time
from typing import Protocol

from app.ai.schemas import (
    DocumentRequirement,
    DocumentRequirements,
    ExecutiveSummary,
    GeneratedBacklog,
    GeneratedEpic,
    GeneratedStory,
    GeneratedTask,
    ScenarioExplanation,
)
from app.config import get_settings
from app.planning.compare import recommendation_key
from app.errors import AIUnavailable
from app.schemas import AcceptanceCriterion, AnalysisResult, ClarificationQuestion

log = logging.getLogger("pm_agent.ai")


class AIProvider(Protocol):
    name: str
    model: str
    is_simulated: bool

    def analyze_requirements(self, project: dict, requirements: list[dict]) -> AnalysisResult: ...

    def generate_backlog(self, project: dict, requirements: list[dict], analysis: dict | None, answers: dict,
                         profiles: list[dict], extra: str) -> GeneratedBacklog: ...

    def executive_summary(self, project: dict, metrics: dict) -> ExecutiveSummary: ...

    def explain_scenarios(self, project: dict, comparisons: list[dict]) -> ScenarioExplanation: ...

    def extract_requirements_from_document(self, project: dict, filename: str, kind: str,
                                           data: bytes) -> DocumentRequirements: ...


# --------------------------------------------------------------------------- Demo (simulado)

_VAGUE = ["rápido", "rapido", "fácil", "facil", "intuitiv", "escalable", "etc", "varios", "moderno", "flexible",
          "robusto", "amigable", "óptimo", "optimo", "adecuad", "simple"]
_ACTORS = {"paciente": "Paciente", "administrador": "Administrador", "admin": "Administrador", "cliente": "Cliente",
           "usuario": "Usuario", "operador": "Operador", "supervisor": "Supervisor", "gerente": "Gerente",
           "proveedor": "Proveedor", "auditor": "Auditor"}
_INTEGRATIONS = ["api", "jira", "sap", "salesforce", "pago", "email", "correo", "sso", "oauth", "webhook",
                 "erp", "crm", "slack", "whatsapp", "sms"]
_NFR = {"rendimiento": "Rendimiento", "segur": "Seguridad", "disponib": "Disponibilidad", "escal": "Escalabilidad",
        "accesib": "Accesibilidad", "auditor": "Auditoría", "backup": "Respaldo", "latencia": "Latencia"}
_UI_WORDS = ["pantalla", "formulario", "vista", "dashboard", "tablero", "interfaz", "listado", "botón", "boton",
             "reporte", "web", "móvil", "movil", "página", "pagina", "usuario"]


def _norm(text: str) -> str:
    return text.lower()


class DemoProvider:
    """Resultados heurísticos y deterministas. Siempre identificados como SIMULADOS."""

    name = "demo"
    model = "demo-heuristico"
    is_simulated = True

    def analyze_requirements(self, project, requirements):
        corpus = " ".join(f"{r['title']} {r['description']}" for r in requirements)
        low = _norm(corpus)
        actors = sorted({v for k, v in _ACTORS.items() if k in low}) or ["Usuario final"]
        integrations = sorted({w.upper() if len(w) <= 4 else w.capitalize() for w in _INTEGRATIONS
                               if re.search(rf"\b{w}", low)})
        nfr = sorted({v for k, v in _NFR.items() if k in low})
        ambiguities, questions = [], []
        for r in requirements:
            text = _norm(f"{r['title']} {r['description']}")
            vague = [w for w in _VAGUE if w in text]
            if vague:
                ambiguities.append(f"{r['code']}: términos imprecisos ({', '.join(vague)}).")
                questions.append(ClarificationQuestion(
                    question=f"¿Qué criterio medible define '{vague[0]}' en {r['code']} ({r['title']})?",
                    why_it_matters="Sin un criterio medible no se puede estimar ni verificar el requisito.",
                    impact="medium"))
            if len(r["description"].strip()) < 40:
                questions.append(ClarificationQuestion(
                    question=f"¿Podés detallar el alcance de {r['code']} ({r['title']})?",
                    why_it_matters="La descripción es muy breve; el esfuerzo puede variar mucho.",
                    impact="high"))
        missing = []
        if not nfr:
            missing.append("No se indicaron requisitos no funcionales (rendimiento, seguridad, disponibilidad).")
        if not project.get("target_date"):
            missing.append("No hay fecha objetivo definida.")
        return AnalysisResult(
            summary=f"[SIMULADO] Análisis heurístico de {len(requirements)} requisitos del proyecto "
                    f"{project.get('name', '')}. No reemplaza el análisis con IA.",
            objectives=[project.get("business_objective")] if project.get("business_objective") else [],
            actors=actors,
            functionalities=[r["title"] for r in requirements if r["type"] == "functional"],
            constraints=[],
            non_functional=nfr,
            integrations=integrations,
            dependencies=[f"Integración con {i}" for i in integrations],
            ambiguities=ambiguities,
            risks=["Requisitos con términos imprecisos pueden generar retrabajo."] if ambiguities else [],
            missing_information=missing,
            clarification_questions=questions[:8],
            suggested_requirements=[],
        )

    def generate_backlog(self, project, requirements, analysis, answers, profiles, extra):
        keys = {p["profile_key"] for p in profiles}
        qa_key = next((p["profile_key"] for p in profiles if p.get("is_qa")), None)
        fe = "frontend" if "frontend" in keys else None
        be = "backend" if "backend" in keys else (next(iter(keys - {qa_key}), None) if keys else None)
        groups: dict[str, list[dict]] = {}
        for r in requirements:
            if r["status"] in ("rejected", "duplicate"):
                continue
            groups.setdefault(r.get("group_name") or _type_label(r["type"]), []).append(r)
        epics: list[GeneratedEpic] = []
        for ei, (group, reqs) in enumerate(groups.items(), start=1):
            stories = []
            for si, r in enumerate(reqs, start=1):
                text = _norm(f"{r['title']} {r['description']}")
                size = 1.0 + min(len(r["description"]), 600) / 300.0  # 1.0 – 3.0
                tasks: list[GeneratedTask] = []
                if be:
                    tasks.append(GeneratedTask(ref="T1", title=f"Backend: {r['title'][:80]}", category="backend",
                                               profile_key=be, estimated_hours=round(8 * size),
                                               done_criteria="Endpoints implementados con pruebas unitarias."))
                if fe and any(w in text for w in _UI_WORDS):
                    tasks.append(GeneratedTask(ref="T2", title=f"Frontend: {r['title'][:80]}", category="frontend",
                                               profile_key=fe, estimated_hours=round(6 * size),
                                               depends_on=["T1"] if be else [],
                                               done_criteria="Pantalla funcional conectada a la API."))
                if qa_key:
                    tasks.append(GeneratedTask(ref="T3", title=f"QA funcional: {r['title'][:80]}", category="qa",
                                               profile_key=qa_key, estimated_hours=round(3 * size),
                                               done_criteria="Casos de prueba ejecutados y defectos reportados."))
                stories.append(GeneratedStory(
                    ref=f"E{ei}-S{si}",
                    title=r["title"][:200],
                    as_a="usuario del sistema", i_want=f"contar con: {r['title'][:150]}",
                    so_that="cumplir el objetivo del requisito",
                    description=f"[SIMULADO] Derivada de {r['code']}. {r['description'][:500]}",
                    priority=r["priority"],
                    business_value={"critical": 9, "high": 7, "medium": 5, "low": 3}[r["priority"]],
                    acceptance_criteria=[AcceptanceCriterion(
                        given="un usuario autorizado", when=f"utiliza la funcionalidad '{r['title'][:80]}'",
                        then="el sistema responde según lo descripto en el requisito")],
                    assumptions="Estimación heurística de demostración; debe revisarse.",
                    confidence="low",
                    tasks=tasks,
                ))
            epics.append(GeneratedEpic(title=group, description=f"[SIMULADO] Agrupa {len(reqs)} requisitos.",
                                       priority="medium", requirement_codes=[r["code"] for r in reqs],
                                       stories=stories))
        if not epics:
            raise AIUnavailable("No hay requisitos activos para generar el backlog.", code="no_requirements",
                                status_code=422)
        return GeneratedBacklog(epics=epics, assumptions=["Backlog generado en modo demostración (simulado)."],
                                notes="[SIMULADO]")

    def executive_summary(self, project, metrics):
        return ExecutiveSummary(summary=(
            f"[SIMULADO] El proyecto {project.get('name', '')} requiere {metrics.get('planned_effort_hours')} h "
            f"planificadas ({metrics.get('base_effort_hours')} h de esfuerzo base). El motor estima "
            f"{metrics.get('duration_working_days')} días laborables, con fin el {metrics.get('completion_date')}. "
            f"Cuello de botella principal: {metrics.get('main_bottleneck') or 'sin identificar'}. "
            "Las estimaciones no son garantías."))

    def extract_requirements_from_document(self, project, filename, kind, data):
        from app.services.documents import extract_text, split_free_text

        try:
            text = extract_text(filename, data).text
        except AIUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 - p. ej. PDF escaneado: la demo no tiene visión
            raise AIUnavailable(f"[SIMULADO] El modo demostración no pudo leer el documento: {exc}")
        items = split_free_text(text)[:100]
        return DocumentRequirements(
            summary=f"[SIMULADO] Lectura heurística de «{filename}». No reemplaza la lectura con IA.",
            requirements=[DocumentRequirement(title=re.split(r"(?<=[.!?])\s", i, maxsplit=1)[0][:300],
                                              description=i, source_reference=filename) for i in items],
            observations=["Requisitos detectados por viñetas y párrafos (modo demostración)."],
        )

    def explain_scenarios(self, project, comparisons):
        if not comparisons:
            return ScenarioExplanation(explanation="[SIMULADO] No hay escenarios simulados para comparar.")
        best = min(comparisons, key=lambda c: recommendation_key(c["name"], c["metrics"]))
        lines = [f"{c['name']}: {c['metrics']['scenario_duration']} días ({c['metrics']['variation_pct']:+.1f} %)."
                 for c in comparisons]
        return ScenarioExplanation(
            explanation="[SIMULADO] " + " ".join(lines),
            recommended_scenario=best["name"],
            rationale="[SIMULADO] Menor duración calculada por el motor.",
            caveats=["Explicación heurística de demostración; no proviene de un modelo de IA."],
        )


def _type_label(t: str) -> str:
    return {"functional": "Funcionalidades principales", "non_functional": "Requisitos no funcionales",
            "technical": "Base técnica", "security": "Seguridad", "integration": "Integraciones",
            "performance": "Rendimiento", "operational": "Operación"}.get(t, "General")


# --------------------------------------------------------------------------- resolución


# Solo para pruebas automatizadas: permite inyectar un proveedor simulado.
_test_override: AIProvider | None = None


def set_test_provider(provider: AIProvider | None) -> None:
    global _test_override
    _test_override = provider


def get_ai_provider() -> AIProvider:
    if _test_override is not None:
        return _test_override
    settings = get_settings()
    choice = settings.resolved_ai_provider
    if choice == "claude_code":
        from app.ai.claude_code import ClaudeCodeProvider

        return ClaudeCodeProvider(settings)
    if choice == "demo":
        return DemoProvider()
    raise AIUnavailable(
        "La IA no está configurada. Usá AI_PROVIDER=claude_code (CLI de Claude Code con sesión iniciada) o "
        "AI_PROVIDER=demo para resultados simulados. Mientras tanto podés cargar requisitos y backlog a mano.",
        code="ai_not_configured",
    )


def timed(operation: str):
    """Mide la duración de una llamada de IA (ms)."""

    class _Timer:
        def __enter__(self):
            self.start = time.perf_counter()
            return self

        def __exit__(self, *exc):
            self.ms = int((time.perf_counter() - self.start) * 1000)
            return False

    return _Timer()
