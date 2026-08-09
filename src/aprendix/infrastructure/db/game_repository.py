"""Encrypted game state isolated from learning evidence and mastery."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4


class GameRepository:
    def __init__(self, database, cipher) -> None:
        self._database, self._cipher = database, cipher

    def save(self, user_id: UUID, *, session_id: UUID | None, game: str, difficulty: str,
             seed: int, state: dict[str, object], elapsed_seconds: int,
             status: str = "active", daily_key: str | None = None) -> UUID:
        identity, now = session_id or uuid4(), datetime.now(UTC).isoformat()
        blob = self._cipher.encrypt(
            json.dumps(state, ensure_ascii=False, sort_keys=True).encode(),
            associated_data=f"game_sessions.state:{identity}".encode(),
        )
        with self._database.transaction() as connection:
            connection.execute(
                """INSERT INTO game_sessions VALUES(?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET state_encrypted=excluded.state_encrypted,
                   elapsed_seconds=excluded.elapsed_seconds,status=excluded.status,
                   updated_at=excluded.updated_at""",
                (str(identity), str(user_id), game, difficulty, seed, blob, status,
                 max(0, elapsed_seconds), daily_key, now, now),
            )
        return identity

    def latest(self, user_id: UUID, game: str, difficulty: str):
        with self._database.read_connection() as connection:
            row = connection.execute(
                """SELECT * FROM game_sessions WHERE user_id=? AND game=? AND difficulty=?
                   AND status='active' ORDER BY updated_at DESC LIMIT 1""",
                (str(user_id), game, difficulty),
            ).fetchone()
        if row is None: return None
        state = json.loads(self._cipher.decrypt(
            row["state_encrypted"], associated_data=f"game_sessions.state:{row['id']}".encode(),
        ))
        return {**dict(row), "id": UUID(row["id"]), "state": state}

    def by_daily_key(self, user_id: UUID, daily_key: str):
        with self._database.read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM game_sessions WHERE user_id=? AND daily_key=?",
                (str(user_id), daily_key),
            ).fetchone()
        if row is None: return None
        state = json.loads(self._cipher.decrypt(
            row["state_encrypted"], associated_data=f"game_sessions.state:{row['id']}".encode(),
        ))
        return {**dict(row), "id": UUID(row["id"]), "state": state}

    def finish(self, user_id: UUID, session_id: UUID, *, won: bool, elapsed_seconds: int) -> None:
        now = datetime.now(UTC).isoformat()
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT game,difficulty,status FROM game_sessions WHERE id=? AND user_id=?",
                (str(session_id), str(user_id)),
            ).fetchone()
            if row is None: raise KeyError("Sessão de jogo desconhecida.")
            if row["status"] != "active": return
            connection.execute(
                "UPDATE game_sessions SET status=?,elapsed_seconds=?,updated_at=? WHERE id=?",
                ("won" if won else "lost", max(0, elapsed_seconds), now, str(session_id)),
            )
            connection.execute(
                """INSERT INTO game_statistics VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(user_id,game,difficulty) DO UPDATE SET
                     plays=plays+1,wins=wins+excluded.wins,
                     best_seconds=CASE WHEN excluded.wins=1 AND
                       (best_seconds IS NULL OR excluded.best_seconds<best_seconds)
                       THEN excluded.best_seconds ELSE best_seconds END,
                     updated_at=excluded.updated_at""",
                (str(user_id), row["game"], row["difficulty"], 1, int(won),
                 max(0, elapsed_seconds) if won else None, now),
            )

    def statistics(self, user_id: UUID):
        with self._database.read_connection() as connection:
            rows = connection.execute(
                "SELECT game,difficulty,plays,wins,best_seconds FROM game_statistics WHERE user_id=? ORDER BY game,difficulty",
                (str(user_id),),
            ).fetchall()
        return tuple(dict(row) for row in rows)
