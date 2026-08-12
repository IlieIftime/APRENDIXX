"""Contracts for guided projects and the private local portfolio."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from aprendix.application.contracts.models import ContractModel, NonBlankText, utc_now
from aprendix.application.contracts.access import LearningAccessDTO


class ProjectTemplateDTO(ContractModel):
    id: str = Field(min_length=1, max_length=160)
    track_slug: str = Field(min_length=1, max_length=120)
    title: NonBlankText = Field(max_length=240)
    brief: NonBlankText = Field(max_length=8_000)
    requirements: tuple[str, ...] = Field(min_length=3, max_length=20)
    milestones: tuple[str, ...] = Field(min_length=3, max_length=12)
    rubric: tuple[str, ...] = Field(min_length=3, max_length=12)
    level: str = Field(pattern=r"^(beginner|intermediate|advanced)$")
    capstone: bool = True
    professional_briefing: bool = False


class ProjectEvaluationDTO(ContractModel):
    project_id: UUID
    score: float = Field(ge=0.0, le=1.0)
    passed: bool
    rubric_scores: dict[str, float] = Field(default_factory=dict)
    findings: tuple[str, ...] = Field(default=(), max_length=50)
    demonstrated_skills: tuple[str, ...] = Field(default=(), max_length=50)
    template_id: str = Field(default="", max_length=160)
    track_slug: str = Field(default="", max_length=120)
    work_mode: str = Field(default="guided", pattern=r"^(guided|autonomous)$")
    domain_contracts: tuple[str, ...] = Field(default=(), max_length=20)
    access: LearningAccessDTO = Field(default_factory=LearningAccessDTO)
    credit_awarded: bool = False
    evaluated_at: datetime = Field(default_factory=utc_now)


class PortfolioEntryDTO(ContractModel):
    project_id: UUID
    template_id: str = Field(max_length=160)
    title: NonBlankText = Field(max_length=240)
    work_mode: str = Field(pattern=r"^(guided|autonomous)$")
    status: str = Field(pattern=r"^(active|submitted|passed|revision)$")
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    demonstrated_skills: tuple[str, ...] = Field(default=(), max_length=50)
    updated_at: datetime
