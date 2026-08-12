"""SQLite persistence for learning evidence, mastery and weekly plans."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from aprendix.application.contracts import (
    ErrorCategory,
    EvidenceType,
    LearningAction,
    LearningEvidenceDTO,
    MasteryStateDTO,
    WeeklyPlanItemDTO,
)


class LearningProgressRepository:
    def __init__(self, database) -> None:
        self._database = database

    @staticmethod
    def _state(row) -> MasteryStateDTO:
        return MasteryStateDTO(
            user_id=UUID(row["user_id"]), node_id=UUID(row["node_id"]),
            p_known=row["p_known"], retention=row["retention"],
            autonomy=row["autonomy"], velocity=row["velocity"],
            confidence=row["confidence"], evidence_count=row["evidence_count"],
            irt_ability=row["irt_ability"], irt_information=row["irt_information"],
            successful_reviews=row["successful_reviews"],
            last_practiced_at=datetime.fromisoformat(row["last_practiced_at"]) if row["last_practiced_at"] else None,
            next_review_at=datetime.fromisoformat(row["next_review_at"]) if row["next_review_at"] else None,
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def state(self, user_id: UUID, node_id: UUID) -> MasteryStateDTO | None:
        with self._database.read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM mastery_states WHERE user_id=? AND node_id=?",
                (str(user_id), str(node_id)),
            ).fetchone()
        return self._state(row) if row else None

    def states(self, user_id: UUID) -> tuple[MasteryStateDTO, ...]:
        with self._database.read_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM mastery_states WHERE user_id=? ORDER BY node_id",
                (str(user_id),),
            ).fetchall()
        return tuple(self._state(row) for row in rows)

    def commit_evidence(self, evidence: LearningEvidenceDTO, state: MasteryStateDTO) -> bool:
        with self._database.transaction() as connection:
            cursor = connection.execute(
                """INSERT OR IGNORE INTO learning_evidence(
                   id,user_id,node_id,source_key,evidence_type,score,duration_seconds,
                   hint_count,paste_ratio,context_key,occurred_at,active_seconds,
                   error_category,transfer_score,project_quality,item_difficulty,
                   item_discrimination,response_confidence)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (str(evidence.id), str(evidence.user_id), str(evidence.node_id),
                 evidence.source_key, evidence.evidence_type.value, evidence.score,
                 evidence.duration_seconds, evidence.hint_count, evidence.paste_ratio,
                 evidence.context_key, evidence.occurred_at.isoformat(),
                 evidence.active_seconds, evidence.error_category.value,
                 evidence.transfer_score, evidence.project_quality,
                 evidence.item_difficulty, evidence.item_discrimination,
                 evidence.response_confidence),
            )
            if cursor.rowcount == 0:
                return False
            connection.execute(
                """INSERT INTO mastery_states(
                   user_id,node_id,p_known,retention,autonomy,velocity,confidence,
                   evidence_count,successful_reviews,last_practiced_at,next_review_at,updated_at,
                   irt_ability,irt_information)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(user_id,node_id) DO UPDATE SET
                   p_known=excluded.p_known,retention=excluded.retention,
                   autonomy=excluded.autonomy,velocity=excluded.velocity,
                   confidence=excluded.confidence,evidence_count=excluded.evidence_count,
                   successful_reviews=excluded.successful_reviews,
                   last_practiced_at=excluded.last_practiced_at,
                   next_review_at=excluded.next_review_at,updated_at=excluded.updated_at,
                   irt_ability=excluded.irt_ability,irt_information=excluded.irt_information""",
                (str(state.user_id), str(state.node_id), state.p_known,
                 state.retention, state.autonomy, state.velocity, state.confidence,
                 state.evidence_count, state.successful_reviews,
                 state.last_practiced_at.isoformat() if state.last_practiced_at else None,
                 state.next_review_at.isoformat() if state.next_review_at else None,
                 state.updated_at.isoformat(), state.irt_ability, state.irt_information),
            )
        return True

    def node_catalog(self, user_id: UUID | None = None) -> tuple[tuple[UUID, str, float], ...]:
        with self._database.read_connection() as connection:
            if user_id is None:
                rows = connection.execute(
                    "SELECT id,title,difficulty FROM graph_nodes ORDER BY difficulty,title"
                ).fetchall()
            else:
                rows = connection.execute(
                    """SELECT DISTINCT g.id,g.title,g.difficulty FROM graph_nodes g
                       LEFT JOIN learning_chapters c ON c.graph_node_id=g.id
                       WHERE c.track_id IS NULL OR EXISTS(
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
                           AND pc.track_id=cp.prerequisite_track_id))
                       ORDER BY g.difficulty,g.title""", (str(user_id), str(user_id))
                ).fetchall()
        return tuple((UUID(row["id"]), row["title"], row["difficulty"]) for row in rows)

    def node_for_card(self, card_id: UUID) -> UUID | None:
        with self._database.read_connection() as connection:
            row = connection.execute(
                "SELECT graph_node_id FROM theory_cards WHERE id=?", (str(card_id),)
            ).fetchone()
        return UUID(row[0]) if row and row[0] else None

    def legacy_evidence(self, user_id: UUID) -> tuple[LearningEvidenceDTO, ...]:
        """Project pre-v16 numeric history into the new model without user content."""
        with self._database.read_connection() as connection:
            attempts = connection.execute(
                """SELECT a.id,e.graph_node_id,a.score,a.duration_ms,a.created_at
                   FROM attempts a JOIN exercises e ON e.id=a.exercise_id
                   WHERE a.user_id=? AND a.score IS NOT NULL AND NOT EXISTS(
                     SELECT 1 FROM learning_evidence le
                     WHERE le.user_id=a.user_id AND le.source_key='attempt:' || a.id)
                   ORDER BY a.created_at,a.id""", (str(user_id),)
            ).fetchall()
            assessments = connection.execute(
                """SELECT aa.id,c.graph_node_id,aa.score,aa.duration_seconds,
                          aa.created_at,ai.kind
                   FROM assessment_attempts aa
                   JOIN assessment_items ai ON ai.id=aa.item_id
                   JOIN learning_units u ON u.id=ai.unit_id
                   JOIN learning_chapters c ON c.id=u.chapter_id
                   WHERE aa.user_id=? AND NOT EXISTS(
                     SELECT 1 FROM learning_evidence le
                     WHERE le.user_id=aa.user_id AND le.source_key='assessment:' || aa.id)
                   ORDER BY aa.created_at,aa.id""", (str(user_id),)
            ).fetchall()
            reviews = connection.execute(
                """SELECT r.card_id,t.graph_node_id,r.mastery,r.successful_reviews,r.updated_at
                   FROM card_review_state r JOIN theory_cards t ON t.id=r.card_id
                   WHERE r.user_id=? AND t.graph_node_id IS NOT NULL AND NOT EXISTS(
                     SELECT 1 FROM learning_evidence le WHERE le.user_id=r.user_id
                     AND le.source_key='legacy-card:' || r.card_id || ':' || r.updated_at)
                   ORDER BY r.updated_at,r.card_id""", (str(user_id),)
            ).fetchall()
        result = [LearningEvidenceDTO(
            user_id=user_id, node_id=UUID(row["graph_node_id"]),
            source_key=f"attempt:{row['id']}", evidence_type=EvidenceType.PRACTICE,
            score=float(row["score"]),
            duration_seconds=max(0, int(row["duration_ms"] or 0) // 1000),
            occurred_at=datetime.fromisoformat(row["created_at"]),
        ) for row in attempts]
        result.extend(LearningEvidenceDTO(
            user_id=user_id, node_id=UUID(row["graph_node_id"]),
            source_key=f"assessment:{row['id']}",
            evidence_type={"hybrid": EvidenceType.HYBRID,
                           "practical": EvidenceType.PRACTICE}.get(row["kind"], EvidenceType.THEORY),
            score=float(row["score"]), duration_seconds=row["duration_seconds"],
            occurred_at=datetime.fromisoformat(row["created_at"]),
        ) for row in assessments)
        result.extend(LearningEvidenceDTO(
            user_id=user_id, node_id=UUID(row["graph_node_id"]),
            source_key=f"legacy-card:{row['card_id']}:{row['updated_at']}",
            evidence_type=EvidenceType.REVIEW, score=float(row["mastery"]),
            occurred_at=datetime.fromisoformat(row["updated_at"]),
        ) for row in reviews)
        return tuple(sorted(result, key=lambda item: (item.occurred_at, item.source_key)))

    def study_plan(self, user_id: UUID):
        with self._database.read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM study_plans WHERE user_id=?", (str(user_id),)
            ).fetchone()
        return dict(row) if row else None

    def activity_summary(self, user_id: UUID) -> dict[str, int]:
        with self._database.read_connection() as connection:
            row = connection.execute(
                """SELECT COALESCE(sum(duration_seconds),0) total_seconds,
                          COALESCE(sum(COALESCE(active_seconds,duration_seconds,0)),0) active_seconds
                   FROM learning_evidence WHERE user_id=?""",
                (str(user_id),),
            ).fetchone()
        return {"total_seconds": int(row["total_seconds"]),
                "active_seconds": int(row["active_seconds"])}

    def period_summary(self, user_id: UUID, start: datetime, end: datetime) -> dict[str, float | int]:
        with self._database.read_connection() as connection:
            row = connection.execute(
                """SELECT count(*) evidence_count,COALESCE(avg(score),0) average_score,
                          COALESCE(sum(COALESCE(active_seconds,duration_seconds,0)),0) active_seconds
                   FROM learning_evidence WHERE user_id=? AND occurred_at>=? AND occurred_at<?""",
                (str(user_id), start.isoformat(), end.isoformat()),
            ).fetchone()
        return {
            "evidence_count": int(row["evidence_count"]),
            "average_score": float(row["average_score"]),
            "active_seconds": int(row["active_seconds"]),
        }

    def curriculum_node_count(self) -> int:
        with self._database.read_connection() as connection:
            return int(connection.execute(
                "SELECT count(DISTINCT graph_node_id) FROM learning_chapters"
            ).fetchone()[0])

    def plan_completion(self, user_id: UUID, start: date, end: date) -> dict[str, int]:
        with self._database.read_connection() as connection:
            row = connection.execute(
                """SELECT count(*) planned,COALESCE(sum(completed),0) completed
                   FROM weekly_plan_items WHERE user_id=? AND scheduled_for BETWEEN ? AND ?""",
                (str(user_id), start.isoformat(), end.isoformat()),
            ).fetchone()
        return {"planned": int(row["planned"]), "completed": int(row["completed"])}

    def complete_plan_item(self, user_id: UUID, item_id: UUID, completed: bool = True) -> bool:
        from datetime import UTC
        with self._database.transaction() as connection:
            cursor = connection.execute(
                """UPDATE weekly_plan_items SET completed=?,updated_at=?
                   WHERE id=? AND user_id=?""",
                (int(completed), datetime.now(UTC).isoformat(), str(item_id), str(user_id)),
            )
        return cursor.rowcount == 1

    def replace_week(self, user_id: UUID, start: date, items: tuple[WeeklyPlanItemDTO, ...]) -> None:
        from datetime import UTC, datetime, timedelta
        now = datetime.now(UTC).isoformat()
        end = start + timedelta(days=6)
        with self._database.transaction() as connection:
            connection.execute(
                "DELETE FROM weekly_plan_items WHERE user_id=? AND scheduled_for BETWEEN ? AND ? AND completed=0",
                (str(user_id), start.isoformat(), end.isoformat()),
            )
            connection.executemany(
                """INSERT OR IGNORE INTO weekly_plan_items(
                   id,user_id,scheduled_for,node_id,title,action,duration_minutes,
                   reason_code,completed,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                [(str(item.id), str(item.user_id), item.scheduled_for.isoformat(),
                  str(item.node_id), item.title, item.action.value, item.duration_minutes,
                  item.reason_code, int(item.completed), now, now) for item in items],
            )

    def weekly_plan(self, user_id: UUID, start: date, end: date) -> tuple[WeeklyPlanItemDTO, ...]:
        with self._database.read_connection() as connection:
            rows = connection.execute(
                """SELECT * FROM weekly_plan_items WHERE user_id=?
                   AND scheduled_for BETWEEN ? AND ? ORDER BY scheduled_for,id""",
                (str(user_id), start.isoformat(), end.isoformat()),
            ).fetchall()
        return tuple(WeeklyPlanItemDTO(
            id=UUID(row["id"]), user_id=UUID(row["user_id"]),
            scheduled_for=date.fromisoformat(row["scheduled_for"]),
            node_id=UUID(row["node_id"]), title=row["title"],
            action=LearningAction(row["action"]), duration_minutes=row["duration_minutes"],
            reason_code=row["reason_code"], completed=bool(row["completed"]),
        ) for row in rows)

    def analytics_scope_nodes(
        self,
        *,
        track_slug: str | None = None,
        node_id: UUID | None = None,
    ) -> tuple[dict[str, object], ...]:
        """Return only curriculum nodes for a global, track, or node scope.

        Dictionary/glossary nodes deliberately never enter the global denominator.
        A graph node reused by more than one chapter is counted exactly once.
        """

        clauses: list[str] = []
        parameters: list[str] = []
        if track_slug is not None:
            clauses.append("t.slug = ?")
            parameters.append(track_slug)
        if node_id is not None:
            clauses.append("g.id = ?")
            parameters.append(str(node_id))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._database.read_connection() as connection:
            rows = connection.execute(
                f"""SELECT g.id AS node_id,g.title,t.slug AS track_slug,
                           t.title AS track_title,t.position AS track_position,
                           MIN(c.position) AS chapter_position
                    FROM learning_chapters c
                    JOIN learning_tracks t ON t.id=c.track_id
                    JOIN graph_nodes g ON g.id=c.graph_node_id
                    {where}
                    GROUP BY g.id,g.title,t.slug,t.title,t.position
                    ORDER BY t.position,chapter_position,g.title,g.id""",
                tuple(parameters),
            ).fetchall()
        # A shared graph concept has one denominator entry. Retain the first
        # curricular placement for display/grouping deterministically.
        unique: dict[str, dict[str, object]] = {}
        for row in rows:
            unique.setdefault(
                row["node_id"],
                {
                    "node_id": UUID(row["node_id"]),
                    "title": row["title"],
                    "track_slug": row["track_slug"],
                    "track_title": row["track_title"],
                },
            )
        return tuple(unique.values())

    def analytics_evidence(
        self,
        user_id: UUID,
        node_ids: tuple[UUID, ...],
        *,
        before: datetime,
    ) -> tuple[LearningEvidenceDTO, ...]:
        """Load numeric evidence needed to reconstruct historical mastery."""

        if not node_ids:
            return ()
        placeholders = ",".join("?" for _ in node_ids)
        parameters = (
            str(user_id),
            *(str(node_id) for node_id in node_ids),
            before.isoformat(),
        )
        with self._database.read_connection() as connection:
            rows = connection.execute(
                f"""SELECT * FROM learning_evidence
                    WHERE user_id=? AND node_id IN ({placeholders})
                      AND occurred_at<?
                    ORDER BY occurred_at,id""",
                parameters,
            ).fetchall()
        return tuple(
            LearningEvidenceDTO(
                id=UUID(row["id"]),
                user_id=UUID(row["user_id"]),
                node_id=UUID(row["node_id"]),
                source_key=row["source_key"],
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
            )
            for row in rows
        )

    def analytics_planned_minutes(
        self,
        user_id: UUID,
        start: date,
        end: date,
    ) -> dict[date, float]:
        """Return explicit daily plan minutes, or the configured weekly pace."""

        with self._database.read_connection() as connection:
            rows = connection.execute(
                """SELECT scheduled_for,sum(duration_minutes) AS minutes
                   FROM weekly_plan_items
                   WHERE user_id=? AND scheduled_for>=? AND scheduled_for<?
                   GROUP BY scheduled_for ORDER BY scheduled_for""",
                (str(user_id), start.isoformat(), end.isoformat()),
            ).fetchall()
            plan = connection.execute(
                "SELECT start_date,weekly_hours FROM study_plans WHERE user_id=?",
                (str(user_id),),
            ).fetchone()
        explicit = {
            date.fromisoformat(row["scheduled_for"]): float(row["minutes"])
            for row in rows
        }
        daily = (float(plan["weekly_hours"]) * 60.0 / 7.0) if plan else 0.0
        plan_start = date.fromisoformat(plan["start_date"]) if plan else None
        result: dict[date, float] = {}
        current = start
        while current < end:
            result[current] = daily if plan_start is None or current >= plan_start else 0.0
            current = date.fromordinal(current.toordinal() + 1)
        result.update(explicit)
        return result

    def analytics_next_milestone(self, user_id: UUID) -> dict[str, object] | None:
        """Return the next unfinished local milestone without exposing evidence."""

        with self._database.read_connection() as connection:
            row = connection.execute(
                """SELECT md.theme,md.rank_to,md.required_distinct_passes,
                          COALESCE(json_array_length(um.completed_exercises_json),0)
                              AS completed
                   FROM milestone_definitions md
                   LEFT JOIN user_milestones um
                     ON um.milestone_id=md.id AND um.user_id=?
                   WHERE um.completed_at IS NULL
                   ORDER BY md.position,md.id LIMIT 1""",
                (str(user_id),),
            ).fetchone()
        if row is None:
            return None
        return {
            "title": f"{row['theme']} · {row['rank_to']}",
            "completed": int(row["completed"]),
            "required": int(row["required_distinct_passes"]),
        }
