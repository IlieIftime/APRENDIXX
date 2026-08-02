"""Touch-first Kivy presentation for Sprints 14-16."""

from __future__ import annotations

from functools import partial
import time
import webbrowser

from aprendix_mobile.runtime import MobileRuntime, build_mobile_runtime
from aprendix.application.games import DIFFICULTIES, MinesweeperGame, SudokuGame


def launch_mobile() -> int:
    from kivy.app import App
    from kivy.core.window import Window
    from kivy.graphics import Color, RoundedRectangle
    from kivy.metrics import dp, sp
    from kivy.properties import ListProperty, NumericProperty, ObjectProperty, StringProperty
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
    from kivy.uix.gridlayout import GridLayout
    from kivy.uix.progressbar import ProgressBar
    from kivy.uix.screenmanager import Screen, ScreenManager
    from kivy.uix.scrollview import ScrollView
    from kivy.uix.spinner import Spinner
    from kivy.uix.textinput import TextInput
    from kivy.uix.togglebutton import ToggleButton

    class Surface(BoxLayout):
        background = ListProperty([0.055, 0.075, 0.12, 1])
        radius = NumericProperty(dp(18))
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            with self.canvas.before:
                self._color = Color(*self.background)
                self._shape = RoundedRectangle(pos=self.pos, size=self.size, radius=[self.radius])
            self.bind(pos=self._redraw, size=self._redraw, background=self._redraw)
        def _redraw(self, *_args):
            self._shape.pos, self._shape.size = self.pos, self.size
            self._color.rgba = self.background

    class SwipeCard(Surface):
        on_swipe = ObjectProperty(None, allownone=True)
        on_tap = ObjectProperty(None, allownone=True)
        _start_x = NumericProperty(0)
        _start_y = NumericProperty(0)
        def on_touch_down(self, touch):
            if self.collide_point(*touch.pos): self._start_x, self._start_y = touch.x, touch.y
            return super().on_touch_down(touch)
        def on_touch_up(self, touch):
            if self.collide_point(*touch.pos):
                dx, dy = touch.x - self._start_x, touch.y - self._start_y
                if abs(dx) > dp(72) and abs(dx) >= abs(dy):
                    if self.on_swipe: self.on_swipe("known" if dx > 0 else "again")
                    return True
                if abs(dy) > dp(72):
                    if self.on_swipe: self.on_swipe("theme-prev" if dy > 0 else "theme-next")
                    return True
                if abs(dx) < dp(18) and abs(dy) < dp(18) and self.on_tap:
                    self.on_tap(); return True
            return super().on_touch_up(touch)

    class CardsScreen(Screen):
        def __init__(self, runtime: MobileRuntime, **kwargs):
            super().__init__(**kwargs); self.runtime = runtime; self.index = 0
            self.cards = runtime.cards(); self.revealed: set[str] = set()
            root = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(10))
            header = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(106), spacing=dp(6))
            row_one = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(6))
            row_two = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(6))
            self.mode = Spinner(text="Recomendado", values=("Recomendado", "Livre"))
            self.mode.bind(text=self._mode_changed)
            areas = runtime.areas()
            self._area_ids = {
                ("  " * int(item["depth"]) + ("↳ " if item["depth"] else "") + str(item["title"])): str(item["id"])
                for item in areas
            }
            self.area = Spinner(text="Toda a árvore", values=("Toda a árvore",) + tuple(self._area_ids))
            self.area.bind(text=self._mode_changed)
            theme = Button(text="Claro/Escuro", size_hint_x=.38)
            theme.bind(on_release=lambda *_: App.get_running_app().toggle_theme())
            reference = Button(text="Dicionário", size_hint_x=.34)
            reference.bind(on_release=lambda *_: setattr(self.manager, "current", "glossary"))
            search = Button(text="Pesquisa", size_hint_x=.34)
            search.bind(on_release=lambda *_: setattr(self.manager, "current", "search"))
            games = Button(text="Games", size_hint_x=.28)
            games.bind(on_release=lambda *_: setattr(self.manager, "current", "games"))
            row_one.add_widget(self.mode); row_one.add_widget(self.area)
            row_two.add_widget(search); row_two.add_widget(reference); row_two.add_widget(games); row_two.add_widget(theme)
            header.add_widget(row_one); header.add_widget(row_two)
            root.add_widget(header)
            self.card = SwipeCard(orientation="vertical", padding=dp(20), spacing=dp(12), on_swipe=self._swipe, on_tap=self._flip)
            self.title = Label(font_size=sp(25), bold=True, halign="left", valign="middle", size_hint_y=.22)
            self.title.bind(size=lambda widget, _size: setattr(widget, "text_size", widget.size))
            self.body = Label(font_size=sp(18), halign="left", valign="top")
            self.body.bind(size=lambda widget, _size: setattr(widget, "text_size", widget.size))
            self.code = Label(font_size=sp(16), color=(.55, .9, 1, 1), halign="left", valign="top")
            self.code.bind(size=lambda widget, _size: setattr(widget, "text_size", widget.size))
            self.card.add_widget(self.title); self.card.add_widget(self.body); self.card.add_widget(self.code)
            root.add_widget(self.card)
            actions = BoxLayout(size_hint_y=None, height=dp(58), spacing=dp(8))
            again = Button(text="← Rever", font_size=sp(18)); again.bind(on_release=lambda *_: self._swipe("again"))
            self.practice = Button(text="Praticar", font_size=sp(18)); self.practice.bind(on_release=self._practice)
            known = Button(text="Sei isto →", font_size=sp(18)); known.bind(on_release=lambda *_: self._swipe("known"))
            actions.add_widget(again); actions.add_widget(self.practice); actions.add_widget(known)
            root.add_widget(actions); self.add_widget(root); self._render()

        def _current(self): return self.cards[self.index % len(self.cards)] if self.cards else None
        def _render(self):
            item = self._current()
            if not item:
                self.title.text, self.body.text, self.code.text = "Sem cards", "Altera os filtros.", ""
                return
            self.title.text = str(item["title"])
            if str(item["id"]) in self.revealed:
                sources = self.runtime.sources(str(item["area_id"]))
                self.body.text = "Referências\n\n" + "\n".join(str(source["title"]) for source in sources)
                self.code.text = "Toca em ‘Abrir referência’ para consultar a primeira fonte."
                self.practice.text = "Abrir referência"
            else:
                self.body.text = str(item["body"])
                self.code.text = str(item["code"]) + "\n\nDesliza ←/→ para avaliar · ↑/↓ muda tema · toca para referências"
                self.practice.text = "Praticar"
        def _swipe(self, action):
            if action.startswith("theme-"):
                values = ("Toda a árvore",) + tuple(self._area_ids)
                current = values.index(self.area.text) if self.area.text in values else 0
                self.area.text = values[(current + (1 if action.endswith("next") else -1)) % len(values)]
                return
            item = self._current()
            if item:
                self.runtime.review_card(str(item["id"]), action)
            self.index += 1; self._render()
        def _flip(self):
            item = self._current()
            if not item: return
            identity = str(item["id"])
            self.revealed.remove(identity) if identity in self.revealed else self.revealed.add(identity)
            self._render()
        def _practice(self, *_args):
            item = self._current()
            if not item: return
            if str(item["id"]) in self.revealed:
                sources = self.runtime.sources(str(item["area_id"]))
                if sources: webbrowser.open(str(sources[0]["canonical_url"]))
                return
            if not item.get("exercise_id"):
                self.manager.get_screen("reader").load(str(item["id"]))
                self.manager.current = "reader"
                return
            self.manager.get_screen("ide").load_card(item)
            self.manager.current = "ide"
        def reveal(self, card_id): self.revealed.add(card_id); self._render()
        def _mode_changed(self, *_args):
            mode = "recommended" if self.mode.text == "Recomendado" else "free"
            area_id = self._area_ids.get(self.area.text)
            self.cards, self.index = self.runtime.cards(mode, area_id=area_id), 0; self._render()
    class IdeScreen(Screen):
        def __init__(self, runtime: MobileRuntime, **kwargs):
            super().__init__(**kwargs); self.runtime = runtime; self.item = None
            root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(7))
            top = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
            back = Button(text="‹ Cards", size_hint_x=.25); back.bind(on_release=self._back)
            self.rank = Label(text="Iniciante · 0/10", size_hint_x=.35)
            self.progress = ProgressBar(max=10, value=0)
            top.add_widget(back); top.add_widget(self.rank); top.add_widget(self.progress); root.add_widget(top)
            self.prompt = Label(text="Escolhe um card", size_hint_y=.18, halign="left", valign="middle", font_size=sp(18))
            self.prompt.bind(size=lambda widget, _size: setattr(widget, "text_size", widget.size)); root.add_widget(self.prompt)
            self.editor = TextInput(multiline=True, font_name="RobotoMono", font_size=sp(17),
                background_color=(.02, .025, .04, 1), foreground_color=(.94, .97, 1, 1),
                cursor_color=(.3, .85, 1, 1))
            self.editor.bind(text=lambda *_: self._chips()); root.add_widget(self.editor)
            code_row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(4))
            for token in ("{", "}", "[", "]", ":", "=", "def", "class"):
                button = Button(text=token, font_size=sp(17)); button.bind(on_release=partial(self._insert_raw, token)); code_row.add_widget(button)
            root.add_widget(code_row)
            self.chips = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4)); root.add_widget(self.chips)
            actions = BoxLayout(size_hint_y=None, height=dp(54), spacing=dp(8))
            vary = Button(text="Variar contexto"); vary.bind(on_release=self._vary)
            run = Button(text="Executar e corrigir"); run.bind(on_release=self._run)
            actions.add_widget(vary); actions.add_widget(run); root.add_widget(actions)
            self.output = Label(text="Output local", size_hint_y=.18, halign="left", valign="top")
            self.output.bind(size=lambda widget, _size: setattr(widget, "text_size", widget.size)); root.add_widget(self.output)
            quiz_row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
            self.quiz = Spinner(text="Pergunta teórica", values=())
            answer = Button(text="Validar teoria", size_hint_x=.36); answer.bind(on_release=self._answer_quiz)
            quiz_row.add_widget(self.quiz); quiz_row.add_widget(answer); root.add_widget(quiz_row)
            self.add_widget(root); self._chips()
        def load_card(self, item):
            self.item = item; self.prompt.text = str(item["prompt"])
            self.editor.text = str(item["starter_code"])
            self.quiz.text = str(item["question"])
            self.quiz.values = tuple(
                f"{chr(65 + index)}. {value}" for index, value in enumerate(item["options"])
            )
            self._progress()
        def _insert_raw(self, token, *_args):
            cursor = self.editor.cursor_index(); value = token + (" " if token in {"def", "class"} else "")
            self.editor.text = self.editor.text[:cursor] + value + self.editor.text[cursor:]
            self.editor.cursor = self.editor.get_cursor_from_index(cursor + len(value))
        def _chips(self):
            self.chips.clear_widgets(); cursor = self.editor.cursor_index()
            for token in self.runtime.completion.suggestions(self.editor.text, cursor, limit=6):
                button = Button(text=token, font_size=sp(14)); button.bind(on_release=partial(self._complete, token)); self.chips.add_widget(button)
        def _complete(self, token, *_args):
            text, cursor = self.runtime.completion.insert(self.editor.text, self.editor.cursor_index(), token)
            self.editor.text, self.editor.cursor = text, self.editor.get_cursor_from_index(cursor)
        def _run(self, *_args):
            if not self.item: return
            result, passed = self.runtime.execute(
                str(self.item["exercise_id"]), self.editor.text,
                str(self.item["expected_output"]),
            )
            self.output.text = ("✓ Código aceite\n" if passed else "⚠ Revê o código\n") + (result.stdout or result.error_message or "Sem output")
            if passed: self.manager.get_screen("cards").reveal(str(self.item["id"]))
            self._progress()
        def _answer_quiz(self, *_args):
            if not self.item or self.quiz.text == str(self.item["question"]):
                self.output.text = "Escolhe primeiro uma das respostas."
                return
            index = ord(self.quiz.text[0].lower()) - ord("a")
            passed, explanation = self.runtime.grade_quiz(self.item, index)
            self.output.text = ("✓ Resposta certa\n" if passed else "⚠ Resposta incorreta\n") + explanation
        def _vary(self, *_args):
            if not self.item: return
            contexts = ("finanças pessoais", "jogos offline", "dados locais", "automação doméstica")
            index = (len(self.editor.text) + self.runtime.state.passed_attempts()) % len(contexts)
            self.prompt.text = f"Variação A2 ({contexts[index]}): mantém a mesma estrutura e cria um exemplo novo."
        def _progress(self):
            passed = min(10, self.runtime.state.passed_attempts()); self.progress.value = passed
            self.rank.text = ("Adepto" if passed >= 10 else "Iniciante") + f" · {passed}/10"
        def _back(self, *_args): self.manager.current = "cards"

    class GlossaryScreen(Screen):
        def __init__(self, runtime: MobileRuntime, **kwargs):
            super().__init__(**kwargs); self.runtime = runtime
            root = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(8))
            row = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(8))
            back = Button(text="‹ Cards", size_hint_x=.25)
            back.bind(on_release=lambda *_: setattr(self.manager, "current", "cards"))
            self.query = TextInput(hint_text="Função ou conceito", multiline=False)
            self.query.bind(text=lambda *_: self._render())
            row.add_widget(back); row.add_widget(self.query); root.add_widget(row)
            scroll = ScrollView(do_scroll_x=False, scroll_type=["bars", "content"], bar_width=dp(10))
            self.results = Label(halign="left", valign="top", font_size=sp(18), size_hint_y=None)
            self.results.bind(width=lambda widget, width: setattr(widget, "text_size", (width - dp(12), None)))
            self.results.bind(texture_size=lambda widget, size: setattr(widget, "height", size[1] + dp(20)))
            scroll.add_widget(self.results); root.add_widget(scroll); self.add_widget(root); self._render()
        def _render(self):
            entries = self.runtime.glossary(self.query.text if hasattr(self, "query") else "")
            self.results.text = "\n\n".join(
                f"[b]{item['term']}[/b]  {item['signature']}\n{item['definition']}"
                for item in entries
            ) or "Nenhuma entrada encontrada."
            self.results.markup = True

    class SearchScreen(Screen):
        def __init__(self, runtime: MobileRuntime, **kwargs):
            super().__init__(**kwargs); self.runtime = runtime
            root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(7))
            top = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
            back = Button(text="‹ Cards", size_hint_x=.25)
            back.bind(on_release=lambda *_: setattr(self.manager, "current", "cards"))
            areas = runtime.areas()
            self._area_ids = {
                ("  " * int(item["depth"]) + ("↳ " if item["depth"] else "") + str(item["title"])): str(item["id"])
                for item in areas
            }
            self.area = Spinner(text="Toda a árvore", values=("Toda a árvore",) + tuple(self._area_ids))
            self.area.bind(text=self._area_changed)
            top.add_widget(back); top.add_widget(self.area); root.add_widget(top)
            self.shortcut = Spinner(text="Atalhos recomendados", values=(), size_hint_y=None, height=dp(48))
            self.shortcut.bind(text=self._shortcut_changed); root.add_widget(self.shortcut)
            query_row = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(6))
            self.query = TextInput(hint_text="Tema, método, autor ou aplicação", multiline=False)
            submit = Button(text="Pesquisar", size_hint_x=.3); submit.bind(on_release=self._search)
            query_row.add_widget(self.query); query_row.add_widget(submit); root.add_widget(query_row)
            scroll = ScrollView(do_scroll_x=False, scroll_type=["bars", "content"], bar_width=dp(10)); self.results = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(7))
            self.results.bind(minimum_height=self.results.setter("height")); scroll.add_widget(self.results)
            root.add_widget(scroll); self.add_widget(root); self._area_changed()

        def _area_changed(self, *_args):
            area_id = self._area_ids.get(self.area.text)
            shortcuts = self.runtime.shortcuts(area_id)
            self._shortcut_queries = {str(item["label"]): str(item["query"]) for item in shortcuts}
            self.shortcut.values = tuple(self._shortcut_queries)
            self.shortcut.text = "Atalhos recomendados"

        def _shortcut_changed(self, *_args):
            query = getattr(self, "_shortcut_queries", {}).get(self.shortcut.text)
            if query: self.query.text = query

        def _search(self, *_args):
            self.results.clear_widgets()
            query = self.query.text.strip()
            if not query:
                self.results.add_widget(Label(text="Escreve um tema ou escolhe um atalho.", size_hint_y=None, height=dp(60)))
                return
            hits = self.runtime.search(query, area_id=self._area_ids.get(self.area.text))
            if not hits:
                self.results.add_widget(Label(text="Sem resultados neste ramo.", size_hint_y=None, height=dp(60)))
            for hit in hits:
                label = f"{hit['title']}\n{str(hit['excerpt'])[:230]}"
                button = Button(text=label, halign="left", valign="middle", size_hint_y=None, height=dp(120))
                button.bind(size=lambda widget, _size: setattr(widget, "text_size", (widget.width - dp(20), None)))
                button.bind(on_release=partial(self._open, str(hit["id"])))
                self.results.add_widget(button)

        def _open(self, item_id, *_args):
            self.manager.get_screen("reader").load(item_id, self.query.text)
            self.manager.current = "reader"

    class ReaderScreen(Screen):
        def __init__(self, runtime: MobileRuntime, **kwargs):
            super().__init__(**kwargs); self.runtime = runtime; self.detail = None
            root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(7))
            top = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(5))
            back = Button(text="‹ Pesquisa"); back.bind(on_release=lambda *_: setattr(self.manager, "current", "search"))
            top.add_widget(back)
            for title, mode in (("Resumo", "summary"), ("Simples", "simplified"), ("Normal", "body")):
                button = Button(text=title); button.bind(on_release=partial(self._show, mode)); top.add_widget(button)
            source = Button(text="Fonte"); source.bind(on_release=self._open_source); top.add_widget(source)
            root.add_widget(top)
            self.content = TextInput(readonly=True, font_size=sp(17), padding=dp(12))
            self.content.bind(on_touch_down=self._concept_tap)
            root.add_widget(self.content); self.add_widget(root)

        def load(self, item_id, query=""):
            try:
                self.detail = self.runtime.reading(item_id, query)
                self._show("summary")
            except Exception as exc:
                self.detail = None; self.content.text = f"Leitura indisponível: {exc}"

        def _show(self, mode, *_args):
            if not self.detail: return
            body = str(self.detail[mode])
            self.content.text = f"{self.detail['title']}\n\n{body}\n\nDuplo toque numa palavra para consultar o dicionário."

        def _concept_tap(self, widget, touch):
            if not getattr(touch, "is_double_tap", False) or not widget.collide_point(*touch.pos): return False
            local_x, local_y = widget.to_widget(*touch.pos)
            try:
                column, row = widget.get_cursor_from_xy(local_x, local_y)
                line = widget.text.splitlines()[row]
                import re
                match = next((item for item in re.finditer(r"[A-Za-zÀ-ÿ_][A-Za-zÀ-ÿ0-9_-]*", line)
                              if item.start() <= column <= item.end()), None)
            except (IndexError, AttributeError): match = None
            if match:
                glossary = self.manager.get_screen("glossary"); glossary.query.text = match.group(0)
                self.manager.current = "glossary"; return True
            return False

        def _open_source(self, *_args):
            if self.detail and str(self.detail.get("canonical_url") or "").startswith("https://"):
                webbrowser.open(str(self.detail["canonical_url"]))

    class GamesScreen(Screen):
        def __init__(self, runtime: MobileRuntime, **kwargs):
            super().__init__(**kwargs); self.runtime = runtime
            self.selected, self.flag_mode = None, False
            root = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(5))
            top = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(4))
            back = Button(text="‹ Cards"); back.bind(on_release=lambda *_: setattr(self.manager, "current", "cards"))
            self.kind = Spinner(text="Sudoku", values=("Sudoku", "Minesweeper"))
            self.level = Spinner(text="Fácil", values=DIFFICULTIES)
            new = Button(text="Novo"); new.bind(on_release=self.new)
            top.add_widget(back); top.add_widget(self.kind); top.add_widget(self.level); top.add_widget(new); root.add_widget(top)
            self.status = Label(text="Intervalo sem animações", size_hint_y=None, height=dp(34)); root.add_widget(self.status)
            self.grid = GridLayout(spacing=dp(1)); root.add_widget(self.grid)
            bottom = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(2))
            for value in range(1, 10):
                button = Button(text=str(value)); button.bind(on_release=partial(self.number, value)); bottom.add_widget(button)
            self.mode = Button(text="Revelar"); self.mode.bind(on_release=self.toggle); bottom.add_widget(self.mode)
            root.add_widget(bottom); self.add_widget(root)
            self.kind.bind(text=lambda *_: self.new()); self.level.bind(text=lambda *_: self.new()); self.new()

        def new(self, *_args):
            seed = int(time.time_ns() % 2_147_483_647); self.selected = None
            self.game = SudokuGame(self.level.text, seed) if self.kind.text == "Sudoku" else MinesweeperGame(self.level.text, seed)
            self.mode.disabled = isinstance(self.game, SudokuGame); self.draw()

        def draw(self):
            self.grid.clear_widgets()
            if isinstance(self.game, SudokuGame):
                self.grid.cols = 9
                for row in range(9):
                    for col in range(9):
                        value = self.game.board[row][col]
                        button = Button(text=str(value) if value else "", font_size=sp(15))
                        button.bind(on_release=lambda _b, r=row, c=col: self.pick(r, c)); self.grid.add_widget(button)
            else:
                self.grid.cols = self.game.cols
                for row in range(self.game.rows):
                    for col in range(self.game.cols):
                        cell = (row, col)
                        title = "⚑" if cell in self.game.flagged else ""
                        if cell in self.game.revealed:
                            count = self.game.count(row, col)
                            title = "✹" if cell in self.game.mines else (str(count) if count else "·")
                        button = Button(text=title, font_size=sp(11))
                        button.bind(on_release=lambda _b, r=row, c=col: self.mine(r, c)); self.grid.add_widget(button)

        def pick(self, row, col):
            if (row, col) not in self.game.fixed: self.selected = (row, col)

        def number(self, value, *_args):
            if self.selected and isinstance(self.game, SudokuGame):
                self.game.set(*self.selected, value); self.draw()
                self.status.text = "Sudoku concluído" if self.game.won else "Continua ao teu ritmo"

        def mine(self, row, col):
            self.game.toggle_flag(row, col) if self.flag_mode else self.game.reveal(row, col)
            self.draw(); self.status.text = "Mina encontrada" if self.game.lost else "Concluído" if self.game.won else "Sem animações"

        def toggle(self, *_args):
            self.flag_mode = not self.flag_mode; self.mode.text = "Marcar" if self.flag_mode else "Revelar"

    class AprendixMobileApp(App):
        title = "Aprendix Mobile"
        def build(self):
            self.runtime = build_mobile_runtime()
            self.theme = self.runtime.state.setting("theme", "dark")
            manager = ScreenManager()
            manager.add_widget(CardsScreen(self.runtime, name="cards"))
            manager.add_widget(IdeScreen(self.runtime, name="ide"))
            manager.add_widget(GlossaryScreen(self.runtime, name="glossary"))
            manager.add_widget(SearchScreen(self.runtime, name="search"))
            manager.add_widget(ReaderScreen(self.runtime, name="reader"))
            manager.add_widget(GamesScreen(self.runtime, name="games"))
            self.manager = manager
            self.apply_theme()
            return manager
        def toggle_theme(self):
            self.theme = "light" if self.theme == "dark" else "dark"
            self.runtime.state.set_setting("theme", self.theme); self.apply_theme()
        def apply_theme(self):
            dark = self.theme == "dark"
            Window.clearcolor = (.025, .035, .065, 1) if dark else (.93, .95, .98, 1)
            if not hasattr(self, "manager"): return
            foreground = (.94, .97, 1, 1) if dark else (.08, .11, .18, 1)
            input_bg = (.02, .025, .04, 1) if dark else (1, 1, 1, 1)
            for widget in self.manager.walk():
                if isinstance(widget, Surface):
                    widget.background = [.055, .075, .12, 1] if dark else [1, 1, 1, 1]
                elif isinstance(widget, TextInput):
                    widget.background_color, widget.foreground_color = input_bg, foreground
                elif isinstance(widget, Label):
                    widget.color = foreground
        def on_start(self):
            try:
                from android.permissions import request_permissions
                request_permissions(["android.permission.POST_NOTIFICATIONS"])
            except (ImportError, AttributeError):
                pass

    AprendixMobileApp().run()
    return 0
