"""Encrypted persistence for desktop projects, milestones, and editor sessions."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from aprendix.application.contracts import (
    LearnerRank, LearningTheme, MilestoneProgressDTO, ProjectDTO, Technology,
)
from aprendix.infrastructure.db.database import Database
from aprendix.infrastructure.security import AesGcmFieldCipher


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

    def record_card_review(self, user_id: UUID, card_id: UUID, *, known: bool) -> None:
        now = datetime.now(UTC)
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT mastery,successful_reviews FROM card_review_state WHERE user_id=? AND card_id=?",
                (str(user_id), str(card_id)),
            ).fetchone()
            mastery = float(row["mastery"]) if row else 0.0
            reviews = int(row["successful_reviews"]) if row else 0
            if known:
                mastery, reviews = min(1.0, mastery + 0.16), reviews + 1
                due = now + timedelta(days=min(30, 2 ** min(reviews - 1, 4)))
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
            project.source_code.encode(), associated_data=f"project_files.content:{project.id}:main".encode()
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
        return project

    def list_projects(self, user_id: UUID) -> tuple[ProjectDTO, ...]:
        with self._database.read_connection() as connection:
            rows = connection.execute(
                """SELECT p.*, f.relative_path, f.content_encrypted
                   FROM local_projects p JOIN project_files f ON f.project_id=p.id
                   WHERE p.user_id=? ORDER BY p.updated_at DESC""", (str(user_id),)
            ).fetchall()
        result = []
        for row in rows:
            project_id = UUID(row["id"])
            result.append(ProjectDTO(
                id=project_id, user_id=user_id,
                name=self._cipher.decrypt(row["name_encrypted"], associated_data=f"local_projects.name:{project_id}".encode()).decode(),
                technology=Technology(row["technology"]), relative_path=row["relative_path"],
                source_code=self._cipher.decrypt(row["content_encrypted"], associated_data=f"project_files.content:{project_id}:main".encode()).decode(),
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
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

    def complete_practice_unit(self, user_id: UUID, exercise_id: UUID) -> None:
        now = datetime.now(UTC).isoformat()
        with self._database.transaction() as connection:
            connection.execute("""
                INSERT OR IGNORE INTO learning_unit_progress(user_id,unit_id,completed_at)
                SELECT ?,id,? FROM learning_units
                WHERE exercise_id=? AND kind='practice'
            """, (str(user_id), now, str(exercise_id)))
