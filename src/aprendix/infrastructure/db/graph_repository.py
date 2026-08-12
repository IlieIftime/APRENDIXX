"""SQLite adapter for adaptive graph state and snapshots."""

from __future__ import annotations

import math
import sqlite3
from datetime import UTC, datetime, timedelta
from uuid import UUID

from aprendix.application.contracts import (
    ErrorCategory,
    EventDTO,
    EvidenceType,
    LearningEvidenceDTO,
)
from aprendix.application.contracts.graph import (
    GraphEdgeSnapshotDTO,
    GraphNodeSnapshotDTO,
    GraphRelationType,
    NodeAnalyticsDTO,
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

    def list_nodes(
        self,
        user_id: UUID,
        node_ids: tuple[UUID, ...] | None = None,
    ) -> tuple[GraphNodeSnapshotDTO, ...]:
        if node_ids is not None and not node_ids:
            return ()
        node_filter = ""
        parameters: list[str] = [str(user_id)]
        if node_ids is not None:
            placeholders = ",".join("?" for _ in node_ids)
            node_filter = f"WHERE n.id IN ({placeholders})"
            parameters.extend(str(node_id) for node_id in node_ids)
        with self._database.read_connection() as connection:
            rows = connection.execute(
                f"""
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
                {node_filter}
                ORDER BY n.slug, n.id
                """,
                tuple(parameters),
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
                relation_type=GraphRelationType.CO_OCCURRENCE,
                directed=False,
                reason="Conceitos praticados pelo utilizador num intervalo de 30 minutos.",
                origin="graph_edges",
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
            for row in rows
        )

    def visible_node_ids(
        self,
        user_id: UUID,
        *,
        start: datetime,
        end: datetime,
        include_eligible: bool,
        limit: int,
    ) -> dict[str, object]:
        """Select practiced/mastered curriculum nodes and an optional frontier."""

        if not 1 <= limit <= 150:
            raise ValueError("visible graph node limit must be in [1, 150]")
        user_text = str(user_id)
        with self._database.read_connection() as connection:
            rows = connection.execute(
                """SELECT c.graph_node_id AS node_id,
                          MAX(le.occurred_at) AS activity_at,
                          COALESCE(ms.p_known,0) AS p_known,
                          COALESCE(ms.successful_reviews,0) AS successful_reviews,
                          ms.last_practiced_at
                   FROM learning_chapters c
                   LEFT JOIN learning_evidence le
                     ON le.node_id=c.graph_node_id AND le.user_id=?
                    AND le.occurred_at>=? AND le.occurred_at<?
                   LEFT JOIN mastery_states ms
                     ON ms.node_id=c.graph_node_id AND ms.user_id=?
                   GROUP BY c.graph_node_id
                   HAVING activity_at IS NOT NULL OR (
                     p_known>=0.8 AND ms.last_practiced_at>=? AND ms.last_practiced_at<?)
                   ORDER BY activity_at DESC,p_known DESC,c.graph_node_id""",
                (
                    user_text, start.isoformat(), end.isoformat(), user_text,
                    start.isoformat(), end.isoformat(),
                ),
            ).fetchall()
        practiced = tuple(
            UUID(row["node_id"]) for row in rows if row["activity_at"] is not None
        )
        mastered_items: list[UUID] = []
        for row in rows:
            if float(row["p_known"]) < 0.8 or not row["last_practiced_at"]:
                continue
            last = datetime.fromisoformat(row["last_practiced_at"])
            elapsed = max(0.0, (end - last).total_seconds() / 86_400)
            half_life = min(
                120.0,
                2.0 * (1.75 ** min(8, int(row["successful_reviews"]))),
            )
            if 2 ** (-elapsed / half_life) >= 0.6:
                mastered_items.append(UUID(row["node_id"]))
        mastered = tuple(mastered_items)
        ordered_base = tuple(dict.fromkeys((*practiced, *mastered)))
        selected = list(ordered_base[:limit])
        frontier: tuple[UUID, ...] = ()
        frontier_candidates: tuple[UUID, ...] = ()
        if include_eligible and len(selected) < limit:
            frontier_candidates = self._eligible_frontier(
                user_id, tuple(selected), limit=min(24, limit - len(selected)),
            )
            frontier = tuple(
                node_id for node_id in frontier_candidates if node_id not in selected
            )[: limit - len(selected)]
            selected.extend(frontier)
        total_candidates = len(ordered_base) + len(
            tuple(node for node in frontier_candidates if node not in ordered_base)
        )
        selected_set = set(selected)
        return {
            "node_ids": tuple(selected),
            "practiced": tuple(node for node in practiced if node in selected_set),
            "mastered": tuple(node for node in mastered if node in selected_set),
            "frontier": frontier,
            "omitted": max(0, total_candidates - len(selected)),
        }

    def _eligible_frontier(
        self,
        user_id: UUID,
        visible: tuple[UUID, ...],
        *,
        limit: int,
    ) -> tuple[UUID, ...]:
        if limit <= 0:
            return ()
        eligible = set(self.eligible_node_ids(user_id))
        if not eligible:
            return ()
        with self._database.read_connection() as connection:
            if visible:
                placeholders = ",".join("?" for _ in visible)
                parameters = tuple(str(node_id) for node_id in visible)
                rows = connection.execute(
                    f"""WITH adjacent AS (
                           SELECT previous.graph_node_id AS source_node_id,
                                  following.graph_node_id AS target_node_id,
                                  t.position AS track_position,
                                  following.position AS target_position
                           FROM learning_chapters previous
                           JOIN learning_chapters following
                             ON following.track_id=previous.track_id
                            AND following.position=previous.position+1
                           JOIN learning_tracks t ON t.id=following.track_id
                         ), dependencies AS (
                           SELECT prerequisite_chapter.graph_node_id AS source_node_id,
                                  target_chapter.graph_node_id AS target_node_id,
                                  target_track.position AS track_position,
                                  target_chapter.position AS target_position
                           FROM learning_unit_dependencies d
                           JOIN learning_units prerequisite_unit
                             ON prerequisite_unit.id=d.prerequisite_unit_id
                           JOIN learning_chapters prerequisite_chapter
                             ON prerequisite_chapter.id=prerequisite_unit.chapter_id
                           JOIN learning_units target_unit ON target_unit.id=d.unit_id
                           JOIN learning_chapters target_chapter
                             ON target_chapter.id=target_unit.chapter_id
                           JOIN learning_tracks target_track
                             ON target_track.id=target_chapter.track_id
                           WHERE prerequisite_chapter.graph_node_id<>target_chapter.graph_node_id
                         )
                         SELECT target_node_id,MIN(track_position) track_position,
                                MIN(target_position) target_position
                         FROM (SELECT * FROM adjacent UNION ALL SELECT * FROM dependencies)
                         WHERE source_node_id IN ({placeholders})
                         GROUP BY target_node_id
                         ORDER BY track_position,target_position,target_node_id""",
                    parameters,
                ).fetchall()
            else:
                rows = connection.execute(
                    """SELECT c.graph_node_id AS target_node_id,
                              t.position AS track_position,c.position AS target_position
                       FROM learning_chapters c
                       JOIN learning_tracks t ON t.id=c.track_id
                       WHERE c.position=(
                         SELECT min(first_chapter.position)
                         FROM learning_chapters first_chapter
                         WHERE first_chapter.track_id=c.track_id
                       ) AND NOT EXISTS(
                         SELECT 1 FROM course_prerequisites cp WHERE cp.track_id=t.id)
                       ORDER BY t.position,c.position,c.graph_node_id"""
                ).fetchall()
        visible_set = set(visible)
        return tuple(
            UUID(row["target_node_id"])
            for row in rows
            if UUID(row["target_node_id"]) in eligible
            and UUID(row["target_node_id"]) not in visible_set
        )[:limit]

    def semantic_edges(
        self,
        node_ids: tuple[UUID, ...],
        *,
        limit: int,
        generated_at: datetime,
    ) -> tuple[tuple[GraphEdgeSnapshotDTO, ...], int]:
        """Compose typed relations from normalized existing tables."""

        if not 0 <= limit <= 300:
            raise ValueError("visible graph edge limit must be in [0, 300]")
        if len(node_ids) < 2:
            return (), 0
        placeholders = ",".join("?" for _ in node_ids)
        parameters = tuple(str(node_id) for node_id in node_ids)
        edges: dict[tuple[str, str, GraphRelationType], GraphEdgeSnapshotDTO] = {}

        def add(
            source: str,
            target: str,
            relation: GraphRelationType,
            *,
            weight: float,
            directed: bool,
            reason: str,
            origin: str,
            count: int = 0,
            updated_at: datetime | None = None,
        ) -> None:
            if source == target:
                return
            if not directed and source > target:
                source, target = target, source
            key = (source, target, relation)
            candidate = GraphEdgeSnapshotDTO(
                source_node_id=UUID(source), target_node_id=UUID(target),
                weight=weight, co_occurrence_count=count,
                relation_type=relation, directed=directed,
                reason=reason, origin=origin,
                updated_at=updated_at or generated_at,
            )
            previous = edges.get(key)
            if previous is None or candidate.weight > previous.weight:
                edges[key] = candidate

        with self._database.read_connection() as connection:
            dependency_rows = connection.execute(
                f"""SELECT DISTINCT prerequisite_chapter.graph_node_id AS source_node_id,
                                  target_chapter.graph_node_id AS target_node_id,
                                  prerequisite_chapter.title AS source_title,
                                  target_chapter.title AS target_title
                    FROM learning_unit_dependencies d
                    JOIN learning_units prerequisite_unit
                      ON prerequisite_unit.id=d.prerequisite_unit_id
                    JOIN learning_chapters prerequisite_chapter
                      ON prerequisite_chapter.id=prerequisite_unit.chapter_id
                    JOIN learning_units target_unit ON target_unit.id=d.unit_id
                    JOIN learning_chapters target_chapter
                      ON target_chapter.id=target_unit.chapter_id
                    WHERE prerequisite_chapter.graph_node_id IN ({placeholders})
                      AND target_chapter.graph_node_id IN ({placeholders})
                      AND prerequisite_chapter.graph_node_id<>target_chapter.graph_node_id""",
                (*parameters, *parameters),
            ).fetchall()
            course_rows = connection.execute(
                f"""SELECT source.graph_node_id AS source_node_id,
                           target.graph_node_id AS target_node_id,
                           source.title AS source_title,target.title AS target_title
                    FROM course_prerequisites cp
                    JOIN learning_chapters source ON source.track_id=cp.prerequisite_track_id
                    JOIN learning_chapters target ON target.track_id=cp.track_id
                    WHERE source.position=(SELECT max(s2.position) FROM learning_chapters s2
                                           WHERE s2.track_id=source.track_id)
                      AND target.position=(SELECT min(t2.position) FROM learning_chapters t2
                                           WHERE t2.track_id=target.track_id)
                      AND source.graph_node_id IN ({placeholders})
                      AND target.graph_node_id IN ({placeholders})""",
                (*parameters, *parameters),
            ).fetchall()
            progression_rows = connection.execute(
                f"""SELECT previous.graph_node_id AS source_node_id,
                           following.graph_node_id AS target_node_id,
                           previous.title AS source_title,following.title AS target_title
                    FROM learning_chapters previous
                    JOIN learning_chapters following
                      ON following.track_id=previous.track_id
                     AND following.position=previous.position+1
                    WHERE previous.graph_node_id IN ({placeholders})
                      AND following.graph_node_id IN ({placeholders})
                      AND previous.graph_node_id<>following.graph_node_id""",
                (*parameters, *parameters),
            ).fetchall()
            related_rows = connection.execute(
                f"""SELECT first_chapter.graph_node_id AS source_node_id,
                           second_chapter.graph_node_id AS target_node_id,
                           MIN(objective.description) AS objective
                    FROM unit_objectives first_mapping
                    JOIN unit_objectives second_mapping
                      ON second_mapping.objective_id=first_mapping.objective_id
                     AND second_mapping.unit_id>first_mapping.unit_id
                    JOIN curriculum_objectives objective
                      ON objective.id=first_mapping.objective_id
                    JOIN learning_units first_unit ON first_unit.id=first_mapping.unit_id
                    JOIN learning_units second_unit ON second_unit.id=second_mapping.unit_id
                    JOIN learning_chapters first_chapter ON first_chapter.id=first_unit.chapter_id
                    JOIN learning_chapters second_chapter ON second_chapter.id=second_unit.chapter_id
                    WHERE first_chapter.graph_node_id IN ({placeholders})
                      AND second_chapter.graph_node_id IN ({placeholders})
                      AND first_chapter.graph_node_id<>second_chapter.graph_node_id
                    GROUP BY first_chapter.graph_node_id,second_chapter.graph_node_id""",
                (*parameters, *parameters),
            ).fetchall()
            co_rows = connection.execute(
                f"""SELECT source_node_id,target_node_id,weight,
                           co_occurrence_count,updated_at
                    FROM graph_edges
                    WHERE source_node_id IN ({placeholders})
                      AND target_node_id IN ({placeholders})""",
                (*parameters, *parameters),
            ).fetchall()

        for row in dependency_rows:
            add(
                row["source_node_id"], row["target_node_id"],
                GraphRelationType.PREREQUISITE, weight=1.0, directed=True,
                reason=f"«{row['source_title']}» é requisito de «{row['target_title']}».",
                origin="learning_unit_dependencies",
            )
        for row in course_rows:
            add(
                row["source_node_id"], row["target_node_id"],
                GraphRelationType.PREREQUISITE, weight=1.0, directed=True,
                reason=f"«{row['source_title']}» conclui o percurso exigido por «{row['target_title']}».",
                origin="course_prerequisites",
            )
        for row in progression_rows:
            add(
                row["source_node_id"], row["target_node_id"],
                GraphRelationType.PROGRESSION, weight=0.85, directed=True,
                reason=f"Progressão curricular de «{row['source_title']}» para «{row['target_title']}».",
                origin="learning_chapters",
            )
        for row in related_rows:
            related_reason = (
                f"Partilham o objetivo curricular: {row['objective']}"
            )[:500]
            add(
                row["source_node_id"], row["target_node_id"],
                GraphRelationType.RELATED, weight=0.55, directed=False,
                reason=related_reason,
                origin="unit_objectives",
            )
        for row in co_rows:
            add(
                row["source_node_id"], row["target_node_id"],
                GraphRelationType.CO_OCCURRENCE, weight=float(row["weight"]),
                directed=False,
                reason="Conceitos praticados em proximidade temporal.",
                origin="graph_edges", count=int(row["co_occurrence_count"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
        priority = {
            GraphRelationType.PREREQUISITE: 0,
            GraphRelationType.PROGRESSION: 1,
            GraphRelationType.RELATED: 2,
            GraphRelationType.CO_OCCURRENCE: 3,
        }
        ordered = sorted(
            edges.values(),
            key=lambda item: (
                priority[item.relation_type], -item.weight,
                str(item.source_node_id), str(item.target_node_id),
            ),
        )
        return tuple(ordered[:limit]), len(ordered)

    def node_analytics(
        self,
        user_id: UUID,
        node_ids: tuple[UUID, ...],
        *,
        start: datetime,
        end: datetime,
    ) -> dict[UUID, NodeAnalyticsDTO]:
        """Return period metrics for visible nodes using bounded batch queries."""

        if not node_ids:
            return {}
        placeholders = ",".join("?" for _ in node_ids)
        ids = tuple(str(node_id) for node_id in node_ids)
        midpoint = start + (end - start) / 2
        with self._database.read_connection() as connection:
            title_rows = connection.execute(
                f"SELECT id,title FROM graph_nodes WHERE id IN ({placeholders})",
                ids,
            ).fetchall()
            attempt_rows = connection.execute(
                f"""SELECT e.graph_node_id AS node_id,
                           count(*) AS attempts,
                           count(DISTINCT a.exercise_id) AS distinct_exercises,
                           sum(a.status='passed') AS successes,
                           sum(a.status IN ('failed','error')) AS failures
                    FROM attempts a JOIN exercises e ON e.id=a.exercise_id
                    WHERE a.user_id=? AND e.graph_node_id IN ({placeholders})
                      AND a.status IN ('passed','failed','error')
                      AND COALESCE(a.submitted_at,a.created_at)>=?
                      AND COALESCE(a.submitted_at,a.created_at)<?
                    GROUP BY e.graph_node_id""",
                (str(user_id), *ids, start.isoformat(), end.isoformat()),
            ).fetchall()
            evidence_rows = connection.execute(
                f"""SELECT *
                    FROM learning_evidence
                    WHERE user_id=? AND node_id IN ({placeholders})
                      AND occurred_at<? ORDER BY occurred_at,id""",
                (str(user_id), *ids, end.isoformat()),
            ).fetchall()
        titles = {UUID(row["id"]): row["title"] for row in title_rows}
        attempts = {UUID(row["node_id"]): row for row in attempt_rows}
        evidence_by_node: dict[UUID, list[sqlite3.Row]] = {}
        for row in evidence_rows:
            evidence_by_node.setdefault(UUID(row["node_id"]), []).append(row)
        result: dict[UUID, NodeAnalyticsDTO] = {}
        for node_id in node_ids:
            node_evidence = evidence_by_node.get(node_id, [])
            from aprendix.application.progress import update_mastery_state
            reconstructed = None
            for row in node_evidence:
                reconstructed = update_mastery_state(
                    reconstructed,
                    LearningEvidenceDTO(
                        id=UUID(row["id"]), user_id=UUID(row["user_id"]),
                        node_id=UUID(row["node_id"]), source_key=row["source_key"],
                        evidence_type=EvidenceType(row["evidence_type"]),
                        score=float(row["score"]),
                        duration_seconds=row["duration_seconds"],
                        active_seconds=row["active_seconds"],
                        hint_count=int(row["hint_count"]),
                        paste_ratio=float(row["paste_ratio"]),
                        error_category=ErrorCategory(row["error_category"]),
                        transfer_score=row["transfer_score"],
                        project_quality=row["project_quality"],
                        item_difficulty=float(row["item_difficulty"]),
                        item_discrimination=float(row["item_discrimination"]),
                        response_confidence=float(row["response_confidence"]),
                        context_key=row["context_key"],
                        occurred_at=datetime.fromisoformat(row["occurred_at"]),
                    ),
                )
            period_items = [
                row for row in node_evidence
                if start <= datetime.fromisoformat(row["occurred_at"]) < end
            ]
            earlier = [float(row["score"]) for row in period_items
                       if datetime.fromisoformat(row["occurred_at"]) < midpoint]
            later = [float(row["score"]) for row in period_items
                     if datetime.fromisoformat(row["occurred_at"]) >= midpoint]
            trend = (
                sum(later) / len(later) - sum(earlier) / len(earlier)
                if earlier and later else 0.0
            )
            attempt = attempts.get(node_id)
            attempt_count = int(attempt["attempts"]) if attempt else 0
            success_count = int(attempt["successes"] or 0) if attempt else 0
            failure_count = int(attempt["failures"] or 0) if attempt else 0
            last_practiced = (
                datetime.fromisoformat(node_evidence[-1]["occurred_at"])
                if node_evidence else None
            )
            retention = 0.0
            if reconstructed is not None and reconstructed.last_practiced_at:
                last_state = reconstructed.last_practiced_at
                elapsed = max(0.0, (end - last_state).total_seconds() / 86_400)
                half_life = min(
                    120.0,
                    2.0 * (1.75 ** min(8, reconstructed.successful_reviews)),
                )
                retention = max(0.0, min(1.0, 2 ** (-elapsed / half_life)))
            mastery = reconstructed.p_known if reconstructed is not None else 0.0
            autonomy = reconstructed.autonomy if reconstructed is not None else 0.0
            if not node_evidence:
                action = "Começa por uma prática guiada curta."
            elif retention < 0.58:
                action = "Revê este conceito para reduzir o risco de esquecimento."
            elif mastery < 0.8:
                action = "Resolve uma nova variação sem aumentar a dificuldade."
            elif autonomy < 0.65:
                action = "Repete sem pistas para consolidar a autonomia."
            else:
                action = "Valida a transferência num problema ou projeto diferente."
            result[node_id] = NodeAnalyticsDTO(
                node_id=node_id, title=titles[node_id],
                period_start=start, period_end=end,
                distinct_exercises=(int(attempt["distinct_exercises"]) if attempt else 0),
                attempts=attempt_count, successes=success_count, failures=failure_count,
                active_seconds=sum(
                    max(0, int(row["active_seconds"] if row["active_seconds"] is not None
                               else (row["duration_seconds"] or 0)))
                    for row in period_items
                ),
                hint_count=sum(int(row["hint_count"]) for row in period_items),
                evidence_count=len(period_items), mastery=mastery,
                retention=retention, autonomy=autonomy,
                success_rate=(success_count / attempt_count if attempt_count else 0.0),
                trend=max(-1.0, min(1.0, trend)),
                last_practiced_at=last_practiced,
                recommended_action=action,
            )
        return result

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
