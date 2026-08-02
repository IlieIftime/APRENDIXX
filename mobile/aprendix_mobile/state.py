"""Private mobile state: local, encrypted fields and durable review state."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

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
