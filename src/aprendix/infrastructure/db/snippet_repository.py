"""Encrypted, user-deletable history for snippet analysis."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID


class SnippetRepository:
    def __init__(self, database, cipher) -> None:
        self._database, self._cipher = database, cipher

    def save(self, user_id: UUID, request, result) -> None:
        identity = result.id
        def encrypted(field, value):
            return self._cipher.encrypt(
                json.dumps(value, ensure_ascii=False).encode(),
                associated_data=f"snippet_analyses.{field}:{identity}".encode(),
            )
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO snippet_analyses VALUES(?,?,?,?,?,?,?)",
                (str(identity), str(user_id), request.action.value,
                 encrypted("original", result.original),
                 encrypted("result", result.model_dump(mode="json")),
                 result.confidence, datetime.now(UTC).isoformat()),
            )

    def delete(self, user_id: UUID) -> int:
        with self._database.transaction() as connection:
            cursor = connection.execute("DELETE FROM snippet_analyses WHERE user_id=?", (str(user_id),))
        return max(0, cursor.rowcount)
