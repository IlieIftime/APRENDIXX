from aprendix.application.games import (
    DIFFICULTIES,
    MinesweeperGame,
    SudokuGame,
    _sudoku_solution_count,
)
from aprendix.bootstrap import build_runtime


def test_sudoku_is_deterministic_editable_and_solvable():
    game = SudokuGame("Médio", seed=7)
    clone = SudokuGame("Médio", seed=7)
    assert game.board == clone.board
    row, col = next(cell for cell in ((r, c) for r in range(9) for c in range(9)) if cell not in game.fixed)
    assert game.set(row, col, game.solution[row][col])
    for r in range(9):
        for c in range(9):
            if (r, c) not in game.fixed:
                game.set(r, c, game.solution[r][c])
    assert game.won


def test_every_sudoku_difficulty_is_valid_and_has_one_solution():
    minimum_holes = {"Fácil": 34, "Médio": 40, "Difícil": 45}
    for difficulty in DIFFICULTIES:
        for seed in range(6):
            game = SudokuGame(difficulty, seed=seed)
            assert _sudoku_solution_count([row[:] for row in game.board]) == 1
            assert sum(value == 0 for row in game.board for value in row) >= minimum_holes[difficulty]
            for row in game.solution:
                assert set(row) == set(range(1, 10))


def test_minesweeper_reveal_flag_loss_and_win_contracts():
    game = MinesweeperGame("Fácil", seed=3)
    mine = next(iter(game.mines))
    game.toggle_flag(*mine); game.reveal(*mine)
    assert not game.lost
    game.toggle_flag(*mine); game.reveal(*mine)
    assert game.lost
    safe = MinesweeperGame("Fácil", seed=4)
    for row in range(safe.rows):
        for col in range(safe.cols):
            if (row, col) not in safe.mines:
                safe.reveal(row, col)
    assert safe.won


def test_game_sessions_resume_daily_and_never_create_learning_evidence(tmp_path):
    runtime = build_runtime(tmp_path / "profile")
    session = runtime.games.new("sudoku", "Fácil", daily=True)
    editable = next(cell for cell in ((r, c) for r in range(9) for c in range(9))
                    if cell not in session.game.fixed)
    session.game.set(*editable, session.game.solution[editable[0]][editable[1]])
    session.elapsed_seconds = 42
    runtime.games.save(session)
    resumed = runtime.games.new("sudoku", "Fácil", daily=True)
    assert resumed.id == session.id and resumed.elapsed_seconds == 42
    assert resumed.game.board == session.game.board
    with runtime.database.read_connection() as connection:
        assert connection.execute("SELECT count(*) FROM learning_evidence").fetchone()[0] == 0


def test_finished_game_records_only_game_statistics(tmp_path):
    runtime = build_runtime(tmp_path / "profile")
    session = runtime.games.new("sudoku", "Fácil")
    session.game.board = [row[:] for row in session.game.solution]
    session.elapsed_seconds = 75
    runtime.games.save(session)
    runtime.games.finish(session)
    assert runtime.games.statistics()[0]["wins"] == 1
