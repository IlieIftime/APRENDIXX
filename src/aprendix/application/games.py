"""Small deterministic break games with no animation or network dependency."""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field


DIFFICULTIES = ("Fácil", "Médio", "Difícil")


def _sudoku_solution(seed: int) -> list[list[int]]:
    rng = random.Random(seed)
    base = 3
    pattern = lambda row, col: (base * (row % base) + row // base + col) % 9
    rows = [group * base + row for group in rng.sample(range(base), base)
            for row in rng.sample(range(base), base)]
    cols = [group * base + col for group in rng.sample(range(base), base)
            for col in rng.sample(range(base), base)]
    numbers = rng.sample(range(1, 10), 9)
    return [[numbers[pattern(row, col)] for col in cols] for row in rows]


def _sudoku_solution_count(board: list[list[int]], *, limit: int = 2) -> int:
    """Count solutions up to ``limit`` using minimum-remaining-values search."""
    rows = [set(range(1, 10)) - set(row) for row in board]
    cols = [set(range(1, 10)) - {board[row][col] for row in range(9)} for col in range(9)]
    boxes = [set(range(1, 10)) for _ in range(9)]
    for row in range(9):
        for col in range(9):
            value = board[row][col]
            if value:
                boxes[(row // 3) * 3 + col // 3].discard(value)

    def solve() -> int:
        candidate_cell: tuple[int, int] | None = None
        candidates: set[int] | None = None
        for row in range(9):
            for col in range(9):
                if board[row][col]:
                    continue
                available = rows[row] & cols[col] & boxes[(row // 3) * 3 + col // 3]
                if not available:
                    return 0
                if candidates is None or len(available) < len(candidates):
                    candidate_cell, candidates = (row, col), available
                    if len(available) == 1:
                        break
            if candidates is not None and len(candidates) == 1:
                break
        if candidate_cell is None or candidates is None:
            return 1
        row, col = candidate_cell
        box = (row // 3) * 3 + col // 3
        total = 0
        for value in sorted(candidates):
            board[row][col] = value
            rows[row].remove(value); cols[col].remove(value); boxes[box].remove(value)
            total += solve()
            rows[row].add(value); cols[col].add(value); boxes[box].add(value)
            board[row][col] = 0
            if total >= limit:
                return total
        return total

    return solve()


@dataclass(slots=True)
class SudokuGame:
    difficulty: str = "Fácil"
    seed: int = 0
    solution: list[list[int]] = field(init=False)
    board: list[list[int]] = field(init=False)
    fixed: set[tuple[int, int]] = field(init=False)

    def __post_init__(self) -> None:
        if self.difficulty not in DIFFICULTIES:
            raise ValueError("Dificuldade de Sudoku inválida.")
        self.solution = _sudoku_solution(self.seed)
        self.board = [row[:] for row in self.solution]
        holes = {"Fácil": 34, "Médio": 46, "Difícil": 54}[self.difficulty]
        positions = list(range(81)); random.Random(self.seed + 7919).shuffle(positions)
        removed = 0
        for position in positions:
            if removed >= holes:
                break
            row, col = divmod(position, 9)
            previous = self.board[row][col]
            self.board[row][col] = 0
            if _sudoku_solution_count(self.board) == 1:
                removed += 1
            else:
                self.board[row][col] = previous
        self.fixed = {(row, col) for row in range(9) for col in range(9) if self.board[row][col]}

    def set(self, row: int, col: int, value: int) -> bool:
        if not (0 <= row < 9 and 0 <= col < 9 and 0 <= value <= 9):
            raise ValueError("Jogada fora do tabuleiro.")
        if (row, col) in self.fixed:
            return False
        self.board[row][col] = value
        return True

    def correct(self, row: int, col: int) -> bool:
        return self.board[row][col] in {0, self.solution[row][col]}

    @property
    def won(self) -> bool:
        return self.board == self.solution


@dataclass(slots=True)
class MinesweeperGame:
    difficulty: str = "Fácil"
    seed: int = 0
    rows: int = field(init=False)
    cols: int = field(init=False)
    mines: set[tuple[int, int]] = field(init=False)
    revealed: set[tuple[int, int]] = field(default_factory=set)
    flagged: set[tuple[int, int]] = field(default_factory=set)
    lost: bool = False

    def __post_init__(self) -> None:
        settings = {"Fácil": (8, 8, 10), "Médio": (12, 12, 24), "Difícil": (16, 16, 48)}
        if self.difficulty not in settings:
            raise ValueError("Dificuldade de Minesweeper inválida.")
        self.rows, self.cols, count = settings[self.difficulty]
        cells = [(row, col) for row in range(self.rows) for col in range(self.cols)]
        self.mines = set(random.Random(self.seed).sample(cells, count))

    def neighbours(self, row: int, col: int):
        for other_row in range(max(0, row - 1), min(self.rows, row + 2)):
            for other_col in range(max(0, col - 1), min(self.cols, col + 2)):
                if (other_row, other_col) != (row, col):
                    yield other_row, other_col

    def count(self, row: int, col: int) -> int:
        return sum(cell in self.mines for cell in self.neighbours(row, col))

    def toggle_flag(self, row: int, col: int) -> None:
        cell = (row, col)
        if cell in self.revealed:
            return
        if cell in self.flagged:
            self.flagged.remove(cell)
        else:
            self.flagged.add(cell)

    def reveal(self, row: int, col: int) -> None:
        start = (row, col)
        if start in self.flagged or start in self.revealed or self.lost:
            return
        if start in self.mines:
            self.revealed.add(start); self.lost = True; return
        pending = deque([start])
        while pending:
            cell = pending.popleft()
            if cell in self.revealed or cell in self.flagged or cell in self.mines:
                continue
            self.revealed.add(cell)
            if self.count(*cell) == 0:
                pending.extend(self.neighbours(*cell))

    @property
    def won(self) -> bool:
        return not self.lost and len(self.revealed) == self.rows * self.cols - len(self.mines)
