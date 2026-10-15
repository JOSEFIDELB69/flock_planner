"""Estructuras que debe devolver el proveedor de IA. Se validan antes de persistir nada."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas import AcceptanceCriterion, AnalysisResult  # noqa: F401  (re-export)

TASK_CATEGORIES = [
    "analysis", "design", "frontend", "backend", "integration", "database", "security", "unit_tests",
    "integration_tests", "qa", "documentation", "deployment",
]


class GeneratedTask(BaseModel):
    ref: str = ""
    title: str = Field(min_length=1, max_length=300)
    description: str = ""
    category: str = "backend"
    profile_key: str = Field(min_length=1, max_length=40)
    estimated_hours: float = Field(ge=0, le=400)
    optimistic_hours: float | None = Field(default=None, ge=0, le=400)
    pessimistic_hours: float | None = Field(default=None, ge=0, le=1200)
    depends_on: list[str] = Field(default_factory=list)
    done_criteria: str = ""
    risks: str = ""

    @field_validator("profile_key")
    @classmethod
    def _key(cls, v: str) -> str:
        return v.strip().lower().replace(" ", "_")


class GeneratedStory(BaseModel):
    ref: str = ""
    title: str = Field(min_length=1, max_length=300)
    as_a: str = ""
    i_want: str = ""
    so_that: str = ""
    description: str = ""
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    business_value: int = Field(default=5, ge=1, le=10)
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    assumptions: str = ""
    risks: str = ""
    confidence: Literal["low", "medium", "high"] = "medium"
    depends_on: list[str] = Field(default_factory=list)
    tasks: list[GeneratedTask] = Field(default_factory=list)


class GeneratedEpic(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = ""
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    requirement_codes: list[str] = Field(default_factory=list)
    stories: list[GeneratedStory] = Field(default_factory=list)


class GeneratedBacklog(BaseModel):
    epics: list[GeneratedEpic] = Field(min_length=1)
    assumptions: list[str] = Field(default_factory=list)
    notes: str = ""


class DocumentRequirement(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = ""
    type: Literal["functional", "non_functional", "technical", "security", "integration", "performance",
                  "operational"] = "functional"
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    source_reference: str = Field(default="", max_length=200)  # página o sección del documento
    assumptions: str = ""


class DocumentRequirements(BaseModel):
    summary: str = ""
    requirements: list[DocumentRequirement] = Field(default_factory=list, max_length=300)
    observations: list[str] = Field(default_factory=list)


class ExecutiveSummary(BaseModel):
    summary: str = Field(min_length=1)


class ScenarioExplanation(BaseModel):
    explanation: str = Field(min_length=1)
    recommended_scenario: str = ""
    rationale: str = ""
    caveats: list[str] = Field(default_factory=list)
