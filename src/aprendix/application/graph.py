"""Adaptive graph worker, recommender mathematics, and snapshot service."""

from __future__ import annotations

import math
import random
from datetime import UTC, datetime, timedelta
from typing import ClassVar, Protocol
from uuid import UUID

from aprendix.application.contracts import EventDTO
from aprendix.application.contracts.graph import (
    GraphEdgeSnapshotDTO,
    GraphNodeSnapshotDTO,
    GraphSnapshotDTO,
    GraphViewFilterDTO,
    GraphVisibilityDTO,
    NodeAnalyticsDTO,
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

    def list_nodes(
        self, user_id: UUID, node_ids: tuple[UUID, ...] | None = None,
    ) -> tuple[GraphNodeSnapshotDTO, ...]: ...

    def list_edges(self) -> tuple[GraphEdgeSnapshotDTO, ...]: ...

    def theta_for_user(self, user_id: UUID) -> float: ...

    def visible_node_ids(
        self, user_id: UUID, *, start: datetime, end: datetime,
        include_eligible: bool, limit: int,
    ) -> dict[str, object]: ...

    def semantic_edges(
        self, node_ids: tuple[UUID, ...], *, limit: int, generated_at: datetime,
    ) -> tuple[tuple[GraphEdgeSnapshotDTO, ...], int]: ...

    def node_analytics(
        self, user_id: UUID, node_ids: tuple[UUID, ...], *,
        start: datetime, end: datetime,
    ) -> dict[UUID, NodeAnalyticsDTO]: ...


class GraphWorker:
    """Map immutable events onto knowledge nodes and update graph state."""

    _CO_OCCURRENCE_EVENTS: ClassVar[set[EventType]] = {
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
        node_ids: tuple[UUID, ...] | None = None,
    ) -> tuple[RecommendationDTO, ...]:
        if top_k != 3:
            raise ValueError("Sprint 3 recommender requires top_k=3")

        if node_ids is None:
            nodes = self._store.list_nodes(user_id)
        else:
            try:
                nodes = self._store.list_nodes(user_id, node_ids)
            except TypeError:
                # Backwards-compatible support for small in-memory test adapters.
                allowed = set(node_ids)
                nodes = tuple(
                    node for node in self._store.list_nodes(user_id)
                    if node.id in allowed
                )
        eligibility_provider = getattr(self._store, "eligible_node_ids", None)
        if eligibility_provider is not None:
            eligible = set(eligibility_provider(user_id))
            nodes = tuple(node for node in nodes if node.id in eligible)
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

    def get_visible_snapshot(
        self,
        user_id: UUID,
        *,
        period_days: int = 30,
        start: datetime | None = None,
        end: datetime | None = None,
        include_eligible: bool = False,
        node_limit: int = 150,
        edge_limit: int = 300,
        generated_at: datetime | None = None,
    ) -> GraphSnapshotDTO:
        """Build a bounded curriculum graph without untouched hidden nodes."""

        reference = (generated_at or datetime.now(UTC)).astimezone(UTC)
        view_filter = self._view_filter(
            period_days=period_days, start=start, end=end,
            include_eligible=include_eligible,
            node_limit=node_limit, edge_limit=edge_limit,
            reference=reference,
        )
        selector = getattr(self._store, "visible_node_ids", None)
        semantic_provider = getattr(self._store, "semantic_edges", None)
        analytics_provider = getattr(self._store, "node_analytics", None)
        if selector is None or semantic_provider is None or analytics_provider is None:
            # Compatibility for lightweight adapters; production SQLite always
            # implements the server-side selection and budgets.
            legacy = self.get_snapshot(user_id, generated_at=reference)
            return legacy.model_copy(update={
                "nodes": legacy.nodes[:node_limit],
                "edges": legacy.edges[:edge_limit],
            })
        selection = selector(
            user_id, start=view_filter.start, end=view_filter.end,
            include_eligible=view_filter.include_eligible,
            limit=view_filter.node_limit,
        )
        node_ids = tuple(selection["node_ids"])
        analytics = analytics_provider(
            user_id, node_ids, start=view_filter.start, end=view_filter.end,
        )
        nodes = tuple(
            node.model_copy(update={"analytics": analytics.get(node.id)})
            for node in self._store.list_nodes(user_id, node_ids)
        )
        edges, total_edges = semantic_provider(
            node_ids, limit=view_filter.edge_limit, generated_at=reference,
        )
        visible_ids = set(node_ids)
        recommendations = tuple(
            item for item in self._recommender.recommend(
                user_id, node_ids=node_ids,
            )
            if item.node_id in visible_ids
        )
        recommendations = tuple(
            item.model_copy(update={"rank": rank})
            for rank, item in enumerate(recommendations[:3], start=1)
        )
        visibility = GraphVisibilityDTO(
            filter=view_filter,
            practiced_nodes=len(selection["practiced"]),
            mastered_nodes=len(selection["mastered"]),
            frontier_nodes=len(selection["frontier"]),
            omitted_nodes=int(selection["omitted"]),
            omitted_edges=max(0, total_edges - len(edges)),
        )
        return GraphSnapshotDTO(
            user_id=user_id,
            generated_at=reference,
            theta=self._store.theta_for_user(user_id),
            nodes=nodes,
            edges=edges,
            recommendations=recommendations,
            visibility=visibility,
        )

    def node_analytics(
        self,
        user_id: UUID,
        node_id: UUID,
        *,
        period_days: int = 30,
        start: datetime | None = None,
        end: datetime | None = None,
        generated_at: datetime | None = None,
    ) -> NodeAnalyticsDTO:
        """Return the same period metrics shown by node selection in the UI."""

        if not self._store.has_node(node_id):
            raise ValueError(f"unknown graph node {node_id}")
        reference = (generated_at or datetime.now(UTC)).astimezone(UTC)
        view_filter = self._view_filter(
            period_days=period_days, start=start, end=end,
            include_eligible=False, node_limit=1, edge_limit=0,
            reference=reference,
        )
        provider = getattr(self._store, "node_analytics", None)
        if provider is None:
            raise RuntimeError("graph store does not expose node analytics")
        result = provider(
            user_id, (node_id,), start=view_filter.start, end=view_filter.end,
        )
        try:
            return result[node_id]
        except KeyError as exc:
            raise ValueError(f"graph node {node_id} has no analytics metadata") from exc

    @staticmethod
    def _view_filter(
        *,
        period_days: int,
        start: datetime | None,
        end: datetime | None,
        include_eligible: bool,
        node_limit: int,
        edge_limit: int,
        reference: datetime,
    ) -> GraphViewFilterDTO:
        if (start is None) != (end is None):
            raise ValueError("custom graph period requires both start and end")
        if start is None:
            if period_days not in {7, 30, 90}:
                raise ValueError("period_days must be 7, 30, or 90")
            first = reference.date() - timedelta(days=period_days - 1)
            start = datetime.combine(first, datetime.min.time(), tzinfo=UTC)
            end = reference
        return GraphViewFilterDTO(
            start=start, end=end,
            include_eligible=include_eligible,
            node_limit=node_limit, edge_limit=edge_limit,
        )
