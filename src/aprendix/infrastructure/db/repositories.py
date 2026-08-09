"""Transactional repository base and the first concrete aggregate repository."""

from __future__ import annotations

import json
import sqlite3
from abc import ABC
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar
from uuid import UUID

from aprendix.application.contracts import AttemptDTO, EventDTO, ExerciseDTO, UserDTO
from aprendix.domain import AttemptStatus, EventType
from aprendix.infrastructure.db.database import Database
from aprendix.infrastructure.security.field_cipher import AesGcmFieldCipher

EntityT = TypeVar("EntityT")


class EntityNotFoundError(LookupError):
    """Raised when an aggregate cannot be found by its stable identifier."""


class IdempotencyConflictError(ValueError):
    """Raised when an idempotency key is reused for different content."""


class BaseSQLiteRepository(ABC, Generic[EntityT]):
    """Shared SQL, JSON encryption, and transaction behavior.

    Concrete repositories own their SQL mappings. Keeping table and column names
    out of generic runtime arguments prevents accidental identifier injection.
    """

    def __init__(self, database: Database, cipher: AesGcmFieldCipher) -> None:
        self._database = database
        self._cipher = cipher

    @staticmethod
    def _execute(
        connection: sqlite3.Connection,
        sql: str,
        parameters: Sequence[Any] | Mapping[str, Any] = (),
    ) -> sqlite3.Cursor:
        return connection.execute(sql, parameters)

    def _encrypt_text(self, value: str, *, context: str) -> bytes:
        return self._cipher.encrypt(
            value.encode("utf-8"),
            associated_data=context.encode("utf-8"),
        )

    def _decrypt_text(self, value: bytes, *, context: str) -> str:
        return self._cipher.decrypt(
            value,
            associated_data=context.encode("utf-8"),
        ).decode("utf-8")

    def _encrypt_json(self, value: Mapping[str, Any], *, context: str) -> bytes:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return self._encrypt_text(payload, context=context)

    def _decrypt_json(self, value: bytes, *, context: str) -> dict[str, Any]:
        decoded = json.loads(self._decrypt_text(value, context=context))
        if not isinstance(decoded, dict):
            raise ValueError("encrypted JSON payload must contain an object")
        return decoded


class UserRepository(BaseSQLiteRepository[UserDTO]):
    """Persist the user aggregate while encrypting its optional display name."""

    @staticmethod
    def _name_context(user_id: UUID | str) -> str:
        return f"users.display_name:{user_id}"

    def add(self, user: UserDTO) -> None:
        encrypted_name = (
            self._encrypt_text(
                user.display_name,
                context=self._name_context(user.id),
            )
            if user.display_name is not None
            else None
        )
        with self._database.transaction() as connection:
            self._execute(
                connection,
                """
                INSERT INTO users(
                    id, display_name_encrypted, consent_sync, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(user.id),
                    encrypted_name,
                    int(user.consent_sync),
                    user.created_at.astimezone(UTC).isoformat(),
                    user.updated_at.astimezone(UTC).isoformat(),
                ),
            )

    def get(self, user_id: UUID) -> UserDTO:
        with self._database.read_connection() as connection:
            row = self._execute(
                connection,
                """
                SELECT id, display_name_encrypted, consent_sync, created_at, updated_at
                FROM users
                WHERE id = ?
                """,
                (str(user_id),),
            ).fetchone()
        if row is None:
            raise EntityNotFoundError(f"user {user_id} was not found")

        encrypted_name = row["display_name_encrypted"]
        display_name = (
            self._decrypt_text(
                encrypted_name,
                context=self._name_context(row["id"]),
            )
            if encrypted_name is not None
            else None
        )
        return UserDTO(
            id=UUID(row["id"]),
            display_name=display_name,
            consent_sync=bool(row["consent_sync"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def delete(self, user_id: UUID) -> bool:
        with self._database.transaction() as connection:
            cursor = self._execute(
                connection,
                "DELETE FROM users WHERE id = ?",
                (str(user_id),),
            )
            return cursor.rowcount == 1

    def first(self) -> UserDTO | None:
        with self._database.read_connection() as connection:
            row = self._execute(
                connection,
                "SELECT id FROM users ORDER BY created_at, id LIMIT 1",
            ).fetchone()
        return self.get(UUID(row["id"])) if row is not None else None


class EventRepository(BaseSQLiteRepository[EventDTO]):
    """Append-only encrypted event repository with replay protection."""

    @staticmethod
    def _payload_context(event_id: UUID | str, user_id: UUID | str) -> str:
        return f"events.payload:{user_id}:{event_id}"

    def append(self, event: EventDTO) -> bool:
        with self._database.transaction() as connection:
            return self.add_in_transaction(connection, event)

    def add_in_transaction(
        self,
        connection: sqlite3.Connection,
        event: EventDTO,
    ) -> bool:
        existing = self._find_by_idempotency(
            connection,
            event.user_id,
            event.idempotency_key,
        )
        if existing is not None:
            if existing == event:
                return False
            raise IdempotencyConflictError(
                f"event idempotency key {event.idempotency_key} has different content"
            )

        encrypted_payload = self._encrypt_json(
            event.payload,
            context=self._payload_context(event.id, event.user_id),
        )
        self._execute(
            connection,
            """
            INSERT INTO events(
                id, idempotency_key, user_id, event_type, payload_encrypted,
                occurred_at, created_at, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(event.id),
                str(event.idempotency_key),
                str(event.user_id),
                event.event_type.value,
                encrypted_payload,
                event.occurred_at.astimezone(UTC).isoformat(),
                event.created_at.astimezone(UTC).isoformat(),
                event.schema_version,
            ),
        )
        return True

    def get(self, event_id: UUID) -> EventDTO:
        with self._database.read_connection() as connection:
            row = self._execute(
                connection,
                "SELECT * FROM events WHERE id = ?",
                (str(event_id),),
            ).fetchone()
        if row is None:
            raise EntityNotFoundError(f"event {event_id} was not found")
        return self._from_row(row)

    def list_for_user(self, user_id: UUID, *, limit: int = 100) -> tuple[EventDTO, ...]:
        if not 1 <= limit <= 1_000:
            raise ValueError("limit must be between 1 and 1000")
        with self._database.read_connection() as connection:
            rows = self._execute(
                connection,
                """
                SELECT * FROM events
                WHERE user_id = ?
                ORDER BY occurred_at, id
                LIMIT ?
                """,
                (str(user_id), limit),
            ).fetchall()
        return tuple(self._from_row(row) for row in rows)

    def _find_by_idempotency(
        self,
        connection: sqlite3.Connection,
        user_id: UUID,
        idempotency_key: UUID,
    ) -> EventDTO | None:
        row = self._execute(
            connection,
            """
            SELECT * FROM events
            WHERE user_id = ? AND idempotency_key = ?
            """,
            (str(user_id), str(idempotency_key)),
        ).fetchone()
        return self._from_row(row) if row is not None else None

    def _from_row(self, row: sqlite3.Row) -> EventDTO:
        return EventDTO(
            id=UUID(row["id"]),
            idempotency_key=UUID(row["idempotency_key"]),
            user_id=UUID(row["user_id"]),
            event_type=EventType(row["event_type"]),
            payload=self._decrypt_json(
                row["payload_encrypted"],
                context=self._payload_context(row["id"], row["user_id"]),
            ),
            occurred_at=datetime.fromisoformat(row["occurred_at"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            schema_version=row["schema_version"],
        )


class AttemptRepository(BaseSQLiteRepository[AttemptDTO]):
    """Encrypted attempt repository with per-user idempotency."""

    @staticmethod
    def _field_context(
        field: str,
        attempt_id: UUID | str,
        user_id: UUID | str,
    ) -> str:
        return f"attempts.{field}:{user_id}:{attempt_id}"

    def add(self, attempt: AttemptDTO) -> bool:
        with self._database.transaction() as connection:
            return self.add_in_transaction(connection, attempt)

    def add_in_transaction(
        self,
        connection: sqlite3.Connection,
        attempt: AttemptDTO,
    ) -> bool:
        existing = self._find_by_idempotency(
            connection,
            attempt.user_id,
            attempt.idempotency_key,
        )
        if existing is not None:
            if existing == attempt:
                return False
            raise IdempotencyConflictError(
                f"attempt idempotency key {attempt.idempotency_key} has different content"
            )

        source = self._encrypt_text(
            attempt.source_code,
            context=self._field_context("source_code", attempt.id, attempt.user_id),
        )
        output = (
            self._encrypt_text(
                attempt.output,
                context=self._field_context("output", attempt.id, attempt.user_id),
            )
            if attempt.output is not None
            else None
        )
        self._execute(
            connection,
            """
            INSERT INTO attempts(
                id, idempotency_key, user_id, exercise_id, status,
                source_code_encrypted, output_encrypted, score, duration_ms,
                submitted_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(attempt.id),
                str(attempt.idempotency_key),
                str(attempt.user_id),
                str(attempt.exercise_id),
                attempt.status.value,
                source,
                output,
                attempt.score,
                attempt.duration_ms,
                (
                    attempt.submitted_at.astimezone(UTC).isoformat()
                    if attempt.submitted_at is not None
                    else None
                ),
                attempt.created_at.astimezone(UTC).isoformat(),
            ),
        )
        return True

    def replace_for_profile(
        self, connection: sqlite3.Connection, attempt: AttemptDTO,
    ) -> None:
        """Insert or replace one authenticated cross-device profile record."""
        existing = self._execute(
            connection, "SELECT user_id FROM attempts WHERE id=?", (str(attempt.id),)
        ).fetchone()
        if existing is not None and existing["user_id"] != str(attempt.user_id):
            raise ValueError("attempt identity belongs to another local profile")
        source = self._encrypt_text(
            attempt.source_code,
            context=self._field_context("source_code", attempt.id, attempt.user_id),
        )
        output = (
            self._encrypt_text(
                attempt.output,
                context=self._field_context("output", attempt.id, attempt.user_id),
            )
            if attempt.output is not None else None
        )
        values = (
            str(attempt.id), str(attempt.idempotency_key), str(attempt.user_id),
            str(attempt.exercise_id), attempt.status.value, source, output,
            attempt.score, attempt.duration_ms,
            attempt.submitted_at.astimezone(UTC).isoformat() if attempt.submitted_at else None,
            attempt.created_at.astimezone(UTC).isoformat(),
        )
        self._execute(
            connection,
            """INSERT INTO attempts(id,idempotency_key,user_id,exercise_id,status,
               source_code_encrypted,output_encrypted,score,duration_ms,submitted_at,created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
               idempotency_key=excluded.idempotency_key,exercise_id=excluded.exercise_id,
               status=excluded.status,source_code_encrypted=excluded.source_code_encrypted,
               output_encrypted=excluded.output_encrypted,score=excluded.score,
               duration_ms=excluded.duration_ms,submitted_at=excluded.submitted_at,
               created_at=excluded.created_at""",
            values,
        )

    def get(self, attempt_id: UUID) -> AttemptDTO:
        with self._database.read_connection() as connection:
            row = self._execute(
                connection,
                "SELECT * FROM attempts WHERE id = ?",
                (str(attempt_id),),
            ).fetchone()
        if row is None:
            raise EntityNotFoundError(f"attempt {attempt_id} was not found")
        return self._from_row(row)

    def finalize(
        self, attempt_id: UUID, *, status: AttemptStatus, output: str,
        score: float,
    ) -> AttemptDTO:
        if status not in {AttemptStatus.PASSED, AttemptStatus.FAILED, AttemptStatus.ERROR}:
            raise ValueError("final attempt status must be passed, failed, or error")
        if not 0.0 <= score <= 1.0:
            raise ValueError("score must be between 0 and 1")
        current = self.get(attempt_id)
        encrypted_output = self._encrypt_text(
            output[:100_000],
            context=self._field_context("output", current.id, current.user_id),
        )
        with self._database.transaction() as connection:
            cursor = self._execute(
                connection,
                """UPDATE attempts SET status = ?, output_encrypted = ?, score = ?
                   WHERE id = ?""",
                (status.value, encrypted_output, score, str(attempt_id)),
            )
            if cursor.rowcount != 1:
                raise EntityNotFoundError(f"attempt {attempt_id} was not found")
        return self.get(attempt_id)

    def list_for_user(
        self,
        user_id: UUID,
        *,
        limit: int = 100,
    ) -> tuple[AttemptDTO, ...]:
        if not 1 <= limit <= 100_000:
            raise ValueError("limit must be between 1 and 100000")
        with self._database.read_connection() as connection:
            rows = self._execute(
                connection,
                """
                SELECT * FROM attempts
                WHERE user_id = ?
                ORDER BY created_at, id
                LIMIT ?
                """,
                (str(user_id), limit),
            ).fetchall()
        return tuple(self._from_row(row) for row in rows)

    def _find_by_idempotency(
        self,
        connection: sqlite3.Connection,
        user_id: UUID,
        idempotency_key: UUID,
    ) -> AttemptDTO | None:
        row = self._execute(
            connection,
            """
            SELECT * FROM attempts
            WHERE user_id = ? AND idempotency_key = ?
            """,
            (str(user_id), str(idempotency_key)),
        ).fetchone()
        return self._from_row(row) if row is not None else None

    def _from_row(self, row: sqlite3.Row) -> AttemptDTO:
        return AttemptDTO(
            id=UUID(row["id"]),
            idempotency_key=UUID(row["idempotency_key"]),
            user_id=UUID(row["user_id"]),
            exercise_id=UUID(row["exercise_id"]),
            status=AttemptStatus(row["status"]),
            source_code=self._decrypt_text(
                row["source_code_encrypted"],
                context=self._field_context(
                    "source_code",
                    row["id"],
                    row["user_id"],
                ),
            ),
            output=(
                self._decrypt_text(
                    row["output_encrypted"],
                    context=self._field_context(
                        "output",
                        row["id"],
                        row["user_id"],
                    ),
                )
                if row["output_encrypted"] is not None
                else None
            ),
            score=row["score"],
            duration_ms=row["duration_ms"],
            submitted_at=(
                datetime.fromisoformat(row["submitted_at"])
                if row["submitted_at"] is not None
                else None
            ),
            created_at=datetime.fromisoformat(row["created_at"]),
        )


class ExerciseRepository(BaseSQLiteRepository[ExerciseDTO]):
    """Read the locally seeded exercise catalogue."""

    def get(self, exercise_id: UUID) -> ExerciseDTO:
        with self._database.read_connection() as connection:
            row = self._execute(
                connection,
                "SELECT * FROM exercises WHERE id = ?",
                (str(exercise_id),),
            ).fetchone()
        if row is None:
            raise EntityNotFoundError(f"exercise {exercise_id} was not found")
        return self._from_row(row)

    def list_all(self) -> tuple[ExerciseDTO, ...]:
        with self._database.read_connection() as connection:
            rows = self._execute(
                connection,
                "SELECT * FROM exercises ORDER BY difficulty, slug, version",
            ).fetchall()
        return tuple(self._from_row(row) for row in rows)

    @staticmethod
    def _from_row(row: sqlite3.Row) -> ExerciseDTO:
        tests = json.loads(row["tests_json"])
        if not isinstance(tests, list) or not all(
            isinstance(test, str) for test in tests
        ):
            raise ValueError("exercise tests_json must contain a list of strings")
        return ExerciseDTO(
            id=UUID(row["id"]),
            graph_node_id=UUID(row["graph_node_id"]),
            slug=row["slug"],
            title=row["title"],
            prompt=sanitize_exercise_prompt(row["prompt"]),
            starter_code=row["starter_code"],
            tests=tuple(tests),
            difficulty=row["difficulty"],
            version=row["version"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )


class LearningRecordRepository:
    """Coordinate the atomic attempt/event write required by the use case."""

    def __init__(
        self,
        database: Database,
        attempt_repository: AttemptRepository,
        event_repository: EventRepository,
    ) -> None:
        self._database = database
        self._attempts = attempt_repository
        self._events = event_repository

    def record(self, attempt: AttemptDTO, event: EventDTO) -> bool:
        if event.event_type is not EventType.ATTEMPT_SUBMITTED:
            raise ValueError("submission event must be attempt.submitted")
        if event.user_id != attempt.user_id:
            raise ValueError("attempt and event must belong to the same user")
        if event.payload.get("attempt_id") != str(attempt.id):
            raise ValueError("submission event references a different attempt")
        if event.payload.get("exercise_id") != str(attempt.exercise_id):
            raise ValueError("submission event references a different exercise")

        with self._database.transaction() as connection:
            attempt_created = self._attempts.add_in_transaction(connection, attempt)
            event_created = self._events.add_in_transaction(connection, event)
        return attempt_created or event_created
from aprendix.application.editor_support import sanitize_exercise_prompt
