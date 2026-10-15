"""Esquemas Pydantic de entrada/salida de la API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Priority = Literal["low", "medium", "high", "critical"]
Confidence = Literal["low", "medium", "high"]
RequirementType = Literal[
    "functional", "non_functional", "technical", "security", "integration", "performance", "operational"
]
RequirementStatus = Literal["draft", "confirmed", "rejected", "duplicate", "suggested"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------- proyectos


class CalendarConfig(BaseModel):
    working_days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])
    hours_per_day: float = Field(default=8.0, gt=0, le=24)
    holidays: list[date] = Field(default_factory=list)

    @field_validator("working_days")
    @classmethod
    def _wd(cls, v: list[int]) -> list[int]:
        if not v or any(d < 0 or d > 6 for d in v):
            raise ValueError("Los días laborables deben estar entre 0 (lunes) y 6 (domingo) y no estar vacíos.")
        return sorted(set(v))


class ProjectBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10_000)
    business_objective: str = Field(default="", max_length=10_000)
    owner: str = Field(default="", max_length=200)
    target_date: date | None = None
    timezone: str = Field(default="America/Argentina/Buenos_Aires", max_length=64)
    calendar_configuration: CalendarConfig = Field(default_factory=CalendarConfig)
    mode: Literal["standalone", "jira"] = "standalone"
    currency: str = Field(default="USD", max_length=10)


class ProjectCreate(ProjectBase):
    status: Literal["draft", "active"] = "draft"


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    business_objective: str | None = Field(default=None, max_length=10_000)
    owner: str | None = Field(default=None, max_length=200)
    target_date: date | None = None
    timezone: str | None = Field(default=None, max_length=64)
    calendar_configuration: CalendarConfig | None = None
    mode: Literal["standalone", "jira"] | None = None
    currency: str | None = Field(default=None, max_length=10)
    status: Literal["draft", "active", "archived"] | None = None


class ProjectOut(ORM, ProjectBase):
    id: int
    status: str
    active_plan_version_id: int | None
    created_at: datetime
    updated_at: datetime


class ProjectSummary(ProjectOut):
    requirement_count: int = 0
    epic_count: int = 0
    story_count: int = 0
    task_count: int = 0
    total_hours: float = 0
    has_baseline: bool = False
    export_count: int = 0
    active_version_number: int | None = None
    estimated_completion_date: date | None = None
    estimated_duration: int | None = None


# --------------------------------------------------------------------------- requisitos


class RequirementCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=20_000)
    type: RequirementType = "functional"
    priority: Priority = "medium"
    source: str = Field(default="manual", max_length=200)
    status: RequirementStatus = "draft"
    group_name: str = Field(default="", max_length=120)
    assumptions: str = Field(default="", max_length=10_000)
    risks: str = Field(default="", max_length=10_000)


class RequirementUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=20_000)
    type: RequirementType | None = None
    priority: Priority | None = None
    source: str | None = Field(default=None, max_length=200)
    status: RequirementStatus | None = None
    group_name: str | None = Field(default=None, max_length=120)
    assumptions: str | None = Field(default=None, max_length=10_000)
    risks: str | None = Field(default=None, max_length=10_000)
    duplicate_of_id: int | None = None
    related_ids: list[int] | None = None
    depends_on_ids: list[int] | None = None


class RequirementOut(ORM):
    id: int
    project_id: int
    code: str
    title: str
    description: str
    type: str
    priority: str
    source: str
    status: str
    group_name: str
    assumptions: str
    risks: str
    duplicate_of_id: int | None
    source_document_id: int | None = None
    related_ids: list[int] = Field(default_factory=list)
    depends_on_ids: list[int] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ProjectBulkDelete(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)
    confirm: bool = False
    confirmation_text: str = Field(default="", max_length=50)


class RequirementBulkDelete(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=1000)
    confirm: bool = False


class RequirementBulkStatus(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=1000)
    status: Literal["confirmed", "rejected", "draft"]


class RequirementBulkText(BaseModel):
    """Texto libre: una línea o párrafo por requisito (separados por líneas en blanco o viñetas)."""

    text: str = Field(min_length=1, max_length=100_000)
    source: str = Field(default="texto libre", max_length=200)


# --------------------------------------------------------------------------- análisis IA


class ClarificationQuestion(BaseModel):
    question: str
    why_it_matters: str = ""
    impact: Literal["low", "medium", "high"] = "medium"


class SuggestedRequirement(BaseModel):
    title: str
    description: str = ""
    type: RequirementType = "functional"
    priority: Priority = "medium"
    rationale: str = ""


class AnalysisResult(BaseModel):
    summary: str = ""
    objectives: list[str] = Field(default_factory=list)
    actors: list[str] = Field(default_factory=list)
    functionalities: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    non_functional: list[str] = Field(default_factory=list)
    integrations: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    clarification_questions: list[ClarificationQuestion] = Field(default_factory=list)
    suggested_requirements: list[SuggestedRequirement] = Field(default_factory=list)


class AnalysisOut(ORM):
    id: int
    project_id: int
    result: AnalysisResult
    answers: dict[str, Any]
    proceed_with_assumptions: bool
    is_simulated: bool
    model: str
    created_at: datetime
    created_by: str


class AnalysisAnswers(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)
    proceed_with_assumptions: bool = False


class AcceptSuggestions(BaseModel):
    indexes: list[int]


# --------------------------------------------------------------------------- backlog


class AcceptanceCriterion(BaseModel):
    given: str = ""
    when: str = ""
    then: str = ""


class TaskOut(ORM):
    id: int
    story_id: int
    code: str
    title: str
    description: str
    category: str
    profile_key: str
    estimated_hours: float
    original_estimate_hours: float
    estimate_status: str
    done_criteria: str
    risks: str
    status: str
    depends_on_ids: list[int] = Field(default_factory=list)


class StoryOut(ORM):
    id: int
    epic_id: int
    code: str
    title: str
    description: str
    acceptance_criteria: list[AcceptanceCriterion]
    priority: str
    business_value: int
    assumptions: str
    risks: str
    estimate_confidence: str
    estimate_status: str
    status: str
    depends_on_ids: list[int] = Field(default_factory=list)
    tasks: list[TaskOut] = Field(default_factory=list)
    hours_by_profile: dict[str, float] = Field(default_factory=dict)
    total_hours: float = 0


class EpicOut(ORM):
    id: int
    project_id: int
    code: str
    title: str
    description: str
    priority: str
    status: str
    source: str
    stories: list[StoryOut] = Field(default_factory=list)
    total_hours: float = 0


class BacklogOut(BaseModel):
    project_id: int
    epics: list[EpicOut]
    total_hours: float
    hours_by_profile: dict[str, float]
    story_count: int
    task_count: int
    is_simulated: bool = False


class EpicCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=20_000)
    priority: Priority = "medium"


class EpicUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=20_000)
    priority: Priority | None = None
    status: str | None = Field(default=None, max_length=20)


class StoryCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=20_000)
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    priority: Priority = "medium"
    business_value: int = Field(default=5, ge=1, le=10)
    assumptions: str = ""
    risks: str = ""
    estimate_confidence: Confidence = "medium"


class StoryUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=20_000)
    acceptance_criteria: list[AcceptanceCriterion] | None = None
    priority: Priority | None = None
    business_value: int | None = Field(default=None, ge=1, le=10)
    assumptions: str | None = None
    risks: str | None = None
    estimate_confidence: Confidence | None = None
    status: str | None = Field(default=None, max_length=20)
    epic_id: int | None = None
    depends_on_ids: list[int] | None = None


def check_task_range(low: float | None, likely: float | None, high: float | None) -> None:
    if (low is None) != (high is None):
        raise ValueError("Cargá las dos horas del rango (optimista y pesimista) o ninguna.")
    if low is not None and high is not None:
        if likely is not None and not (low <= likely <= high):
            raise ValueError("El rango debe cumplir: optimista ≤ horas estimadas ≤ pesimista.")
        if high <= low:
            raise ValueError("Las horas pesimistas deben ser mayores que las optimistas.")


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=20_000)
    category: str = Field(default="backend", max_length=40)
    profile_key: str = Field(min_length=1, max_length=40)
    estimated_hours: float = Field(default=0, ge=0, le=2000)
    optimistic_hours: float | None = Field(default=None, ge=0, le=2000)
    pessimistic_hours: float | None = Field(default=None, ge=0, le=4000)
    done_criteria: str = ""
    risks: str = ""
    depends_on_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def _range(self) -> "TaskCreate":
        check_task_range(self.optimistic_hours, self.estimated_hours, self.pessimistic_hours)
        return self


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=20_000)
    category: str | None = Field(default=None, max_length=40)
    profile_key: str | None = Field(default=None, min_length=1, max_length=40)
    estimated_hours: float | None = Field(default=None, ge=0, le=2000)
    optimistic_hours: float | None = Field(default=None, ge=0, le=2000)
    pessimistic_hours: float | None = Field(default=None, ge=0, le=4000)
    done_criteria: str | None = None
    risks: str | None = None
    status: str | None = Field(default=None, max_length=20)
    depends_on_ids: list[int] | None = None


class BacklogGenerateRequest(BaseModel):
    analysis_id: int | None = None
    replace_existing: bool = False
    additional_instructions: str = Field(default="", max_length=4000)
    # enviar al agente las correcciones y los supuestos aceptados de la generación anterior
    apply_observations: bool = True


class ObservationUpdate(BaseModel):
    status: Literal["pending", "accepted", "correction"]
    correction: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def _needs_text(self) -> "ObservationUpdate":
        if self.status == "correction" and not self.correction.strip():
            raise ValueError("Indicá qué es lo correcto para registrar la corrección.")
        return self


class ObservationOut(ORM):
    id: int
    project_id: int
    kind: str
    text: str
    position: int
    status: str
    correction: str
    links: list[dict[str, Any]]
    created_at: datetime
    resolved_at: datetime | None
    resolved_by: str


# --------------------------------------------------------------------------- equipo


class Absence(BaseModel):
    start: date
    end: date


class MemberAvailability(BaseModel):
    name: str = Field(default="", max_length=120)
    availability_percentage: float = Field(default=100, ge=0, le=100)
    hours_per_day: float | None = Field(default=None, gt=0, le=24)
    absences: list[Absence] = Field(default_factory=list)


class SeniorityMix(BaseModel):
    """Cuántas personas del perfil son SR, SSR y JR. Las que no se asignan no tienen ajuste."""
    sr: int = Field(default=0, ge=0, le=100)
    ssr: int = Field(default=0, ge=0, le=100)
    jr: int = Field(default=0, ge=0, le=100)


class AvailabilityConfig(BaseModel):
    members: list[MemberAvailability] = Field(default_factory=list)
    seniority: SeniorityMix | None = None


class TeamProfileIn(BaseModel):
    profile_key: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9_\-]+$")
    profile_name: str = Field(min_length=1, max_length=120)
    quantity: int = Field(ge=0, le=100)
    available_hours_per_day: float = Field(default=6.0, gt=0, le=24)
    dedication_percentage: float = Field(default=100.0, gt=0, le=100)
    hourly_rate: float | None = Field(default=None, ge=0)
    is_qa: bool = False
    availability_configuration: AvailabilityConfig = Field(default_factory=AvailabilityConfig)

    @model_validator(mode="after")
    def _seniority_fits(self) -> "TeamProfileIn":
        mix = self.availability_configuration.seniority
        if mix and mix.sr + mix.ssr + mix.jr > self.quantity:
            raise ValueError(f"{self.profile_name}: la seniority asignada (SR + SSR + JR) supera la cantidad de personas.")
        return self


class TeamProfileOut(ORM, TeamProfileIn):
    id: int


class SeniorityFactors(BaseModel):
    """% que se suma al tiempo de cada tarea según la seniority (negativo = más rápido)."""
    sr: float = Field(default=-15.0, ge=-80, le=300)
    ssr: float = Field(default=0.0, ge=-80, le=300)
    jr: float = Field(default=30.0, ge=-80, le=300)


class Uncertainty(BaseModel):
    """Rango [optimista, pesimista] en % sobre las horas, según la confianza de la historia."""
    high: tuple[float, float] = (-10.0, 25.0)
    medium: tuple[float, float] = (-15.0, 50.0)
    low: tuple[float, float] = (-25.0, 100.0)

    @model_validator(mode="after")
    def _ranges(self) -> "Uncertainty":
        for name, (lo, hi) in (("alta", self.high), ("media", self.medium), ("baja", self.low)):
            if not (-95 <= lo <= 0 <= hi <= 500):
                raise ValueError(f"Confianza {name}: el optimista va de −95 % a 0 % y el pesimista de 0 % a 500 %.")
        return self


class PlanningParametersIn(BaseModel):
    start_date: date | None = None
    working_days: list[int] | None = None
    holidays: list[date] | None = None
    review_overhead_pct: float = Field(default=10.0, ge=0, le=200)
    rework_pct: float = Field(default=10.0, ge=0, le=200)
    coordination_overhead_pct: float = Field(default=5.0, ge=0, le=50)
    qa_after_dev: bool = True
    contingency_pct: float = Field(default=0.0, ge=0, le=100, description="Reserva por imprevistos (% de la duración)")
    seniority_factors: SeniorityFactors | None = None
    uncertainty: Uncertainty | None = None


class TeamPut(BaseModel):
    profiles: list[TeamProfileIn]

    @field_validator("profiles")
    @classmethod
    def _unique(cls, v: list[TeamProfileIn]) -> list[TeamProfileIn]:
        keys = [p.profile_key for p in v]
        if len(keys) != len(set(keys)):
            raise ValueError("Hay perfiles repetidos.")
        return v


# --------------------------------------------------------------------------- planes


class PlanGenerateRequest(BaseModel):
    parameters: PlanningParametersIn = Field(default_factory=PlanningParametersIn)
    confirm: bool = False
    label: str = Field(default="", max_length=200)
    change_reason: str = Field(default="", max_length=2000)
    include_ai_summary: bool = False


class PlanVersionOut(ORM):
    id: int
    project_id: int
    version_number: int
    label: str
    is_baseline: bool
    is_active: bool = False
    source_scenario_id: int | None
    restored_from_version_id: int | None
    team_configuration: list[dict[str, Any]]
    planning_parameters: dict[str, Any]
    metrics: dict[str, Any]
    schedule: list[dict[str, Any]]
    backlog_snapshot: dict[str, Any]
    estimated_effort: float
    estimated_duration: int
    start_date: date
    estimated_completion_date: date
    assumptions: list[str]
    risks: list[dict[str, Any]]
    executive_summary: str
    executive_summary_simulated: bool
    change_reason: str
    created_at: datetime
    created_by: str


class PlanVersionListItem(ORM):
    id: int
    version_number: int
    label: str
    is_baseline: bool
    is_active: bool = False
    source_scenario_id: int | None
    estimated_effort: float
    estimated_duration: int
    start_date: date
    estimated_completion_date: date
    change_reason: str
    created_at: datetime
    created_by: str
    main_bottleneck: str | None = None
    total_cost: float | None = None


class PlanPreviewOut(BaseModel):
    is_preview: bool = True
    team_configuration: list[dict[str, Any]]
    planning_parameters: dict[str, Any]
    result: dict[str, Any]


class RecalculateRequest(BaseModel):
    change_reason: str = Field(default="Recalculo con el backlog y el equipo actuales", max_length=2000)
    use_current_team: bool = True


class RestoreRequest(BaseModel):
    change_reason: str = Field(default="", max_length=2000)


# --------------------------------------------------------------------------- escenarios


class ScenarioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    base_version_id: int | None = None
    team_configuration: list[TeamProfileIn] | None = None
    planning_parameters: PlanningParametersIn | None = None
    simulate: bool = True


class ScenarioUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    team_configuration: list[TeamProfileIn] | None = None
    planning_parameters: PlanningParametersIn | None = None


class ScenarioOut(ORM):
    id: int
    project_id: int
    base_version_id: int
    name: str
    description: str
    source: str
    team_configuration: list[dict[str, Any]]
    planning_parameters: dict[str, Any]
    results: dict[str, Any] | None
    estimated_effort: float | None
    estimated_duration: int | None
    estimated_completion_date: date | None
    comparison_metrics: dict[str, Any] | None
    status: str
    error_message: str
    applied_version_id: int | None
    created_at: datetime
    simulated_at: datetime | None


class ScenarioApplyRequest(BaseModel):
    confirm: bool = False
    change_reason: str = Field(default="", max_length=2000)


class SuggestScenariosRequest(BaseModel):
    base_version_id: int | None = None


class ExplainScenariosRequest(BaseModel):
    scenario_ids: list[int] = Field(default_factory=list)


# --------------------------------------------------------------------------- exportaciones


class ExportRequest(BaseModel):
    report_type: Literal["full", "executive", "optimization"] = "full"


class ExportOut(ORM):
    id: int
    project_id: int
    plan_version_id: int
    report_type: str
    filename: str
    size_bytes: int
    sha256: str
    created_at: datetime
    created_by: str


# --------------------------------------------------------------------------- integraciones


class JiraConfigIn(BaseModel):
    enabled: bool = False
    site_url: str = Field(default="", max_length=300)
    account_email: str = Field(default="", max_length=200)
    api_token: str | None = Field(default=None, max_length=500)

    @field_validator("site_url")
    @classmethod
    def _url(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if v and not v.startswith("https://"):
            raise ValueError("La URL del sitio debe empezar con https://")
        if v:
            # se acepta cualquier URL del sitio (tablero, ticket…) y se conserva solo https://<sitio>
            from urllib.parse import urlsplit

            host = urlsplit(v).netloc
            if not host:
                raise ValueError("La URL del sitio no es válida.")
            v = f"https://{host}"
        return v


class JiraConfigOut(BaseModel):
    project_id: int
    enabled: bool
    configuration_status: str
    site_url: str
    auth_method: str
    account_email: str
    has_secret: bool
    last_validated_at: datetime | None
    last_error: str
    project_mode: str


class JiraIssueTypeMapping(BaseModel):
    epic: str = Field(default="", max_length=100)
    story: str = Field(default="", max_length=100)
    task: str = Field(default="", max_length=100)


class JiraTarget(BaseModel):
    """Destino elegido al publicar (leído del JIRA conectado; no forma parte de la configuración)."""

    project_key: str = Field(default="", max_length=50, pattern=r"^$|^[A-Za-z][A-Za-z0-9_]*$")
    issue_type_mapping: JiraIssueTypeMapping = Field(default_factory=JiraIssueTypeMapping)


class JiraPublishRequest(JiraTarget):
    confirm: bool = False
    confirmation_text: str = ""
    preview_fingerprint: str = ""


class SystemStatus(BaseModel):
    app_env: str
    database: str
    database_ok: bool
    ai_demo_mode: bool
    ai_provider: str | None = None
    ai_model: str = ""
    ai_available: bool
    secrets_encryption_configured: bool
    version: str
