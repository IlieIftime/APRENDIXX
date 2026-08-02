"""Adaptive graph worker, recommender mathematics, and snapshot service."""

from __future__ import annotations

import math
import random
from datetime import datetime
from typing import Protocol
from uuid import UUID

from aprendix.application.contracts import EventDTO
from aprendix.application.contracts.graph import (
    GraphEdgeSnapshotDTO,
    GraphNodeSnapshotDTO,
    GraphSnapshotDTO,
    NodeStatisticsDTO,
    RecommendationDTO,
)
from aprendix.domain import EventType


class GraphMappingError(ValueError):
    """Raised when a graph-relevant event carries an invalid reference."""


class GraphStore(Protocol):
    """Persistence boundary needed by graph application services."""

    def node_for_exercise(self, exercise_id: UUID) -> UUID | None: ...

    def node_for_attempt(self, attempt_id: UUID) -> UUID | None: ...

    def has_node(self, node_id: UUID) -> bool: ...

    def apply_event(
        self,
        event: EventDTO,
        node_id: UUID,
        *,
        reward: float | None,
        update_co_occurrence: bool,
    ) -> NodeStatisticsDTO: ...

    def list_nodes(self, user_id: UUID) -> tuple[GraphNodeSnapshotDTO, ...]: ...

    def list_edges(self) -> tuple[GraphEdgeSnapshotDTO, ...]: ...

    def theta_for_user(self, user_id: UUID) -> float: ...


class GraphWorker:
    """Map immutable events onto knowledge nodes and update graph state."""

    _CO_OCCURRENCE_EVENTS = {
        EventType.EXERCISE_OPENED,
        EventType.ATTEMPT_SUBMITTED,
        EventType.ATTEMPT_EVALUATED,
        EventType.ASSESSMENT_EVALUATED,
    }

    def __init__(self, store: GraphStore) -> None:
        self._store = store

    def map_event_to_node(self, event: EventDTO) -> UUID | None:
        """Resolve an explicit node, exercise, or attempt reference."""

        raw_node_id = event.payload.get("node_id")
        if raw_node_id is not None:
            node_id = self._parse_uuid(raw_node_id, field="node_id")
            if not self._store.has_node(node_id):
                raise GraphMappingError(f"unknown graph node {node_id}")
            return node_id

        raw_exercise_id = event.payload.get("exercise_id")
        if raw_exercise_id is not None:
            exercise_id = self._parse_uuid(raw_exercise_id, field="exercise_id")
            node_id = self._store.node_for_exercise(exercise_id)
            if node_id is None:
                raise GraphMappingError(
                    f"exercise {exercise_id} is not mapped to a graph node"
                )
            return node_id

        raw_attempt_id = event.payload.get("attempt_id")
        if raw_attempt_id is not None:
            attempt_id = self._parse_uuid(raw_attempt_id, field="attempt_id")
            node_id = self._store.node_for_attempt(attempt_id)
            if node_id is None:
                raise GraphMappingError(
                    f"attempt {attempt_id} is not mapped to a graph node"
                )
            return node_id

        return None

    def update_node_stats(self, event: EventDTO) -> NodeStatisticsDTO | None:
        """Apply an event exactly once and return its resulting node state."""

        node_id = self.map_event_to_node(event)
        if node_id is None:
            return None
        reward = self._reward_for_event(event)
        return self._store.apply_event(
            event,
            node_id,
            reward=reward,
            update_co_occurrence=event.event_type in self._CO_OCCURRENCE_EVENTS,
        )

    @staticmethod
    def _parse_uuid(value: object, *, field: str) -> UUID:
        try:
            return UUID(str(value))
        except (TypeError, ValueError, AttributeError) as exc:
            raise GraphMappingError(f"{field} must be a UUID") from exc

    @staticmethod
    def _reward_for_event(event: EventDTO) -> float | None:
        if event.event_type not in {
            EventType.ATTEMPT_EVALUATED,
            EventType.ASSESSMENT_EVALUATED,
        }:
            return None

        passed = event.payload.get("passed")
        if isinstance(passed, bool):
            return 1.0 if passed else 0.0

        status = event.payload.get("status")
        if status == "passed":
            return 1.0
        if status in {"failed", "error"}:
            return 0.0

        score = event.payload.get("score")
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            numeric_score = float(score)
            if math.isfinite(numeric_score) and 0.0 <= numeric_score <= 1.0:
                return numeric_score

        raise GraphMappingError(
            "attempt.evaluated requires passed, status, or a score in [0, 1]"
        )


def irt_probability(theta: float, difficulty: float) -> float:
    """One-parameter logistic IRT probability ``P(correct | theta, b)``."""

    exponent = max(-60.0, min(60.0, difficulty - theta))
    return 1.0 / (1.0 + math.exp(exponent))


def ucb_score(
    posterior_mean: float,
    node_attempts: int,
    total_attempts: int,
    *,
    exploration: float = 0.35,
) -> float:
    """Bounded UCB1 score with explicit support for unexplored nodes."""

    if node_attempts < 0 or total_attempts < 0:
        raise ValueError("attempt counts cannot be negative")
    if exploration < 0.0:
        raise ValueError("exploration must be non-negative")
    bonus = exploration * math.sqrt(
        math.log(total_attempts + 2.0) / (node_attempts + 1.0)
    )
    return max(0.0, min(1.0, posterior_mean + bonus))


class GraphRecommender:
    """Blend Thompson/UCB exploration with IRT learner fit."""

    def __init__(
        self,
        store: GraphStore,
        *,
        blend_alpha: float = 0.65,
        thompson_weight: float = 0.5,
        exploration: float = 0.35,
        rng: random.Random | None = None,
    ) -> None:
        for name, value in (
            ("blend_alpha", blend_alpha),
            ("thompson_weight", thompson_weight),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
        if exploration < 0.0:
            raise ValueError("exploration must be non-negative")
        self._store = store
        self._blend_alpha = blend_alpha
        self._thompson_weight = thompson_weight
        self._exploration = exploration
        self._rng = rng or random.Random()

    def recommend(
        self,
        user_id: UUID,
        *,
        top_k: int = 3,
    ) -> tuple[RecommendationDTO, ...]:
        if top_k != 3:
            raise ValueError("Sprint 3 recommender requires top_k=3")

        nodes = self._store.list_nodes(user_id)
        theta = self._store.theta_for_user(user_id)
        total_attempts = sum(node.statistics.attempt_count for node in nodes)
        scored: list[tuple[float, str, RecommendationDTO]] = []
        for node in nodes:
            stats = node.statistics
            sample = self._rng.betavariate(
                stats.thompson_alpha,
                stats.thompson_beta,
            )
            posterior_mean = stats.thompson_alpha / (
                stats.thompson_alpha + stats.thompson_beta
            )
            ucb = ucb_score(
                posterior_mean,
                stats.attempt_count,
                total_attempts,
                exploration=self._exploration,
            )
            bandit = self._thompson_weight * sample + (
                1.0 - self._thompson_weight
            ) * ucb
            irt = irt_probability(theta, node.difficulty)
            combined = self._blend_alpha * bandit + (
                1.0 - self._blend_alpha
            ) * irt
            recommendation = RecommendationDTO(
                node_id=node.id,
                rank=1,
                thompson_sample=sample,
                ucb_score=ucb,
                bandit_score=bandit,
                irt_probability=irt,
                combined_score=combined,
            )
            scored.append((combined, str(node.id), recommendation))

        scored.sort(key=lambda item: (-item[0], item[1]))
        return tuple(
            recommendation.model_copy(update={"rank": rank})
            for rank, (_, _, recommendation) in enumerate(scored[:top_k], start=1)
        )


class GraphSnapshotService:
    """Build the Pydantic response served by the local HTTP adapter."""

    def __init__(
        self,
        store: GraphStore,
        recommender: GraphRecommender,
    ) -> None:
        self._store = store
        self._recommender = recommender

    def get_snapshot(
        self,
        user_id: UUID,
        *,
        generated_at: datetime | None = None,
    ) -> GraphSnapshotDTO:
        values: dict[str, object] = {
            "user_id": user_id,
            "theta": self._store.theta_for_user(user_id),
            "nodes": self._store.list_nodes(user_id),
            "edges": self._store.list_edges(),
            "recommendations": self._recommender.recommend(user_id),
        }
        if generated_at is not None:
            values["generated_at"] = generated_at
        return GraphSnapshotDTO.model_validate(values)
