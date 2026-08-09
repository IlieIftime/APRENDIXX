"""Private mobile state: local, encrypted fields and durable review state."""

from __future__ import annotations

import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import re

UTC = timezone.utc


class MobileStateStore:
    def __init__(self, path: Path, cipher) -> None:
        self.path, self._cipher = path, cipher
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS review_state(
                    card_id TEXT PRIMARY KEY, mastery REAL NOT NULL DEFAULT 0,
                    interval_days INTEGER NOT NULL DEFAULT 0,
                    next_review_at TEXT, updated_at TEXT NOT NULL
                ) STRICT;
                CREATE TABLE IF NOT EXISTS card_actions(
                    id TEXT PRIMARY KEY, card_id TEXT NOT NULL, action TEXT NOT NULL,
                    occurred_at TEXT NOT NULL
                ) STRICT;
                CREATE TABLE IF NOT EXISTS mobile_attempts(
                    id TEXT PRIMARY KEY, exercise_id TEXT NOT NULL,
                    source_encrypted BLOB NOT NULL, status TEXT NOT NULL,
                    score REAL NOT NULL, output_encrypted BLOB NOT NULL,
                    created_at TEXT NOT NULL
                ) STRICT;
                CREATE TABLE IF NOT EXISTS mobile_settings(
                    name TEXT PRIMARY KEY, value TEXT NOT NULL
                ) STRICT;
                CREATE TABLE IF NOT EXISTS mobile_quiz_attempts(
                    id TEXT PRIMARY KEY, quiz_id TEXT NOT NULL,
                    option_id TEXT NOT NULL, passed INTEGER NOT NULL CHECK(passed IN (0,1)),
                    feedback_encrypted BLOB NOT NULL, created_at TEXT NOT NULL
                ) STRICT;
                CREATE TABLE IF NOT EXISTS unit_progress(
                    unit_slug TEXT PRIMARY KEY, status TEXT NOT NULL CHECK(status IN ('started','completed')),
                    updated_at TEXT NOT NULL
                ) STRICT;
                CREATE TABLE IF NOT EXISTS mobile_game_sessions(
                    id TEXT PRIMARY KEY, game TEXT NOT NULL, difficulty TEXT NOT NULL,
                    seed INTEGER NOT NULL, state_encrypted BLOB NOT NULL, status TEXT NOT NULL,
                    elapsed_seconds INTEGER NOT NULL, daily_key TEXT UNIQUE,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                ) STRICT;
                CREATE TABLE IF NOT EXISTS mobile_game_statistics(
                    game TEXT NOT NULL, difficulty TEXT NOT NULL, plays INTEGER NOT NULL,
                    wins INTEGER NOT NULL, best_seconds INTEGER, updated_at TEXT NOT NULL,
                    PRIMARY KEY(game,difficulty)
                ) WITHOUT ROWID, STRICT;
                CREATE TABLE IF NOT EXISTS mobile_projects(
                    id TEXT PRIMARY KEY, name_encrypted BLOB NOT NULL,
                    relative_path TEXT NOT NULL, source_encrypted BLOB NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                ) STRICT;
            """)
            connection.commit()
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def record_card(self, card_id: str, action: str) -> None:
        if action not in {"again", "known", "open"}:
            raise ValueError("unknown card action")
        now = datetime.now(UTC).isoformat()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("INSERT INTO card_actions VALUES(?,?,?,?)", (str(uuid4()), card_id, action, now))
            row = connection.execute("SELECT mastery,interval_days FROM review_state WHERE card_id=?", (card_id,)).fetchone()
            mastery, interval = row if row else (0.0, 0)
            if action == "known":
                mastery, interval = min(1.0, mastery + 0.16), max(1, interval * 2 or 1)
            elif action == "again":
                mastery, interval = max(0.0, mastery - 0.12), 0
            connection.execute(
                """INSERT INTO review_state(card_id,mastery,interval_days,next_review_at,updated_at)
                   VALUES(?,?,?,?,?) ON CONFLICT(card_id) DO UPDATE SET
                   mastery=excluded.mastery,interval_days=excluded.interval_days,updated_at=excluded.updated_at""",
                (card_id, mastery, interval, None, now),
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def mastery(self, card_id: str) -> float:
        connection = self._connect()
        try:
            row = connection.execute("SELECT mastery FROM review_state WHERE card_id=?", (card_id,)).fetchone()
            return float(row[0]) if row else 0.0
        finally:
            connection.close()

    def save_attempt(self, exercise_id: str, source: str, status: str, score: float, output: str) -> str:
        attempt_id, now = str(uuid4()), datetime.now(UTC).isoformat()
        source_blob = self._cipher.encrypt(source.encode(), associated_data=f"mobile_attempt.source:{attempt_id}".encode())
        output_blob = self._cipher.encrypt(output.encode(), associated_data=f"mobile_attempt.output:{attempt_id}".encode())
        connection = self._connect()
        try:
            connection.execute(
                "INSERT INTO mobile_attempts VALUES(?,?,?,?,?,?,?)",
                (attempt_id, exercise_id, source_blob, status, score, output_blob, now),
            )
            connection.commit()
        finally:
            connection.close()
        return attempt_id

    def save_quiz_attempt(self, quiz_id: str, option_id: str, passed: bool, feedback: str) -> str:
        attempt_id, now = str(uuid4()), datetime.now(UTC).isoformat()
        blob = self._cipher.encrypt(
            feedback.encode(), associated_data=f"mobile_quiz.feedback:{attempt_id}".encode()
        )
        connection = self._connect()
        try:
            connection.execute(
                "INSERT INTO mobile_quiz_attempts VALUES(?,?,?,?,?,?)",
                (attempt_id, quiz_id, option_id, int(passed), blob, now),
            )
            connection.commit()
        finally:
            connection.close()
        return attempt_id

    def setting(self, name: str, default: str) -> str:
        connection = self._connect()
        try:
            row = connection.execute("SELECT value FROM mobile_settings WHERE name=?", (name,)).fetchone()
            return row[0] if row else default
        finally:
            connection.close()

    def set_setting(self, name: str, value: str) -> None:
        connection = self._connect()
        try:
            connection.execute(
                "INSERT INTO mobile_settings VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value",
                (name, value),
            )
            connection.commit()
        finally:
            connection.close()

    def passed_attempts(self) -> int:
        connection = self._connect()
        try:
            return int(connection.execute(
                "SELECT count(DISTINCT exercise_id) FROM mobile_attempts WHERE score=1"
            ).fetchone()[0])
        finally:
            connection.close()

    def complete_unit(self, unit_slug: str) -> None:
        now = datetime.now(UTC).isoformat(); connection = self._connect()
        try:
            connection.execute(
                """INSERT INTO unit_progress VALUES(?, 'completed', ?)
                   ON CONFLICT(unit_slug) DO UPDATE SET status='completed',updated_at=excluded.updated_at""",
                (unit_slug, now),
            ); connection.commit()
        finally:
            connection.close()

    def completed_units(self) -> tuple[str, ...]:
        connection = self._connect()
        try:
            return tuple(row[0] for row in connection.execute(
                "SELECT unit_slug FROM unit_progress WHERE status='completed' ORDER BY unit_slug"
            ))
        finally:
            connection.close()

    @staticmethod
    def _project_path(value: str) -> str:
        normalized = value.strip().replace("\\", "/")
        parts = normalized.split("/")
        if (
            not normalized or len(normalized) > 240
            or any(part in {"", ".", ".."} for part in parts)
            or any(not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", part) for part in parts)
        ):
            raise ValueError("Caminho relativo inválido ou inseguro.")
        return normalized

    def save_project(
        self, name: str, source: str, *, project_id: str | None = None,
        relative_path: str = "main.py",
    ) -> dict[str, str]:
        clean_name = name.strip()
        if not 1 <= len(clean_name) <= 160 or len(source) > 100_000:
            raise ValueError("Nome ou código do projeto fora dos limites.")
        relative_path = self._project_path(relative_path)
        identity, now = project_id or str(uuid4()), datetime.now(UTC).isoformat()
        encrypted_name = self._cipher.encrypt(
            clean_name.encode(), associated_data=f"mobile_project.name:{identity}".encode()
        )
        encrypted_source = self._cipher.encrypt(
            source.encode(), associated_data=f"mobile_project.source:{identity}:{relative_path}".encode()
        )
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            created = connection.execute(
                "SELECT created_at FROM mobile_projects WHERE id=?", (identity,)
            ).fetchone()
            connection.execute(
                """INSERT INTO mobile_projects VALUES(?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET name_encrypted=excluded.name_encrypted,
                   relative_path=excluded.relative_path,source_encrypted=excluded.source_encrypted,
                   updated_at=excluded.updated_at""",
                (identity, encrypted_name, relative_path, encrypted_source,
                 created[0] if created else now, now),
            )
            connection.commit()
        except BaseException:
            connection.rollback(); raise
        finally:
            connection.close()
        return {"id": identity, "name": clean_name, "relative_path": relative_path,
                "source": source, "updated_at": now}

    def projects(self) -> tuple[dict[str, str], ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM mobile_projects ORDER BY updated_at DESC"
            ).fetchall()
        finally:
            connection.close()
        result = []
        for identity, name, relative_path, source, _created, updated in rows:
            result.append({
                "id": identity,
                "name": self._cipher.decrypt(
                    name, associated_data=f"mobile_project.name:{identity}".encode()
                ).decode(),
                "relative_path": relative_path,
                "source": self._cipher.decrypt(
                    source,
                    associated_data=f"mobile_project.source:{identity}:{relative_path}".encode(),
                ).decode(),
                "updated_at": updated,
            })
        return tuple(result)

    def export_snapshot(self) -> dict[str, object]:
        connection = self._connect()
        try:
            reviews = [dict(zip(("id", "mastery", "interval_days", "next_review_at", "updated_at"), row))
                       for row in connection.execute(
                           "SELECT card_id,mastery,interval_days,next_review_at,updated_at FROM review_state ORDER BY card_id"
                       )]
            attempts = []
            for row in connection.execute(
                "SELECT id,exercise_id,source_encrypted,status,score,output_encrypted,created_at FROM mobile_attempts ORDER BY id"
            ):
                identity = row[0]
                attempts.append({
                    "id": identity, "exercise_id": row[1],
                    "source": self._cipher.decrypt(row[2], associated_data=f"mobile_attempt.source:{identity}".encode()).decode(),
                    "status": row[3], "score": row[4],
                    "output": self._cipher.decrypt(row[5], associated_data=f"mobile_attempt.output:{identity}".encode()).decode(),
                    "updated_at": row[6],
                })
            completed_units = [
                {"id": row[0], "status": row[1], "updated_at": row[2]}
                for row in connection.execute(
                    "SELECT unit_slug,status,updated_at FROM unit_progress ORDER BY unit_slug"
                )
            ]
            return {
                "platform": "mobile", "reviews": reviews, "attempts": attempts,
                "completed_units": completed_units, "projects": list(self.projects()),
            }
        finally:
            connection.close()

    def preview_snapshot(self, snapshot: dict[str, object]) -> dict[str, int]:
        from aprendix.application.profile_transfer import merge_by_identity
        local = self.export_snapshot()
        _, review_conflicts = merge_by_identity(list(local["reviews"]), list(snapshot.get("reviews", [])))
        _, attempt_conflicts = merge_by_identity(list(local["attempts"]), list(snapshot.get("attempts", [])))
        _, unit_conflicts = merge_by_identity(
            list(local["completed_units"]), list(snapshot.get("completed_units", []))
        )
        _, project_conflicts = merge_by_identity(
            list(local.get("projects", [])), list(snapshot.get("projects", []))
        )
        return {
            "incoming_reviews": len(snapshot.get("reviews", [])),
            "incoming_attempts": len(snapshot.get("attempts", [])),
            "incoming_completed_units": len(snapshot.get("completed_units", [])),
            "incoming_projects": len(snapshot.get("projects", [])),
            "conflicts": (
                len(review_conflicts) + len(attempt_conflicts)
                + len(unit_conflicts) + len(project_conflicts)
            ),
        }

    def import_snapshot(self, snapshot: dict[str, object]) -> dict[str, int]:
        from aprendix.application.profile_transfer import merge_by_identity
        local = self.export_snapshot()
        reviews, review_conflicts = merge_by_identity(list(local["reviews"]), list(snapshot.get("reviews", [])))
        attempts, attempt_conflicts = merge_by_identity(list(local["attempts"]), list(snapshot.get("attempts", [])))
        units, unit_conflicts = merge_by_identity(
            list(local["completed_units"]), list(snapshot.get("completed_units", []))
        )
        projects, project_conflicts = merge_by_identity(
            list(local.get("projects", [])), list(snapshot.get("projects", []))
        )
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            for item in reviews:
                connection.execute(
                    """INSERT INTO review_state VALUES(?,?,?,?,?) ON CONFLICT(card_id) DO UPDATE SET
                       mastery=excluded.mastery,interval_days=excluded.interval_days,
                       next_review_at=excluded.next_review_at,updated_at=excluded.updated_at""",
                    (str(item["id"]), float(item["mastery"]), int(item["interval_days"]),
                     item.get("next_review_at"), str(item["updated_at"])),
                )
            for item in attempts:
                identity = str(item["id"])
                source = self._cipher.encrypt(str(item["source"]).encode(), associated_data=f"mobile_attempt.source:{identity}".encode())
                output = self._cipher.encrypt(str(item["output"]).encode(), associated_data=f"mobile_attempt.output:{identity}".encode())
                connection.execute(
                    """INSERT INTO mobile_attempts VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                       exercise_id=excluded.exercise_id,source_encrypted=excluded.source_encrypted,
                       status=excluded.status,score=excluded.score,output_encrypted=excluded.output_encrypted,
                       created_at=excluded.created_at""",
                    (identity, str(item["exercise_id"]), source, str(item["status"]),
                     float(item["score"]), output, str(item["updated_at"])),
                )
            for item in units:
                status = str(item.get("status", "completed"))
                if status not in {"started", "completed"}:
                    raise ValueError("invalid unit status")
                connection.execute(
                    """INSERT INTO unit_progress VALUES(?,?,?) ON CONFLICT(unit_slug) DO UPDATE SET
                       status=excluded.status,updated_at=excluded.updated_at""",
                    (str(item["id"]), status, str(item["updated_at"])),
                )
            for item in projects:
                identity = str(item["id"])
                relative_path = self._project_path(str(item.get("relative_path", "main.py")))
                name = str(item.get("name", "Projeto")).strip()
                source = str(item.get("source", ""))
                if not 1 <= len(name) <= 160 or len(source) > 100_000:
                    raise ValueError("invalid mobile project")
                encrypted_name = self._cipher.encrypt(
                    name.encode(), associated_data=f"mobile_project.name:{identity}".encode()
                )
                encrypted_source = self._cipher.encrypt(
                    source.encode(),
                    associated_data=f"mobile_project.source:{identity}:{relative_path}".encode(),
                )
                updated = str(item["updated_at"])
                connection.execute(
                    """INSERT INTO mobile_projects VALUES(?,?,?,?,?,?)
                       ON CONFLICT(id) DO UPDATE SET name_encrypted=excluded.name_encrypted,
                       relative_path=excluded.relative_path,source_encrypted=excluded.source_encrypted,
                       updated_at=excluded.updated_at""",
                    (identity, encrypted_name, relative_path, encrypted_source, updated, updated),
                )
            connection.commit()
        except BaseException:
            connection.rollback(); raise
        finally:
            connection.close()
        return {"reviews": len(reviews), "attempts": len(attempts),
                "completed_units": len(units), "projects": len(projects),
                "conflicts": len(review_conflicts) + len(attempt_conflicts)
                + len(unit_conflicts) + len(project_conflicts)}
