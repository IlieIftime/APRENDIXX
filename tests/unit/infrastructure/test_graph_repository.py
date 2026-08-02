"""Integration behavior for persisted graph statistics and co-occurrences."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from aprendix.application.contracts import EventDTO, UserDTO
from aprendix.application.graph import GraphWorker
from aprendix.domain import EventType
from aprendix.infrastructure.db import (
    Database,
    EventRepository,
    SQLiteGraphRepository,
    UserRepository,
)
from aprendix.infrastructure.security import AesGcmFieldCipher
from aprendix.infrastructure.seed import DEFAULT_EXERCISES, seed_default_catalog

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)


def _persist_and_process(
    event_repository: EventRepository,
    worker: GraphWorker,
    event: EventDTO,
) -> None:
    assert event_repository.append(event) is True
    assert worker.update_node_stats(event) is not None


def test_updates_stats_idempotently_and_creates_co_occurrence_edge(
    database: Database,
    cipher: AesGcmFieldCipher,
) -> None:
    seed_default_catalog(database)
    user = UserDTO(created_at=NOW, updated_at=NOW)
    UserRepository(database, cipher).add(user)
    events = EventRepository(database, cipher)
    graph = SQLiteGraphRepository(database)
    worker = GraphWorker(graph)

    first_open = EventDTO(
        user_id=user.id,
        event_type=EventType.EXERCISE_OPENED,
        payload={"exercise_id": str(DEFAULT_EXERCISES[0].id)},
        occurred_at=NOW,
        created_at=NOW,
    )
    second_open = EventDTO(
        user_id=user.id,
        event_type=EventType.EXERCISE_OPENED,
        payload={"exercise_id": str(DEFAULT_EXERCISES[1].id)},
        occurred_at=NOW + timedelta(minutes=2),
        created_at=NOW + timedelta(minutes=2),
    )
    evaluation = EventDTO(
        user_id=user.id,
        event_type=EventType.ATTEMPT_EVALUATED,
        payload={
            "exercise_id": str(DEFAULT_EXERCISES[1].id),
            "passed": True,
        },
        occurred_at=NOW + timedelta(minutes=3),
        created_at=NOW + timedelta(minutes=3),
    )
    _persist_and_process(events, worker, first_open)
    _persist_and_process(events, worker, second_open)
    _persist_and_process(events, worker, evaluation)

    replayed = worker.update_node_stats(evaluation)
    nodes = {node.id: node for node in graph.list_nodes(user.id)}
    evaluated = nodes[DEFAULT_EXERCISES[1].graph_node_id].statistics
    edges = graph.list_edges()

    assert replayed is not None
    assert replayed.attempt_count == 1
    assert evaluated.success_count == 1
    assert evaluated.failure_count == 0
    assert evaluated.thompson_alpha == 2.0
    assert evaluated.thompson_beta == 1.0
    assert len(edges) == 1
    assert edges[0].co_occurrence_count == 2
    assert 0.0 < edges[0].weight < 1.0

    with database.read_connection() as connection:
        processed_count = connection.execute(
            "SELECT count(*) FROM graph_processed_events"
        ).fetchone()[0]
    assert processed_count == 3


def test_events_outside_window_do_not_create_edge(
    database: Database,
    cipher: AesGcmFieldCipher,
) -> None:
    seed_default_catalog(database)
    user = UserDTO(created_at=NOW, updated_at=NOW)
    UserRepository(database, cipher).add(user)
    events = EventRepository(database, cipher)
    graph = SQLiteGraphRepository(database)
    worker = GraphWorker(graph)

    for exercise, occurred_at in (
        (DEFAULT_EXERCISES[0], NOW),
        (DEFAULT_EXERCISES[1], NOW + timedelta(hours=1)),
    ):
        _persist_and_process(
            events,
            worker,
            EventDTO(
                user_id=user.id,
                event_type=EventType.EXERCISE_OPENED,
                payload={"exercise_id": str(exercise.id)},
                occurred_at=occurred_at,
                created_at=occurred_at,
            ),
        )

    assert graph.list_edges() == ()
