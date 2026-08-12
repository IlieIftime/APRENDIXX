"""Versioned contracts for graph learning state and recommendations."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from pydantic import Field, computed_field, model_validator

from aprendix.application.contracts.models import (
    ContractModel,
    NonBlankText,
    Slug,
    utc_now,
)
from aprendix.domain.enums import StrEnum


class GraphRelationType(StrEnum):
    """Meaning of an edge; behavioral proximity never implies dependency."""

    PREREQUISITE = "prerequisite"
    PROGRESSION = "progression"
    RELATED = "related"
    CO_OCCURRENCE = "co_occurrence"


class NodeAnalyticsDTO(ContractModel):
    """Period-aware, measurable detail for one curriculum node."""

    node_id: UUID
    title: NonBlankText = Field(max_length=160)
    period_start: datetime
    period_end: datetime
    distinct_exercises: int = Field(default=0, ge=0)
    attempts: int = Field(default=0, ge=0)
    successes: int = Field(default=0, ge=0)
    failures: int = Field(default=0, ge=0)
    active_seconds: int = Field(default=0, ge=0)
    hint_count: int = Field(default=0, ge=0)
    evidence_count: int = Field(default=0, ge=0)
    mastery: float = Field(default=0.0, ge=0.0, le=1.0)
    retention: float = Field(default=0.0, ge=0.0, le=1.0)
    autonomy: float = Field(default=0.0, ge=0.0, le=1.0)
    success_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    trend: float = Field(default=0.0, ge=-1.0, le=1.0)
    last_practiced_at: datetime | None = None
    recommended_action: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def counts_and_period_are_coherent(self):
        if self.period_end <= self.period_start:
            raise ValueError("node analytics period end must follow start")
        if self.successes + self.failures > self.attempts:
            raise ValueError("success and failure counts cannot exceed attempts")
        return self


class GraphViewFilterDTO(ContractModel):
    """Safe server-side graph filter and hard rendering budgets."""

    start: datetime
    end: datetime
    include_eligible: bool = False
    node_limit: int = Field(default=150, ge=1, le=150)
    edge_limit: int = Field(default=300, ge=0, le=300)

    @model_validator(mode="after")
    def period_is_ordered(self):
        if self.end <= self.start:
            raise ValueError("graph filter end must follow start")
        if self.end - self.start > timedelta(days=730):
            raise ValueError("graph filters cannot exceed 730 days")
        return self


class GraphVisibilityDTO(ContractModel):
    """Auditable selection counts returned with a visible snapshot."""

    filter: GraphViewFilterDTO
    practiced_nodes: int = Field(default=0, ge=0)
    mastered_nodes: int = Field(default=0, ge=0)
    frontier_nodes: int = Field(default=0, ge=0)
    omitted_nodes: int = Field(default=0, ge=0)
    omitted_edges: int = Field(default=0, ge=0)


class NodeStatisticsDTO(ContractModel):
    """Per-user sufficient statistics for one knowledge node."""

    user_id: UUID
    node_id: UUID
    attempt_count: int = Field(default=0, ge=0)
    success_count: int = Field(default=0, ge=0)
    failure_count: int = Field(default=0, ge=0)
    thompson_alpha: float = Field(default=1.0, gt=0.0)
    thompson_beta: float = Field(default=1.0, gt=0.0)
    last_seen_at: datetime | None = None
    updated_at: datetime = Field(default_factory=utc_now)

    @computed_field
    @property
    def mastery(self) -> float:
        if self.attempt_count == 0:
            return 0.0
        return self.success_count / self.attempt_count


class GraphNodeSnapshotDTO(ContractModel):
    """Knowledge-node definition enriched with one user's learning state."""

    id: UUID
    slug: Slug
    title: NonBlankText = Field(max_length=160)
    description: str = Field(default="", max_length=4_000)
    difficulty: float = Field(ge=-3.0, le=3.0)
    statistics: NodeStatisticsDTO
    analytics: NodeAnalyticsDTO | None = None


class GraphEdgeSnapshotDTO(ContractModel):
    """Serializable, typed relationship exposed by the graph endpoint."""

    source_node_id: UUID
    target_node_id: UUID
    weight: float = Field(ge=0.0, le=1.0)
    co_occurrence_count: int = Field(default=0, ge=0)
    relation_type: GraphRelationType = GraphRelationType.CO_OCCURRENCE
    directed: bool = False
    reason: NonBlankText = Field(
        default="Atividade observada em proximidade temporal.", max_length=500
    )
    origin: NonBlankText = Field(default="behavioral", max_length=100)
    updated_at: datetime


class RecommendationDTO(ContractModel):
    """Auditable decomposition of one recommendation score."""

    node_id: UUID
    rank: int = Field(ge=1, le=3)
    thompson_sample: float = Field(ge=0.0, le=1.0)
    ucb_score: float = Field(ge=0.0, le=1.0)
    bandit_score: float = Field(ge=0.0, le=1.0)
    irt_probability: float = Field(ge=0.0, le=1.0)
    combined_score: float = Field(ge=0.0, le=1.0)


class GraphSnapshotDTO(ContractModel):
    """Complete local JSON response for ``GET /graph/snapshot``."""

    user_id: UUID
    generated_at: datetime = Field(default_factory=utc_now)
    theta: float = Field(default=0.0, ge=-6.0, le=6.0)
    nodes: tuple[GraphNodeSnapshotDTO, ...] = ()
    edges: tuple[GraphEdgeSnapshotDTO, ...] = ()
    recommendations: tuple[RecommendationDTO, ...] = Field(
        default=(),
        max_length=3,
    )
    visibility: GraphVisibilityDTO | None = None
