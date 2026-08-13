"""Encrypted persistence for desktop projects, milestones, and editor sessions."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from aprendix.application.contracts import (
    LearnerRank, LearningAccessDTO, LearningPhase, LearningSessionDTO, LearningTheme,
    MilestoneProgressDTO, ProjectDTO, Technology,
)
from aprendix.infrastructure.db.access_policy import practice_access, unit_access
from aprendix.infrastructure.db.database import Database
from aprendix.infrastructure.security import AesGcmFieldCipher
from aprendix.infrastructure.security.field_cipher import EncryptionError


_MILESTONES = (
    (LearningTheme.FUNDAMENTALS, LearnerRank.INITIATE, LearnerRank.ADEPT, 3),
    (LearningTheme.OOP, LearnerRank.ADEPT, LearnerRank.PROFICIENT, 10),
    (LearningTheme.ALGORITHMS, LearnerRank.ADEPT, LearnerRank.PROFICIENT, 5),
    (LearningTheme.DATA_STRUCTURES, LearnerRank.PROFICIENT, LearnerRank.EXPERT, 5),
)


class DesktopRepository:
    def __init__(self, database: Database, cipher: AesGcmFieldCipher) -> None:
        self._database = database
        self._cipher = cipher

    @staticmethod
    def _project_file_aad(project_id: UUID, relative_path: str) -> bytes:
        return f"project_files.content:{project_id}:{relative_path}".encode()

    def _decrypt_project_file(
        self, project_id: UUID, relative_path: str, envelope: bytes,
    ) -> str:
        try:
            payload = self._cipher.decrypt(
                envelope,
                associated_data=self._project_file_aad(project_id, relative_path),
            )
        except EncryptionError:
            # Compatibility with project files created before multi-file AAD.
            payload = self._cipher.decrypt(
                envelope,
                associated_data=f"project_files.content:{project_id}:main".encode(),
            )
        return payload.decode()

    @staticmethod
    def _learning_session_aad(
        field: str, user_id: UUID, exercise_id: UUID,
    ) -> bytes:
        return f"learning_sessions.{field}:{user_id}:{exercise_id}".encode()

    def learning_session(
        self, user_id: UUID, exercise_id: UUID,
    ) -> LearningSessionDTO:
        """Load a resumable session and its declared curriculum objective."""

        with self._database.read_connection() as connection:
            context = connection.execute(
                """SELECT u.id unit_id,o.id objective_id,o.code objective_code,
                          o.description objective_description
                   FROM learning_units u
                   LEFT JOIN unit_objectives uo ON uo.unit_id=u.id
                   LEFT JOIN curriculum_objectives o ON o.id=uo.objective_id
                   WHERE u.exercise_id=?
                   ORDER BY COALESCE(uo.required,0) DESC,o.code LIMIT 1""",
                (str(exercise_id),),
            ).fetchone()
            row = connection.execute(
                "SELECT * FROM learning_sessions WHERE user_id=? AND exercise_id=?",
                (str(user_id), str(exercise_id)),
            ).fetchone()
        objective = dict(context) if context is not None else {}
        if row is None:
            return LearningSessionDTO(
                user_id=user_id,
                exercise_id=exercise_id,
                unit_id=str(objective.get("unit_id") or ""),
                objective_id=str(objective.get("objective_id") or ""),
                objective_code=str(objective.get("objective_code") or ""),
                objective_description=str(objective.get("objective_description") or ""),
            )

        def decrypt(field: str) -> str:
            value = row[f"{field}_encrypted"]
            if value is None:
                return ""
            return self._cipher.decrypt(
                value,
                associated_data=self._learning_session_aad(field, user_id, exercise_id),
            ).decode("utf-8")

        return LearningSessionDTO(
            user_id=user_id,
            exercise_id=exercise_id,
            unit_id=str(row["unit_id"] or objective.get("unit_id") or ""),
            objective_id=str(row["objective_id"] or objective.get("objective_id") or ""),
            objective_code=str(objective.get("objective_code") or ""),
            objective_description=str(objective.get("objective_description") or ""),
            phase=LearningPhase(row["phase"]),
            mode=str(row["mode"]),
            theory_viewed=bool(row["theory_viewed"]),
            independent_passed=bool(row["independent_passed"]),
            transfer_passed=bool(row["transfer_passed"]),
            hint_count=int(row["hint_count"]),
            active_seconds=int(row["active_seconds"]),
            prediction=decrypt("prediction"),
            reflection=decrypt("reflection"),
            started_at=datetime.fromisoformat(row["started_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def save_learning_session(
        self, session: LearningSessionDTO,
    ) -> LearningSessionDTO:
        """Upsert learner-authored state with sensitive text encrypted."""

        def encrypt(field: str, value: str) -> bytes | None:
            if not value:
                return None
            return self._cipher.encrypt(
                value.encode("utf-8"),
                associated_data=self._learning_session_aad(
                    field, session.user_id, session.exercise_id,
                ),
            )

        with self._database.transaction() as connection:
            connection.execute(
                """INSERT INTO learning_sessions(
                       user_id,exercise_id,unit_id,objective_id,phase,mode,
                       theory_viewed,independent_passed,transfer_passed,hint_count,
                       active_seconds,prediction_encrypted,reflection_encrypted,
                       started_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(user_id,exercise_id) DO UPDATE SET
                       unit_id=excluded.unit_id,objective_id=excluded.objective_id,
                       phase=excluded.phase,mode=excluded.mode,
                       theory_viewed=excluded.theory_viewed,
                       independent_passed=excluded.independent_passed,
                       transfer_passed=excluded.transfer_passed,
                       hint_count=excluded.hint_count,
                       active_seconds=excluded.active_seconds,
                       prediction_encrypted=excluded.prediction_encrypted,
                       reflection_encrypted=excluded.reflection_encrypted,
                       updated_at=excluded.updated_at""",
                (
                    str(session.user_id), str(session.exercise_id),
                    session.unit_id or None, session.objective_id or None,
                    session.phase.value, session.mode,
                    int(session.theory_viewed), int(session.independent_passed),
                    int(session.transfer_passed), session.hint_count,
                    session.active_seconds, encrypt("prediction", session.prediction),
                    encrypt("reflection", session.reflection),
                    session.started_at.isoformat(), session.updated_at.isoformat(),
                ),
            )
        return self.learning_session(session.user_id, session.exercise_id)

    def learning_session_summary(self, user_id: UUID) -> dict[str, int]:
        with self._database.read_connection() as connection:
            row = connection.execute(
                """SELECT count(*) sessions,
                          sum(phase!='completed') in_progress,
                          sum(independent_passed) independent_passes,
                          sum(transfer_passed) transfer_passes,
                          sum(length(prediction_encrypted)>0) predictions,
                          sum(length(reflection_encrypted)>0) reflections
                   FROM learning_sessions WHERE user_id=?""",
                (str(user_id),),
            ).fetchone()
            passed = int(connection.execute(
                """SELECT count(DISTINCT exercise_id) FROM attempts
                   WHERE user_id=? AND status='passed'""",
                (str(user_id),),
            ).fetchone()[0])
        independent = int(row["independent_passes"] or 0)
        return {
            "sessions": int(row["sessions"] or 0),
            "in_progress": int(row["in_progress"] or 0),
            "independent_passes": independent,
            "assisted_passes": max(0, passed - independent),
            "transfer_passes": int(row["transfer_passes"] or 0),
            "predictions": int(row["predictions"] or 0),
            "reflections": int(row["reflections"] or 0),
        }

    @staticmethod
    def _reference_solution_aad(field: str, exercise_id: UUID) -> bytes:
        return f"exercise_reference_solutions.{field}:{exercise_id}".encode()

    def reference_solution(self, exercise_id: UUID) -> dict[str, str] | None:
        with self._database.read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM exercise_reference_solutions WHERE exercise_id=?",
                (str(exercise_id),),
            ).fetchone()
        if row is None:
            return None
        return {
            "solution": self._cipher.decrypt(
                row["solution_encrypted"],
                associated_data=self._reference_solution_aad("solution", exercise_id),
            ).decode("utf-8"),
            "explanation": self._cipher.decrypt(
                row["explanation_encrypted"],
                associated_data=self._reference_solution_aad("explanation", exercise_id),
            ).decode("utf-8"),
            "validation_hash": str(row["validation_hash"]),
            "validator_version": str(row["validator_version"]),
            "validated_at": str(row["validated_at"]),
        }

    def save_reference_solution(
        self, exercise_id: UUID, *, solution: str, explanation: str,
        validation_hash: str, validator_version: str,
    ) -> dict[str, str]:
        now = datetime.now(UTC).isoformat()
        encrypted_solution = self._cipher.encrypt(
            solution.encode("utf-8"),
            associated_data=self._reference_solution_aad("solution", exercise_id),
        )
        encrypted_explanation = self._cipher.encrypt(
            explanation.encode("utf-8"),
            associated_data=self._reference_solution_aad("explanation", exercise_id),
        )
        with self._database.transaction() as connection:
            connection.execute(
                """INSERT INTO exercise_reference_solutions(
                       exercise_id,solution_encrypted,explanation_encrypted,
                       validation_hash,validator_version,validated_at)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(exercise_id) DO UPDATE SET
                       solution_encrypted=excluded.solution_encrypted,
                       explanation_encrypted=excluded.explanation_encrypted,
                       validation_hash=excluded.validation_hash,
                       validator_version=excluded.validator_version,
                       validated_at=excluded.validated_at""",
                (
                    str(exercise_id), encrypted_solution, encrypted_explanation,
                    validation_hash, validator_version, now,
                ),
            )
        return self.reference_solution(exercise_id) or {}

    def seed_milestones(self) -> None:
        with self._database.transaction() as connection:
            for position, (theme, rank_from, rank_to, required) in enumerate(_MILESTONES):
                identity = f"python:{theme.value}:{rank_to.value}"
                milestone_id = str(uuid5(NAMESPACE_URL, f"aprendix:milestone:{identity}"))
                connection.execute(
                    """INSERT OR IGNORE INTO milestone_definitions(
                        id, technology, theme, rank_from, rank_to,
                        required_distinct_passes, position
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (milestone_id, Technology.PYTHON.value, theme.value,
                     rank_from.value, rank_to.value, required, position),
                )

    def milestone_progress(self, user_id: UUID) -> tuple[MilestoneProgressDTO, ...]:
        with self._database.read_connection() as connection:
            rows = connection.execute(
                """SELECT md.*, um.completed_exercises_json, um.completed_at
                   FROM milestone_definitions md
                   LEFT JOIN user_milestones um
                     ON um.milestone_id = md.id AND um.user_id = ?
                   ORDER BY md.position, md.id""",
                (str(user_id),),
            ).fetchall()
        return tuple(self._progress_from_row(row) for row in rows)

    def practice_access(
        self, user_id: UUID, exercise_id: UUID,
    ) -> LearningAccessDTO:
        """Return independent visibility and credit state for an exercise."""

        with self._database.read_connection() as connection:
            return practice_access(connection, user_id, exercise_id)

    def record_distinct_pass(
        self, user_id: UUID, exercise_id: UUID, *, theme: LearningTheme
    ) -> MilestoneProgressDTO | None:
        now = datetime.now(UTC).isoformat()
        with self._database.transaction() as connection:
            row = connection.execute(
                """SELECT * FROM milestone_definitions
                   WHERE technology = ? AND theme = ?
                   ORDER BY position LIMIT 1""",
                (Technology.PYTHON.value, theme.value),
            ).fetchone()
            if row is None:
                row = connection.execute(
                    """SELECT * FROM milestone_definitions
                       WHERE technology = ? AND theme = ? ORDER BY position LIMIT 1""",
                    (Technology.PYTHON.value, LearningTheme.FUNDAMENTALS.value),
                ).fetchone()
            if row is None:
                return None
            state = connection.execute(
                "SELECT completed_exercises_json FROM user_milestones WHERE user_id=? AND milestone_id=?",
                (str(user_id), row["id"]),
            ).fetchone()
            completed = set(json.loads(state["completed_exercises_json"])) if state else set()
            completed.add(str(exercise_id))
            completed_at = now if len(completed) >= row["required_distinct_passes"] else None
            connection.execute(
                """INSERT INTO user_milestones(
                    user_id, milestone_id, completed_exercises_json, completed_at, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, milestone_id) DO UPDATE SET
                    completed_exercises_json=excluded.completed_exercises_json,
                    completed_at=COALESCE(user_milestones.completed_at, excluded.completed_at),
                    updated_at=excluded.updated_at""",
                (str(user_id), row["id"], json.dumps(sorted(completed)), completed_at, now),
            )
            if completed_at:
                evidence = json.dumps(
                    {"milestone_id": row["id"], "completed": len(completed),
                     "required": int(row["required_distinct_passes"])},
                    sort_keys=True,
                )
                title = f"{row['theme']} · {row['rank_to']}"
                connection.execute(
                    "INSERT OR IGNORE INTO local_achievements VALUES(?,?,?,?,?,?)",
                    (str(user_id), f"badge:{row['id']}", "badge", title,
                     evidence, now),
                )
                connection.execute(
                    "INSERT OR IGNORE INTO local_achievements VALUES(?,?,?,?,?,?)",
                    (str(user_id), f"certificate:{row['id']}", "certificate",
                     f"Certificado local · {title}", evidence, now),
                )
        progress = dict(row)
        progress["completed_exercises_json"] = json.dumps(sorted(completed))
        progress["completed_at"] = completed_at
        return self._progress_from_row(progress)

    def record_learning_activity(self, user_id: UUID, *, passed: bool) -> None:
        """Update XP, streak, onboarding calibration and local badges atomically."""

        now = datetime.now(UTC)
        now_text, today = now.isoformat(), now.date()
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO study_days(user_id,study_date) VALUES(?,?)",
                (str(user_id), today.isoformat()),
            )
            days = [
                date.fromisoformat(item[0])
                for item in connection.execute(
                    "SELECT study_date FROM study_days WHERE user_id=? ORDER BY study_date DESC",
                    (str(user_id),),
                )
            ]
            streak, expected = 0, today
            for study_day in days:
                if study_day != expected:
                    break
                streak += 1
                expected -= timedelta(days=1)
            preferences = self._cipher.encrypt(
                b"{}", associated_data=f"profiles.preferences:{user_id}".encode()
            )
            connection.execute(
                """INSERT INTO profiles(
                       user_id,theta,xp,streak_days,preferences_encrypted,created_at,updated_at
                   ) VALUES(?,0,?,?,?, ?,?)
                   ON CONFLICT(user_id) DO UPDATE SET
                       xp=profiles.xp+excluded.xp,
                       streak_days=excluded.streak_days,
                       updated_at=excluded.updated_at""",
                (str(user_id), 10 if passed else 2, streak, preferences,
                 now_text, now_text),
            )
            count, average = connection.execute(
                """SELECT count(DISTINCT exercise_id),COALESCE(avg(score),0)
                   FROM attempts WHERE user_id=? AND status IN ('passed','failed','error')""",
                (str(user_id),),
            ).fetchone()
            completed = int(count) >= 3
            level = (
                "unassessed" if not completed else
                "initiate" if float(average) < 0.5 else
                "adept" if float(average) < 0.8 else "proficient"
            )
            connection.execute(
                """INSERT INTO onboarding_state VALUES(?,?,?,?,?,?)
                   ON CONFLICT(user_id) DO UPDATE SET
                     status=excluded.status,assessed_level=excluded.assessed_level,
                     attempt_count=excluded.attempt_count,
                     completed_at=COALESCE(onboarding_state.completed_at,excluded.completed_at),
                     updated_at=excluded.updated_at""",
                (str(user_id), "completed" if completed else "pending", level,
                 int(count), now_text if completed else None, now_text),
            )
            if passed:
                connection.execute(
                    "INSERT OR IGNORE INTO local_achievements VALUES(?,?,?,?,?,?)",
                    (str(user_id), "badge:first-pass", "badge", "Primeiro desafio",
                     json.dumps({"passed_exercises": 1}), now_text),
                )
            if streak >= 3:
                connection.execute(
                    "INSERT OR IGNORE INTO local_achievements VALUES(?,?,?,?,?,?)",
                    (str(user_id), "badge:streak-3", "badge", "Ritmo de 3 dias",
                     json.dumps({"streak_days": streak}), now_text),
                )

    def record_practice_attempt_credit(
        self, user_id: UUID, exercise_id: UUID, attempt_id: UUID, *,
        passed: bool, theme: LearningTheme,
    ) -> tuple[LearningAccessDTO, bool, MilestoneProgressDTO | None]:
        """Validate prerequisites and award every practice benefit atomically.

        The attempt itself is intentionally stored before this operation. If a
        unit is not eligible, that attempt remains useful exploration evidence,
        while progress, XP, achievements and milestones remain unchanged.
        """

        now = datetime.now(UTC)
        now_text, today = now.isoformat(), now.date()
        with self._database.transaction() as connection:
            access = practice_access(connection, user_id, exercise_id)
            if not access.credit_eligible:
                return access, False, None

            credit_awarded = False
            if passed and access.resource_kind == "practice":
                cursor = connection.execute(
                    """INSERT OR IGNORE INTO learning_unit_progress(
                           user_id,unit_id,completed_at) VALUES(?,?,?)""",
                    (str(user_id), access.resource_id, now_text),
                )
                credit_awarded = cursor.rowcount == 1
            elif passed:
                previous_passes = int(connection.execute(
                    """SELECT count(*) FROM attempts
                       WHERE user_id=? AND exercise_id=? AND status='passed' AND id<>?""",
                    (str(user_id), str(exercise_id), str(attempt_id)),
                ).fetchone()[0])
                credit_awarded = previous_passes == 0

            # Eligible failures preserve the existing small participation reward.
            # A repeated pass never earns progress or gamification twice.
            if not passed or credit_awarded:
                connection.execute(
                    "INSERT OR IGNORE INTO study_days(user_id,study_date) VALUES(?,?)",
                    (str(user_id), today.isoformat()),
                )
                days = [
                    date.fromisoformat(item[0])
                    for item in connection.execute(
                        """SELECT study_date FROM study_days
                           WHERE user_id=? ORDER BY study_date DESC""",
                        (str(user_id),),
                    )
                ]
                streak, expected = 0, today
                for study_day in days:
                    if study_day != expected:
                        break
                    streak += 1
                    expected -= timedelta(days=1)
                preferences = self._cipher.encrypt(
                    b"{}", associated_data=f"profiles.preferences:{user_id}".encode()
                )
                connection.execute(
                    """INSERT INTO profiles(
                           user_id,theta,xp,streak_days,preferences_encrypted,
                           created_at,updated_at)
                       VALUES(?,0,?,?,?,?,?)
                       ON CONFLICT(user_id) DO UPDATE SET
                           xp=profiles.xp+excluded.xp,
                           streak_days=excluded.streak_days,
                           updated_at=excluded.updated_at""",
                    (str(user_id), 10 if passed else 2, streak, preferences,
                     now_text, now_text),
                )
                count, average = connection.execute(
                    """SELECT count(DISTINCT a.exercise_id),COALESCE(avg(a.score),0)
                       FROM attempts a
                       WHERE a.user_id=? AND a.status IN ('passed','failed','error')
                         AND (NOT EXISTS(
                               SELECT 1 FROM learning_units mapped
                               WHERE mapped.exercise_id=a.exercise_id
                                 AND mapped.kind='practice'
                             ) OR EXISTS(
                               SELECT 1 FROM learning_units mapped
                               JOIN learning_unit_progress credited
                                 ON credited.unit_id=mapped.id
                                AND credited.user_id=a.user_id
                               WHERE mapped.exercise_id=a.exercise_id
                                 AND mapped.kind='practice'
                             ))""",
                    (str(user_id),),
                ).fetchone()
                onboarding_completed = int(count) >= 3
                level = (
                    "unassessed" if not onboarding_completed else
                    "initiate" if float(average) < 0.5 else
                    "adept" if float(average) < 0.8 else "proficient"
                )
                connection.execute(
                    """INSERT INTO onboarding_state VALUES(?,?,?,?,?,?)
                       ON CONFLICT(user_id) DO UPDATE SET
                         status=excluded.status,
                         assessed_level=excluded.assessed_level,
                         attempt_count=excluded.attempt_count,
                         completed_at=COALESCE(
                           onboarding_state.completed_at,excluded.completed_at),
                         updated_at=excluded.updated_at""",
                    (str(user_id),
                     "completed" if onboarding_completed else "pending",
                     level, int(count),
                     now_text if onboarding_completed else None, now_text),
                )
                if passed:
                    connection.execute(
                        "INSERT OR IGNORE INTO local_achievements VALUES(?,?,?,?,?,?)",
                        (str(user_id), "badge:first-pass", "badge",
                         "Primeiro desafio", json.dumps({"passed_exercises": 1}),
                         now_text),
                    )
                if streak >= 3:
                    connection.execute(
                        "INSERT OR IGNORE INTO local_achievements VALUES(?,?,?,?,?,?)",
                        (str(user_id), "badge:streak-3", "badge",
                         "Ritmo de 3 dias", json.dumps({"streak_days": streak}),
                         now_text),
                    )

            milestone = None
            if passed and credit_awarded:
                definition = connection.execute(
                    """SELECT * FROM milestone_definitions
                       WHERE technology=? AND theme=? ORDER BY position LIMIT 1""",
                    (Technology.PYTHON.value, theme.value),
                ).fetchone()
                if definition is None:
                    definition = connection.execute(
                        """SELECT * FROM milestone_definitions
                           WHERE technology=? AND theme=?
                           ORDER BY position LIMIT 1""",
                        (Technology.PYTHON.value, LearningTheme.FUNDAMENTALS.value),
                    ).fetchone()
                if definition is not None:
                    state = connection.execute(
                        """SELECT completed_exercises_json FROM user_milestones
                           WHERE user_id=? AND milestone_id=?""",
                        (str(user_id), definition["id"]),
                    ).fetchone()
                    completed_exercises = (
                        set(json.loads(state["completed_exercises_json"]))
                        if state else set()
                    )
                    completed_exercises.add(str(exercise_id))
                    achieved_at = (
                        now_text if len(completed_exercises) >=
                        definition["required_distinct_passes"] else None
                    )
                    connection.execute(
                        """INSERT INTO user_milestones(
                               user_id,milestone_id,completed_exercises_json,
                               completed_at,updated_at)
                           VALUES(?,?,?,?,?)
                           ON CONFLICT(user_id,milestone_id) DO UPDATE SET
                             completed_exercises_json=excluded.completed_exercises_json,
                             completed_at=COALESCE(
                               user_milestones.completed_at,excluded.completed_at),
                             updated_at=excluded.updated_at""",
                        (str(user_id), definition["id"],
                         json.dumps(sorted(completed_exercises)), achieved_at,
                         now_text),
                    )
                    if achieved_at:
                        evidence = json.dumps({
                            "milestone_id": definition["id"],
                            "completed": len(completed_exercises),
                            "required": int(definition["required_distinct_passes"]),
                        }, sort_keys=True)
                        title = f"{definition['theme']} - {definition['rank_to']}"
                        connection.execute(
                            """INSERT OR IGNORE INTO local_achievements
                               VALUES(?,?,?,?,?,?)""",
                            (str(user_id), f"badge:{definition['id']}", "badge",
                             title, evidence, now_text),
                        )
                        connection.execute(
                            """INSERT OR IGNORE INTO local_achievements
                               VALUES(?,?,?,?,?,?)""",
                            (str(user_id), f"certificate:{definition['id']}",
                             "certificate", f"Certificado local - {title}",
                             evidence, now_text),
                        )
                    progress = dict(definition)
                    progress["completed_exercises_json"] = json.dumps(
                        sorted(completed_exercises)
                    )
                    progress["completed_at"] = achieved_at
                    milestone = self._progress_from_row(progress)

            if access.resource_kind == "practice":
                access = unit_access(connection, user_id, access.resource_id)
            return access, credit_awarded, milestone

    def gamification(self, user_id: UUID) -> dict[str, object]:
        with self._database.read_connection() as connection:
            profile = connection.execute(
                "SELECT xp,streak_days FROM profiles WHERE user_id=?", (str(user_id),)
            ).fetchone()
            onboarding = connection.execute(
                "SELECT status,assessed_level,attempt_count FROM onboarding_state WHERE user_id=?",
                (str(user_id),),
            ).fetchone()
            achievements = connection.execute(
                """SELECT code,kind,title,earned_at FROM local_achievements
                   WHERE user_id=? ORDER BY earned_at DESC,code""",
                (str(user_id),),
            ).fetchall()
        return {
            "xp": int(profile["xp"]) if profile else 0,
            "streak_days": int(profile["streak_days"]) if profile else 0,
            "onboarding": dict(onboarding) if onboarding else {
                "status": "pending", "assessed_level": "unassessed", "attempt_count": 0,
            },
            "achievements": tuple(dict(item) for item in achievements),
        }

    def record_card_review(
        self, user_id: UUID, card_id: UUID, *, known: bool | None = None,
        feedback: str | None = None,
    ) -> None:
        feedback = feedback or ("already_knew" if known else "review")
        if feedback not in {"already_knew", "useful", "confusing", "review"}:
            raise ValueError("Feedback de card desconhecido.")
        now = datetime.now(UTC)
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT mastery,successful_reviews FROM card_review_state WHERE user_id=? AND card_id=?",
                (str(user_id), str(card_id)),
            ).fetchone()
            mastery = float(row["mastery"]) if row else 0.0
            mastery_before = mastery
            reviews = int(row["successful_reviews"]) if row else 0
            if feedback == "already_knew":
                mastery, reviews = min(1.0, mastery + 0.16), reviews + 1
                due = now + timedelta(days=min(30, 2 ** min(reviews - 1, 4)))
            elif feedback == "useful":
                mastery, reviews = min(1.0, mastery + 0.08), reviews + 1
                due = now + timedelta(days=1)
            elif feedback == "confusing":
                mastery, reviews = max(0.0, mastery - 0.15), 0
                due = now + timedelta(hours=2)
            else:
                mastery, reviews = max(0.0, mastery - 0.12), 0
                due = now + timedelta(hours=4)
            connection.execute(
                """INSERT INTO card_review_state VALUES(?,?,?,?,?,?)
                   ON CONFLICT(user_id,card_id) DO UPDATE SET
                     mastery=excluded.mastery,successful_reviews=excluded.successful_reviews,
                     next_review_at=excluded.next_review_at,updated_at=excluded.updated_at""",
                (str(user_id), str(card_id), mastery, reviews,
                 due.isoformat(), now.isoformat()),
            )
            connection.execute(
                "INSERT INTO card_feedback_events VALUES(?,?,?,?,?,?,?)",
                (str(uuid4()), str(user_id), str(card_id), feedback,
                 mastery_before, mastery, now.isoformat()),
            )

    def daily_card_ids(self, user_id: UUID, *, limit: int = 30) -> tuple[UUID, ...]:
        now = datetime.now(UTC).isoformat()
        with self._database.read_connection() as connection:
            rows = connection.execute(
                """SELECT tc.id,
                          CASE WHEN rv.card_id IS NULL THEN 1 ELSE 0 END unseen,
                          COALESCE(rv.next_review_at, '') due,
                          COALESCE(rv.mastery, 0.0) mastery
                   FROM theory_cards tc
                   JOIN document_chunks dc ON dc.id=tc.chunk_id
                   JOIN documents d ON d.id=dc.document_id
                   JOIN card_presentation cp ON cp.card_id=tc.id
                   JOIN pedagogical_quality pq
                     ON pq.item_type='card' AND pq.item_id=tc.id
                    AND pq.status='accepted'
                   JOIN content_catalog_items ci
                     ON ci.item_type='card' AND ci.item_id=tc.id
                    AND ci.content_type='editorial' AND ci.status='active'
                   JOIN content_catalog_releases cr
                     ON cr.id=ci.release_id AND cr.status='active'
                   LEFT JOIN chunk_quality q ON q.chunk_id=dc.id
                   LEFT JOIN card_review_state rv ON rv.card_id=tc.id AND rv.user_id=?
                   WHERE d.lifecycle='active'
                     AND d.source_path='aprendix://authored-facts/v1'
                     AND COALESCE(q.status,'accepted')='accepted'
                     AND EXISTS(
                         SELECT 1 FROM card_source_links csl WHERE csl.card_id=tc.id
                     )
                     AND (rv.card_id IS NULL OR rv.next_review_at <= ?)
                   ORDER BY unseen ASC, due ASC, mastery ASC, tc.created_at DESC
                   LIMIT ?""",
                (str(user_id), now, max(1, min(limit, 100))),
            ).fetchall()
        return tuple(UUID(row["id"]) for row in rows)

    @staticmethod
    def _progress_from_row(row) -> MilestoneProgressDTO:
        completed = len(json.loads(row["completed_exercises_json"] or "[]"))
        required = int(row["required_distinct_passes"])
        return MilestoneProgressDTO(
            id=row["id"], technology=Technology(row["technology"]),
            theme=LearningTheme(row["theme"]), rank_from=LearnerRank(row["rank_from"]),
            rank_to=LearnerRank(row["rank_to"]), completed=completed,
            required=required, achieved=completed >= required,
        )

    def save_project(self, project: ProjectDTO) -> ProjectDTO:
        name = self._cipher.encrypt(
            project.name.encode(), associated_data=f"local_projects.name:{project.id}".encode()
        )
        content = self._cipher.encrypt(
            project.source_code.encode(),
            associated_data=self._project_file_aad(project.id, project.relative_path),
        )
        file_id = uuid5(NAMESPACE_URL, f"aprendix:project-file:{project.id}:{project.relative_path}")
        with self._database.transaction() as connection:
            connection.execute(
                """INSERT INTO local_projects(id,user_id,name_encrypted,technology,created_at,updated_at)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET name_encrypted=excluded.name_encrypted,
                       technology=excluded.technology, updated_at=excluded.updated_at""",
                (str(project.id), str(project.user_id), name, project.technology.value,
                 project.created_at.isoformat(), project.updated_at.isoformat()),
            )
            connection.execute(
                """INSERT INTO project_files(id,project_id,relative_path,content_encrypted,updated_at)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(project_id,relative_path) DO UPDATE SET
                       content_encrypted=excluded.content_encrypted, updated_at=excluded.updated_at""",
                (str(file_id), str(project.id), project.relative_path, content, project.updated_at.isoformat()),
            )
            version = int(connection.execute(
                "SELECT COALESCE(max(version),0)+1 FROM project_file_versions WHERE file_id=?",
                (str(file_id),),
            ).fetchone()[0])
            version_id = uuid5(
                NAMESPACE_URL, f"aprendix:project-version:{file_id}:{version}"
            )
            version_content = self._cipher.encrypt(
                project.source_code.encode(),
                associated_data=f"project_file_versions.content:{version_id}".encode(),
            )
            connection.execute(
                "INSERT INTO project_file_versions VALUES(?,?,?,?,?,?,?)",
                (str(version_id), str(project.id), str(file_id), version,
                 version_content, "manual-save", project.updated_at.isoformat()),
            )
        return project

    def project_versions(self, project_id: UUID, relative_path: str = "main.py") -> tuple[dict[str, object], ...]:
        with self._database.read_connection() as connection:
            rows = connection.execute(
                """SELECT v.* FROM project_file_versions v
                   JOIN project_files f ON f.id=v.file_id
                   WHERE v.project_id=? AND f.relative_path=? ORDER BY v.version DESC""",
                (str(project_id), relative_path),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["source_code"] = self._cipher.decrypt(
                item.pop("content_encrypted"),
                associated_data=f"project_file_versions.content:{row['id']}".encode(),
            ).decode()
            result.append(item)
        return tuple(result)

    def save_debug_recovery(
        self, user_id: UUID, exercise_id: UUID, source: str, *, cursor_index: int,
        breakpoints: tuple[dict[str, object], ...] = (), watches: tuple[str, ...] = (),
    ) -> None:
        identity = f"{user_id}:{exercise_id}"
        def encrypt(field: str, value: object) -> bytes:
            payload = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            return self._cipher.encrypt(
                payload.encode(), associated_data=f"editor_recovery_state.{field}:{identity}".encode()
            )
        with self._database.transaction() as connection:
            connection.execute(
                """INSERT INTO editor_recovery_state VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(user_id,exercise_id) DO UPDATE SET
                   source_encrypted=excluded.source_encrypted,cursor_index=excluded.cursor_index,
                   breakpoints_encrypted=excluded.breakpoints_encrypted,
                   watches_encrypted=excluded.watches_encrypted,updated_at=excluded.updated_at""",
                (str(user_id), str(exercise_id), encrypt("source", source), max(0, cursor_index),
                 encrypt("breakpoints", breakpoints), encrypt("watches", watches),
                 datetime.now(UTC).isoformat()),
            )

    def load_debug_recovery(self, user_id: UUID, exercise_id: UUID) -> dict[str, object] | None:
        with self._database.read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM editor_recovery_state WHERE user_id=? AND exercise_id=?",
                (str(user_id), str(exercise_id)),
            ).fetchone()
        if row is None:
            return None
        identity = f"{user_id}:{exercise_id}"
        def decrypt(field: str) -> str:
            return self._cipher.decrypt(
                row[f"{field}_encrypted"],
                associated_data=f"editor_recovery_state.{field}:{identity}".encode(),
            ).decode()
        return {
            "source": decrypt("source"), "cursor_index": row["cursor_index"],
            "breakpoints": tuple(json.loads(decrypt("breakpoints"))),
            "watches": tuple(json.loads(decrypt("watches"))),
            "updated_at": row["updated_at"],
        }

    def record_debug_session(self, user_id: UUID, exercise_id: UUID | None, request, result) -> str:
        identity, now = uuid4(), datetime.now(UTC).isoformat()
        def encrypt(field: str, value: object) -> bytes:
            return self._cipher.encrypt(
                json.dumps(value, ensure_ascii=False).encode(),
                associated_data=f"debug_sessions.{field}:{identity}".encode(),
            )
        with self._database.transaction() as connection:
            connection.execute(
                """INSERT INTO debug_sessions VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (str(identity), str(user_id), str(exercise_id) if exercise_id else None,
                 result.status, encrypt("breakpoints", [item.model_dump(mode="json") for item in request.breakpoints]),
                 encrypt("watches", request.watches), max(0, len(result.frames) - 1),
                 result.coverage_percent, result.duration_ms, now),
            )
        return str(identity)

    def record_test_run(
        self, user_id: UUID, exercise_id: UUID | None, *, public_passed: int,
        public_total: int, hidden_passed: int, hidden_total: int,
        coverage_percent: float, result: dict[str, object],
    ) -> str:
        identity, now = uuid4(), datetime.now(UTC).isoformat()
        encrypted = self._cipher.encrypt(
            json.dumps(result, ensure_ascii=False).encode(),
            associated_data=f"local_test_runs.result:{identity}".encode(),
        )
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO local_test_runs VALUES(?,?,?,?,?,?,?,?,?,?)",
                (str(identity), str(user_id), str(exercise_id) if exercise_id else None,
                 public_passed, public_total, hidden_passed, hidden_total,
                 min(100.0, max(0.0, coverage_percent)), encrypted, now),
            )
        return str(identity)

    def debug_history(self, user_id: UUID, *, limit: int = 30) -> tuple[dict[str, object], ...]:
        with self._database.read_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM debug_sessions WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                (str(user_id), max(1, min(limit, 200))),
            ).fetchall()
        result = []
        for row in rows:
            identity = row["id"]

            def decrypt(field: str):
                return json.loads(self._cipher.decrypt(
                    row[f"{field}_encrypted"],
                    associated_data=f"debug_sessions.{field}:{identity}".encode(),
                ).decode())

            result.append({
                "id": identity, "exercise_id": row["exercise_id"], "status": row["status"],
                "breakpoints": tuple(decrypt("breakpoints")), "watches": tuple(decrypt("watches")),
                "last_step": row["last_step"], "coverage_percent": row["coverage_percent"],
                "duration_ms": row["duration_ms"], "created_at": row["created_at"],
            })
        return tuple(result)

    def test_history(self, user_id: UUID, *, limit: int = 30) -> tuple[dict[str, object], ...]:
        with self._database.read_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM local_test_runs WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                (str(user_id), max(1, min(limit, 200))),
            ).fetchall()
        result = []
        for row in rows:
            payload = json.loads(self._cipher.decrypt(
                row["result_encrypted"],
                associated_data=f"local_test_runs.result:{row['id']}".encode(),
            ).decode())
            result.append({
                "id": row["id"], "exercise_id": row["exercise_id"],
                "public_passed": row["public_passed"], "public_total": row["public_total"],
                "hidden_passed": row["hidden_passed"], "hidden_total": row["hidden_total"],
                "coverage_percent": row["coverage_percent"], "result": payload,
                "created_at": row["created_at"],
            })
        return tuple(result)

    def list_projects(self, user_id: UUID) -> tuple[ProjectDTO, ...]:
        with self._database.read_connection() as connection:
            rows = connection.execute(
                """SELECT p.*, f.relative_path, f.content_encrypted
                   FROM local_projects p JOIN project_files f ON f.project_id=p.id
                   WHERE p.user_id=?
                   ORDER BY p.updated_at DESC,
                            CASE WHEN f.relative_path='main.py' THEN 0 ELSE 1 END,
                            f.relative_path""", (str(user_id),)
            ).fetchall()
        result, seen = [], set()
        for row in rows:
            project_id = UUID(row["id"])
            if project_id in seen:
                continue
            seen.add(project_id)
            result.append(ProjectDTO(
                id=project_id, user_id=user_id,
                name=self._cipher.decrypt(row["name_encrypted"], associated_data=f"local_projects.name:{project_id}".encode()).decode(),
                technology=Technology(row["technology"]), relative_path=row["relative_path"],
                source_code=self._decrypt_project_file(
                    project_id, row["relative_path"], row["content_encrypted"],
                ),
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            ))
        return tuple(result)

    def project_files(self, user_id: UUID, project_id: UUID) -> tuple[ProjectDTO, ...]:
        with self._database.read_connection() as connection:
            rows = connection.execute(
                """SELECT p.*, f.relative_path, f.content_encrypted, f.updated_at file_updated_at
                   FROM local_projects p JOIN project_files f ON f.project_id=p.id
                   WHERE p.user_id=? AND p.id=?
                   ORDER BY CASE WHEN f.relative_path='main.py' THEN 0 ELSE 1 END,
                            f.relative_path""",
                (str(user_id), str(project_id)),
            ).fetchall()
        result = []
        for row in rows:
            identity = UUID(row["id"])
            result.append(ProjectDTO(
                id=identity,
                user_id=user_id,
                name=self._cipher.decrypt(
                    row["name_encrypted"],
                    associated_data=f"local_projects.name:{identity}".encode(),
                ).decode(),
                technology=Technology(row["technology"]),
                relative_path=row["relative_path"],
                source_code=self._decrypt_project_file(
                    identity, row["relative_path"], row["content_encrypted"],
                ),
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["file_updated_at"]),
            ))
        return tuple(result)

    def record_focus(self, user_id: UUID, *, minutes: int, elapsed_seconds: int, status: str) -> None:
        now = datetime.now(UTC).isoformat()
        with self._database.transaction() as connection:
            connection.execute(
                """INSERT INTO focus_sessions(id,user_id,minutes,elapsed_seconds,status,started_at,ended_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (str(uuid4()), str(user_id), minutes, elapsed_seconds, status, now,
                 now if status in {"completed", "cancelled"} else None),
            )

    def save_study_plan(self, user_id: UUID, *, start_date: date,
                        weekly_hours: float, assessment_percent: int) -> dict[str, object]:
        if not .5 <= weekly_hours <= 168:
            raise ValueError("As horas semanais devem estar entre 0,5 e 168.")
        if not 0 <= assessment_percent <= 100:
            raise ValueError("A percentagem de avaliação deve estar entre 0 e 100.")
        now = datetime.now(UTC).isoformat()
        with self._database.transaction() as connection:
            connection.execute(
                """INSERT INTO study_plans(user_id,start_date,weekly_hours,assessment_percent,updated_at)
                   VALUES(?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET
                   start_date=excluded.start_date,weekly_hours=excluded.weekly_hours,
                   assessment_percent=excluded.assessment_percent,updated_at=excluded.updated_at""",
                (str(user_id), start_date.isoformat(), weekly_hours, assessment_percent, now),
            )
        return {"start_date": start_date.isoformat(), "weekly_hours": weekly_hours,
                "assessment_percent": assessment_percent, "updated_at": now}

    def study_plan(self, user_id: UUID) -> dict[str, object]:
        with self._database.read_connection() as connection:
            row = connection.execute("SELECT * FROM study_plans WHERE user_id=?", (str(user_id),)).fetchone()
        return dict(row) if row else {
            "start_date": date.today().isoformat(), "weekly_hours": 7.0,
            "assessment_percent": 20, "updated_at": "",
        }

    def save_generated_exercise(self, user_id: UUID, base_exercise_id: UUID, generated) -> int:
        now = datetime.now(UTC).isoformat()
        with self._database.transaction() as connection:
            variation = int(connection.execute(
                "SELECT COALESCE(max(variation),0)+1 FROM generated_exercises WHERE user_id=? AND base_exercise_id=?",
                (str(user_id), str(base_exercise_id)),
            ).fetchone()[0])
            identity = uuid5(
                NAMESPACE_URL,
                f"aprendix:generated:{user_id}:{base_exercise_id}:{variation}",
            )
            payload = self._cipher.encrypt(
                generated.model_dump_json().encode("utf-8"),
                associated_data=f"generated_exercises.payload:{identity}".encode(),
            )
            connection.execute(
                "INSERT INTO generated_exercises VALUES(?,?,?,?,?,?)",
                (str(identity), str(user_id), str(base_exercise_id), variation, payload, now),
            )
        return variation

    def record_editor_evidence(
        self, *, user_id: UUID, exercise_id: UUID, attempt_id: UUID,
        typed: int, pasted: int, deleted: int, justification: str,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        total = max(1, typed + pasted)
        paste_ratio = min(1.0, max(0.0, pasted / total))
        with self._database.transaction() as connection:
            connection.execute(
                """INSERT INTO editor_sessions(
                    id,user_id,exercise_id,typed_characters,pasted_characters,
                    deleted_characters,started_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?)""",
                (str(uuid4()), str(user_id), str(exercise_id), max(0, typed),
                 max(0, pasted), max(0, deleted), now, now),
            )
            if pasted or justification.strip():
                encrypted = self._cipher.encrypt(
                    justification.strip().encode("utf-8"),
                    associated_data=f"attempt_justifications.justification:{attempt_id}".encode(),
                )
                connection.execute(
                    "INSERT OR REPLACE INTO attempt_justifications VALUES(?,?,?,?)",
                    (str(attempt_id), encrypted, paste_ratio, now),
                )

    def complete_practice_unit(
        self, user_id: UUID, exercise_id: UUID,
    ) -> LearningAccessDTO:
        """Reject detached completion so an old pass is never promoted later."""

        del user_id, exercise_id
        raise RuntimeError(
            "practice credit requires a new passed attempt through the atomic evaluator"
        )
