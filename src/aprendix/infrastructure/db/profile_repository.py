"""Portable desktop profile snapshots with deterministic conflict resolution."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import NAMESPACE_URL, UUID, uuid5

from aprendix.application.contracts import AttemptDTO
from aprendix.application.profile_transfer import merge_by_identity, validate_snapshot
from aprendix.domain import AttemptStatus
from aprendix.infrastructure.db.database import Database
from aprendix.infrastructure.db.repositories import AttemptRepository

UTC = timezone.utc


class DesktopProfileRepository:
    def __init__(self, database: Database, attempts: AttemptRepository, desktop=None) -> None:
        self._database, self._attempts, self._desktop = database, attempts, desktop

    def export_snapshot(self, user_id: UUID) -> dict[str, object]:
        attempts = []
        for item in self._attempts.list_for_user(user_id, limit=100_000):
            with self._database.read_connection() as connection:
                row = connection.execute(
                    "SELECT slug FROM exercises WHERE id=?", (str(item.exercise_id),)
                ).fetchone()
            attempts.append({
                "id": str(item.id), "exercise_id": row["slug"] if row else str(item.exercise_id),
                "source": item.source_code, "status": item.status.value,
                "score": float(item.score or 0.0), "output": item.output or "",
                "duration_ms": item.duration_ms or 0,
                "updated_at": (item.submitted_at or item.created_at).astimezone(UTC).isoformat(),
            })
        with self._database.read_connection() as connection:
            reviews = []
            for row in connection.execute(
                """SELECT r.card_id,r.mastery,r.successful_reviews,r.next_review_at,r.updated_at,
                          c.section,d.source_path
                   FROM card_review_state r JOIN theory_cards t ON t.id=r.card_id
                   JOIN document_chunks c ON c.id=t.chunk_id JOIN documents d ON d.id=c.document_id
                   WHERE r.user_id=? ORDER BY r.card_id""", (str(user_id),),
            ):
                portable_id = (
                    "fact-" + row["section"]
                    if row["source_path"] == "aprendix://authored-facts/v1" else row["card_id"]
                )
                reviews.append({
                    "id": portable_id, "mastery": row["mastery"],
                    "interval_days": max(0, int(row["successful_reviews"])),
                    "next_review_at": row["next_review_at"], "updated_at": row["updated_at"],
                })
            units = [
                {"id": row["slug"], "status": "completed", "updated_at": row["completed_at"]}
                for row in connection.execute(
                    """SELECT c.slug,p.completed_at FROM learning_unit_progress p
                       JOIN learning_units u ON u.id=p.unit_id
                       JOIN learning_chapters c ON c.id=u.chapter_id
                       WHERE p.user_id=? AND u.kind='hybrid' ORDER BY c.slug""",
                    (str(user_id),),
                )
            ]
        projects = []
        if self._desktop is not None:
            for project in self._desktop.projects():
                for project_file in self._desktop.project_files(project.id):
                    projects.append({
                        "id": f"{project.id}:{project_file.relative_path}",
                        "project_id": str(project.id), "name": project.name,
                        "relative_path": project_file.relative_path,
                        "source": project_file.source_code,
                        "updated_at": project_file.updated_at.astimezone(UTC).isoformat(),
                    })
        return validate_snapshot({
            "platform": "desktop", "reviews": reviews, "attempts": attempts,
            "completed_units": units, "projects": projects,
        })

    def preview_snapshot(self, user_id: UUID, snapshot: dict[str, object]) -> dict[str, int]:
        incoming = validate_snapshot(snapshot)
        local = self.export_snapshot(user_id)
        _, review_conflicts = merge_by_identity(local["reviews"], incoming["reviews"])
        _, attempt_conflicts = merge_by_identity(local["attempts"], incoming["attempts"])
        _, unit_conflicts = merge_by_identity(local["completed_units"], incoming["completed_units"])
        _, project_conflicts = merge_by_identity(local["projects"], incoming["projects"])
        return {
            "incoming_reviews": len(incoming["reviews"]),
            "incoming_attempts": len(incoming["attempts"]),
            "incoming_completed_units": len(incoming["completed_units"]),
            "incoming_projects": len(incoming["projects"]),
            "conflicts": len(review_conflicts) + len(attempt_conflicts)
            + len(unit_conflicts) + len(project_conflicts),
        }

    def import_snapshot(self, user_id: UUID, snapshot: dict[str, object]) -> dict[str, int]:
        incoming = validate_snapshot(snapshot)
        local = self.export_snapshot(user_id)
        reviews, review_conflicts = merge_by_identity(local["reviews"], incoming["reviews"])
        attempts, attempt_conflicts = merge_by_identity(local["attempts"], incoming["attempts"])
        units, unit_conflicts = merge_by_identity(local["completed_units"], incoming["completed_units"])
        projects, project_conflicts = merge_by_identity(local["projects"], incoming["projects"])
        imported = {"reviews": 0, "attempts": 0, "completed_units": 0,
                    "projects": 0, "skipped": 0}
        now = datetime.now(UTC).isoformat()
        with self._database.transaction() as connection:
            for item in reviews:
                card_id = self._resolve_card(connection, str(item["id"]))
                if card_id is None:
                    imported["skipped"] += 1
                    continue
                mastery = min(1.0, max(0.0, float(item.get("mastery", 0.0))))
                successful = max(0, int(item.get("interval_days", 0)))
                connection.execute(
                    """INSERT INTO card_review_state VALUES(?,?,?,?,?,?)
                       ON CONFLICT(user_id,card_id) DO UPDATE SET mastery=excluded.mastery,
                       successful_reviews=excluded.successful_reviews,
                       next_review_at=excluded.next_review_at,updated_at=excluded.updated_at""",
                    (str(user_id), card_id, mastery, successful,
                     str(item.get("next_review_at") or now), str(item.get("updated_at") or now)),
                )
                imported["reviews"] += 1
            for item in attempts:
                exercise_id = self._resolve_exercise(connection, str(item["exercise_id"]))
                if exercise_id is None:
                    imported["skipped"] += 1
                    continue
                try:
                    identity = UUID(str(item["id"]))
                except ValueError:
                    identity = uuid5(NAMESPACE_URL, f"aprendix:portable-attempt:{item['id']}")
                submitted = self._timestamp(item.get("updated_at"))
                status = self._status(item.get("status"), item.get("score"))
                attempt = AttemptDTO(
                    id=identity, idempotency_key=identity, user_id=user_id,
                    exercise_id=UUID(exercise_id), status=status,
                    source_code=str(item.get("source", ""))[:100_000],
                    output=str(item.get("output", ""))[:100_000],
                    score=min(1.0, max(0.0, float(item.get("score", 0.0)))),
                    duration_ms=max(0, int(item.get("duration_ms", 0))),
                    submitted_at=submitted, created_at=submitted,
                )
                self._attempts.replace_for_profile(connection, attempt)
                imported["attempts"] += 1
            for item in units:
                rows = connection.execute(
                    """SELECT u.id FROM learning_units u JOIN learning_chapters c ON c.id=u.chapter_id
                       WHERE c.slug=? AND u.kind IN ('practice','theory','quiz','hybrid')
                       ORDER BY u.position""", (str(item["id"]),)
                ).fetchall()
                if not rows:
                    imported["skipped"] += 1
                    continue
                for row in rows:
                    connection.execute(
                        "INSERT OR REPLACE INTO learning_unit_progress VALUES(?,?,?)",
                        (str(user_id), row["id"], str(item.get("updated_at") or now)),
                    )
                imported["completed_units"] += 1
        if self._desktop is not None:
            for item in projects:
                portable_project_id = str(item.get("project_id") or item["id"])
                try:
                    project_id = UUID(portable_project_id)
                except ValueError:
                    project_id = uuid5(
                        NAMESPACE_URL, f"aprendix:portable-project:{portable_project_id}"
                    )
                self._desktop.save_project(
                    str(item.get("name") or "Projeto importado")[:160],
                    str(item.get("source") or "")[:100_000], project_id,
                    relative_path=str(item.get("relative_path") or "main.py"),
                )
                imported["projects"] += 1
        elif projects:
            imported["skipped"] += len(projects)
        imported["conflicts"] = len(review_conflicts) + len(attempt_conflicts) \
            + len(unit_conflicts) + len(project_conflicts)
        return imported

    @staticmethod
    def _resolve_card(connection, portable_id: str) -> str | None:
        candidate = portable_id
        if portable_id.startswith("fact-"):
            candidate = str(uuid5(NAMESPACE_URL, f"aprendix:fact-card:{portable_id[5:]}"))
        row = connection.execute("SELECT id FROM theory_cards WHERE id=?", (candidate,)).fetchone()
        return str(row["id"]) if row else None

    @staticmethod
    def _resolve_exercise(connection, portable_id: str) -> str | None:
        aliases = {
            "exercise-python-output": "hello-python",
            "exercise-python-decisions": "even-or-odd",
            "exercise-python-objects": "oop-account",
            "exercise-python-collections": "ds-unique",
        }
        row = connection.execute(
            "SELECT id FROM exercises WHERE id=? OR slug=? LIMIT 1",
            (portable_id, aliases.get(portable_id, portable_id)),
        ).fetchone()
        return str(row["id"]) if row else None

    @staticmethod
    def _timestamp(value: object) -> datetime:
        try:
            parsed = datetime.fromisoformat(str(value))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            return datetime.now(UTC)

    @staticmethod
    def _status(value: object, score: object) -> AttemptStatus:
        text = str(value)
        if text in {item.value for item in AttemptStatus}:
            status = AttemptStatus(text)
            if status in {AttemptStatus.DRAFT, AttemptStatus.SUBMITTED}:
                return AttemptStatus.PASSED if float(score or 0) >= 1 else AttemptStatus.FAILED
            return status
        return AttemptStatus.PASSED if text == "ok" and float(score or 0) >= 1 else AttemptStatus.ERROR
