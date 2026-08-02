from aprendix.application.games import MinesweeperGame, SudokuGame


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
