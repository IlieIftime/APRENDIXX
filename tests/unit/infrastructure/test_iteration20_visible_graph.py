"""Real SQLite validation for the filtered semantic curriculum graph."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from aprendix.application.contracts import EvidenceType, LearningEvidenceDTO
from aprendix.application.graph import GraphRecommender, GraphSnapshotService
from aprendix.application.progress import LearningProgressService
from aprendix.infrastructure.db import SQLiteGraphRepository
from aprendix.infrastructure.db.progress_repository import LearningProgressRepository
from aprendix.infrastructure.seed import DEFAULT_NODES, seed_default_catalog

NOW = datetime(2026, 8, 12, 12, tzinfo=UTC)


def _seed_small_curriculum(database, user_id) -> None:
    seed_default_catalog(database)
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO users VALUES(?,?,?,?,?)",
            (str(user_id), None, 0, NOW.isoformat(), NOW.isoformat()),
        )
        connection.execute(
            "INSERT INTO learning_tracks VALUES(?,?,?,?,?,?)",
            ("track-one", "track-one", "Bases", "Teste curricular", "python", 0),
        )
        for position, node in enumerate(DEFAULT_NODES):
            connection.execute(
                "INSERT INTO learning_chapters VALUES(?,?,?,?,?,?,?)",
                (
                    f"chapter-{position}", "track-one", str(node.id),
                    f"chapter-{position}", node.title, "Objetivo local", position,
                ),
            )


def test_visible_graph_hides_untouched_nodes_and_composes_typed_edges(
    database,
) -> None:
    user_id = uuid4()
    _seed_small_curriculum(database, user_id)
    with database.read_connection() as connection:
        rows = connection.execute(
            """SELECT c.graph_node_id
               FROM learning_chapters c
               WHERE c.track_id='track-one'
               ORDER BY c.position LIMIT 2"""
        ).fetchall()
    node_ids = tuple(UUID(row["graph_node_id"]) for row in rows)
    progress = LearningProgressService(LearningProgressRepository(database))
    for index, node_id in enumerate(node_ids):
        progress.record(LearningEvidenceDTO(
            user_id=user_id, node_id=node_id,
            source_key=f"iteration20:{index}", evidence_type=EvidenceType.PRACTICE,
            score=1.0, duration_seconds=300, active_seconds=240,
            occurred_at=NOW - timedelta(days=index + 1),
        ))
    graph = SQLiteGraphRepository(database)
    service = GraphSnapshotService(graph, GraphRecommender(graph))

    snapshot = service.get_visible_snapshot(
        user_id, period_days=7, include_eligible=False, generated_at=NOW,
    )

    assert {node.id for node in snapshot.nodes} == set(node_ids)
    assert len(snapshot.nodes) <= 150
    assert len(snapshot.edges) <= 300
    assert snapshot.visibility.practiced_nodes == 2
    assert snapshot.visibility.frontier_nodes == 0
    assert any(edge.relation_type.value == "progression" for edge in snapshot.edges)
    assert all(edge.reason and edge.origin for edge in snapshot.edges)
    first = service.node_analytics(
        user_id, node_ids[0], period_days=7, generated_at=NOW,
    )
    assert first.evidence_count == 1
    assert first.active_seconds == 240
    assert first.mastery > 0.5
    assert first.last_practiced_at is not None

    empty = service.get_visible_snapshot(
        user_id,
        start=NOW - timedelta(days=30),
        end=NOW - timedelta(days=20),
        include_eligible=False,
        generated_at=NOW,
    )
    assert empty.nodes == ()
    with pytest.raises(ValueError, match="period_days"):
        service.get_visible_snapshot(user_id, period_days=14, generated_at=NOW)
    with pytest.raises(ValueError):
        service.get_visible_snapshot(user_id, node_limit=151, generated_at=NOW)


def test_empty_profile_can_opt_in_to_only_the_eligible_frontier(database) -> None:
    user_id = uuid4()
    _seed_small_curriculum(database, user_id)
    graph = SQLiteGraphRepository(database)
    snapshot = GraphSnapshotService(graph, GraphRecommender(graph)).get_visible_snapshot(
        user_id, period_days=7, include_eligible=True, generated_at=NOW,
    )

    assert 0 < len(snapshot.nodes) <= 24
    assert snapshot.visibility.practiced_nodes == 0
    assert snapshot.visibility.frontier_nodes == len(snapshot.nodes)
    assert {node.id for node in snapshot.nodes}.issubset(set(graph.eligible_node_ids(user_id)))
