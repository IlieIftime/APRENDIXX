"""Encrypted persistence for local tutor history."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID


class TutorRepository:
    def __init__(self, database, cipher) -> None:
        self._database, self._cipher = database, cipher

    def save(self, user_id: UUID, request, response) -> None:
        identity = response.id
        def encrypt(field: str, value: object) -> bytes:
            return self._cipher.encrypt(
                json.dumps(value, ensure_ascii=False).encode("utf-8"),
                associated_data=f"tutor_messages.{field}:{identity}".encode(),
            )
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO tutor_messages VALUES(?,?,?,?,?,?,?,?,?)",
                (str(identity), str(user_id), request.strategy.value,
                 encrypt("question", request.question), encrypt("answer", response.answer),
                 encrypt("evidence", [item.model_dump(mode="json") for item in response.evidence]),
                 response.confidence, int(response.declined), datetime.now(UTC).isoformat()),
            )

    def history(self, user_id: UUID, *, limit: int = 50) -> tuple[dict[str, object], ...]:
        with self._database.read_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM tutor_messages WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                (str(user_id), max(1, min(limit, 200))),
            ).fetchall()
        result = []
        for row in rows:
            identity = row["id"]
            def decrypt(field: str):
                return json.loads(self._cipher.decrypt(
                    row[f"{field}_encrypted"],
                    associated_data=f"tutor_messages.{field}:{identity}".encode(),
                ))
            result.append({
                "id": identity, "strategy": row["strategy"],
                "question": decrypt("question"), "answer": decrypt("answer"),
                "evidence": decrypt("evidence"), "confidence": row["confidence"],
                "declined": bool(row["declined"]), "created_at": row["created_at"],
            })
        return tuple(result)

    def delete_history(self, user_id: UUID) -> int:
        with self._database.transaction() as connection:
            cursor = connection.execute("DELETE FROM tutor_messages WHERE user_id=?", (str(user_id),))
        return max(0, cursor.rowcount)
