"""Versioned contracts for graph learning state and recommendations."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field, computed_field

from aprendix.application.contracts.models import (
    ContractModel,
    NonBlankText,
    Slug,
    utc_now,
)


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


class GraphEdgeSnapshotDTO(ContractModel):
    """Serializable co-occurrence edge exposed by the graph endpoint."""

    source_node_id: UUID
    target_node_id: UUID
    weight: float = Field(ge=0.0, le=1.0)
    co_occurrence_count: int = Field(ge=0)
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
