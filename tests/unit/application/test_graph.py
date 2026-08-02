"""Graph-worker mapping and recommendation mathematics."""

from __future__ import annotations

import random
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from aprendix.application.contracts import EventDTO
from aprendix.application.contracts.graph import (
    GraphNodeSnapshotDTO,
    NodeStatisticsDTO,
)
from aprendix.application.graph import (
    GraphMappingError,
    GraphRecommender,
    GraphWorker,
    irt_probability,
    ucb_score,
)
from aprendix.domain import EventType

NOW = datetime(2026, 7, 30, tzinfo=UTC)


class FakeGraphStore:
    def __init__(self) -> None:
        self.user_id = uuid4()
        self.exercise_id = uuid4()
        self.attempt_id = uuid4()
        self.nodes = tuple(
            self._node(index, difficulty)
            for index, difficulty in enumerate((-2.0, -0.5, 0.5, 2.0), start=1)
        )
        self.applied: list[tuple[EventDTO, UUID, float | None, bool]] = []

    def _node(self, index: int, difficulty: float) -> GraphNodeSnapshotDTO:
        node_id = UUID(int=index)
        return GraphNodeSnapshotDTO(
            id=node_id,
            slug=f"node-{index}",
            title=f"Node {index}",
            difficulty=difficulty,
            statistics=NodeStatisticsDTO(
                user_id=self.user_id,
                node_id=node_id,
                attempt_count=index - 1,
                success_count=max(0, index - 2),
                failure_count=min(1, index - 1),
                thompson_alpha=float(index),
                thompson_beta=2.0,
                updated_at=NOW,
            ),
        )

    def node_for_exercise(self, exercise_id: UUID) -> UUID | None:
        return self.nodes[0].id if exercise_id == self.exercise_id else None

    def node_for_attempt(self, attempt_id: UUID) -> UUID | None:
        return self.nodes[1].id if attempt_id == self.attempt_id else None

    def has_node(self, node_id: UUID) -> bool:
        return any(node.id == node_id for node in self.nodes)

    def apply_event(
        self,
        event: EventDTO,
        node_id: UUID,
        *,
        reward: float | None,
        update_co_occurrence: bool,
    ) -> NodeStatisticsDTO:
        self.applied.append((event, node_id, reward, update_co_occurrence))
        return next(node.statistics for node in self.nodes if node.id == node_id)

    def list_nodes(self, user_id: UUID) -> tuple[GraphNodeSnapshotDTO, ...]:
        assert user_id == self.user_id
        return self.nodes

    def list_edges(self) -> tuple[()]:
        return ()

    def theta_for_user(self, user_id: UUID) -> float:
        assert user_id == self.user_id
        return 0.25


def test_worker_maps_exercise_and_updates_fractional_reward() -> None:
    store = FakeGraphStore()
    event = EventDTO(
        user_id=store.user_id,
        event_type=EventType.ATTEMPT_EVALUATED,
        payload={"exercise_id": str(store.exercise_id), "score": 0.75},
        occurred_at=NOW,
        created_at=NOW,
    )

    result = GraphWorker(store).update_node_stats(event)

    assert result is not None
    assert result.node_id == store.nodes[0].id
    assert store.applied == [(event, store.nodes[0].id, 0.75, True)]


def test_worker_maps_attempt_and_rejects_invalid_evaluation() -> None:
    store = FakeGraphStore()
    event = EventDTO(
        user_id=store.user_id,
        event_type=EventType.ATTEMPT_EVALUATED,
        payload={"attempt_id": str(store.attempt_id)},
        occurred_at=NOW,
        created_at=NOW,
    )

    assert GraphWorker(store).map_event_to_node(event) == store.nodes[1].id
    with pytest.raises(GraphMappingError, match="requires"):
        GraphWorker(store).update_node_stats(event)


def test_irt_and_ucb_have_expected_mathematical_behavior() -> None:
    assert irt_probability(theta=0.0, difficulty=0.0) == pytest.approx(0.5)
    assert irt_probability(theta=2.0, difficulty=-2.0) > 0.98
    assert irt_probability(theta=-2.0, difficulty=2.0) < 0.02
    assert ucb_score(0.5, node_attempts=0, total_attempts=20) > ucb_score(
        0.5,
        node_attempts=20,
        total_attempts=20,
    )


def test_recommender_returns_three_ranked_auditable_scores() -> None:
    store = FakeGraphStore()
    recommender = GraphRecommender(store, rng=random.Random(2026))

    recommendations = recommender.recommend(store.user_id)

    assert len(recommendations) == 3
    assert [item.rank for item in recommendations] == [1, 2, 3]
    assert [item.combined_score for item in recommendations] == sorted(
        (item.combined_score for item in recommendations),
        reverse=True,
    )
    for item in recommendations:
        expected = 0.65 * item.bandit_score + 0.35 * item.irt_probability
        assert item.combined_score == pytest.approx(expected)


def test_recommender_enforces_sprint_top_k() -> None:
    store = FakeGraphStore()
    with pytest.raises(ValueError, match="top_k=3"):
        GraphRecommender(store).recommend(store.user_id, top_k=2)
