"""SQLite adapter for adaptive graph state and snapshots."""

from __future__ import annotations

import math
import sqlite3
from datetime import UTC, datetime, timedelta
from uuid import UUID

from aprendix.application.contracts import EventDTO
from aprendix.application.contracts.graph import (
    GraphEdgeSnapshotDTO,
    GraphNodeSnapshotDTO,
    NodeStatisticsDTO,
)
from aprendix.infrastructure.db.database import Database


class SQLiteGraphRepository:
    """Persist idempotent per-user graph updates and global co-occurrence edges."""

    def __init__(
        self,
        database: Database,
        *,
        co_occurrence_window: timedelta = timedelta(minutes=30),
        edge_decay: float = 5.0,
    ) -> None:
        if co_occurrence_window <= timedelta(0):
            raise ValueError("co_occurrence_window must be positive")
        if edge_decay <= 0.0:
            raise ValueError("edge_decay must be positive")
        self._database = database
        self._window = co_occurrence_window
        self._edge_decay = edge_decay

    def node_for_exercise(self, exercise_id: UUID) -> UUID | None:
        with self._database.read_connection() as connection:
            row = connection.execute(
                "SELECT graph_node_id FROM exercises WHERE id = ?",
                (str(exercise_id),),
            ).fetchone()
        return UUID(row["graph_node_id"]) if row is not None else None

    def node_for_attempt(self, attempt_id: UUID) -> UUID | None:
        with self._database.read_connection() as connection:
            row = connection.execute(
                """
                SELECT exercises.graph_node_id
                FROM attempts
                JOIN exercises ON exercises.id = attempts.exercise_id
                WHERE attempts.id = ?
                """,
                (str(attempt_id),),
            ).fetchone()
        return UUID(row["graph_node_id"]) if row is not None else None

    def has_node(self, node_id: UUID) -> bool:
        with self._database.read_connection() as connection:
            row = connection.execute(
                "SELECT 1 FROM graph_nodes WHERE id = ?",
                (str(node_id),),
            ).fetchone()
        return row is not None

    def eligible_node_ids(self, user_id: UUID) -> tuple[UUID, ...]:
        """Exclude nodes behind an unfinished blocking course prerequisite."""
        with self._database.read_connection() as connection:
            rows = connection.execute(
                """SELECT DISTINCT g.id FROM graph_nodes g
                   LEFT JOIN learning_chapters c ON c.graph_node_id=g.id
                   WHERE EXISTS(SELECT 1 FROM exercises e WHERE e.graph_node_id=g.id)
                   AND (c.track_id IS NULL OR EXISTS(
                     SELECT 1 FROM learning_unit_progress started
                     JOIN learning_units su ON su.id=started.unit_id
                     JOIN learning_chapters sc ON sc.id=su.chapter_id
                     WHERE started.user_id=? AND sc.track_id=c.track_id
                   ) OR NOT EXISTS(
                     SELECT 1 FROM course_prerequisites cp
                     WHERE cp.track_id=c.track_id AND NOT EXISTS(
                       SELECT 1 FROM learning_unit_progress up
                       JOIN learning_units u ON u.id=up.unit_id
                       JOIN learning_chapters pc ON pc.id=u.chapter_id
                       WHERE up.user_id=? AND u.kind='project'
                       AND pc.track_id=cp.prerequisite_track_id)))
                   ORDER BY g.id""", (str(user_id), str(user_id))
            ).fetchall()
        return tuple(UUID(row["id"]) for row in rows)

    def apply_event(
        self,
        event: EventDTO,
        node_id: UUID,
        *,
        reward: float | None,
        update_co_occurrence: bool,
    ) -> NodeStatisticsDTO:
        if reward is not None and not 0.0 <= reward <= 1.0:
            raise ValueError("reward must be in [0, 1]")

        event_time = event.occurred_at.astimezone(UTC)
        event_time_text = event_time.isoformat()
        processed_at = datetime.now(UTC)
        with self._database.transaction() as connection:
            processed = connection.execute(
                "SELECT node_id FROM graph_processed_events WHERE event_id = ?",
                (str(event.id),),
            ).fetchone()
            if processed is not None:
                if processed["node_id"] != str(node_id):
                    raise ValueError("processed event is mapped to a different node")
                return self._statistics_in_transaction(
                    connection,
                    event.user_id,
                    node_id,
                )

            connection.execute(
                """
                INSERT INTO user_node_stats(
                    user_id, node_id, last_seen_at, updated_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, node_id) DO UPDATE SET
                    last_seen_at = excluded.last_seen_at,
                    updated_at = excluded.updated_at
                """,
                (
                    str(event.user_id),
                    str(node_id),
                    event_time_text,
                    processed_at.isoformat(),
                ),
            )
            if reward is not None:
                connection.execute(
                    """
                    UPDATE user_node_stats
                    SET attempt_count = attempt_count + 1,
                        success_count = success_count + ?,
                        failure_count = failure_count + ?,
                        thompson_alpha = thompson_alpha + ?,
                        thompson_beta = thompson_beta + ?,
                        updated_at = ?
                    WHERE user_id = ? AND node_id = ?
                    """,
                    (
                        int(reward >= 0.5),
                        int(reward < 0.5),
                        reward,
                        1.0 - reward,
                        processed_at.isoformat(),
                        str(event.user_id),
                        str(node_id),
                    ),
                )

            if update_co_occurrence:
                self._update_co_occurrences(
                    connection,
                    event.user_id,
                    node_id,
                    event_time,
                    processed_at,
                )

            connection.execute(
                """
                INSERT INTO graph_processed_events(
                    event_id, user_id, node_id, event_type, occurred_at, processed_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(event.id),
                    str(event.user_id),
                    str(node_id),
                    event.event_type.value,
                    event_time_text,
                    processed_at.isoformat(),
                ),
            )
            return self._statistics_in_transaction(
                connection,
                event.user_id,
                node_id,
            )

    def _update_co_occurrences(
        self,
        connection: sqlite3.Connection,
        user_id: UUID,
        node_id: UUID,
        event_time: datetime,
        updated_at: datetime,
    ) -> None:
        window_start = event_time - self._window
        rows = connection.execute(
            """
            SELECT DISTINCT node_id
            FROM graph_processed_events
            WHERE user_id = ?
              AND occurred_at >= ?
              AND occurred_at <= ?
              AND node_id <> ?
            """,
            (
                str(user_id),
                window_start.isoformat(),
                event_time.isoformat(),
                str(node_id),
            ),
        ).fetchall()
        for row in rows:
            source, target = sorted((str(node_id), row["node_id"]))
            existing = connection.execute(
                """
                SELECT co_occurrence_count
                FROM graph_edges
                WHERE source_node_id = ? AND target_node_id = ?
                """,
                (source, target),
            ).fetchone()
            count = 1 if existing is None else int(existing[0]) + 1
            weight = 1.0 - math.exp(-count / self._edge_decay)
            connection.execute(
                """
                INSERT INTO graph_edges(
                    source_node_id, target_node_id, weight,
                    co_occurrence_count, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source_node_id, target_node_id) DO UPDATE SET
                    weight = excluded.weight,
                    co_occurrence_count = excluded.co_occurrence_count,
                    updated_at = excluded.updated_at
                """,
                (
                    source,
                    target,
                    weight,
                    count,
                    updated_at.isoformat(),
                ),
            )

    def list_nodes(self, user_id: UUID) -> tuple[GraphNodeSnapshotDTO, ...]:
        with self._database.read_connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    n.id, n.slug, n.title, n.description, n.difficulty,
                    COALESCE(s.attempt_count, 0) AS attempt_count,
                    COALESCE(s.success_count, 0) AS success_count,
                    COALESCE(s.failure_count, 0) AS failure_count,
                    COALESCE(s.thompson_alpha, 1.0) AS thompson_alpha,
                    COALESCE(s.thompson_beta, 1.0) AS thompson_beta,
                    s.last_seen_at,
                    COALESCE(s.updated_at, n.updated_at) AS stats_updated_at
                FROM graph_nodes AS n
                LEFT JOIN user_node_stats AS s
                  ON s.node_id = n.id AND s.user_id = ?
                ORDER BY n.slug, n.id
                """,
                (str(user_id),),
            ).fetchall()
        return tuple(
            GraphNodeSnapshotDTO(
                id=UUID(row["id"]),
                slug=row["slug"],
                title=row["title"],
                description=row["description"],
                difficulty=row["difficulty"],
                statistics=NodeStatisticsDTO(
                    user_id=user_id,
                    node_id=UUID(row["id"]),
                    attempt_count=row["attempt_count"],
                    success_count=row["success_count"],
                    failure_count=row["failure_count"],
                    thompson_alpha=row["thompson_alpha"],
                    thompson_beta=row["thompson_beta"],
                    last_seen_at=(
                        datetime.fromisoformat(row["last_seen_at"])
                        if row["last_seen_at"] is not None
                        else None
                    ),
                    updated_at=datetime.fromisoformat(row["stats_updated_at"]),
                ),
            )
            for row in rows
        )

    def list_edges(self) -> tuple[GraphEdgeSnapshotDTO, ...]:
        with self._database.read_connection() as connection:
            rows = connection.execute(
                """
                SELECT source_node_id, target_node_id, weight,
                       co_occurrence_count, updated_at
                FROM graph_edges
                ORDER BY source_node_id, target_node_id
                """
            ).fetchall()
        return tuple(
            GraphEdgeSnapshotDTO(
                source_node_id=UUID(row["source_node_id"]),
                target_node_id=UUID(row["target_node_id"]),
                weight=row["weight"],
                co_occurrence_count=row["co_occurrence_count"],
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
            for row in rows
        )

    def theta_for_user(self, user_id: UUID) -> float:
        with self._database.read_connection() as connection:
            row = connection.execute(
                "SELECT theta FROM profiles WHERE user_id = ?",
                (str(user_id),),
            ).fetchone()
        return float(row["theta"]) if row is not None else 0.0

    @staticmethod
    def _statistics_in_transaction(
        connection: sqlite3.Connection,
        user_id: UUID,
        node_id: UUID,
    ) -> NodeStatisticsDTO:
        row = connection.execute(
            """
            SELECT attempt_count, success_count, failure_count,
                   thompson_alpha, thompson_beta, last_seen_at, updated_at
            FROM user_node_stats
            WHERE user_id = ? AND node_id = ?
            """,
            (str(user_id), str(node_id)),
        ).fetchone()
        if row is None:
            raise RuntimeError("node statistics disappeared during transaction")
        return NodeStatisticsDTO(
            user_id=user_id,
            node_id=node_id,
            attempt_count=row["attempt_count"],
            success_count=row["success_count"],
            failure_count=row["failure_count"],
            thompson_alpha=row["thompson_alpha"],
            thompson_beta=row["thompson_beta"],
            last_seen_at=(
                datetime.fromisoformat(row["last_seen_at"])
                if row["last_seen_at"] is not None
                else None
            ),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
