"""Daily and resumable break games with no pedagogical rewards."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from aprendix.application.games import MinesweeperGame, SudokuGame


@dataclass(slots=True)
class GameSession:
    id: UUID | None
    game: SudokuGame | MinesweeperGame
    elapsed_seconds: int = 0
    daily_key: str | None = None


class GameBreakService:
    def __init__(self, *, user, repository) -> None:
        self.user, self._repository = user, repository

    def new(self, game: str, difficulty: str, *, daily: bool = False) -> GameSession:
        today = datetime.now(timezone.utc).date().isoformat()
        daily_key = f"{today}:{game}:{difficulty}" if daily else None
        if daily_key:
            existing = self._repository.by_daily_key(self.user.id, daily_key)
            if existing and existing["status"] == "active":
                return self._restore(existing)
        seed_source = daily_key or (
            f"{self.user.id}:{game}:{difficulty}:{today}:"
            f"{secrets.token_hex(16)}"
        )
        seed = int.from_bytes(hashlib.sha256(seed_source.encode()).digest()[:4], "big")
        instance = SudokuGame(difficulty, seed) if game == "sudoku" else MinesweeperGame(difficulty, seed)
        session = GameSession(None, instance, daily_key=daily_key)
        self.save(session)
        return session

    def resume(self, game: str, difficulty: str) -> GameSession | None:
        row = self._repository.latest(self.user.id, game, difficulty)
        if row is None: return None
        return self._restore(row)

    @staticmethod
    def _restore(row) -> GameSession:
        game, difficulty = row["game"], row["difficulty"]
        instance = SudokuGame(difficulty, int(row["seed"])) if game == "sudoku" else MinesweeperGame(difficulty, int(row["seed"]))
        state = row["state"]
        if game == "sudoku": instance.board = [list(map(int, values)) for values in state["board"]]
        else:
            instance.revealed = {tuple(map(int, item)) for item in state["revealed"]}
            instance.flagged = {tuple(map(int, item)) for item in state["flagged"]}
            instance.lost = bool(state["lost"])
        return GameSession(row["id"], instance, int(row["elapsed_seconds"]), row["daily_key"])

    def save(self, session: GameSession) -> UUID:
        game_name = "sudoku" if isinstance(session.game, SudokuGame) else "minesweeper"
        state = ({"board": session.game.board} if game_name == "sudoku" else {
            "revealed": sorted(session.game.revealed), "flagged": sorted(session.game.flagged),
            "lost": session.game.lost,
        })
        session.id = self._repository.save(
            self.user.id, session_id=session.id, game=game_name,
            difficulty=session.game.difficulty, seed=session.game.seed,
            state=state, elapsed_seconds=session.elapsed_seconds, daily_key=session.daily_key,
        )
        return session.id

    def finish(self, session: GameSession) -> None:
        if session.id is None: self.save(session)
        self._repository.finish(
            self.user.id, session.id, won=session.game.won,
            elapsed_seconds=session.elapsed_seconds,
        )

    def statistics(self): return self._repository.statistics(self.user.id)
