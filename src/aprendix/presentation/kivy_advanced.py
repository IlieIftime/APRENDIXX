"""Card-based Kivy shell with dashboard, learning, search, and rich theory."""

from __future__ import annotations

import threading
import time
import re
import webbrowser
import ast
import ctypes
import os
from datetime import date
from pathlib import Path

from aprendix.application.contracts import (
    Complexity,
    ContentKind,
    LearningTheme,
    SearchFiltersDTO,
    SearchRequestDTO,
    Technology,
)
from aprendix.application.mobile import EditTelemetry, FocusMinutes, PomodoroTimer
from aprendix.application.editor_support import diagnose_python
from aprendix.application.games import DIFFICULTIES, MinesweeperGame, SudokuGame


def launch_advanced_kivy(controller) -> int:
    if os.name == "nt":
        # The DPI mode must be selected before SDL creates its first window.
        # Without this, Windows can scale the native window while Kivy keeps
        # laying widgets out in unscaled pixels, clipping the right/bottom UI.
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError, OSError):
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except (AttributeError, OSError):
                pass
    from kivy.app import App
    from kivy.clock import Clock
    from kivy.core.window import Window
    from kivy.core.clipboard import Clipboard
    from kivy.graphics import Color, RoundedRectangle
    from kivy.metrics import dp
    from kivy.uix.image import AsyncImage
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.checkbox import CheckBox
    from kivy.uix.codeinput import CodeInput
    from kivy.uix.label import Label
    from kivy.uix.gridlayout import GridLayout
    from kivy.uix.progressbar import ProgressBar
    from kivy.uix.screenmanager import NoTransition, Screen, ScreenManager
    from kivy.uix.scrollview import ScrollView
    from kivy.uix.spinner import Spinner
    from kivy.uix.textinput import TextInput
    from kivy.uix.togglebutton import ToggleButton

    palettes = {
        "dark": {
            "bg": (0.025, 0.04, 0.075, 1), "card": (0.065, 0.095, 0.15, 1),
            "accent": (0.43, 0.32, 0.90, 1), "text": (0.94, 0.97, 1, 1),
            "muted": (0.66, 0.74, 0.85, 1),
        },
        "light": {
            "bg": (0.94, 0.96, 0.985, 1), "card": (1, 1, 1, 1),
            "accent": (0.28, 0.20, 0.72, 1), "text": (0.07, 0.09, 0.14, 1),
            "muted": (0.31, 0.36, 0.45, 1),
        },
    }
    theme_name = controller.load_preference("theme", "dark")
    if theme_name not in palettes:
        theme_name = "dark"
    colors = dict(palettes[theme_name])

    class Card(BoxLayout):
        def __init__(self, **kwargs):
            kwargs.setdefault("size_hint_y", None)
            super().__init__(
                orientation="vertical", padding=dp(15), spacing=dp(8), **kwargs
            )
            with self.canvas.before:
                self.theme_color = Color(*colors["card"])
                self.shape = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(18)])
            self.bind(pos=self._sync, size=self._sync)
            self.bind(minimum_height=self.setter("height"))

        def _sync(self, *_args):
            self.shape.pos, self.shape.size = self.pos, self.size

        def refresh_theme(self):
            self.theme_color.rgba = colors["card"]

    def text(value="", *, size=16, muted=False, bold=False, fixed=None):
        widget = Label(
            text=value, bold=bold, markup=False,
            color=colors["muted" if muted else "text"], font_size=dp(size),
            halign="left", valign="top", size_hint_y=None,
            height=dp(fixed or 40),
        )
        widget.theme_role = "muted" if muted else "text"
        widget.bind(
            width=lambda item, width: setattr(
                item, "text_size", (max(0, width - dp(2)), None)
            )
        )
        if fixed is None:
            widget.bind(texture_size=lambda item, dimensions: setattr(item, "height", dimensions[1] + dp(10)))
        return widget

    def action(title, callback):
        button = Button(
            text=title, bold=True, size_hint_y=None, height=dp(46),
            background_normal="", background_color=colors["accent"], color=colors["text"],
        )
        button.theme_role = "accent"
        button.bind(on_release=callback)
        return button

    def scroll_column():
        scroll = ScrollView(
            do_scroll_x=False, do_scroll_y=True, scroll_type=["bars", "content"],
            bar_width=dp(12), bar_margin=dp(3), bar_color=colors["accent"],
            bar_inactive_color=(*colors["muted"][:3], .45),
        )
        column = BoxLayout(
            orientation="vertical", size_hint_y=None, padding=dp(16), spacing=dp(12)
        )
        column.bind(minimum_height=column.setter("height"))
        scroll.add_widget(column)
        return scroll, column

    class Dashboard(Screen):
        def on_pre_enter(self, *_args):
            self.clear_widgets()
            scroll, column = scroll_column()
            column.add_widget(text("Dashboard de progresso", size=28, bold=True))
            column.add_widget(text("Perfil local anónimo · sem login · sincronização de rede desativada", muted=True, fixed=30))
            column.add_widget(action("Explorar grafo interativo", lambda _button: controller.open_graph()))
            try:
                plan = controller.study_plan()
                plan_card = Card()
                plan_card.add_widget(text("Plano de estudo personalizável", size=20, bold=True))
                plan_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
                self.plan_start = TextInput(text=str(plan["start_date"]), hint_text="Início AAAA-MM-DD", multiline=False)
                self.plan_hours = TextInput(text=str(plan["weekly_hours"]), hint_text="Horas/semana", multiline=False)
                self.plan_assessment = TextInput(text=str(plan["assessment_percent"]), hint_text="% avaliações", multiline=False)
                plan_row.add_widget(self.plan_start); plan_row.add_widget(self.plan_hours); plan_row.add_widget(self.plan_assessment)
                plan_card.add_widget(plan_row)
                self.plan_status = text("Define o ritmo; a prática continua ilimitada.", muted=True, fixed=30)
                plan_card.add_widget(action("Guardar plano", self._save_plan)); plan_card.add_widget(self.plan_status)
                column.add_widget(plan_card)
                model = controller.dashboard()
                hero = Card(size_hint_y=None, height=dp(160))
                hero.add_widget(text(f"{model.overall_mastery:.0%}", size=38, bold=True))
                hero.add_widget(text("Proficiência global", muted=True, fixed=30))
                hero.add_widget(ProgressBar(max=1, value=model.overall_mastery, size_hint_y=None, height=dp(16)))
                hero.add_widget(text(
                    f"{model.total_attempts} tentativas · {model.mastered_nodes} tópicos dominados",
                    muted=True, fixed=32,
                ))
                column.add_widget(hero)
                game = controller.gamification()
                onboarding = game["onboarding"]
                game_card = Card()
                game_card.add_widget(text(
                    f"{game['xp']} XP · sequência de {game['streak_days']} dia(s)",
                    size=20, bold=True, fixed=36,
                ))
                if onboarding["status"] == "completed":
                    game_card.add_widget(text(
                        f"Avaliação inicial: {onboarding['assessed_level']}",
                        muted=True, fixed=28,
                    ))
                else:
                    remaining = max(0, 3 - int(onboarding["attempt_count"]))
                    game_card.add_widget(text(
                        f"Onboarding A1: completa {remaining} desafio(s) distintos para calibrar o nível.",
                        muted=True, fixed=32,
                    ))
                achievements = game["achievements"]
                if achievements:
                    game_card.add_widget(text(
                        "Emblemas e certificados · " + " · ".join(
                            item["title"] for item in achievements[:4]
                        ), muted=True,
                    ))
                column.add_widget(game_card)
                column.add_widget(text(
                    f"{len(model.nodes)} tópicos no grafo · destaques",
                    size=18, bold=True,
                ))
                visible_nodes = sorted(
                    model.nodes,
                    key=lambda node: (
                        not node.recommended, -node.attempts, -node.mastery, node.title
                    ),
                )[:30]
                for node in visible_nodes:
                    card = Card()
                    suffix = " · recomendado" if node.recommended else ""
                    card.add_widget(text(node.title + suffix, bold=True, fixed=34))
                    card.add_widget(ProgressBar(max=1, value=node.mastery, size_hint_y=None, height=dp(14)))
                    card.add_widget(text(f"{node.mastery:.0%} · {node.attempts} tentativas", muted=True, fixed=28))
                    column.add_widget(card)
                column.add_widget(text("Milestones fixos", size=20, bold=True))
                for milestone in controller.milestones():
                    card = Card()
                    state = "concluído" if milestone.achieved else f"{milestone.completed}/{milestone.required}"
                    card.add_widget(text(
                        f"{milestone.technology.value} · {milestone.theme.value} · {milestone.rank_to.value}",
                        bold=True, fixed=34,
                    ))
                    card.add_widget(text(state, muted=True, fixed=28))
                    column.add_widget(card)
            except Exception as exc:
                column.add_widget(text(f"Dashboard indisponível: {exc}", muted=True))
            self.add_widget(scroll)

        def _save_plan(self, *_args):
            try:
                controller.save_study_plan(
                    start_date=date.fromisoformat(self.plan_start.text.strip()),
                    weekly_hours=float(self.plan_hours.text.replace(",", ".")),
                    assessment_percent=int(self.plan_assessment.text),
                )
                self.plan_status.text = "Plano guardado localmente; progresso e avaliações usam este objetivo."
            except (ValueError, TypeError) as exc:
                self.plan_status.text = f"Plano inválido: {exc}"

    class Learning(Screen):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.catalogue = controller.exercises()
            self.selected = self.catalogue[0] if self.catalogue else None
            self.started = time.monotonic()
            self.previous_source = self.selected.starter_code if self.selected else ""
            self.last_copykate_source = self.previous_source
            self.typed = self.pasted = self.deleted = 0
            self.timer = PomodoroTimer(FocusMinutes.SHORT)
            self.focus_event = None
            self.draft_event = None
            root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(7))
            titles = tuple(item.title for item in self.catalogue)
            self.selector = Spinner(
                text=titles[0] if titles else "Sem exercícios", values=titles,
                size_hint_y=None, height=dp(48),
            )
            self.prompt = TextInput(
                text=self.selected.prompt if self.selected else "", readonly=True,
                background_color=colors["card"], foreground_color=colors["text"],
                size_hint_y=0.18, font_size=dp(15), padding=dp(10),
            )
            self.editor = CodeInput(
                text=self.selected.starter_code if self.selected else "", font_size=dp(16),
                background_color=colors["card"], foreground_color=colors["text"],
                size_hint_y=0.42,
            )
            self.editor.bind(text=self.track_edit)
            self.glossary_tip = text(
                "Dicionário: passa o rato sobre uma função ou conceito.",
                muted=True, fixed=30,
            )
            self._hover_term = ""
            self._hover_event = None
            Window.bind(mouse_pos=self._hover_dictionary)
            row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
            for title, callback in (("Executar", self.run_code), ("Corrigir", self.evaluate),
                                    ("Nova variação", self.variation), ("Completar", self.complete)):
                row.add_widget(action(title, callback))
            edit_tools = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(5))
            for title, callback in (("Enunciado +", lambda *_: self._resize_prompt(dp(45))),
                                    ("Enunciado −", lambda *_: self._resize_prompt(-dp(45))),
                                    ("Copiar enunciado", lambda *_: Clipboard.copy(self.prompt.text)),
                                    ("Copiar código", lambda *_: Clipboard.copy(self.editor.text)),
                                    ("Copiar terminal", lambda *_: Clipboard.copy(self.output.text))):
                edit_tools.add_widget(action(title, callback))
            assists = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
            for title, callback in (("CopyKate", self.copykate), ("Guardar projeto", self.save_project),
                                    ("Ver grafo", self.open_graph)):
                assists.add_widget(action(title, callback))
            self.focus_duration = Spinner(text="25", values=("25", "50", "90", "120"))
            assists.add_widget(self.focus_duration)
            assists.add_widget(action("Foco", self.toggle_focus))
            self.status = text("Pronto", muted=True, fixed=34)
            self.diagnostics = text("Diagnóstico local: sem erros de sintaxe.", muted=True, fixed=32)
            self.justification = TextInput(
                hint_text="Justificação conceptual (pedida apenas após colagem extensa)",
                multiline=False, size_hint_y=None, height=dp(38),
            )
            self.output = TextInput(
                text="Output e correção aparecem aqui.", readonly=True,
                background_color=colors["card"], foreground_color=colors["text"],
                size_hint_y=0.22,
            )
            self.selector.bind(text=self.select)
            for widget in (self.selector, self.prompt, edit_tools, self.editor, self.glossary_tip,
                           row, assists, self.status, self.diagnostics, self.justification, self.output):
                root.add_widget(widget)
            self.add_widget(root)

        def track_edit(self, _editor, value):
            delta = len(value) - len(self.previous_source)
            if delta > 0:
                if delta >= 20:
                    self.pasted += delta
                else:
                    self.typed += delta
            elif delta < 0:
                self.deleted += -delta
            self.previous_source = value
            if self.selected:
                if self.draft_event is not None:
                    self.draft_event.cancel()
                self.draft_event = Clock.schedule_once(
                    lambda _dt: controller.save_draft(self.selected.id, self.editor.text), 0.6
                )
            Clock.unschedule(self._update_diagnostics)
            Clock.schedule_once(self._update_diagnostics, .35)

        def _resize_prompt(self, delta):
            self.prompt.size_hint_y = None
            self.prompt.height = max(dp(90), min(dp(420), self.prompt.height + delta))

        def _update_diagnostics(self, *_args):
            issues = diagnose_python(self.editor.text)
            if not issues:
                self.diagnostics.text = "Diagnóstico local: sintaxe válida; sem alertas imediatos."
                return
            self.diagnostics.text = "  ·  ".join(
                f"L{item.line}:{item.column} {item.severity}: {item.message}" for item in issues[:4]
            )

        def open_graph(self, _button):
            try:
                controller.open_graph()
                self.status.text = "Grafo aberto no navegador padrão."
            except Exception as exc:
                self.status.text = f"Não foi possível abrir o grafo: {exc}"

        def select(self, _spinner, title):
            self.selected = next((item for item in self.catalogue if item.title == title), None)
            if self.selected:
                draft = controller.load_draft(self.selected.id)
                self.prompt.text = self.selected.prompt
                self.editor.text = draft if draft is not None else self.selected.starter_code
                self.started = time.monotonic()
                self.previous_source = self.editor.text
                self.last_copykate_source = self.editor.text
                self.typed = self.pasted = self.deleted = 0

        def load_exercise(self, exercise_id):
            exercise = next(
                (item for item in self.catalogue if str(item.id) == str(exercise_id)),
                None,
            )
            if exercise is not None:
                self.selector.text = exercise.title

        def _hover_dictionary(self, _window, position):
            if not self.editor.collide_point(*position):
                return
            local_x, local_y = self.editor.to_widget(*position)
            try:
                column, row = self.editor.get_cursor_from_xy(local_x, local_y)
                lines = self.editor.text.splitlines()
                line = lines[row] if 0 <= row < len(lines) else ""
                for match in re.finditer(r"[A-Za-z_][A-Za-z0-9_]*", line):
                    if match.start() <= column <= match.end():
                        term = match.group(0)
                        if term != self._hover_term:
                            self._hover_term = term
                            if self._hover_event is not None:
                                self._hover_event.cancel()
                            self._hover_event = Clock.schedule_once(
                                lambda _dt: self._show_dictionary_term(term), 0.18
                            )
                        return
            except (IndexError, AttributeError):
                return

        def _show_dictionary_term(self, term):
            entries = controller.glossary(term, limit=1)
            if entries and entries[0]["normalized_term"] == term.casefold():
                entry = entries[0]
                self.glossary_tip.text = (
                    f"{entry['term']}: {entry['definition']}  ·  {entry['signature']}"
                )

        def run_code(self, _button):
            if not self.selected or not self.editor.text.strip():
                self.status.text = "Escreve código antes de executar."
                return
            self.status.text = "A executar no subprocesso isolado…"
            threading.Thread(target=self._run_worker, daemon=True).start()

        def _run_worker(self):
            try:
                result = controller.run_code(self.editor.text)
                Clock.schedule_once(lambda _dt: self._show_run(result), 0)
            except Exception as exc:
                Clock.schedule_once(lambda _dt, message=str(exc): self._show_error(message), 0)

        def _show_run(self, result):
            self.status.text = f"Execução: {result.status} · {result.duration_ms} ms"
            self.output.text = result.stdout or result.error_message or "Sem output."

        def evaluate(self, _button):
            if not self.selected or not self.editor.text.strip():
                self.status.text = "Escreve código antes de corrigir."
                return
            elapsed = max(0, round((time.monotonic() - self.started) * 1000))
            telemetry = EditTelemetry(self.typed, self.pasted, self.deleted)
            self.status.text = "A corrigir e persistir localmente…"
            threading.Thread(target=self._evaluate_worker, args=(elapsed, telemetry), daemon=True).start()

        def _evaluate_worker(self, elapsed, telemetry):
            try:
                receipt = controller.evaluate(
                    self.selected, self.editor.text, elapsed, telemetry=telemetry,
                    justification=self.justification.text,
                    proficiency=self._proficiency(),
                )
                Clock.schedule_once(lambda _dt: self._show_evaluation(receipt), 0)
            except Exception as exc:
                Clock.schedule_once(lambda _dt, message=str(exc): self._show_error(message), 0)

        def _show_evaluation(self, receipt):
            self.status.text = "Aprovado" if receipt.passed else "Ainda não aprovado"
            lines = list(receipt.feedback)
            if receipt.milestone:
                lines.append(f"Milestone {receipt.milestone.rank_to.value}: {receipt.milestone.completed}/{receipt.milestone.required}")
            self.output.text = "\n".join(lines) or f"Score: {receipt.score:.0%}"
            if receipt.passed and self.catalogue:
                Clock.schedule_once(lambda _dt: self._next_exercise(), 1.2)

        def _next_exercise(self):
            if not self.selected or not self.catalogue:
                return
            index = self.catalogue.index(self.selected)
            self.selector.text = self.catalogue[(index + 1) % len(self.catalogue)].title

        def variation(self, _button):
            if not self.selected:
                return
            try:
                generated = controller.variation(
                    self.selected, proficiency=self._proficiency()
                )
                self.prompt.text, self.editor.text = generated.prompt, generated.starter_code
                self.output.text = "Dicas graduais:\n" + "\n".join(f"• {hint.text}" for hint in generated.hints)
                self.status.text = "Variação A2 criada no mesmo nível."
            except Exception as exc:
                self._show_error(str(exc))

        def complete(self, _button):
            try:
                suggestions = controller.autocomplete(
                    self.editor.text, self.editor.cursor_index(),
                    proficiency=self._proficiency(),
                )
                if not suggestions:
                    self.status.text = "Sem sugestão estrutural neste ponto."
                    return
                suggestion = suggestions[0]
                cursor = self.editor.cursor_index()
                self.editor.text = self.editor.text[:cursor] + suggestion.insert_text + self.editor.text[cursor:]
                self.status.text = f"Autocomplete: {suggestion.structural_reason}"
            except Exception as exc:
                self._show_error(str(exc))

        def copykate(self, _button):
            if self.editor.text.strip():
                self.status.text = "CopyKate local a analisar o teu estilo…"
                threading.Thread(target=self._copykate_worker, daemon=True).start()

        def _copykate_worker(self):
            try:
                current = self.editor.text
                response = controller.copykate(current, self.last_copykate_source)
                self.last_copykate_source = current
                Clock.schedule_once(lambda _dt: self._show_copykate(response), 0)
            except Exception as exc:
                Clock.schedule_once(lambda _dt, message=str(exc): self._show_error(message), 0)

        def _show_copykate(self, response):
            self.status.text = "CopyKate criou 3 alternativas; nenhuma foi inserida automaticamente."
            self.output.text = "\n\n".join(
                f"{index}. {item.strategy}: {item.justification}\nAlterações AST: {len(item.ast_changes)}\n{item.source_code[:700]}"
                for index, item in enumerate(response.alternatives, start=1)
            )

        def save_project(self, _button):
            try:
                project = controller.save_project(self.selected.title if self.selected else "Projeto Python", self.editor.text)
                self.status.text = f"Projeto local guardado: {project.name}"
            except Exception as exc:
                self._show_error(str(exc))

        def toggle_focus(self, _button):
            if self.timer.state.value == "completed":
                self.timer.reset()
            if self.timer.state.value in {"idle", "paused"}:
                if self.timer.state.value == "idle":
                    self.timer = PomodoroTimer(FocusMinutes(int(self.focus_duration.text)))
                self.timer.start()
                if self.focus_event is None:
                    self.focus_event = Clock.schedule_interval(
                        self._focus_tick, 1.0
                    )
                self.status.text = f"Pomodoro de {self.focus_duration.text} minutos iniciado."
            else:
                self.timer.pause()
                controller.record_focus(
                    int(self.focus_duration.text), int(self.timer.elapsed_seconds()), "paused"
                )
                self.status.text = f"Foco pausado · faltam {self.timer.remaining_seconds()/60:.1f} min"

        def _focus_tick(self, _dt):
            if self.timer.state.value == "completed":
                controller.record_focus(
                    int(self.focus_duration.text),
                    int(self.timer.elapsed_seconds()), "completed",
                )
                self.status.text = "Sessão de foco concluída e guardada localmente."
                self.focus_event = None
                return False
            return True

        def _proficiency(self):
            if not self.selected:
                return 0.0
            try:
                node = next(
                    item for item in controller.dashboard().nodes
                    if item.node_id == self.selected.graph_node_id
                )
                return node.mastery
            except (StopIteration, AttributeError):
                return 0.0

        def _show_error(self, message):
            self.status.text = "Operação indisponível."
            self.output.text = message

    class TheoryCards(Screen):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.mode = "Recomendado"

        def on_pre_enter(self, *_args):
            self.render()

        def render(self, *_args):
            self.clear_widgets()
            root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(7))
            controls = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(94), spacing=dp(5))
            primary = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
            secondary = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
            mode = Button(text=f"Modo: {self.mode}")
            mode.bind(on_release=self.switch_mode)
            self.technology = Spinner(
                text=getattr(self, "technology", None).text if hasattr(self, "technology") else "Todas as tecnologias",
                values=("Todas as tecnologias",) + tuple(item.value for item in Technology if item is not Technology.OTHER),
            )
            self.theme = Spinner(
                text=getattr(self, "theme", None).text if hasattr(self, "theme") else "Todos os temas",
                values=("Todos os temas",) + tuple(item.value for item in LearningTheme if item is not LearningTheme.OTHER),
            )
            clusters = tuple(controller.clusters())
            self._cluster_ids = {item.label: item.id for item in clusters}
            self.cluster = Spinner(
                text=getattr(self, "cluster", None).text if hasattr(self, "cluster") else "Todos os clusters",
                values=("Todos os clusters",) + tuple(self._cluster_ids),
            )
            areas = tuple(controller.knowledge_areas())
            self._area_ids = {
                ("   " * item.depth + ("↳ " if item.depth else "") + item.title): item.id
                for item in areas
            }
            previous_area = getattr(getattr(self, "area", None), "text", "Toda a árvore")
            self.area = Spinner(
                text=previous_area if previous_area in self._area_ids else "Toda a árvore",
                values=("Toda a árvore",) + tuple(self._area_ids),
            )
            primary.add_widget(mode); primary.add_widget(self.area); primary.add_widget(action("Aplicar", self.render))
            secondary.add_widget(self.technology); secondary.add_widget(self.theme); secondary.add_widget(self.cluster)
            controls.add_widget(primary); controls.add_widget(secondary)
            root.add_widget(controls)
            scroll, column = scroll_column()
            column.add_widget(text(f"Cards · navegação {self.mode.lower()}", size=28, bold=True))
            filters = {}
            if self.technology.text != "Todas as tecnologias":
                filters["technology"] = Technology(self.technology.text)
            if self.theme.text != "Todos os temas":
                filters["theme"] = LearningTheme(self.theme.text)
            if self.area.text != "Toda a árvore":
                filters["area_id"] = self._area_ids.get(self.area.text)
            cards = list(controller.theory_cards(**filters))
            if self.mode == "Recomendado":
                snapshot = controller.snapshot()
                recommended = {item["node_id"] for item in snapshot.get("recommendations", [])}
                cards.sort(key=lambda item: (str(item.graph_node_id) not in recommended, item.title))
            elif self.cluster.text != "Todos os clusters":
                cluster_id = self._cluster_ids.get(self.cluster.text)
                cards = [item for item in cards if item.cluster_id == cluster_id]
            if not cards:
                column.add_widget(text("Ainda não existem cards. Executa a ingestão local.", muted=True))
            elif len(cards) > 20:
                column.add_widget(text(
                    f"A mostrar 20 de {len(cards)} cards recentes.", muted=True
                ))
            for item in cards[:20]:
                card = Card()
                card.add_widget(text(item.title, size=21, bold=True))
                if item.image_path and Path(item.image_path).is_file():
                    card.add_widget(AsyncImage(source=item.image_path, size_hint_y=None, height=dp(200)))
                body = item.body.strip()
                if len(body) > 900:
                    body = body[:900].rstrip() + "…"
                card.add_widget(text(body, size=15))
                if item.code_example:
                    card.add_widget(CodeInput(
                        text=item.code_example, readonly=True, size_hint_y=None, height=dp(170),
                        background_color=colors["card"], foreground_color=colors["text"],
                    ))
                citation = item.source_title or "Fonte local"
                if item.source_page:
                    citation += f" · pág. {item.source_page}"
                card.add_widget(text(citation, muted=True, fixed=28))
                review = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
                feedback = text("Repetição espaçada local", muted=True, fixed=38)
                review.add_widget(action(
                    "Rever depois",
                    lambda _button, card_id=item.id, label=feedback: self._review(
                        card_id, False, label
                    ),
                ))
                review.add_widget(action(
                    "Já domino",
                    lambda _button, card_id=item.id, label=feedback: self._review(
                        card_id, True, label
                    ),
                ))
                card.add_widget(review); card.add_widget(feedback)
                column.add_widget(card)
            root.add_widget(scroll)
            self.add_widget(root)

        def switch_mode(self, _button):
            self.mode = "Livre" if self.mode == "Recomendado" else "Recomendado"
            self.render()

        def _review(self, card_id, known, label):
            try:
                controller.review_card(card_id, known=known)
                label.text = (
                    "Domínio registado; o intervalo de revisão aumentou."
                    if known else "Revisão reagendada para daqui a 4 horas."
                )
            except Exception as exc:
                label.text = f"Não foi possível guardar a revisão: {exc}"

    class FactCards(Screen):
        """One-card deck with explicit review direction and source flip."""

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.index, self.flipped, self.filters_visible = 0, False, False
            self.cards = []
            self.area_id = None

        def on_pre_enter(self, *_args):
            self.render()

        def render(self, *_args):
            self.clear_widgets()
            root = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(9))
            areas = tuple(controller.knowledge_areas())
            leaves = tuple(item for item in areas if item.depth > 0)
            filters = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
            filters.add_widget(action("Filtros", self.toggle_filters))
            self._area_names = {item.title: item.id for item in leaves}
            self.area = Spinner(
                text=next((name for name, identity in self._area_names.items() if identity == self.area_id), "Todos os temas"),
                values=("Todos os temas",) + tuple(self._area_names),
            )
            self.area.bind(text=self.apply_area)
            filters.add_widget(self.area)
            filters.add_widget(text("PC: < > para avaliar · ^ v para temas", muted=True, fixed=40))
            root.add_widget(filters)
            self.cards = list(controller.theory_cards(area_id=self.area_id)) if self.area_id else list(controller.theory_cards())
            if not self.cards:
                root.add_widget(text("Sem cards originais para este tema.", muted=True))
                self.add_widget(root); return
            self.index %= len(self.cards)
            item = self.cards[self.index]
            root.add_widget(text(f"Sabias que? · {self.index + 1}/{len(self.cards)}", size=26, bold=True, fixed=48))
            body = item.body if not self.flipped else self.reference_text(item)
            face = Button(
                text=body, halign="left", valign="middle", font_size=dp(20),
                background_normal="", background_color=colors["card"], color=colors["text"],
            )
            face.bind(size=lambda widget, _value: setattr(widget, "text_size", (widget.width - dp(48), widget.height - dp(48))))
            face.bind(on_release=self.flip)
            root.add_widget(face)
            if self.flipped:
                links = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(5))
                for source in controller.curated_sources(item.area_ids, limit=4):
                    links.add_widget(action(source.title[:25], lambda _b, url=source.canonical_url: webbrowser.open(url)))
                root.add_widget(links)
            arrows = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(7))
            arrows.add_widget(action("<  útil", lambda *_: self.navigate(-1, True)))
            arrows.add_widget(action("^  tema", lambda *_: self.step_area(-1)))
            arrows.add_widget(action("tema  v", lambda *_: self.step_area(1)))
            arrows.add_widget(action("rever  >", lambda *_: self.navigate(1, False)))
            root.add_widget(arrows)
            root.add_widget(text("Toca no card para o virar e abrir as referências.", muted=True, fixed=32))
            self.add_widget(root)

        def reference_text(self, item):
            sources = controller.curated_sources(item.area_ids, limit=5)
            if not sources:
                return "Referências não disponíveis para este tema."
            return "Referências\n\n" + "\n".join(f"• {source.title} — {', '.join(source.authors)}" for source in sources)

        def flip(self, *_args):
            self.flipped = not self.flipped
            self.render()

        def navigate(self, delta, known):
            try:
                controller.review_card(self.cards[self.index].id, known=known)
            except Exception:
                pass
            self.index = (self.index + delta) % len(self.cards)
            self.flipped = False
            self.render()

        def apply_area(self, _spinner, value):
            self.area_id = self._area_names.get(value)
            self.index, self.flipped = 0, False
            self.render()

        def step_area(self, delta):
            values = (None, *self._area_names.values())
            current = values.index(self.area_id) if self.area_id in values else 0
            self.area_id = values[(current + delta) % len(values)]
            self.index, self.flipped = 0, False
            self.render()

        def toggle_filters(self, *_args):
            self.area_id = None
            self.index, self.flipped = 0, False
            self.render()

    class Curriculum(Screen):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            tracks = tuple(controller.tracks())
            self._tracks = {item["title"]: item["slug"] for item in tracks}
            root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
            controls = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
            self.track = Spinner(
                text=next(iter(self._tracks), "Sem percurso"),
                values=tuple(self._tracks),
            )
            self.track.bind(text=lambda *_: self.render())
            self.status = text("Prática antes da teoria · progresso local", muted=True, fixed=34)
            controls.add_widget(self.track)
            self.assessment_mode = Spinner(
                text="Treino livre",
                values=("Treino livre", "Avaliação · 10 min", "Avaliação · 20 min", "Avaliação · 45 min"),
            )
            controls.add_widget(self.assessment_mode)
            controls.add_widget(action("Atualizar", lambda *_: self.render()))
            root.add_widget(controls); root.add_widget(self.status)
            self.scroll, self.column = scroll_column(); root.add_widget(self.scroll)
            self.add_widget(root)

        def on_pre_enter(self, *_args):
            self.render()

        def render(self):
            self.column.clear_widgets()
            slug = self._tracks.get(self.track.text)
            if not slug:
                self.column.add_widget(text("Ainda não existe um percurso local."))
                return
            units = controller.units(slug)
            self.column.add_widget(text(self.track.text, size=28, bold=True))
            for unit in units:
                card = Card()
                state = "concluído" if unit["completed"] else (
                    "disponível" if unit["unlocked"] else "bloqueado"
                )
                card.add_widget(text(
                    f"{unit['chapter_title']} · {unit['kind']} · {state}",
                    muted=True, fixed=28,
                ))
                card.add_widget(text(unit["title"], size=20, bold=True))
                if not unit["unlocked"]:
                    card.add_widget(text(
                        "Conclui a etapa anterior para abrir este conteúdo.",
                        muted=True,
                    ))
                else:
                    card.add_widget(text(unit["body"], size=15))
                    if unit["example"]:
                        card.add_widget(CodeInput(
                            text=unit["example"], readonly=True, size_hint_y=None,
                            height=dp(120), background_color=colors["card"],
                            foreground_color=colors["text"],
                        ))
                    if unit["kind"] == "practice" and unit["exercise_id"]:
                        card.add_widget(action(
                            "Abrir exercício no IDE",
                            lambda _button, exercise_id=unit["exercise_id"]: self._practice(exercise_id),
                        ))
                    elif unit["assessment_id"] and unit["kind"] in {"quiz", "hybrid"}:
                        card.add_widget(action(
                            "Responder teste",
                            lambda _button, item_id=unit["assessment_id"]: self._assessment(item_id),
                        ))
                    elif not unit["completed"]:
                        card.add_widget(action(
                            "Marcar etapa concluída",
                            lambda _button, unit_id=unit["id"]: self._complete(unit_id),
                        ))
                self.column.add_widget(card)

        def _practice(self, exercise_id):
            learning = self.manager.get_screen("learning")
            learning.load_exercise(exercise_id)
            self.manager.current = "learning"

        def _complete(self, unit_id):
            try:
                controller.complete_unit(unit_id)
                self.status.text = "Etapa concluída; a próxima foi desbloqueada."
                self.render()
            except Exception as exc:
                self.status.text = str(exc)

        def _assessment(self, item_id):
            try:
                assessment = controller.assessment(item_id)
            except Exception as exc:
                self.status.text = str(exc); return
            self.column.clear_widgets()
            self.assessment_started = time.monotonic()
            match = re.search(r"\d+", self.assessment_mode.text)
            self.assessment_limit = int(match.group()) * 60 if match else 0
            self.assessment_clock = text("Treino sem limite", muted=True, fixed=32)
            self.column.add_widget(self.assessment_clock)
            Clock.unschedule(self._assessment_tick)
            Clock.schedule_interval(self._assessment_tick, 1)
            self.column.add_widget(text(assessment["prompt"], size=22, bold=True))
            if assessment["options"]:
                for option in assessment["options"]:
                    self.column.add_widget(action(
                        f"{option['id']}. {option['text']}",
                        lambda _button, answer=option["id"]: self._answer(item_id, answer),
                    ))
            else:
                answer = TextInput(
                    hint_text="Escreve a previsão curta", multiline=False,
                    size_hint_y=None, height=dp(46),
                )
                self.column.add_widget(answer)
                self.column.add_widget(action(
                    "Validar resposta", lambda _button: self._answer(item_id, answer.text)
                ))
            self.column.add_widget(action("Voltar ao percurso", lambda *_: self.render()))

        def _answer(self, item_id, answer):
            try:
                elapsed = max(0, int(time.monotonic() - getattr(self, "assessment_started", time.monotonic())))
                if getattr(self, "assessment_limit", 0) and elapsed > self.assessment_limit:
                    self.status.text = "Tempo de avaliação terminado; a resposta não foi submetida."
                    return
                result = controller.answer_assessment(
                    item_id, answer, duration_seconds=elapsed,
                    mode="evaluation" if getattr(self, "assessment_limit", 0) else "training",
                )
                Clock.unschedule(self._assessment_tick)
                self.status.text = (
                    "Resposta validada. " if result["passed"] else "Resposta a rever. "
                ) + result["explanation"]
                self.render()
            except Exception as exc:
                self.status.text = str(exc)

        def _assessment_tick(self, *_args):
            if not hasattr(self, "assessment_clock"):
                return False
            elapsed = max(0, int(time.monotonic() - self.assessment_started))
            if self.assessment_limit:
                remaining = max(0, self.assessment_limit - elapsed)
                self.assessment_clock.text = f"Avaliação · {remaining // 60:02d}:{remaining % 60:02d} restantes"
                if remaining == 0:
                    self.status.text = "Tempo de avaliação terminado."
                    return False
            else:
                self.assessment_clock.text = f"Treino · {elapsed // 60:02d}:{elapsed % 60:02d}"
            return True

    class Reference(Screen):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
            row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
            self.query = TextInput(
                hint_text="Função ou conceito: print, dict, JOIN, Django…",
                multiline=False,
            )
            self.query.bind(on_text_validate=lambda *_: self.search())
            row.add_widget(self.query); row.add_widget(action("Consultar", lambda *_: self.search()))
            root.add_widget(row)
            self.scroll, self.column = scroll_column(); root.add_widget(self.scroll)
            self.add_widget(root)

        def search(self):
            self.column.clear_widgets()
            self.column.add_widget(text("A consultar o dicionário local…", muted=True))
            threading.Thread(target=self._lookup, args=(self.query.text,), daemon=True).start()

        def _lookup(self, query):
            try:
                entries = controller.glossary(query, limit=20)
                Clock.schedule_once(lambda _dt: self._render(entries), 0)
            except Exception as exc:
                Clock.schedule_once(lambda _dt, message=str(exc): self._render_error(message), 0)

        def _render_error(self, message):
            self.column.clear_widgets()
            self.column.add_widget(text(f"Consulta indisponível: {message}", muted=True))

        def _render(self, entries):
            self.column.clear_widgets()
            if not entries:
                self.column.add_widget(text("Sem entrada exata. Experimenta um prefixo mais curto.", muted=True))
                return
            for entry in entries:
                card = Card()
                card.add_widget(text(f"{entry['term']} · {entry['technology']}", size=23, bold=True))
                card.add_widget(text(entry["definition"], size=16))
                card.add_widget(text(entry["signature"], muted=True))
                if entry["example"]:
                    card.add_widget(CodeInput(
                        text=entry["example"], readonly=True,
                        size_hint_y=None, height=dp(100),
                        background_color=colors["card"], foreground_color=colors["text"],
                    ))
                if entry["related_terms"]:
                    card.add_widget(text(
                        "Relacionados: " + " · ".join(entry["related_terms"]),
                        muted=True, fixed=28,
                    ))
                references = entry.get("references", ())
                if references:
                    links = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(5))
                    for title, url in references[:4]:
                        links.add_widget(action(
                            title[:28], lambda _button, target=url: webbrowser.open(target)
                            if target.startswith(("https://", "http://")) else None,
                        ))
                    card.add_widget(links)
                self.column.add_widget(card)

    class Search(Screen):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(7))
            self.query = TextInput(hint_text="Pesquisar localmente por tema ou tecnologia…", multiline=False, size_hint_y=None, height=dp(46))
            filters = Card(size_hint_y=None, height=dp(326))
            kinds = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(5))
            self.kind_buttons = {}
            for kind, title in ((ContentKind.THEORY, "Teoria"), (ContentKind.EXERCISE, "Exercício"), (ContentKind.PAPER, "Paper")):
                button = ToggleButton(text=title, state="down")
                self.kind_buttons[kind] = button
                kinds.add_widget(button)
            filters.add_widget(kinds)
            row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(5))
            self.author = TextInput(hint_text="Autor preferido", multiline=False)
            self.complexity = Spinner(text="Todas", values=("Todas", "Iniciante", "Intermédio", "Avançado"))
            row.add_widget(self.author); row.add_widget(self.complexity); filters.add_widget(row)
            taxonomy = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(5))
            self.technology = Spinner(
                text="Todas as tecnologias",
                values=("Todas as tecnologias",) + tuple(item.value for item in Technology if item is not Technology.OTHER),
            )
            self.theme = Spinner(
                text="Todos os temas",
                values=("Todos os temas",) + tuple(item.value for item in LearningTheme if item is not LearningTheme.OTHER),
            )
            taxonomy.add_widget(self.technology); taxonomy.add_widget(self.theme); filters.add_widget(taxonomy)
            areas = tuple(controller.knowledge_areas())
            self._area_ids = {
                ("   " * item.depth + ("↳ " if item.depth else "") + item.title): item.id
                for item in areas
            }
            hierarchy = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(5))
            self.area = Spinner(text="Toda a árvore", values=("Toda a árvore",) + tuple(self._area_ids))
            self.shortcut = Spinner(text="Atalhos de aprendizagem", values=())
            self.area.bind(text=self._area_changed)
            self.shortcut.bind(text=self._shortcut_changed)
            hierarchy.add_widget(self.area); hierarchy.add_widget(self.shortcut); filters.add_widget(hierarchy)
            dates = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(5))
            self.date_from = TextInput(hint_text="Desde AAAA-MM-DD", multiline=False)
            self.date_to = TextInput(hint_text="Até AAAA-MM-DD", multiline=False)
            self.web = CheckBox(active=False, size_hint_x=None, width=dp(38))
            dates.add_widget(self.date_from); dates.add_widget(self.date_to); dates.add_widget(self.web)
            dates.add_widget(text("Web", muted=True, fixed=38)); filters.add_widget(dates)
            self.status = text("Pesquisa local primeiro; web só com baixa confiança.", muted=True, fixed=32)
            result_scroll = ScrollView(
                do_scroll_x=False, do_scroll_y=True, scroll_type=["bars", "content"],
                bar_width=dp(12), bar_margin=dp(3), bar_color=colors["accent"],
                bar_inactive_color=(*colors["muted"][:3], .45),
            )
            self.results = BoxLayout(
                orientation="vertical", spacing=dp(10), padding=(0, dp(4)),
                size_hint_y=None,
            )
            self.results.bind(minimum_height=self.results.setter("height")); result_scroll.add_widget(self.results)
            self.search_button = action("Pesquisar", self.start)
            for widget in (self.query, filters, self.search_button, self.status, result_scroll):
                root.add_widget(widget)
            self.add_widget(root)
            self._area_changed()

        def _area_changed(self, *_args):
            area_id = self._area_ids.get(self.area.text)
            shortcuts = tuple(controller.search_shortcuts(area_id, limit=30))
            self._shortcut_queries = {item.label: item.query for item in shortcuts}
            self.shortcut.values = tuple(self._shortcut_queries)
            self.shortcut.text = "Atalhos de aprendizagem"

        def _shortcut_changed(self, *_args):
            query = getattr(self, "_shortcut_queries", {}).get(self.shortcut.text)
            if query:
                self.query.text = query

        def start(self, _button):
            if not self.query.text.strip():
                self.status.text = "Escreve uma pergunta."
                return
            mapping = {"Iniciante": (Complexity.BEGINNER,), "Intermédio": (Complexity.INTERMEDIATE,), "Avançado": (Complexity.ADVANCED,)}
            try:
                request = SearchRequestDTO(
                    query=self.query.text,
                    filters=SearchFiltersDTO(
                        preferred_authors=(self.author.text,) if self.author.text.strip() else (),
                        content_types=tuple(kind for kind, button in self.kind_buttons.items() if button.state == "down"),
                        complexities=mapping.get(self.complexity.text, ()),
                        technologies=(Technology(self.technology.text),)
                        if self.technology.text != "Todas as tecnologias" else (),
                        themes=(LearningTheme(self.theme.text),)
                        if self.theme.text != "Todos os temas" else (),
                        area_ids=(self._area_ids[self.area.text],)
                        if self.area.text != "Toda a árvore" else (),
                        published_from=date.fromisoformat(self.date_from.text) if self.date_from.text.strip() else None,
                        published_to=date.fromisoformat(self.date_to.text) if self.date_to.text.strip() else None,
                    ), allow_web_fallback=self.web.active,
                )
            except ValueError as exc:
                self.status.text = f"Filtros inválidos: {exc}"; return
            self.status.text = "A pesquisar…"
            self.search_button.disabled = True
            threading.Thread(target=self.worker, args=(request,), daemon=True).start()

        def worker(self, request):
            try:
                response = controller.search(request)
                Clock.schedule_once(lambda _dt: self.render(response), 0)
            except Exception as exc:
                Clock.schedule_once(
                    lambda _dt, message=str(exc): self.render_error(message), 0
                )

        def render_error(self, message):
            self.search_button.disabled = False
            self.status.text = f"Pesquisa indisponível: {message}"

        def render(self, response):
            self.results.clear_widgets()
            self.search_button.disabled = False
            mode = "local + web" if response.used_web_fallback else "local"
            self.status.text = f"Resposta {mode} · confiança {response.confidence:.0%}"
            answer_text = response.answer.strip()
            if len(answer_text) > 2_400:
                answer_text = answer_text[:2_400].rstrip() + "…"
            answer = Card()
            answer.add_widget(text("Resposta", size=19, bold=True))
            answer.add_widget(text(answer_text))
            self.results.add_widget(answer)
            if response.similar_topics:
                topic_card = Card()
                topic_card.add_widget(text("Tópicos semelhantes", size=18, bold=True))
                topic_card.add_widget(text(
                    " · ".join(f"{item.label} ({item.member_count})" for item in response.similar_topics),
                    muted=True,
                ))
                self.results.add_widget(topic_card)
            for hit in response.evidence[:10]:
                card = Card()
                badge = "WEB" if hit.origin.value == "web" else "LOCAL"
                card.add_widget(text(f"[{badge}] {hit.title}", bold=True))
                excerpt = hit.excerpt.strip()
                if len(excerpt) > 900:
                    excerpt = excerpt[:900].rstrip() + "…"
                card.add_widget(text(excerpt, size=14))
                card.add_widget(text(f"{hit.content_type.value} · {hit.complexity.value} · {hit.relevance:.0%}", muted=True, fixed=28))
                if hit.origin.value == "local":
                    card.add_widget(action(
                        "Expandir · resumo · versão simples",
                        lambda _button, evidence_id=hit.id: self._open_reader(evidence_id),
                    ))
                elif hit.source.startswith(("https://", "http://")):
                    card.add_widget(action(
                        "Abrir fonte externa",
                        lambda _button, url=hit.source: webbrowser.open(url),
                    ))
                self.results.add_widget(card)

        def _open_reader(self, evidence_id):
            reader = self.manager.get_screen("reader")
            reader.load(evidence_id, self.query.text)
            self.manager.current = "reader"

    class AssistedReader(Screen):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.detail = None
            root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(7))
            top = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
            top.add_widget(action("‹ Pesquisa", lambda *_: setattr(self.manager, "current", "search")))
            for label, mode in (("Resumo", "summary"), ("Versão simples", "simplified"), ("Conteúdo normal", "original")):
                top.add_widget(action(label, lambda _button, value=mode: self.show(value)))
            self.open_source = action("Abrir fonte", self._open_source)
            top.add_widget(self.open_source)
            root.add_widget(top)
            self.status = text("Escolhe um resultado local.", muted=True, fixed=32)
            root.add_widget(self.status)
            self.scroll, self.column = scroll_column(); root.add_widget(self.scroll)
            self.add_widget(root)

        def load(self, evidence_id, query=""):
            self.detail = None; self.column.clear_widgets()
            self.status.text = "A preparar leitura assistida local…"
            threading.Thread(target=self._worker, args=(evidence_id, query), daemon=True).start()

        def _worker(self, evidence_id, query):
            try:
                detail = controller.reading_detail(evidence_id, query=query)
                Clock.schedule_once(lambda _dt: self._loaded(detail), 0)
            except Exception as exc:
                Clock.schedule_once(lambda _dt, message=str(exc): setattr(self.status, "text", message), 0)

        def _loaded(self, detail):
            self.detail = detail
            self.status.text = detail.copyright_note
            self.show("summary")

        def show(self, mode):
            self.column.clear_widgets()
            if self.detail is None:
                self.column.add_widget(text("A carregar…", muted=True)); return
            detail = self.detail
            self.column.add_widget(text(detail.title, size=26, bold=True))
            labels = {"summary": "Resumo essencial", "simplified": "Versão simplificada com rigor", "original": "Conteúdo normal"}
            body = {"summary": detail.summary, "simplified": detail.simplified, "original": detail.original_content}[mode]
            card = Card(); card.add_widget(text(labels[mode], size=20, bold=True))
            reading = TextInput(
                text=body, readonly=True, font_size=dp(15),
                background_color=colors["card"], foreground_color=colors["text"],
                size_hint_y=None, height=dp(min(680, max(220, 80 + len(body) // 3))),
                padding=dp(10),
            )
            reading.bind(on_touch_down=self._concept_double_click)
            card.add_widget(reading); self.column.add_widget(card)
            if mode == "original":
                for asset in detail.visual_assets:
                    if Path(asset).is_file():
                        visual = Card()
                        visual.add_widget(text("Visualização extraída da fonte", muted=True, fixed=30))
                        visual.add_widget(AsyncImage(source=asset, size_hint_y=None, height=dp(360)))
                        self.column.add_widget(visual)
            self.column.add_widget(text(
                "Tutor: faz duplo clique numa palavra para a consultar no dicionário.",
                muted=True, fixed=34,
            ))
            if detail.related_sources:
                sources = Card(); sources.add_widget(text("Bibliografia orientada", size=20, bold=True))
                for source in detail.related_sources:
                    sources.add_widget(action(
                        f"{source.title} · {', '.join(source.authors)} ({source.publication_year or 's/d'})",
                        lambda _button, url=source.canonical_url: webbrowser.open(url),
                    ))
                self.column.add_widget(sources)

        def _concept_double_click(self, widget, touch):
            if not getattr(touch, "is_double_tap", False) or not widget.collide_point(*touch.pos):
                return False
            local_x, local_y = widget.to_widget(*touch.pos)
            try:
                column, row = widget.get_cursor_from_xy(local_x, local_y)
                line = widget.text.splitlines()[row]
                match = next((item for item in re.finditer(r"[A-Za-zÀ-ÿ_][A-Za-zÀ-ÿ0-9_-]*", line)
                              if item.start() <= column <= item.end()), None)
            except (IndexError, AttributeError):
                match = None
            if match:
                reference = self.manager.get_screen("reference")
                reference.query.text = match.group(0)
                reference.search()
                self.manager.current = "reference"
                return True
            return False

        def _open_source(self, *_args):
            if self.detail is None:
                return
            target = self.detail.canonical_url or self.detail.source
            if target.startswith(("https://", "http://")):
                webbrowser.open(target)
                self.status.text = "Fonte aberta no navegador."
                return
            path = Path(target).expanduser()
            if path.is_file():
                webbrowser.open(path.resolve().as_uri())
                self.status.text = "Ficheiro original aberto na aplicação predefinida."
            else:
                self.status.text = "A fonte local já não existe neste caminho."

    class Games(Screen):
        """Quiet break area with no timers, animations, network or rewards."""

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.selected_cell, self.flag_mode = None, False
            root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(7))
            controls = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
            self.kind = Spinner(text="Sudoku", values=("Sudoku", "Minesweeper"))
            self.difficulty = Spinner(text="Fácil", values=DIFFICULTIES)
            controls.add_widget(self.kind); controls.add_widget(self.difficulty)
            controls.add_widget(action("Novo jogo", self.new_game))
            self.mode_button = action("Modo: revelar", self.toggle_mode)
            controls.add_widget(self.mode_button); root.add_widget(controls)
            self.status = text("Intervalo sem animações · o progresso pedagógico não é afetado.", muted=True, fixed=34)
            root.add_widget(self.status)
            self.board = GridLayout(spacing=dp(2)); root.add_widget(self.board)
            self.keypad = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(3))
            for value in range(1, 10):
                self.keypad.add_widget(action(str(value), lambda _b, number=value: self.enter_number(number)))
            self.keypad.add_widget(action("×", lambda *_: self.enter_number(0)))
            root.add_widget(self.keypad); self.add_widget(root)
            self.kind.bind(text=lambda *_: self.new_game())
            self.difficulty.bind(text=lambda *_: self.new_game())
            self.new_game()

        def new_game(self, *_args):
            seed = int(time.time_ns() % 2_147_483_647)
            self.selected_cell = None
            self.game = (SudokuGame(self.difficulty.text, seed=seed) if self.kind.text == "Sudoku"
                         else MinesweeperGame(self.difficulty.text, seed=seed))
            self.keypad.opacity = 1 if self.kind.text == "Sudoku" else 0
            self.keypad.disabled = self.kind.text != "Sudoku"
            self.mode_button.disabled = self.kind.text == "Sudoku"
            self.status.text = f"{self.kind.text} · {self.difficulty.text} · sem animações"
            self.draw()

        def draw(self):
            self.board.clear_widgets()
            if isinstance(self.game, SudokuGame):
                self.board.cols = 9
                for row in range(9):
                    for col in range(9):
                        value = self.game.board[row][col]
                        title = str(value) if value else " "
                        if (row, col) == self.selected_cell: title = f"[{title}]"
                        button = Button(text=title, font_size=dp(19), background_normal="",
                            background_color=colors["accent"] if (row, col) in self.game.fixed else colors["card"],
                            color=colors["text"])
                        button.bind(on_release=lambda _b, r=row, c=col: self.select_sudoku(r, c))
                        self.board.add_widget(button)
            else:
                self.board.cols = self.game.cols
                for row in range(self.game.rows):
                    for col in range(self.game.cols):
                        cell = (row, col)
                        if cell in self.game.flagged: title = "⚑"
                        elif cell not in self.game.revealed: title = " "
                        elif cell in self.game.mines: title = "✹"
                        else:
                            count = self.game.count(row, col); title = str(count) if count else "·"
                        button = Button(text=title, font_size=dp(12), background_normal="",
                                        background_color=colors["card"], color=colors["text"])
                        button.bind(on_release=lambda _b, r=row, c=col: self.play_mine(r, c))
                        self.board.add_widget(button)

        def select_sudoku(self, row, col):
            if (row, col) not in self.game.fixed:
                self.selected_cell = (row, col); self.draw()

        def enter_number(self, value):
            if self.selected_cell and isinstance(self.game, SudokuGame):
                self.game.set(*self.selected_cell, value)
                self.status.text = ("Sudoku concluído." if self.game.won else
                    "Valor correto." if self.game.correct(*self.selected_cell) else "Valor em conflito; podes corrigi-lo.")
                self.draw()

        def play_mine(self, row, col):
            self.game.toggle_flag(row, col) if self.flag_mode else self.game.reveal(row, col)
            if self.game.lost: self.status.text = "Encontraste uma mina. Podes iniciar um novo tabuleiro."
            elif self.game.won: self.status.text = "Minesweeper concluído. Bom intervalo!"
            self.draw()

        def toggle_mode(self, *_args):
            self.flag_mode = not self.flag_mode
            self.mode_button.text = "Modo: marcar" if self.flag_mode else "Modo: revelar"

    class AprendixApp(App):
        def build(self):
            self.title = "Aprendix"
            root = BoxLayout(orientation="vertical")
            with root.canvas.before:
                root.theme_color = Color(*colors["bg"])
                root.background = RoundedRectangle(pos=root.pos, size=root.size)
            root.bind(pos=lambda *_: setattr(root.background, "pos", root.pos), size=lambda *_: setattr(root.background, "size", root.size))
            manager = ScreenManager(transition=NoTransition())
            manager.add_widget(Dashboard(name="dashboard")); manager.add_widget(Learning(name="learning"))
            manager.add_widget(Curriculum(name="curriculum")); manager.add_widget(Search(name="search"))
            manager.add_widget(FactCards(name="cards")); manager.add_widget(Reference(name="reference"))
            manager.add_widget(AssistedReader(name="reader"))
            manager.add_widget(Games(name="games"))
            nav = BoxLayout(size_hint_y=None, height=dp(60), padding=dp(4), spacing=dp(4))
            for target, title in (("dashboard", "Painel"), ("curriculum", "Curso"),
                                  ("learning", "IDE"), ("search", "Pesquisa"),
                                  ("cards", "Cards"), ("reference", "Dicionário"),
                                  ("games", "Games")):
                button = Button(text=title, background_normal="", background_color=colors["card"], color=colors["text"])
                button.theme_role = "navigation"
                button.bind(on_release=lambda _button, screen=target: setattr(manager, "current", screen)); nav.add_widget(button)
            theme = Button(
                text="Claro" if theme_name == "dark" else "Escuro",
                size_hint_x=.55, background_normal="",
                background_color=colors["accent"], color=colors["text"],
            )
            theme.theme_role = "accent"
            theme.bind(on_release=lambda button: self.toggle_theme(root, button))
            nav.add_widget(theme)
            root.add_widget(manager); root.add_widget(nav); return root

        def toggle_theme(self, root, button):
            nonlocal theme_name
            theme_name = "light" if theme_name == "dark" else "dark"
            colors.update(palettes[theme_name])
            controller.save_preference("theme", theme_name)
            Window.clearcolor = colors["bg"]
            root.theme_color.rgba = colors["bg"]
            button.text = "Claro" if theme_name == "dark" else "Escuro"
            for widget in root.walk():
                if isinstance(widget, Card):
                    widget.refresh_theme()
                role = getattr(widget, "theme_role", None)
                if isinstance(widget, Label) and role in {"text", "muted"}:
                    widget.color = colors[role]
                elif isinstance(widget, Button):
                    widget.color = colors["text"]
                    widget.background_color = colors[
                        "accent" if role == "accent" else "card"
                    ]
                elif isinstance(widget, TextInput):
                    widget.background_color = colors["card"]
                    widget.foreground_color = colors["text"]

    AprendixApp().run()
    return 0
