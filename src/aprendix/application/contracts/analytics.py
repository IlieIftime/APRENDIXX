"""Contracts for explainable, curriculum-scoped learning analytics."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from aprendix.application.contracts.models import (
    ContractModel,
    NonBlankText,
    utc_now,
)
from aprendix.domain.enums import StrEnum


class AnalyticsScope(StrEnum):
    """Supported aggregation levels for the dashboard."""

    GLOBAL = "global"
    TRACK = "track"
    NODE = "node"


class AnalyticsPeriodDTO(ContractModel):
    """Half-open UTC interval used by every analytics query."""

    start: datetime
    end: datetime
    label: NonBlankText = Field(max_length=80)

    @model_validator(mode="after")
    def interval_is_bounded_and_ordered(self):
        if self.end <= self.start:
            raise ValueError("analytics period end must follow start")
        if self.end - self.start > timedelta(days=730):
            raise ValueError("analytics periods cannot exceed 730 days")
        return self


class ProgressSeriesPointDTO(ContractModel):
    """One daily point; state metrics are cumulative, activity is per day."""

    occurred_on: date
    mastery: float = Field(default=0.0, ge=0.0, le=1.0)
    retention: float = Field(default=0.0, ge=0.0, le=1.0)
    autonomy: float = Field(default=0.0, ge=0.0, le=1.0)
    consistency: float = Field(default=0.0, ge=0.0, le=1.0)
    active_minutes: float = Field(default=0.0, ge=0.0)
    planned_minutes: float = Field(default=0.0, ge=0.0)
    evidence_count: int = Field(default=0, ge=0)
    attempts: int = Field(default=0, ge=0)
    successes: int = Field(default=0, ge=0)
    failures: int = Field(default=0, ge=0)
    practiced_nodes: int = Field(default=0, ge=0)
    mastered_nodes: int = Field(default=0, ge=0)


class MetricDefinitionDTO(ContractModel):
    """Human-readable formula and denominator for an exposed metric."""

    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,60}$")
    label: NonBlankText = Field(max_length=100)
    unit: NonBlankText = Field(max_length=40)
    definition: NonBlankText = Field(max_length=700)
    denominator: NonBlankText = Field(max_length=300)


class DashboardIndicatorDTO(ContractModel):
    """First-level dashboard indicator with an auditable interpretation."""

    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,60}$")
    label: NonBlankText = Field(max_length=100)
    value: float
    unit: NonBlankText = Field(max_length=40)
    target_value: float | None = None
    trend_delta: float = 0.0
    trend: Literal["starting", "improving", "stable", "slowing"] = "stable"
    definition: NonBlankText = Field(max_length=700)
    denominator: NonBlankText = Field(max_length=300)
    detail: str = Field(default="", max_length=300)


class MasteryDistributionDTO(ContractModel):
    """Mutually exclusive curriculum-node states at the period end."""

    untouched: int = Field(default=0, ge=0)
    new: int = Field(default=0, ge=0)
    consolidating: int = Field(default=0, ge=0)
    mastered: int = Field(default=0, ge=0)
    at_risk: int = Field(default=0, ge=0)


class TrackAnalyticsDTO(ContractModel):
    """Compact track comparison used by the dashboard's Percursos view."""

    track_slug: str = Field(min_length=1, max_length=80)
    title: NonBlankText = Field(max_length=160)
    curriculum_nodes: int = Field(ge=0)
    practiced_nodes: int = Field(ge=0)
    mastered_nodes: int = Field(ge=0)
    mastery: float = Field(ge=0.0, le=1.0)
    retention: float = Field(ge=0.0, le=1.0)
    autonomy: float = Field(ge=0.0, le=1.0)
    active_minutes: float = Field(ge=0.0)


class DashboardAnalyticsDTO(ContractModel):
    """Complete second-level analytics response for one dashboard filter."""

    user_id: UUID
    generated_at: datetime = Field(default_factory=utc_now)
    scope: AnalyticsScope = AnalyticsScope.GLOBAL
    scope_id: str | None = Field(default=None, max_length=100)
    scope_title: NonBlankText = Field(max_length=160)
    period: AnalyticsPeriodDTO
    indicators: tuple[DashboardIndicatorDTO, ...] = Field(
        default=(), max_length=6
    )
    series: tuple[ProgressSeriesPointDTO, ...] = Field(
        default=(), max_length=731
    )
    mastery_distribution: MasteryDistributionDTO = Field(
        default_factory=MasteryDistributionDTO
    )
    tracks: tuple[TrackAnalyticsDTO, ...] = Field(default=(), max_length=100)
    definitions: tuple[MetricDefinitionDTO, ...] = Field(
        default=(), max_length=20
    )
