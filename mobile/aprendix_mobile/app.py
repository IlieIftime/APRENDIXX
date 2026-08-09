"""Touch-first Kivy presentation for Sprints 14-16."""

from __future__ import annotations

from functools import partial
import time
import webbrowser
import threading
from pathlib import Path

from aprendix_mobile.runtime import MobileRuntime, build_mobile_runtime
from aprendix.application.games import DIFFICULTIES, MinesweeperGame, SudokuGame
from aprendix.application.navigation import NavigationHistory, Route
from aprendix_mobile.contracts import SnippetAction, SnippetRequestDTO
from aprendix_mobile.documents import document_portal


def launch_mobile() -> int:
    from kivy.app import App
    from kivy.core.window import Window
    from kivy.clock import Clock
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
    from kivy.uix.checkbox import CheckBox

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

    class CourseScreen(Screen):
        def __init__(self, runtime: MobileRuntime, **kwargs):
            super().__init__(**kwargs); self.runtime = runtime
            root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(7))
            courses = runtime.courses()
            self._slugs = {str(item["title"]): str(item["slug"]) for item in courses}
            self.track = Spinner(text=next(iter(self._slugs), "Curso"), values=tuple(self._slugs),
                                 size_hint_y=None, height=dp(52))
            self.track.bind(text=lambda *_: self.render()); root.add_widget(self.track)
            scroll = ScrollView(do_scroll_x=False, scroll_type=["bars", "content"], bar_width=dp(10))
            self.column = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8))
            self.column.bind(minimum_height=self.column.setter("height")); scroll.add_widget(self.column)
            root.add_widget(scroll); self.add_widget(root); self.render()

        def render(self):
            self.column.clear_widgets(); completed = set(self.runtime.state.completed_units())
            for unit in self.runtime.course_units(self._slugs.get(self.track.text, "")):
                card = Surface(orientation="vertical", padding=dp(12), spacing=dp(6),
                               size_hint_y=None, height=dp(250))
                card.add_widget(Label(text=str(unit["title"]), bold=True, font_size=sp(20),
                                      halign="left", text_size=(Window.width-dp(60), None)))
                card.add_widget(Label(text=str(unit["objective"]) + "\n\n" + str(unit["explanation"]),
                                      halign="left", valign="top", text_size=(Window.width-dp(60), None)))
                title = "Concluída ✓" if unit["slug"] in completed else "Marcar prática concluída"
                button = Button(text=title, disabled=unit["slug"] in completed, size_hint_y=None, height=dp(44))
                button.bind(on_release=partial(self.complete, str(unit["slug"])))
                card.add_widget(button); self.column.add_widget(card)

        def complete(self, slug, *_args):
            self.runtime.complete_unit(slug); self.render()

    class ProgressScreen(Screen):
        def __init__(self, runtime: MobileRuntime, **kwargs):
            super().__init__(**kwargs); self.runtime = runtime
            self.root_box = BoxLayout(orientation="vertical", padding=dp(18), spacing=dp(12))
            self.add_widget(self.root_box)

        def on_pre_enter(self, *_args):
            self.root_box.clear_widgets()
            complete = len(self.runtime.state.completed_units())
            total = sum(int(item["unit_count"]) for item in self.runtime.courses())
            passed = self.runtime.state.passed_attempts()
            self.root_box.add_widget(Label(text="O teu progresso local", font_size=sp(28), bold=True,
                                           size_hint_y=None, height=dp(62)))
            panel = Surface(orientation="vertical", padding=dp(18), spacing=dp(10), size_hint_y=None, height=dp(240))
            panel.add_widget(Label(text=f"Unidades praticadas: {complete}/{total}", font_size=sp(21)))
            bar = ProgressBar(max=max(1, total), value=complete); panel.add_widget(bar)
            panel.add_widget(Label(text=f"Exercícios distintos aprovados: {passed}\n"
                                        "Os jogos não alteram este progresso.", font_size=sp(18)))
            self.root_box.add_widget(panel)
            self.root_box.add_widget(Label(text="O próximo passo recomendado é continuar a primeira unidade não concluída.",
                                           halign="left", valign="top", text_size=(Window.width-dp(40), None)))

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
            for token in ("(", ")", "[", "]", "{", "}", ":", "_", "=", "⇥"):
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
            if token == "⇥":
                token = "    "
            cursor = self.editor.cursor_index(); value = token + (" " if token in {"def", "class"} else "")
            self.editor.text = self.editor.text[:cursor] + value + self.editor.text[cursor:]
            self.editor.cursor = self.editor.get_cursor_from_index(cursor + len(value))

        def on_pre_enter(self, *_args):
            self._set_landscape(True)

        def on_pre_leave(self, *_args):
            self._set_landscape(False)

        @staticmethod
        def _set_landscape(enabled):
            try:
                import os
                if os.environ.get("ANDROID_ARGUMENT"):
                    from jnius import autoclass
                    autoclass("io.aprendix.mobile.AprendixNativeBridge").setEditorLandscape(enabled)
            except (ImportError, RuntimeError):
                pass
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

    class AnalyzerScreen(Screen):
        def __init__(self, runtime: MobileRuntime, **kwargs):
            super().__init__(**kwargs); self.runtime = runtime; self.ocr_pending = False
            self.portal = document_portal(runtime.paths.cache); self._temporary_image = None
            root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(7))
            top = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(5))
            self.action = Spinner(text="Explicar", values=("Explicar", "Converter Python", "Problemas", "Testes"))
            self.image_path = TextInput(hint_text="Imagem da galeria/câmara", multiline=False)
            top.add_widget(self.action); top.add_widget(self.image_path); root.add_widget(top)
            image_actions = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(5))
            gallery = Button(text="Galeria"); gallery.bind(on_release=self.pick_image)
            camera = Button(text="Câmara"); camera.bind(on_release=self.capture_image)
            extract = Button(text="Extrair OCR"); extract.bind(on_release=self.extract)
            image_actions.add_widget(gallery); image_actions.add_widget(camera); image_actions.add_widget(extract)
            root.add_widget(image_actions)
            self.input = TextInput(hint_text="Código ou pseudocódigo", multiline=True)
            root.add_widget(self.input)
            confirm = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
            self.confirmed = CheckBox(size_hint_x=None, width=dp(44))
            confirm.add_widget(self.confirmed); confirm.add_widget(Label(text="Confirmei o OCR", halign="left"))
            analyze = Button(text="Analisar localmente"); analyze.bind(on_release=self.analyze)
            confirm.add_widget(analyze); root.add_widget(confirm)
            self.output = TextInput(readonly=True, font_size=sp(16)); root.add_widget(self.output)
            self.add_widget(root)

        def pick_image(self, *_args):
            try: self.portal.import_image(self._image_received)
            except Exception as exc: self.output.text = str(exc)

        def capture_image(self, *_args):
            try: self.portal.capture_image(self._image_received)
            except Exception as exc: self.output.text = str(exc)

        def _image_received(self, path, error):
            if error or path is None:
                self.output.text = error or "Operação cancelada."; return
            self._temporary_image = Path(path)
            self.image_path.text = str(path)
            self.extract()

        def extract(self, *_args):
            if not self.image_path.text.strip(): return
            self.output.text = "OCR local…"; self.ocr_pending = True; self.confirmed.active = False
            threading.Thread(target=self._extract, daemon=True).start()

        def _extract(self):
            try:
                draft = self.runtime.extract_image(Path(self.image_path.text))
                Clock.schedule_once(lambda _dt: self._ocr_ready(draft), 0)
            except Exception as exc:
                Clock.schedule_once(lambda _dt, message=str(exc): setattr(self.output, "text", message), 0)
            finally:
                if self._temporary_image is not None:
                    try: self._temporary_image.unlink(missing_ok=True)
                    except OSError: pass
                    self._temporary_image = None

        def _ocr_ready(self, draft):
            self.input.text = draft.text
            self.output.text = f"OCR {draft.confidence:.0%}. Confirma caracteres e indentação."

        def analyze(self, *_args):
            if self.ocr_pending and not self.confirmed.active:
                self.output.text = "Confirma primeiro o texto OCR."; return
            actions = {"Explicar": SnippetAction.EXPLAIN, "Converter Python": SnippetAction.TO_PYTHON,
                       "Problemas": SnippetAction.FIND_PROBLEMS, "Testes": SnippetAction.CREATE_TESTS}
            try:
                result = self.runtime.analyze_snippet(SnippetRequestDTO(
                    text=self.input.text, action=actions[self.action.text],
                    ocr_confirmed=not self.ocr_pending or self.confirmed.active,
                ))
                body = result.summary + "\n\n" + "\n".join(result.line_explanations[:30])
                if result.problems: body += "\n\nProblemas\n• " + "\n• ".join(result.problems)
                if result.suggested_tests: body += "\n\nTestes\n• " + "\n• ".join(result.suggested_tests)
                if result.proposed_code: body += "\n\nPython proposto (não executado)\n" + result.proposed_code
                self.output.text = body
            except Exception as exc: self.output.text = str(exc)

    class TutorScreen(Screen):
        def __init__(self, runtime: MobileRuntime, **kwargs):
            super().__init__(**kwargs); self.runtime = runtime
            root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
            top = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(7))
            back = Button(text="‹ Mais", size_hint_x=.25)
            back.bind(on_release=lambda *_: setattr(self.manager, "current", "more"))
            self.strategy = Spinner(
                text="Explicar", values=("Explicar", "Pergunta socrática", "Simplificar"),
            )
            top.add_widget(back); top.add_widget(self.strategy); root.add_widget(top)
            self.question = TextInput(
                hint_text="Pergunta sobre o conteúdo local…", multiline=True,
                size_hint_y=.25, font_size=sp(17),
            )
            root.add_widget(self.question)
            ask = Button(text="Pedir orientação local", size_hint_y=None, height=dp(52))
            ask.bind(on_release=self.ask); root.add_widget(ask)
            self.output = TextInput(readonly=True, font_size=sp(16))
            root.add_widget(self.output); self.add_widget(root)

        def ask(self, *_args):
            if not self.question.text.strip(): return
            self.output.text = "A recuperar evidência aprovada…"
            threading.Thread(target=self._worker, daemon=True).start()

        def _worker(self):
            try:
                strategy = {
                    "Explicar": "explain", "Pergunta socrática": "socratic",
                    "Simplificar": "simplify",
                }[self.strategy.text]
                result = self.runtime.ask_tutor(self.question.text, strategy=strategy)
                evidence = "\n".join(
                    f"• {item['title']}: {item['excerpt']}" for item in result["evidence"]
                )
                message = (
                    f"Confiança {result['confidence']:.0%}\n\n{result['answer']}"
                    + (f"\n\nEvidência local\n{evidence}" if evidence else "")
                )
            except Exception as exc:
                message = f"Tutor indisponível: {exc}"
            Clock.schedule_once(lambda _dt: setattr(self.output, "text", message), 0)

    class ProjectsScreen(Screen):
        def __init__(self, runtime: MobileRuntime, **kwargs):
            super().__init__(**kwargs); self.runtime = runtime; self.project_id = None
            root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(7))
            top = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
            back = Button(text="‹ Mais", size_hint_x=.22)
            back.bind(on_release=lambda *_: setattr(self.manager, "current", "more"))
            self.selector = Spinner(text="Novo projeto", values=())
            self.selector.bind(text=self.load); top.add_widget(back); top.add_widget(self.selector)
            root.add_widget(top)
            metadata = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
            self.name = TextInput(text="Projeto Python", multiline=False)
            self.path = TextInput(text="main.py", multiline=False)
            metadata.add_widget(self.name); metadata.add_widget(self.path); root.add_widget(metadata)
            self.editor = TextInput(
                text='"""Projeto local."""\n', multiline=True, font_name="RobotoMono",
                font_size=sp(16),
            )
            root.add_widget(self.editor)
            actions = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(7))
            save = Button(text="Guardar cifrado"); save.bind(on_release=self.save)
            run = Button(text="Executar isolado"); run.bind(on_release=self.run)
            actions.add_widget(save); actions.add_widget(run); root.add_widget(actions)
            self.output = Label(
                text="Guardado apenas neste dispositivo.", size_hint_y=.16,
                halign="left", valign="top",
            )
            self.output.bind(size=lambda widget, _size: setattr(widget, "text_size", widget.size))
            root.add_widget(self.output); self.add_widget(root); self.refresh()

        def refresh(self):
            self._projects = self.runtime.projects()
            self._by_title = {
                f"{item['name']} · {item['relative_path']}": item for item in self._projects
            }
            self.selector.values = ("Novo projeto",) + tuple(self._by_title)

        def load(self, _spinner, title):
            if title == "Novo projeto":
                self.project_id = None; return
            item = self._by_title.get(title)
            if not item: return
            self.project_id = item["id"]; self.name.text = item["name"]
            self.path.text = item["relative_path"]; self.editor.text = item["source"]

        def save(self, *_args):
            try:
                item = self.runtime.save_project(
                    self.name.text, self.editor.text, project_id=self.project_id,
                    relative_path=self.path.text,
                )
                self.project_id = item["id"]; self.output.text = "Projeto cifrado e guardado."
                self.refresh()
            except Exception as exc: self.output.text = f"Não foi possível guardar: {exc}"

        def run(self, *_args):
            result = self.runtime.executor.run(self.editor.text)
            self.output.text = result.stdout or result.error_message or result.status

    class MoreScreen(Screen):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            root = BoxLayout(orientation="vertical", padding=dp(18), spacing=dp(12))
            root.add_widget(Label(
                text="Mais ferramentas", bold=True, font_size=sp(28),
                size_hint_y=None, height=dp(62),
            ))
            grid = GridLayout(cols=2, spacing=dp(10))
            for title, screen in (
                ("Tutor offline", "tutor"), ("Projetos", "projects"),
                ("Dicionário", "glossary"), ("Analisar trecho", "analyzer"),
                ("Games", "games"), ("Dados e perfil", "data"),
            ):
                button = Button(text=title, font_size=sp(18))
                button.bind(
                    on_release=lambda _button, target=screen:
                    setattr(self.manager, "current", target)
                )
                grid.add_widget(button)
            root.add_widget(grid); self.add_widget(root)

    class DataScreen(Screen):
        def __init__(self, runtime: MobileRuntime, **kwargs):
            super().__init__(**kwargs); self.runtime = runtime
            self.portal = document_portal(runtime.paths.cache)
            root = BoxLayout(orientation="vertical", padding=dp(18), spacing=dp(10))
            root.add_widget(Label(text="Perfil portátil", bold=True, font_size=sp(27),
                                  size_hint_y=None, height=dp(60)))
            root.add_widget(Label(
                text="Transfere progresso entre dispositivos sem conta nem cloud. "
                     "O ficheiro é cifrado e autenticado.",
                halign="left", valign="top", text_size=(Window.width-dp(40), None),
                size_hint_y=None, height=dp(90),
            ))
            self.passphrase = TextInput(
                password=True, multiline=False, hint_text="Frase-passe (mínimo 10 caracteres)",
                size_hint_y=None, height=dp(52),
            )
            root.add_widget(self.passphrase)
            export = Button(text="Exportar perfil…", size_hint_y=None, height=dp(52))
            preview = Button(text="Antever importação…", size_hint_y=None, height=dp(52))
            import_button = Button(text="Importar e fundir…", size_hint_y=None, height=dp(52))
            export.bind(on_release=self.export_profile); preview.bind(on_release=self.preview_profile)
            import_button.bind(on_release=self.import_profile)
            root.add_widget(export); root.add_widget(preview); root.add_widget(import_button)
            self.status = Label(text="Os conflitos são resolvidos de forma determinística e mostrados antes.",
                                halign="left", valign="top", text_size=(Window.width-dp(40), None))
            root.add_widget(self.status); self.add_widget(root)

        def _secret(self):
            if len(self.passphrase.text) < 10:
                self.status.text = "A frase-passe precisa de pelo menos 10 caracteres."
                return None
            return self.passphrase.text

        def export_profile(self, *_args):
            secret = self._secret()
            if secret is None: return
            try:
                temporary = self.runtime.export_profile(
                    self.runtime.paths.cache / "Aprendix-perfil.apxprofile", secret
                )
                self.portal.export_file(temporary, self._exported)
            except Exception as exc: self.status.text = str(exc)

        def _exported(self, _path, error):
            self.status.text = error or "Perfil exportado pelo seletor de documentos."

        def preview_profile(self, *_args):
            secret = self._secret()
            if secret is None: return
            try: self.portal.import_file(lambda path, error: self._received(path, error, secret, False))
            except Exception as exc: self.status.text = str(exc)

        def import_profile(self, *_args):
            secret = self._secret()
            if secret is None: return
            try: self.portal.import_file(lambda path, error: self._received(path, error, secret, True))
            except Exception as exc: self.status.text = str(exc)

        def _received(self, path, error, secret, commit):
            if error or path is None:
                self.status.text = error or "Operação cancelada."; return
            try:
                result = self.runtime.import_profile(path, secret) if commit else self.runtime.preview_profile(path, secret)
                self.status.text = ("Importado: " if commit else "Antevisão: ") + str(result)
            except Exception as exc: self.status.text = str(exc)
            finally:
                try: Path(path).unlink(missing_ok=True)
                except OSError: pass

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
            resume_row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(4))
            resume = Button(text="Retomar"); resume.bind(on_release=self.resume)
            daily = Button(text="Diário"); daily.bind(on_release=self.daily)
            stats = Button(text="Estatísticas"); stats.bind(on_release=self.statistics)
            resume_row.add_widget(resume); resume_row.add_widget(daily); resume_row.add_widget(stats); root.add_widget(resume_row)
            self.status = Label(text="Intervalo sem animações", size_hint_y=None, height=dp(34)); root.add_widget(self.status)
            pause_row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(4))
            pause_row.add_widget(Label(text="Pausa", size_hint_x=.24))
            self.pause_minutes = Spinner(
                text="10 min", values=("Sem limite", "5 min", "10 min", "15 min")
            )
            pause_row.add_widget(self.pause_minutes); root.add_widget(pause_row)
            self.grid = GridLayout(spacing=dp(1)); root.add_widget(self.grid)
            bottom = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(2))
            for value in range(1, 10):
                button = Button(text=str(value)); button.bind(on_release=partial(self.number, value)); bottom.add_widget(button)
            self.mode = Button(text="Revelar"); self.mode.bind(on_release=self.toggle); bottom.add_widget(self.mode)
            root.add_widget(bottom); self.add_widget(root)
            self.kind.bind(text=lambda *_: self.new()); self.level.bind(text=lambda *_: self.new()); self.new()
            Clock.schedule_interval(self._tick, 1)

        def new(self, *_args):
            self.selected = None
            self.session = self.runtime.games.new(self._game_key(), self.level.text)
            self.game = self.session.game; self._last_tick = time.monotonic()
            self._pause_notified = False
            self.mode.disabled = isinstance(self.game, SudokuGame); self.draw()

        def _game_key(self): return "sudoku" if self.kind.text == "Sudoku" else "minesweeper"

        def resume(self, *_args):
            session = self.runtime.games.resume(self._game_key(), self.level.text)
            if session is None: self.status.text = "Sem jogo guardado."; return
            self.session, self.game = session, session.game; self._last_tick = time.monotonic(); self.draw()
            self._pause_notified = False

        def daily(self, *_args):
            self.session = self.runtime.games.new(self._game_key(), self.level.text, daily=True)
            self.game = self.session.game; self._last_tick = time.monotonic(); self.draw()
            self._pause_notified = False
            self.status.text = "Desafio diário local"

        def statistics(self, *_args):
            rows = self.runtime.games.statistics()
            self.status.text = " · ".join(f"{row['game']} {row['wins']}/{row['plays']}" for row in rows) or "Sem jogos terminados"

        def _save(self):
            if hasattr(self, "session"):
                self.session.elapsed_seconds += max(0, int(time.monotonic() - self._last_tick))
                self._last_tick = time.monotonic(); self.runtime.games.save(self.session)

        def _tick(self, _dt):
            if not hasattr(self, "session"):
                return
            elapsed = self.session.elapsed_seconds + max(0, int(time.monotonic() - self._last_tick))
            selected = self.pause_minutes.text
            if selected != "Sem limite":
                goal = int(selected.split()[0]) * 60
                if elapsed >= goal and not self._pause_notified:
                    self._pause_notified = True
                    self.status.text = "Pausa terminada · regressa ao teu melhor próximo passo quando quiseres."
                    self.runtime.haptics.emit("success")
                elif not self._pause_notified:
                    remaining = max(0, goal - elapsed)
                    self.status.text = f"Pausa · {remaining // 60:02d}:{remaining % 60:02d} restantes"
            if elapsed and elapsed % 30 == 0:
                self._save()

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
                self._save()
                if self.game.won: self.runtime.games.finish(self.session)

        def mine(self, row, col):
            self.game.toggle_flag(row, col) if self.flag_mode else self.game.reveal(row, col)
            self.draw(); self.status.text = "Mina encontrada" if self.game.lost else "Concluído" if self.game.won else "Sem animações"
            self._save()
            if self.game.lost or self.game.won: self.runtime.games.finish(self.session)

        def toggle(self, *_args):
            self.flag_mode = not self.flag_mode; self.mode.text = "Marcar" if self.flag_mode else "Revelar"

    class AprendixMobileApp(App):
        title = "Aprendix Mobile"
        def build(self):
            self.runtime = build_mobile_runtime()
            self.theme = self.runtime.state.setting("theme", "dark")
            if self.theme not in {"dark", "light", "contrast"}: self.theme = "dark"
            manager = ScreenManager()
            manager.add_widget(CardsScreen(self.runtime, name="cards"))
            manager.add_widget(CourseScreen(self.runtime, name="curriculum"))
            manager.add_widget(ProgressScreen(self.runtime, name="dashboard"))
            manager.add_widget(IdeScreen(self.runtime, name="ide"))
            manager.add_widget(GlossaryScreen(self.runtime, name="glossary"))
            manager.add_widget(SearchScreen(self.runtime, name="search"))
            manager.add_widget(ReaderScreen(self.runtime, name="reader"))
            manager.add_widget(GamesScreen(self.runtime, name="games"))
            manager.add_widget(AnalyzerScreen(self.runtime, name="analyzer"))
            manager.add_widget(TutorScreen(self.runtime, name="tutor"))
            manager.add_widget(ProjectsScreen(self.runtime, name="projects"))
            manager.add_widget(MoreScreen(name="more"))
            manager.add_widget(DataScreen(self.runtime, name="data"))
            self.manager = manager
            route_to_screen = {
                Route.CARDS: "cards", Route.IDE: "ide", Route.SEARCH: "search",
                Route.DICTIONARY: "glossary", Route.GAMES: "games", Route.READER: "reader",
                Route.CURRICULUM: "curriculum", Route.DASHBOARD: "dashboard",
                Route.ANALYZER: "analyzer",
                Route.TUTOR: "tutor", Route.PROJECTS: "projects",
                Route.DATA: "data",
            }
            self._route_to_screen = route_to_screen
            self._screen_to_route = {screen: route for route, screen in route_to_screen.items()}
            stored = self.runtime.state.setting("last_screen", "cards")
            if stored not in self._screen_to_route or stored == "reader": stored = "cards"
            self.history = NavigationHistory(self._screen_to_route[stored])
            manager.current = stored
            manager.bind(current=self._screen_changed)
            root = BoxLayout(orientation="vertical")
            root.add_widget(manager)
            nav = BoxLayout(size_hint_y=None, height=dp(58), spacing=dp(3), padding=dp(3))
            for route, title in (
                (Route.CARDS, "Cards"), (Route.CURRICULUM, "Curso"),
                (Route.IDE, "IDE"), (Route.SEARCH, "Pesquisa"),
                (Route.DASHBOARD, "Progresso"),
            ):
                button = Button(text=title, font_size=sp(14))
                button.bind(on_release=lambda _button, target=route: self.go(target))
                nav.add_widget(button)
            more = Button(text="Mais", font_size=sp(14))
            more.bind(on_release=lambda *_: setattr(manager, "current", "more"))
            nav.add_widget(more)
            root.add_widget(nav)
            Window.bind(on_keyboard=self._keyboard)
            self.apply_theme()
            return root
        def go(self, route):
            target = self.history.navigate(route)
            self.manager.current = self._route_to_screen[target]
        def _screen_changed(self, _manager, screen):
            route = self._screen_to_route.get(screen)
            if route is not None and route != self.history.current:
                self.history.navigate(route)
            self.runtime.state.set_setting("last_screen", screen)
        def _keyboard(self, _window, key, *_args):
            if key != 27 or not self.history.can_go_back: return False
            self.manager.current = self._route_to_screen[self.history.back()]
            return True
        def toggle_theme(self):
            order = ("dark", "light", "contrast")
            self.theme = order[(order.index(self.theme) + 1) % len(order)]
            self.runtime.state.set_setting("theme", self.theme); self.apply_theme()
        def apply_theme(self):
            dark, contrast = self.theme == "dark", self.theme == "contrast"
            Window.clearcolor = (0, 0, 0, 1) if contrast else ((.025, .035, .065, 1) if dark else (.93, .95, .98, 1))
            if not hasattr(self, "manager"): return
            foreground = (1, 1, 1, 1) if contrast else ((.94, .97, 1, 1) if dark else (.08, .11, .18, 1))
            input_bg = (.04, .04, .04, 1) if contrast else ((.02, .025, .04, 1) if dark else (1, 1, 1, 1))
            for widget in self.manager.walk():
                if isinstance(widget, Surface):
                    widget.background = ([.04, .04, .04, 1] if contrast else ([.055, .075, .12, 1] if dark else [1, 1, 1, 1]))
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
        def on_stop(self):
            Window.unbind(on_keyboard=self._keyboard)

    AprendixMobileApp().run()
    return 0
