"""Configuración de pruebas: base SQLite temporal creada con las migraciones reales de Alembic.

Los proveedores de IA y JIRA se simulan (identificados como tales); el motor de planificación es el real.
"""

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="pm_agent_test_"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["APP_ENV"] = "test"
os.environ["AI_PROVIDER"] = "none"  # nunca usar Claude Code real en las pruebas (se inyectan proveedores simulados)
os.environ["AI_RATE_LIMIT_PER_MINUTE"] = "0"
os.environ["SECRETS_ENCRYPTION_KEY"] = "u3Uc-qAi9iiCv3fkBfRUAKrM1gH8w51-nVU8M8A73Jg="

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.ai import provider as ai_provider  # noqa: E402
from app.ai.schemas import (  # noqa: E402
    DocumentRequirement,
    DocumentRequirements,
    ExecutiveSummary,
    GeneratedBacklog,
    GeneratedEpic,
    GeneratedStory,
    GeneratedTask,
    ScenarioExplanation,
)
from app.errors import AIUnavailable  # noqa: E402
from app.schemas import AcceptanceCriterion, AnalysisResult, ClarificationQuestion, SuggestedRequirement  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]


def _migrate() -> None:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.attributes["database_url"] = os.environ["DATABASE_URL"]
    command.upgrade(cfg, "head")


_migrate()


class FakeAIProvider:
    """Proveedor SIMULADO para pruebas (no llama a Claude Code)."""

    name = "fake"
    model = "fake-model"
    is_simulated = False  # simula al proveedor real para verificar el flujo de producción

    def __init__(self):
        self.calls: list[str] = []

    def analyze_requirements(self, project, requirements):
        self.calls.append("analyze")
        return AnalysisResult(
            summary="Análisis de prueba",
            actors=["Administrador"],
            ambiguities=["'rápido' no está definido"],
            clarification_questions=[ClarificationQuestion(question="¿Cuántos usuarios concurrentes?",
                                                           why_it_matters="Define la arquitectura", impact="high")],
            suggested_requirements=[SuggestedRequirement(title="Auditoría de acciones", type="security",
                                                         priority="medium", rationale="Trazabilidad")],
        )

    def generate_backlog(self, project, requirements, analysis, answers, profiles, extra):
        self.calls.append("backlog")
        self.last_extra = extra
        ac = [AcceptanceCriterion(given="un usuario registrado", when="ingresa", then="ve su panel")]
        return GeneratedBacklog(epics=[
            GeneratedEpic(title="Gestión de usuarios", stories=[
                GeneratedStory(ref="E1-S1", title="Login", as_a="usuario", i_want="ingresar", so_that="usar el sistema",
                               acceptance_criteria=ac, confidence="high", tasks=[
                                   GeneratedTask(ref="T1", title="API de login", profile_key="backend",
                                                 category="backend", estimated_hours=12),
                                   GeneratedTask(ref="T2", title="Pantalla de login", profile_key="frontend",
                                                 category="frontend", estimated_hours=8, depends_on=["T1"]),
                                   GeneratedTask(ref="T3", title="QA login", profile_key="qa", category="qa",
                                                 estimated_hours=4),
                               ]),
                GeneratedStory(ref="E1-S2", title="Perfil", depends_on=["E1-S1"], confidence="medium", tasks=[
                    GeneratedTask(ref="T1", title="API de perfil", profile_key="backend", estimated_hours=10),
                    GeneratedTask(ref="T2", title="Pantalla de perfil", profile_key="frontend", estimated_hours=10,
                                  depends_on=["T1", "T9"]),
                    GeneratedTask(ref="T3", title="QA perfil", profile_key="qa", category="qa", estimated_hours=4),
                ]),
            ]),
            GeneratedEpic(title="Reportes", stories=[
                GeneratedStory(ref="E2-S1", title="Reporte mensual", confidence="low", depends_on=["E2-S1"], tasks=[
                    GeneratedTask(ref="T1", title="Consulta de datos", profile_key="backend", estimated_hours=16),
                    GeneratedTask(ref="T2", title="Vista de reporte", profile_key="frontend", estimated_hours=12),
                    GeneratedTask(ref="T3", title="QA reporte", profile_key="qa", category="qa", estimated_hours=6),
                ]),
            ]),
        ], assumptions=["Supuesto de prueba", "El login de REQ-001 usa email y contraseña"])

    def executive_summary(self, project, metrics):
        self.calls.append("summary")
        return ExecutiveSummary(summary=f"Resumen: {metrics['duration_working_days']} días.")

    def explain_scenarios(self, project, comparisons):
        self.calls.append("explain")
        return ScenarioExplanation(explanation="Explicación de prueba", recommended_scenario=comparisons[0]["name"])

    def extract_requirements_from_document(self, project, filename, kind, data):
        self.calls.append(f"document:{kind}")
        self.last_document = (filename, kind, data)
        return DocumentRequirements(summary=f"Documento {filename}", requirements=[
            DocumentRequirement(title="Reserva de turnos online", description="El paciente reserva turnos.",
                                source_reference="p. 1"),
            DocumentRequirement(title="Disponibilidad 99,5 %", type="non_functional", priority="high",
                                source_reference="p. 2"),
        ], observations=["Falta definir horarios de atención"])


class FailingAIProvider(FakeAIProvider):
    """Simula la IA caída."""

    def _fail(self, *a, **k):
        raise AIUnavailable("Claude Code no respondió a tiempo. Probá de nuevo.")

    analyze_requirements = generate_backlog = executive_summary = explain_scenarios = _fail
    extract_requirements_from_document = _fail


@pytest.fixture()
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def fake_ai():
    fake = FakeAIProvider()
    ai_provider.set_test_provider(fake)
    yield fake
    ai_provider.set_test_provider(None)


@pytest.fixture()
def failing_ai():
    ai_provider.set_test_provider(FailingAIProvider())
    yield
    ai_provider.set_test_provider(None)


@pytest.fixture()
def project(client):
    r = client.post("/api/v1/projects", json={
        "name": "Portal de clientes", "description": "Portal web", "business_objective": "Reducir llamadas",
        "owner": "Ana", "calendar_configuration": {"working_days": [0, 1, 2, 3, 4], "holidays": ["2026-10-12"]},
    })
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture()
def planned_project(client, project, fake_ai):
    """Proyecto con requisitos, backlog generado y línea base confirmada."""
    pid = project["id"]
    client.post(f"/api/v1/projects/{pid}/requirements", json={"title": "Login de usuarios",
                                                              "description": "Los usuarios ingresan con email"})
    client.post(f"/api/v1/projects/{pid}/requirements/analyze")
    analyses = client.get(f"/api/v1/projects/{pid}/requirements/analyses").json()
    client.put(f"/api/v1/analyses/{analyses[0]['id']}/answers", json={"answers": {"0": "100 usuarios"}})
    r = client.post(f"/api/v1/projects/{pid}/backlog/generate", json={})
    assert r.status_code == 201, r.text
    r = client.post(f"/api/v1/projects/{pid}/plans/generate",
                    json={"confirm": True, "parameters": {"start_date": "2026-10-05"}})
    assert r.status_code == 200, r.text
    return {"project": project, "baseline": r.json()}
