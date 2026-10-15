"""Modelo de datos relacional de Flock Planner.

Los campos JSON usan JSONB en PostgreSQL y JSON en SQLite (solo desarrollo/pruebas).
"""

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("mode IN ('standalone','jira')", name="ck_project_mode"),
        CheckConstraint("status IN ('draft','active','archived')", name="ck_project_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    business_objective: Mapped[str] = mapped_column(Text, default="")
    owner: Mapped[str] = mapped_column(String(200), default="")
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="America/Argentina/Buenos_Aires")
    # {"working_days": [0..6], "hours_per_day": 8, "holidays": ["2026-12-25", ...]}
    calendar_configuration: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    mode: Mapped[str] = mapped_column(String(20), default="standalone")
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    active_plan_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("plan_versions.id", ondelete="SET NULL", use_alter=True, name="fk_project_active_plan"),
        nullable=True,
    )

    requirements: Mapped[list["Requirement"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    epics: Mapped[list["Epic"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True, order_by="Epic.order_index"
    )
    team_profiles: Mapped[list["TeamProfile"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True, order_by="TeamProfile.id"
    )
    plan_versions: Mapped[list["PlanVersion"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="PlanVersion.project_id",
        order_by="PlanVersion.version_number",
    )


class Requirement(TimestampMixin, Base):
    __tablename__ = "requirements"
    __table_args__ = (
        UniqueConstraint("project_id", "code", name="uq_requirement_code"),
        CheckConstraint(
            "type IN ('functional','non_functional','technical','security','integration','performance','operational')",
            name="ck_requirement_type",
        ),
        CheckConstraint("priority IN ('low','medium','high','critical')", name="ck_requirement_priority"),
        CheckConstraint(
            "status IN ('draft','confirmed','rejected','duplicate','suggested')", name="ck_requirement_status"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    type: Mapped[str] = mapped_column(String(30), default="functional")
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    source: Mapped[str] = mapped_column(String(200), default="manual")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    group_name: Mapped[str] = mapped_column(String(120), default="")
    assumptions: Mapped[str] = mapped_column(Text, default="")
    risks: Mapped[str] = mapped_column(Text, default="")
    duplicate_of_id: Mapped[int | None] = mapped_column(
        ForeignKey("requirements.id", ondelete="SET NULL"), nullable=True
    )
    # documento adjunto del que el agente extrajo el requisito (si corresponde)
    source_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_documents.id", ondelete="SET NULL", name="fk_requirement_source_document"), nullable=True,
        index=True,
    )

    project: Mapped[Project] = relationship(back_populates="requirements")


class ProjectDocument(Base):
    """Documento adjunto al proyecto (se guarda el archivo original, sin transformar)."""

    __tablename__ = "project_documents"
    __table_args__ = (
        CheckConstraint("status IN ('pending','processing','processed','error')", name="ck_document_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    kind: Mapped[str] = mapped_column(String(30))  # pdf | docx | text
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    requirements_created: Mapped[int] = mapped_column(Integer, default=0)
    ai_model: Mapped[str] = mapped_column(String(100), default="")
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by: Mapped[str] = mapped_column(String(200), default="")
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BacklogObservation(Base):
    """Supuesto o advertencia de la última generación del backlog, con la decisión del usuario."""

    __tablename__ = "backlog_observations"
    __table_args__ = (
        CheckConstraint("kind IN ('assumption','warning')", name="ck_observation_kind"),
        CheckConstraint("status IN ('pending','accepted','correction')", name="ck_observation_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # assumption | warning
    text: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | accepted | correction
    correction: Mapped[str] = mapped_column(Text, default="")
    # [{"type": "requirement", "id": 12, "code": "REQ-012"}, {"type": "story", "code": "US-003"}, ...]
    links: Mapped[list[dict[str, Any]]] = mapped_column(JsonType, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str] = mapped_column(String(200), default="")


class RequirementLink(Base):
    __tablename__ = "requirement_links"
    __table_args__ = (
        UniqueConstraint("requirement_id", "related_id", name="uq_requirement_link"),
        CheckConstraint("requirement_id <> related_id", name="ck_requirement_link_self"),
        CheckConstraint("relation_type IN ('depends_on','relates_to')", name="ck_requirement_link_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    requirement_id: Mapped[int] = mapped_column(ForeignKey("requirements.id", ondelete="CASCADE"), index=True)
    related_id: Mapped[int] = mapped_column(ForeignKey("requirements.id", ondelete="CASCADE"), index=True)
    relation_type: Mapped[str] = mapped_column(String(20), default="relates_to")


class RequirementAnalysis(Base):
    __tablename__ = "requirement_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    result: Mapped[dict[str, Any]] = mapped_column(JsonType)
    # Respuestas del usuario a las preguntas de aclaración: {"<índice>": "respuesta"}
    answers: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    proceed_with_assumptions: Mapped[bool] = mapped_column(Boolean, default=False)
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    model: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by: Mapped[str] = mapped_column(String(200), default="")


class Epic(TimestampMixin, Base):
    __tablename__ = "epics"
    __table_args__ = (UniqueConstraint("project_id", "code", name="uq_epic_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    source: Mapped[str] = mapped_column(String(20), default="manual")  # ai | manual | demo
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    project: Mapped[Project] = relationship(back_populates="epics")
    stories: Mapped[list["UserStory"]] = relationship(
        back_populates="epic", cascade="all, delete-orphan", passive_deletes=True, order_by="UserStory.order_index"
    )


class StoryDependency(Base):
    __tablename__ = "story_dependencies"
    __table_args__ = (CheckConstraint("story_id <> depends_on_id", name="ck_story_dep_self"),)

    story_id: Mapped[int] = mapped_column(ForeignKey("user_stories.id", ondelete="CASCADE"), primary_key=True)
    depends_on_id: Mapped[int] = mapped_column(ForeignKey("user_stories.id", ondelete="CASCADE"), primary_key=True)


class UserStory(TimestampMixin, Base):
    __tablename__ = "user_stories"
    __table_args__ = (
        UniqueConstraint("project_id", "code", name="uq_story_code"),
        CheckConstraint("estimate_confidence IN ('low','medium','high')", name="ck_story_confidence"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    epic_id: Mapped[int] = mapped_column(ForeignKey("epics.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    # [{"given": "...", "when": "...", "then": "..."}]
    acceptance_criteria: Mapped[list[dict[str, Any]]] = mapped_column(JsonType, default=list)
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    business_value: Mapped[int] = mapped_column(Integer, default=5)
    assumptions: Mapped[str] = mapped_column(Text, default="")
    risks: Mapped[str] = mapped_column(Text, default="")
    estimate_confidence: Mapped[str] = mapped_column(String(10), default="medium")
    estimate_status: Mapped[str] = mapped_column(String(20), default="initial")  # initial | revised
    status: Mapped[str] = mapped_column(String(20), default="draft")
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    epic: Mapped[Epic] = relationship(back_populates="stories")
    tasks: Mapped[list["Task"]] = relationship(
        back_populates="story", cascade="all, delete-orphan", passive_deletes=True, order_by="Task.order_index"
    )
    depends_on: Mapped[list["UserStory"]] = relationship(
        secondary="story_dependencies",
        primaryjoin="UserStory.id == StoryDependency.story_id",
        secondaryjoin="UserStory.id == StoryDependency.depends_on_id",
    )


class TaskDependency(Base):
    __tablename__ = "task_dependencies"
    __table_args__ = (CheckConstraint("task_id <> depends_on_id", name="ck_task_dep_self"),)

    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)
    depends_on_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("project_id", "code", name="uq_task_code"),
        CheckConstraint("estimated_hours >= 0", name="ck_task_hours"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("user_stories.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(40), default="backend")
    profile_key: Mapped[str] = mapped_column(String(40))
    estimated_hours: Mapped[float] = mapped_column(Float, default=0)
    # rango de tres puntos para el pronóstico Monte Carlo (opcional; si falta se usa la confianza de la historia)
    optimistic_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    pessimistic_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    original_estimate_hours: Mapped[float] = mapped_column(Float, default=0)
    estimate_status: Mapped[str] = mapped_column(String(20), default="initial")  # initial | revised
    done_criteria: Mapped[str] = mapped_column(Text, default="")
    risks: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="todo")
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    story: Mapped[UserStory] = relationship(back_populates="tasks")
    depends_on: Mapped[list["Task"]] = relationship(
        secondary="task_dependencies",
        primaryjoin="Task.id == TaskDependency.task_id",
        secondaryjoin="Task.id == TaskDependency.depends_on_id",
    )


class TeamProfile(Base):
    __tablename__ = "team_profiles"
    __table_args__ = (
        UniqueConstraint("project_id", "profile_key", name="uq_team_profile_key"),
        CheckConstraint("quantity >= 0", name="ck_team_quantity"),
        CheckConstraint("available_hours_per_day > 0 AND available_hours_per_day <= 24", name="ck_team_hours"),
        CheckConstraint("dedication_percentage > 0 AND dedication_percentage <= 100", name="ck_team_dedication"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    profile_key: Mapped[str] = mapped_column(String(40))
    profile_name: Mapped[str] = mapped_column(String(120))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    available_hours_per_day: Mapped[float] = mapped_column(Float, default=6.0)
    dedication_percentage: Mapped[float] = mapped_column(Float, default=100.0)
    hourly_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_qa: Mapped[bool] = mapped_column(Boolean, default=False)
    # {"members": [{"name": "...", "availability_percentage": 100, "absences": [{"start": "...", "end": "..."}]}]}
    availability_configuration: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)

    project: Mapped[Project] = relationship(back_populates="team_profiles")


class PlanVersion(Base):
    """Versión inmutable de la planificación. La primera confirmada es la línea base."""

    __tablename__ = "plan_versions"
    __table_args__ = (
        UniqueConstraint("project_id", "version_number", name="uq_plan_version_number"),
        Index(
            "uq_plan_baseline_per_project",
            "project_id",
            unique=True,
            postgresql_where=text("is_baseline"),
            sqlite_where=text("is_baseline = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(200), default="")
    is_baseline: Mapped[bool] = mapped_column(Boolean, default=False)
    source_scenario_id: Mapped[int | None] = mapped_column(
        ForeignKey("scenarios.id", ondelete="SET NULL", use_alter=True, name="fk_plan_source_scenario"),
        nullable=True,
    )
    restored_from_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    team_configuration: Mapped[list[dict[str, Any]]] = mapped_column(JsonType)
    planning_parameters: Mapped[dict[str, Any]] = mapped_column(JsonType)
    backlog_snapshot: Mapped[dict[str, Any]] = mapped_column(JsonType)
    schedule: Mapped[list[dict[str, Any]]] = mapped_column(JsonType)
    metrics: Mapped[dict[str, Any]] = mapped_column(JsonType)
    estimated_effort: Mapped[float] = mapped_column(Float)
    estimated_duration: Mapped[int] = mapped_column(Integer)  # días laborables
    start_date: Mapped[date] = mapped_column(Date)
    estimated_completion_date: Mapped[date] = mapped_column(Date)
    assumptions: Mapped[list[str]] = mapped_column(JsonType, default=list)
    risks: Mapped[list[dict[str, Any]]] = mapped_column(JsonType, default=list)
    executive_summary: Mapped[str] = mapped_column(Text, default="")
    executive_summary_simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    change_reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by: Mapped[str] = mapped_column(String(200), default="")

    project: Mapped[Project] = relationship(back_populates="plan_versions", foreign_keys=[project_id])


IMMUTABLE_PLAN_FIELDS = (
    "version_number",
    "is_baseline",
    "team_configuration",
    "planning_parameters",
    "backlog_snapshot",
    "schedule",
    "metrics",
    "estimated_effort",
    "estimated_duration",
    "start_date",
    "estimated_completion_date",
    "assumptions",
    "risks",
)


class ImmutablePlanError(Exception):
    pass


@event.listens_for(PlanVersion, "before_update")
def _guard_plan_immutability(_mapper, _connection, target: PlanVersion) -> None:
    """Las versiones de plan (incluida la línea base) no pueden modificarse; solo se crean nuevas."""
    from sqlalchemy import inspect as sa_inspect

    state = sa_inspect(target)
    for field in IMMUTABLE_PLAN_FIELDS:
        if state.attrs[field].history.has_changes():
            raise ImmutablePlanError(f"La versión de plan {target.id} es inmutable (campo '{field}').")


class Scenario(Base):
    __tablename__ = "scenarios"
    __table_args__ = (
        CheckConstraint("status IN ('draft','simulated','applied','stale','error')", name="ck_scenario_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    base_version_id: Mapped[int] = mapped_column(ForeignKey("plan_versions.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | suggested
    team_configuration: Mapped[list[dict[str, Any]]] = mapped_column(JsonType)
    planning_parameters: Mapped[dict[str, Any]] = mapped_column(JsonType)
    results: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    estimated_effort: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_duration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    comparison_metrics: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    error_message: Mapped[str] = mapped_column(Text, default="")
    applied_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    simulated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Export(Base):
    __tablename__ = "exports"
    __table_args__ = (
        CheckConstraint("report_type IN ('full','executive','optimization')", name="ck_export_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    plan_version_id: Mapped[int] = mapped_column(ForeignKey("plan_versions.id", ondelete="CASCADE"), index=True)
    report_type: Mapped[str] = mapped_column(String(20))
    filename: Mapped[str] = mapped_column(String(255))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by: Mapped[str] = mapped_column(String(200), default="")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(40))
    before: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    actor: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class AIInteraction(Base):
    """Traza de llamadas al proveedor de IA (sin prompts completos ni secretos)."""

    __tablename__ = "ai_interactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    operation: Mapped[str] = mapped_column(String(60))
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(100), default="")
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20))  # ok | error
    error: Mapped[str] = mapped_column(Text, default="")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StoredSecret(Base):
    """Secreto cifrado con Fernet. Nunca se devuelve por la API."""

    __tablename__ = "stored_secrets"

    id: Mapped[int] = mapped_column(primary_key=True)
    ciphertext: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IntegrationConfiguration(TimestampMixin, Base):
    __tablename__ = "integration_configurations"
    __table_args__ = (UniqueConstraint("project_id", "provider", name="uq_integration_provider"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(30), default="jira")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # not_configured | configured | validated | error
    configuration_status: Mapped[str] = mapped_column(String(20), default="not_configured")
    site_url: Mapped[str] = mapped_column(String(300), default="")
    auth_method: Mapped[str] = mapped_column(String(30), default="api_token")
    account_email: Mapped[str] = mapped_column(String(200), default="")
    external_project_reference: Mapped[str] = mapped_column(String(50), default="")
    issue_type_mapping: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    extra_fields: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    secret_reference: Mapped[int | None] = mapped_column(
        ForeignKey("stored_secrets.id", ondelete="SET NULL"), nullable=True
    )
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")


class JiraPublishRun(Base):
    __tablename__ = "jira_publish_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20))  # completed | partial | failed
    requested_by: Mapped[str] = mapped_column(String(200), default="")
    summary: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    results: Mapped[list[dict[str, Any]]] = mapped_column(JsonType, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class JiraIssueLink(Base):
    """Trazabilidad local ↔ JIRA. La unicidad evita duplicados al reintentar."""

    __tablename__ = "jira_issue_links"
    __table_args__ = (UniqueConstraint("project_id", "local_type", "local_id", name="uq_jira_link_local"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    local_type: Mapped[str] = mapped_column(String(10))  # epic | story | task
    local_id: Mapped[int] = mapped_column(Integer)
    jira_key: Mapped[str] = mapped_column(String(50))
    jira_id: Mapped[str] = mapped_column(String(50))
    publish_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("jira_publish_runs.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
