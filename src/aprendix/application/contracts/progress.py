"""Contracts for evidence-based mastery and personal study planning."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from aprendix.domain.enums import StrEnum
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from aprendix.application.contracts.models import ContractModel, NonBlankText, utc_now


class EvidenceType(StrEnum):
    PRACTICE = "practice"
    THEORY = "theory"
    HYBRID = "hybrid"
    REVIEW = "review"
    PROJECT = "project"


class ErrorCategory(StrEnum):
    NONE = "none"
    CONCEPTUAL = "conceptual"
    SYNTAX = "syntax"
    RUNTIME = "runtime"
    DISTRACTION = "distraction"


class LearningAction(StrEnum):
    LEARN = "learn"
    PRACTICE = "practice"
    REVIEW = "review"
    ASSESS = "assess"
    PROJECT = "project"


class LearningEvidenceDTO(ContractModel):
    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    node_id: UUID
    source_key: NonBlankText = Field(max_length=180)
    evidence_type: EvidenceType
    score: float = Field(ge=0.0, le=1.0)
    duration_seconds: int | None = Field(default=None, ge=0, le=86_400)
    active_seconds: int | None = Field(default=None, ge=0, le=86_400)
    hint_count: int = Field(default=0, ge=0, le=100)
    paste_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    error_category: ErrorCategory = ErrorCategory.NONE
    transfer_score: float | None = Field(default=None, ge=0.0, le=1.0)
    project_quality: float | None = Field(default=None, ge=0.0, le=1.0)
    item_difficulty: float = Field(default=0.0, ge=-4.0, le=4.0)
    item_discrimination: float = Field(default=1.0, ge=0.25, le=3.0)
    response_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    context_key: str = Field(default="", max_length=80)
    occurred_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def active_time_cannot_exceed_total(self):
        if (self.active_seconds is not None and self.duration_seconds is not None
                and self.active_seconds > self.duration_seconds):
            raise ValueError("active_seconds cannot exceed duration_seconds")
        return self


class MasteryStateDTO(ContractModel):
    user_id: UUID
    node_id: UUID
    p_known: float = Field(default=0.2, ge=0.0, le=1.0)
    retention: float = Field(default=1.0, ge=0.0, le=1.0)
    autonomy: float = Field(default=0.0, ge=0.0, le=1.0)
    velocity: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    irt_ability: float = Field(default=-1.0, ge=-4.0, le=4.0)
    irt_information: float = Field(default=0.0, ge=0.0)
    evidence_count: int = Field(default=0, ge=0)
    successful_reviews: int = Field(default=0, ge=0)
    last_practiced_at: datetime | None = None
    next_review_at: datetime | None = None
    updated_at: datetime = Field(default_factory=utc_now)


class NextLearningActionDTO(ContractModel):
    node_id: UUID
    title: NonBlankText = Field(max_length=160)
    action: LearningAction
    duration_minutes: int = Field(ge=5, le=180)
    priority: float = Field(ge=0.0, le=1.0)
    reason_code: NonBlankText = Field(max_length=60)
    explanation: NonBlankText = Field(max_length=500)


class WeeklyPlanItemDTO(ContractModel):
    id: UUID
    user_id: UUID
    scheduled_for: date
    node_id: UUID
    title: NonBlankText = Field(max_length=160)
    action: LearningAction
    duration_minutes: int = Field(ge=5, le=180)
    reason_code: NonBlankText = Field(max_length=60)
    completed: bool = False


class PersonalProgressDTO(ContractModel):
    mastery: float = Field(default=0.0, ge=0.0, le=1.0)
    retention: float = Field(default=0.0, ge=0.0, le=1.0)
    autonomy: float = Field(default=0.0, ge=0.0, le=1.0)
    velocity: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    irt_ability: float = Field(default=-1.0, ge=-4.0, le=4.0)
    active_minutes: int = Field(default=0, ge=0)
    total_minutes: int = Field(default=0, ge=0)
    new_nodes: int = Field(default=0, ge=0)
    consolidating_nodes: int = Field(default=0, ge=0)
    mastered_nodes: int = Field(default=0, ge=0)
    at_risk_nodes: int = Field(default=0, ge=0)
    next_action: NextLearningActionDTO | None = None
    weekly_plan: tuple[WeeklyPlanItemDTO, ...] = ()


class ProgressForecastDTO(ContractModel):
    generated_for: date
    total_nodes: int = Field(ge=0)
    mastered_nodes: int = Field(ge=0)
    remaining_nodes: int = Field(ge=0)
    weekly_capacity_nodes: float = Field(ge=0.0)
    weeks_remaining: int | None = Field(default=None, ge=0, le=5_200)
    estimated_completion: date | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    assumptions: tuple[str, ...] = Field(default=(), max_length=10)


class WeeklyProgressReportDTO(ContractModel):
    week_start: date
    week_end: date
    active_minutes: int = Field(ge=0)
    evidence_count: int = Field(ge=0)
    average_score: float = Field(ge=0.0, le=1.0)
    planned_items: int = Field(ge=0)
    completed_items: int = Field(ge=0)
    activity_change: float = Field(ge=-10.0, le=10.0)
    trend: Literal["starting", "improving", "stable", "slowing"]
    highlights: tuple[str, ...] = Field(default=(), max_length=8)
    recommendations: tuple[str, ...] = Field(default=(), max_length=8)
