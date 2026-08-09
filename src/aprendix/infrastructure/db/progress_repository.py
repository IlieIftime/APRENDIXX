"""SQLite persistence for learning evidence, mastery and weekly plans."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from aprendix.application.contracts import (
    EvidenceType, LearningAction, LearningEvidenceDTO, MasteryStateDTO,
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

    def replace_week(self, user_id: UUID, start: date, items: tuple[WeeklyPlanItemDTO, ...]) -> None:
        from datetime import timedelta, UTC, datetime
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
