"""Native BeeWare/Toga iOS shell sharing the same mobile runtime."""

from __future__ import annotations

import time
import webbrowser


def main():
    import toga
    from toga.style import Pack
    from toga.style.pack import COLUMN, ROW

    from aprendix_mobile.runtime import build_mobile_runtime
    from aprendix.application.games import DIFFICULTIES, MinesweeperGame, SudokuGame

    class AprendixIOS(toga.App):
        def startup(self):
            self.runtime = build_mobile_runtime()
            self.theme = self.runtime.state.setting("theme", "dark")
            self.cards = self.runtime.cards()
            self.index = 0
            self.areas = self.runtime.areas()
            self.area_labels = {
                ("  " * int(item["depth"]) + ("↳ " if item["depth"] else "") + str(item["title"])): str(item["id"])
                for item in self.areas
            }
            self.title_label = toga.Label("", style=Pack(font_size=24, font_weight="bold", margin=10))
            self.body_label = toga.MultilineTextInput(readonly=True, style=Pack(flex=1, margin=10))
            self.mode = toga.Selection(items=["Recomendado", "Livre"], on_change=self.change_mode, style=Pack(flex=1))
            self.area = toga.Selection(items=["Toda a árvore", *self.area_labels], on_change=self.change_mode, style=Pack(flex=2, margin_left=6))
            toolbar = toga.Box(style=Pack(direction=ROW, margin=8), children=[
                self.mode,
                self.area,
                toga.Button("Pesquisa", on_press=self.show_search, style=Pack(margin_left=8)),
                toga.Button("Games", on_press=self.show_games, style=Pack(margin_left=8)),
                toga.Button("Claro/Escuro", on_press=self.toggle_contrast, style=Pack(margin_left=8)),
            ])
            actions = toga.Box(style=Pack(direction=ROW, margin=8), children=[
                toga.Button("← Rever", on_press=lambda _w: self.swipe("again"), style=Pack(flex=1)),
                toga.Button("Praticar", on_press=self.practice, style=Pack(flex=1, margin_left=6)),
                toga.Button("Virar", on_press=self.flip_card, style=Pack(flex=1, margin_left=6)),
                toga.Button("Sei isto →", on_press=lambda _w: self.swipe("known"), style=Pack(flex=1, margin_left=6)),
            ])
            self.cards_box = toga.Box(style=Pack(direction=COLUMN), children=[toolbar, self.title_label, self.body_label, actions])
            self.prompt = toga.Label("", style=Pack(font_size=17, margin=8))
            self.editor = toga.MultilineTextInput(style=Pack(flex=1, margin=8))
            code_row = toga.Box(style=Pack(direction=ROW, margin=6))
            for token in ("{", "}", "[", "]", ":", "=", "def", "class"):
                code_row.add(toga.Button(token, on_press=lambda _w, value=token: self.insert_token(value), style=Pack(flex=1)))
            self.output = toga.MultilineTextInput(readonly=True, style=Pack(height=100, margin=8))
            ide_actions = toga.Box(style=Pack(direction=ROW, margin=8), children=[
                toga.Button("‹ Cards", on_press=self.back, style=Pack(flex=1)),
                toga.Button("Executar e corrigir", on_press=self.run_code, style=Pack(flex=2, margin_left=6)),
            ])
            self.ide_box = toga.Box(style=Pack(direction=COLUMN), children=[self.prompt, self.editor, code_row, ide_actions, self.output])
            self.search_query = toga.TextInput(placeholder="Tema, método, autor ou aplicação", style=Pack(flex=1))
            self.search_area = toga.Selection(items=["Toda a árvore", *self.area_labels], style=Pack(flex=1, margin_left=6))
            search_controls = toga.Box(style=Pack(direction=ROW, margin=8), children=[
                toga.Button("‹ Cards", on_press=self.back, style=Pack(margin_right=6)),
                self.search_query, self.search_area,
                toga.Button("Pesquisar", on_press=self.do_search, style=Pack(margin_left=6)),
            ])
            self.search_results = toga.Selection(items=[], on_change=self.open_search_result, style=Pack(margin=8))
            self.search_preview = toga.MultilineTextInput(readonly=True, style=Pack(flex=1, margin=8))
            self.search_box = toga.Box(style=Pack(direction=COLUMN), children=[search_controls, self.search_results, self.search_preview])
            self.reader_title = toga.Label("", style=Pack(font_size=22, font_weight="bold", margin=8))
            self.reader_content = toga.MultilineTextInput(readonly=True, style=Pack(flex=1, margin=8))
            reader_controls = toga.Box(style=Pack(direction=ROW, margin=8), children=[
                toga.Button("‹ Pesquisa", on_press=self.show_search, style=Pack(flex=1)),
                toga.Button("Resumo", on_press=lambda _w: self.reader_mode("summary"), style=Pack(flex=1)),
                toga.Button("Simples", on_press=lambda _w: self.reader_mode("simplified"), style=Pack(flex=1)),
                toga.Button("Normal", on_press=lambda _w: self.reader_mode("body"), style=Pack(flex=1)),
            ])
            self.reader_box = toga.Box(style=Pack(direction=COLUMN), children=[reader_controls, self.reader_title, self.reader_content])
            self.game_kind = toga.Selection(items=["Sudoku", "Minesweeper"], style=Pack(flex=1))
            self.game_level = toga.Selection(items=list(DIFFICULTIES), style=Pack(flex=1, margin_left=6))
            self.game_status = toga.Label("Intervalo sem animações", style=Pack(margin=8))
            self.game_grid = toga.Box(style=Pack(direction=COLUMN, flex=1, margin=4))
            game_controls = toga.Box(style=Pack(direction=ROW, margin=8), children=[
                toga.Button("‹ Cards", on_press=self.back), self.game_kind, self.game_level,
                toga.Button("Novo", on_press=self.new_game, style=Pack(margin_left=6)),
                toga.Button("Marcar/Revelar", on_press=self.toggle_game_mode, style=Pack(margin_left=6)),
            ])
            keypad = toga.Box(style=Pack(direction=ROW, margin=4))
            for value in range(1, 10):
                keypad.add(toga.Button(str(value), on_press=lambda _w, number=value: self.game_number(number), style=Pack(flex=1)))
            self.games_box = toga.Box(style=Pack(direction=COLUMN), children=[
                game_controls, self.game_status, toga.ScrollContainer(content=self.game_grid, style=Pack(flex=1)), keypad,
            ])
            self.main_window = toga.MainWindow(title=self.formal_name)
            self.main_window.content = self.cards_box
            self.render(); self.toggle_contrast(None, initialise=True); self.main_window.show()

        def current(self):
            return self.cards[self.index % len(self.cards)] if self.cards else None
        def render(self):
            item = self.current()
            self.title_label.text = str(item["title"]) if item else "Sem cards"
            self.body_label.value = str(item["body"]) if item else "Altera os filtros."
        def swipe(self, action):
            item = self.current()
            if item: self.runtime.review_card(str(item["id"]), action)
            self.index += 1; self.render()
        def change_mode(self, _widget):
            area_id = self.area_labels.get(str(self.area.value))
            self.cards = self.runtime.cards(
                "recommended" if self.mode.value == "Recomendado" else "free",
                area_id=area_id,
            )
            self.index = 0; self.render()
        def practice(self, _widget):
            item = self.current()
            if not item: return
            if not item.get("exercise_id"):
                self.open_reader(str(item["id"])); return
            self.prompt.text = str(item["prompt"])
            self.editor.value = str(item["starter_code"]); self.main_window.content = self.ide_box
        def flip_card(self, _widget):
            item = self.current()
            if not item: return
            sources = self.runtime.sources(str(item["area_id"]))
            self.body_label.value = "Referências\n\n" + "\n".join(
                f"{source['title']}\n{source['canonical_url']}" for source in sources
            ) if sources else "Sem referências para este tema."
        def insert_token(self, token):
            self.editor.value = (self.editor.value or "") + token + (" " if token in {"def", "class"} else "")
        def run_code(self, _widget):
            item = self.current()
            result, passed = self.runtime.execute(
                str(item["exercise_id"]), self.editor.value or "",
                str(item["expected_output"]),
            )
            self.output.value = ("Código aceite\n" if passed else "Revê o código\n") + (result.stdout or result.error_message or "Sem output")
            if passed: self.body_label.value = str(item["body"]) + "\n\n" + str(item["code"])
        def back(self, _widget): self.main_window.content = self.cards_box
        def show_search(self, _widget): self.main_window.content = self.search_box
        def do_search(self, _widget):
            self.search_hits = self.runtime.search(
                self.search_query.value or "",
                area_id=self.area_labels.get(str(self.search_area.value)),
            )
            self.search_labels = {f"{item['title']} · {item['score']:.0%}": str(item["id"]) for item in self.search_hits}
            self.search_results.items = list(self.search_labels)
            self.search_preview.value = "\n\n".join(
                f"{item['title']}\n{item['excerpt']}" for item in self.search_hits[:8]
            ) or "Sem resultados neste ramo."
        def open_search_result(self, _widget):
            item_id = getattr(self, "search_labels", {}).get(str(self.search_results.value))
            if item_id: self.open_reader(item_id)
        def open_reader(self, item_id):
            self.reader_detail = self.runtime.reading(item_id, self.search_query.value or "")
            self.reader_title.text = str(self.reader_detail["title"])
            self.reader_mode("summary"); self.main_window.content = self.reader_box
        def reader_mode(self, mode):
            if not getattr(self, "reader_detail", None): return
            body = str(self.reader_detail[mode])
            concepts = self.reader_detail.get("concepts", ())
            if concepts:
                body += "\n\nTutor de conceitos\n" + "\n\n".join(
                    f"{item['term']} · {item['signature']}\n{item['definition']}" for item in concepts
                )
            self.reader_content.value = body
        def show_games(self, _widget):
            self.main_window.content = self.games_box
            self.new_game(None)
        def new_game(self, _widget):
            kind = str(self.game_kind.value or "Sudoku")
            level = str(self.game_level.value or DIFFICULTIES[0])
            seed = int(time.time_ns() % 2_147_483_647)
            self.game = SudokuGame(level, seed) if kind == "Sudoku" else MinesweeperGame(level, seed)
            self.game_selected, self.game_flag_mode = None, False
            self.game_status.text = f"{kind} · {level} · sem animações"
            self.draw_game()
        def draw_game(self):
            self.game_grid.clear()
            rows, cols = (9, 9) if isinstance(self.game, SudokuGame) else (self.game.rows, self.game.cols)
            for row in range(rows):
                line = toga.Box(style=Pack(direction=ROW))
                for col in range(cols):
                    if isinstance(self.game, SudokuGame):
                        value = self.game.board[row][col]; title = str(value) if value else " "
                        callback = lambda _w, r=row, c=col: self.pick_game(r, c)
                    else:
                        cell = (row, col); title = "⚑" if cell in self.game.flagged else " "
                        if cell in self.game.revealed:
                            count = self.game.count(row, col)
                            title = "✹" if cell in self.game.mines else (str(count) if count else "·")
                        callback = lambda _w, r=row, c=col: self.play_mine(r, c)
                    line.add(toga.Button(title, on_press=callback, style=Pack(flex=1)))
                self.game_grid.add(line)
        def pick_game(self, row, col):
            if (row, col) not in self.game.fixed: self.game_selected = (row, col)
        def game_number(self, number):
            if isinstance(self.game, SudokuGame) and self.game_selected:
                self.game.set(*self.game_selected, number); self.draw_game()
                if self.game.won: self.game_status.text = "Sudoku concluído."
        def play_mine(self, row, col):
            self.game.toggle_flag(row, col) if self.game_flag_mode else self.game.reveal(row, col)
            self.draw_game()
            if self.game.lost: self.game_status.text = "Encontraste uma mina."
            elif self.game.won: self.game_status.text = "Minesweeper concluído."
        def toggle_game_mode(self, _widget):
            self.game_flag_mode = not getattr(self, "game_flag_mode", False)
        def toggle_contrast(self, _widget, initialise=False):
            # Native controls retain system Dynamic Type and VoiceOver semantics.
            if not initialise:
                self.theme = "light" if self.theme == "dark" else "dark"
                self.runtime.state.set_setting("theme", self.theme)
            colour = "#07101F" if self.theme == "dark" else "#F3F6FA"
            self.cards_box.style.background_color = colour
            self.ide_box.style.background_color = colour
            self.search_box.style.background_color = colour
            self.reader_box.style.background_color = colour

    return AprendixIOS("Aprendix", "io.aprendix.mobile")
