"""Mobile adapter for the shared resumable break-game service."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

UTC = timezone.utc


class MobileGameRepository:
    def __init__(self, state) -> None:
        self.state, self._cipher = state, state._cipher

    def _decode(self, row):
        if row is None: return None
        state = json.loads(self._cipher.decrypt(
            row["state_encrypted"], associated_data=f"mobile_game.state:{row['id']}".encode(),
        ))
        return {**dict(row), "id": UUID(row["id"]), "state": state}

    def save(self, user_id, *, session_id, game, difficulty, seed, state,
             elapsed_seconds, status="active", daily_key=None):
        identity, now = session_id or uuid4(), datetime.now(UTC).isoformat()
        blob = self._cipher.encrypt(json.dumps(state, sort_keys=True).encode(),
                                    associated_data=f"mobile_game.state:{identity}".encode())
        connection = self.state._connect()
        try:
            connection.execute(
                """INSERT INTO mobile_game_sessions VALUES(?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET state_encrypted=excluded.state_encrypted,
                   elapsed_seconds=excluded.elapsed_seconds,status=excluded.status,updated_at=excluded.updated_at""",
                (str(identity), game, difficulty, seed, blob, status,
                 max(0, elapsed_seconds), daily_key, now, now),
            ); connection.commit()
        finally: connection.close()
        return identity

    def latest(self, _user_id, game, difficulty):
        connection = self.state._connect(); connection.row_factory = __import__("sqlite3").Row
        try:
            row = connection.execute(
                "SELECT * FROM mobile_game_sessions WHERE game=? AND difficulty=? AND status='active' ORDER BY updated_at DESC LIMIT 1",
                (game, difficulty),
            ).fetchone()
        finally: connection.close()
        return self._decode(row)

    def by_daily_key(self, _user_id, daily_key):
        connection = self.state._connect(); connection.row_factory = __import__("sqlite3").Row
        try: row = connection.execute("SELECT * FROM mobile_game_sessions WHERE daily_key=?", (daily_key,)).fetchone()
        finally: connection.close()
        return self._decode(row)

    def finish(self, _user_id, session_id, *, won, elapsed_seconds):
        now = datetime.now(UTC).isoformat(); connection = self.state._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT game,difficulty,status FROM mobile_game_sessions WHERE id=?", (str(session_id),)).fetchone()
            if row and row[2] == "active":
                connection.execute("UPDATE mobile_game_sessions SET status=?,elapsed_seconds=?,updated_at=? WHERE id=?",
                                   ("won" if won else "lost", elapsed_seconds, now, str(session_id)))
                connection.execute(
                    """INSERT INTO mobile_game_statistics VALUES(?,?,?,?,?,?)
                       ON CONFLICT(game,difficulty) DO UPDATE SET plays=plays+1,wins=wins+excluded.wins,
                       best_seconds=CASE WHEN excluded.wins=1 AND (best_seconds IS NULL OR excluded.best_seconds<best_seconds)
                       THEN excluded.best_seconds ELSE best_seconds END,updated_at=excluded.updated_at""",
                    (row[0], row[1], 1, int(won), elapsed_seconds if won else None, now),
                )
            connection.commit()
        except BaseException: connection.rollback(); raise
        finally: connection.close()

    def statistics(self, _user_id):
        connection = self.state._connect(); connection.row_factory = __import__("sqlite3").Row
        try: rows = connection.execute("SELECT * FROM mobile_game_statistics ORDER BY game,difficulty").fetchall()
        finally: connection.close()
        return tuple(dict(row) for row in rows)
