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
    DebugBreakpointDTO,
    DebugRequestDTO,
    LearningTheme,
    SearchFiltersDTO,
    SearchRequestDTO,
    Technology,
    TutorRequestDTO,
    TutorStrategy,
    SnippetAction,
    SnippetRequestDTO,
)
from aprendix.application.mobile import EditTelemetry, FocusMinutes, PomodoroTimer
from aprendix.application.editor_support import (
    analyze_complexity,
    apply_safe_quick_fixes,
    compare_solutions,
    diagnose_python,
    find_replace,
    format_python,
    matching_delimiter,
    organize_imports,
)
from aprendix.application.games import DIFFICULTIES, MinesweeperGame, SudokuGame
from aprendix.application.knowledge import SearchCancellationToken
from aprendix.application.navigation import CommandPalette, NavigationHistory, Route
from aprendix.application.pedagogy_tools import profile_execution, visualize_structures
from aprendix.presentation.design_system import THEMES, palette


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
    from kivy.uix.popup import Popup
    from kivy.uix.screenmanager import NoTransition, Screen, ScreenManager
    from kivy.uix.scrollview import ScrollView
    from kivy.uix.spinner import Spinner
    from kivy.uix.textinput import TextInput
    from kivy.uix.togglebutton import ToggleButton

    palettes = {name: palette(name) for name in THEMES}
    theme_name = controller.load_preference("theme", "dark")
    if theme_name not in palettes:
        theme_name = "dark"
    colors = dict(palettes[theme_name])
    try:
        font_scale = min(
            1.5, max(0.85, float(controller.load_preference("font_scale", "1.0")))
        )
    except ValueError:
        font_scale = 1.0

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
            color=colors["muted" if muted else "text"],
            font_size=dp(size * font_scale),
            halign="left", valign="top", size_hint_y=None,
            height=dp(fixed or 40),
        )
        widget.theme_role = "muted" if muted else "text"
        widget.aprendix_base_font_size = size
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
            background_normal="", background_color=colors["accent"], color=colors["accent_text"],
        )
        button.theme_role = "accent"
        button.aprendix_base_font_size = 14
        button.bind(on_release=callback)
        return button

    def scroll_column(preference_key=None):
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
        if preference_key:
            try:
                restored = min(1.0, max(0.0, float(controller.load_preference(
                    f"scroll:{preference_key}", "1.0"
                ))))
            except ValueError:
                restored = 1.0
            Clock.schedule_once(
                lambda *_: setattr(scroll, "scroll_y", restored), 0
            )

            def persist(_widget, value):
                event = getattr(scroll, "_aprendix_save_event", None)
                if event is not None:
                    event.cancel()
                scroll._aprendix_save_event = Clock.schedule_once(
                    lambda *_: controller.save_preference(
                        f"scroll:{preference_key}", f"{value:.6f}"
                    ),
                    .4,
                )

            scroll.bind(scroll_y=persist)
        return scroll, column

    class Dashboard(Screen):
        def on_pre_enter(self, *_args):
            self.clear_widgets()
            scroll, column = scroll_column("dashboard")
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
                personal = controller.personal_progress()
                evidence_card = Card()
                evidence_card.add_widget(text("Progresso baseado em evidência", size=20, bold=True, fixed=36))
                evidence_card.add_widget(text(
                    f"Domínio {personal.mastery:.0%}  ·  Retenção {personal.retention:.0%}  ·  "
                    f"Autonomia {personal.autonomy:.0%}", muted=True, fixed=30,
                ))
                evidence_card.add_widget(text(
                    f"Velocidade {personal.velocity:.0%}  ·  Confiança {personal.confidence:.0%}  ·  "
                    f"{personal.at_risk_nodes} em risco", muted=True, fixed=30,
                ))
                evidence_card.add_widget(text(
                    f"Tempo ativo {personal.active_minutes} min / total {personal.total_minutes} min  ·  "
                    f"habilidade IRT {personal.irt_ability:+.2f}", muted=True, fixed=30,
                ))
                if personal.next_action:
                    next_item = personal.next_action
                    evidence_card.add_widget(text(
                        f"Fazer agora · {next_item.title} ({next_item.duration_minutes} min)",
                        bold=True, fixed=34,
                    ))
                    evidence_card.add_widget(text(next_item.explanation, muted=True))
                time_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
                for minutes in (10, 25, 50, 90):
                    time_row.add_widget(action(
                        f"Tenho {minutes} min",
                        lambda _button, value=minutes: self._time_action(value),
                    ))
                evidence_card.add_widget(time_row)
                self.time_action_status = text(
                    "Escolhe o tempo disponível para recalcular o melhor próximo passo.",
                    muted=True, fixed=34,
                )
                evidence_card.add_widget(self.time_action_status)
                column.add_widget(evidence_card)
                if personal.weekly_plan:
                    week_card = Card()
                    week_card.add_widget(text("Plano adaptativo desta semana", size=20, bold=True, fixed=36))
                    for item in personal.weekly_plan[:7]:
                        week_card.add_widget(text(
                            f"{item.scheduled_for.strftime('%a %d')} · {item.action.value} · "
                            f"{item.title} · {item.duration_minutes} min",
                            muted=True, fixed=28,
                        ))
                    column.add_widget(week_card)
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
                    diagnostic = controller.diagnostic_exercises(limit=3)
                    if diagnostic:
                        game_card.add_widget(text(
                            "Diagnóstico recomendado · " + " · ".join(
                                item["title"] for item in diagnostic
                            ), muted=True,
                        ))
                        game_card.add_widget(action(
                            "Iniciar diagnóstico",
                            lambda *_: setattr(self.manager, "current", "curriculum"),
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

        def _time_action(self, minutes):
            try:
                item = controller.next_action(minutes)
                self.time_action_status.text = (
                    f"{minutes} min · {item.action.value} · {item.title}. {item.explanation}"
                    if item else "Ainda não existe uma ação elegível."
                )
            except ValueError as exc:
                self.time_action_status.text = str(exc)

    class Learning(Screen):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.catalogue = controller.exercises()
            self.selected = self.catalogue[0] if self.catalogue else None
            self.started = time.monotonic()
            self.previous_source = self.selected.starter_code if self.selected else ""
            self.last_copykate_source = self.previous_source
            self.typed = self.pasted = self.deleted = 0
            self.active_seconds = 0.0
            self.last_edit_at = time.monotonic()
            self.timer = PomodoroTimer(FocusMinutes.SHORT)
            self.focus_event = None
            self.draft_event = None
            self._debug_breakpoints = ()
            self._debug_watches = ()
            self._debug_session = None
            self._debug_step = 0
            self._active_project_id = None
            self._active_project_name = ""
            self._active_project_path = "main.py"
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
            saved_prompt_height = controller.load_preference("ide.prompt_height", "")
            if saved_prompt_height:
                try:
                    self.prompt.size_hint_y = None
                    self.prompt.height = dp(min(420, max(90, float(saved_prompt_height))))
                except ValueError:
                    pass
            self.editor = CodeInput(
                text=self.selected.starter_code if self.selected else "", font_size=dp(16),
                background_color=colors["card"], foreground_color=colors["text"],
                size_hint_y=0.42,
            )
            self.editor.bind(text=self.track_edit)
            self.editor.bind(cursor=self._cursor_changed)
            editor_wrap = BoxLayout(size_hint_y=0.42, spacing=dp(3))
            self.gutter = TextInput(
                text=self._line_numbers(self.editor.text), readonly=True,
                size_hint_x=None, width=dp(52), font_size=dp(14),
                background_color=colors["card"], foreground_color=colors["muted"],
                padding=(dp(7), dp(7)),
            )
            self.editor.size_hint_y = 1
            self.editor.bind(
                scroll_y=lambda _widget, value: setattr(self.gutter, "scroll_y", value)
            )
            editor_wrap.add_widget(self.gutter)
            editor_wrap.add_widget(self.editor)
            self.glossary_tip = text(
                "Dicionário: passa o rato sobre uma função ou conceito.",
                muted=True, fixed=30,
            )
            self._hover_term = ""
            self._hover_event = None
            Window.bind(mouse_pos=self._hover_dictionary)
            Window.bind(on_key_down=self._key_down)
            row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
            for title, callback in (("Executar", self.run_code), ("Corrigir", self.evaluate),
                                    ("Depurar", self.debug_setup),
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
                                    ("Ferramentas", self.engineering_tools),
                                    ("Ver grafo", self.open_graph)):
                assists.add_widget(action(title, callback))
            self.focus_duration = Spinner(text="25", values=("25", "50", "90", "120"))
            assists.add_widget(self.focus_duration)
            self.answer_confidence = Spinner(
                text="Confiança média",
                values=("Confiança baixa", "Confiança média", "Confiança alta"),
            )
            assists.add_widget(self.answer_confidence)
            assists.add_widget(action("Foco", self.toggle_focus))
            self.status = text("Pronto", muted=True, fixed=34)
            diagnostics_row = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(6))
            self.diagnostics = text("Diagnóstico local: sem erros de sintaxe.", muted=True, fixed=32)
            diagnostics_row.add_widget(self.diagnostics)
            diagnostics_row.add_widget(action("Correções seguras", self._apply_quick_fixes))
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
            for widget in (self.selector, self.prompt, edit_tools, editor_wrap, self.glossary_tip,
                           row, assists, self.status, diagnostics_row, self.justification, self.output):
                root.add_widget(widget)
            self.add_widget(root)

        @staticmethod
        def _line_numbers(source):
            return "\n".join(str(index) for index in range(1, source.count("\n") + 2))

        def _cursor_changed(self, _editor, cursor):
            index = self.editor.cursor_index(cursor)
            candidates = (index, index - 1)
            match = next(
                (matching_delimiter(self.editor.text, item) for item in candidates
                 if 0 <= item < len(self.editor.text)
                 and self.editor.text[item] in "()[]{}"),
                None,
            )
            if match is not None:
                line = self.editor.text.count("\n", 0, match) + 1
                self.status.text = f"Delimitador correspondente na linha {line}."

        def track_edit(self, _editor, value):
            now = time.monotonic()
            self.active_seconds += min(60.0, max(0.0, now - self.last_edit_at))
            self.last_edit_at = now
            self.gutter.text = self._line_numbers(value)
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
                    self._persist_editor_state, 0.6
                )
            Clock.unschedule(self._update_diagnostics)
            Clock.schedule_once(self._update_diagnostics, .35)

        def _persist_editor_state(self, *_args):
            if not self.selected:
                return
            controller.save_draft(self.selected.id, self.editor.text)
            controller.save_debug_recovery(
                self.selected.id, self.editor.text,
                cursor_index=self.editor.cursor_index(),
                breakpoints=tuple(item.model_dump(mode="json") for item in self._debug_breakpoints),
                watches=self._debug_watches,
            )

        def _resize_prompt(self, delta):
            self.prompt.size_hint_y = None
            self.prompt.height = max(dp(90), min(dp(420), self.prompt.height + delta))
            controller.save_preference(
                "ide.prompt_height", f"{self.prompt.height / max(dp(1), .001):.2f}"
            )

        def _update_diagnostics(self, *_args):
            issues = diagnose_python(self.editor.text)
            if not issues:
                self.diagnostics.text = "Diagnóstico local: sintaxe válida; sem alertas imediatos."
                return
            self.diagnostics.text = "  ·  ".join(
                f"L{item.line}:{item.column} {item.severity}: {item.message}"
                + (f" Correção: {item.quick_fix}." if item.quick_fix else "")
                for item in issues[:4]
            )

        def _apply_quick_fixes(self, *_args):
            updated, count = apply_safe_quick_fixes(self.editor.text)
            if not count:
                self.status.text = "Não existem correções automáticas seguras neste momento."
                return
            self.editor.text = updated
            self.status.text = f"{count} correção(ões) segura(s) aplicada(s); revê o resultado."
            self._update_diagnostics()

        def debug_setup(self, *_args):
            if not self.selected or not self.editor.text.strip():
                self.status.text = "Escreve código antes de depurar."
                return
            layout = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
            breaks = TextInput(
                text=", ".join(
                    str(item.line) + (f": {item.condition}" if item.condition else "")
                    for item in self._debug_breakpoints
                ),
                hint_text="Breakpoints: 3, 8: total > 10", multiline=False,
                size_hint_y=None, height=dp(44),
            )
            watches = TextInput(
                text=", ".join(self._debug_watches),
                hint_text="Watches: total, item", multiline=False,
                size_hint_y=None, height=dp(44),
            )
            explanation = text(
                "O código corre noutro processo, sem rede nem ficheiros. Condições e watches aceitam apenas expressões AST sem chamadas.",
                muted=True,
            )
            controls = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
            popup = Popup(
                title="Debugger isolado", content=layout, size_hint=(.86, .56),
                auto_dismiss=False,
            )

            def start(*_args):
                try:
                    parsed = []
                    for raw in re.split(r"[,\n]+", breaks.text):
                        raw = raw.strip()
                        if not raw:
                            continue
                        line, separator, condition = raw.partition(":")
                        parsed.append(DebugBreakpointDTO(
                            line=int(line.strip()),
                            condition=condition.strip() if separator else "",
                        ))
                    watch_values = tuple(
                        item.strip() for item in re.split(r"[,\n]+", watches.text)
                        if item.strip()
                    )
                    request = DebugRequestDTO(
                        source_code=self.editor.text, breakpoints=tuple(parsed),
                        watches=watch_values,
                    )
                except (ValueError, TypeError) as exc:
                    self.status.text = f"Configuração de debug inválida: {exc}"
                    return
                self._debug_breakpoints, self._debug_watches = request.breakpoints, request.watches
                self._persist_editor_state()
                popup.dismiss()
                self.status.text = "A executar tracing no processo isolado…"
                threading.Thread(
                    target=self._debug_worker, args=(request,), daemon=True
                ).start()

            controls.add_widget(action("Cancelar", lambda *_: popup.dismiss()))
            controls.add_widget(action("Iniciar debug", start))
            for widget in (explanation, breaks, watches, controls):
                layout.add_widget(widget)
            popup.open()

        def _debug_worker(self, request):
            try:
                result = controller.debug_code(request, self.selected.id)
                Clock.schedule_once(lambda _dt: self._show_debugger(result), 0)
            except Exception as exc:
                Clock.schedule_once(
                    lambda _dt, message=str(exc): self._show_error(message), 0
                )

        def _show_debugger(self, result):
            self._debug_session, self._debug_step = result, 0
            layout = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(7))
            controls = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(5))
            for title, mode in (("Entrar", "into"), ("Passar", "over"),
                                ("Sair", "out"), ("Continuar", "continue")):
                controls.add_widget(action(
                    title, lambda _button, value=mode: self._debug_move(value)
                ))
            analysis_controls = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(5))
            analysis_controls.add_widget(action("Perfil", self._show_execution_profile))
            analysis_controls.add_widget(action("Estruturas", self._show_structure_trace))
            analysis_controls.add_widget(action("Voltar ao passo", lambda *_: self._render_debug_frame()))
            self.debug_view = TextInput(
                readonly=True, background_color=colors["card"],
                foreground_color=colors["text"], font_size=dp(14),
            )
            close = action("Fechar debugger", lambda *_: self.debug_popup.dismiss())
            layout.add_widget(controls); layout.add_widget(analysis_controls)
            layout.add_widget(self.debug_view); layout.add_widget(close)
            self.debug_popup = Popup(
                title="Execução linha a linha", content=layout, size_hint=(.94, .9),
                auto_dismiss=False,
            )
            self._render_debug_frame()
            self.debug_popup.open()

        def _debug_move(self, mode):
            frames = self._debug_session.frames if self._debug_session else ()
            if not frames:
                return
            current = frames[self._debug_step]
            candidates = range(self._debug_step + 1, len(frames))
            if mode == "into":
                target = min(self._debug_step + 1, len(frames) - 1)
            elif mode == "over":
                target = next((index for index in candidates
                               if frames[index].event == "line"
                               and frames[index].call_depth <= current.call_depth), len(frames) - 1)
            elif mode == "out":
                target = next((index for index in candidates
                               if frames[index].call_depth < current.call_depth), len(frames) - 1)
            else:
                target = next((index for index in candidates
                               if frames[index].breakpoint_hit), len(frames) - 1)
            self._debug_step = target
            self._render_debug_frame()

        def _render_debug_frame(self):
            result = self._debug_session
            if result is None or not result.frames:
                self.debug_view.text = (
                    f"Estado: {result.status if result else 'indisponível'}\n"
                    f"{result.error_message if result else 'Sem frames.'}"
                )
                return
            frame = result.frames[self._debug_step]
            source_lines = self.editor.text.splitlines()
            context = []
            for line_number in range(max(1, frame.line - 2), min(len(source_lines), frame.line + 2) + 1):
                marker = "▶" if line_number == frame.line else " "
                context.append(f"{marker} {line_number:4} │ {source_lines[line_number - 1]}")
            def values(items):
                return "\n".join(f"  {key} = {value}" for key, value in items.items()) or "  —"
            self.debug_view.text = (
                f"Estado: {result.status} · passo {frame.step}/{len(result.frames)} · "
                f"cobertura {result.coverage_percent:.1f}%\n"
                f"Stack: profundidade {frame.call_depth} · {frame.function} · evento {frame.event}\n\n"
                + "\n".join(context)
                + f"\n\nWatches:\n{values(frame.watches)}\n\nLocais:\n{values(frame.locals)}"
                + f"\n\nGlobais permitidas:\n{values(frame.globals)}\n\nOutput:\n{frame.stdout}"
            )
            self.status.text = (
                f"Debug {result.status} · {len(result.executed_lines)} linhas · "
                f"{result.duration_ms} ms"
            )

        def _show_execution_profile(self, *_args):
            if self._debug_session is None:
                return
            profile = profile_execution(self._debug_session)
            hotspots = "\n".join(
                f"  linha {line}: {hits} execução(ões)" for line, hits in profile.hottest_lines
            ) or "  —"
            self.debug_view.text = (
                f"PERFIL LOCAL REPRODUZÍVEL\n\nDuração: {profile.duration_ms} ms\n"
                f"Passos observados: {profile.trace_steps}\n"
                f"Linhas distintas: {profile.distinct_lines}\n"
                f"Cobertura estrutural: {profile.coverage_percent:.1f}%\n\n"
                f"Linhas mais executadas:\n{hotspots}\n\n{profile.memory_note}"
            )

        def _show_structure_trace(self, *_args):
            if self._debug_session is None:
                return
            snapshots = visualize_structures(self._debug_session)
            if not snapshots:
                self.debug_view.text = (
                    "Não foram observadas listas, matrizes, conjuntos ou mapas "
                    "nos valores locais serializados pelo debugger."
                )
                return
            self.debug_view.text = "ESTRUTURAS AO LONGO DA EXECUÇÃO\n\n" + "\n".join(
                f"passo {item.step} · L{item.line} · {item.name}: {item.kind} · "
                f"tamanho {item.size}"
                + (f" · forma {item.shape}" if item.shape else "")
                + f"\n  {item.preview}"
                for item in snapshots
            )

        def engineering_tools(self, *_args):
            layout = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(7))
            find_value = TextInput(hint_text="Procurar", multiline=False, size_hint_y=None, height=dp(40))
            replacement = TextInput(hint_text="Substituir por", multiline=False, size_hint_y=None, height=dp(40))
            alternative = TextInput(
                hint_text="Opcional: cola uma segunda solução para comparar",
                multiline=True,
            )
            controls = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(5))
            popup = Popup(
                title="Ferramentas de engenharia", content=layout,
                size_hint=(.9, .78), auto_dismiss=False,
            )

            def format_source(*_args):
                try:
                    self.editor.text = format_python(self.editor.text)
                    self.status.text = "Formatação conservadora aplicada."
                except SyntaxError as exc:
                    self.status.text = f"Formatação bloqueada: sintaxe inválida na linha {exc.lineno}."

            def imports(*_args):
                try:
                    self.editor.text = organize_imports(self.editor.text)
                    self.status.text = "Imports iniciais organizados."
                except SyntaxError as exc:
                    self.status.text = f"Não foi possível organizar: {exc.msg}."

            def replace(*_args):
                try:
                    self.editor.text, count = find_replace(
                        self.editor.text, find_value.text, replacement.text
                    )
                    self.status.text = f"{count} ocorrência(s) substituída(s)."
                except ValueError as exc:
                    self.status.text = str(exc)

            def inspect(*_args):
                try:
                    report = analyze_complexity(self.editor.text)
                    message = (
                        f"Tempo estimado {report['time']} · espaço {report['space']} · "
                        f"profundidade de ciclos {report['max_loop_depth']}.\n{report['note']}"
                    )
                    if alternative.text.strip():
                        comparison = compare_solutions(self.editor.text, alternative.text)
                        message += (
                            f"\nSimilaridade textual {comparison['text_similarity']:.0%}. "
                            f"Alternativa: {comparison['right_complexity']['time']} / "
                            f"{comparison['right_complexity']['space']}."
                        )
                    self.output.text = message
                except SyntaxError as exc:
                    self.status.text = f"Análise indisponível: {exc.msg}."

            for title, callback in (("Formatar", format_source), ("Imports", imports),
                                    ("Substituir", replace), ("Analisar", inspect)):
                controls.add_widget(action(title, callback))
            layout.add_widget(find_value); layout.add_widget(replacement)
            layout.add_widget(alternative); layout.add_widget(controls)
            layout.add_widget(action("Fechar", lambda *_: popup.dismiss()))
            popup.open()

        def open_graph(self, _button):
            try:
                controller.open_graph()
                self.status.text = "Grafo aberto no navegador padrão."
            except Exception as exc:
                self.status.text = f"Não foi possível abrir o grafo: {exc}"

        def select(self, _spinner, title):
            self.selected = next((item for item in self.catalogue if item.title == title), None)
            if self.selected:
                self._active_project_id = None
                self._active_project_name = ""
                self._active_project_path = "main.py"
                draft = controller.load_draft(self.selected.id)
                recovery = controller.load_debug_recovery(self.selected.id)
                self.prompt.text = self.selected.prompt
                self.editor.text = (
                    recovery["source"] if recovery is not None else
                    draft if draft is not None else self.selected.starter_code
                )
                self._debug_breakpoints = tuple(
                    DebugBreakpointDTO(**item) for item in recovery["breakpoints"]
                ) if recovery else ()
                self._debug_watches = tuple(recovery["watches"]) if recovery else ()
                if recovery:
                    Clock.schedule_once(
                        lambda _dt: setattr(
                            self.editor, "cursor",
                            self.editor.get_cursor_from_index(min(
                                int(recovery["cursor_index"]), len(self.editor.text)
                            )),
                        ), 0,
                    )
                self.started = time.monotonic()
                self.previous_source = self.editor.text
                self.last_copykate_source = self.editor.text
                self.typed = self.pasted = self.deleted = 0
                self.active_seconds = 0.0
                self.last_edit_at = self.started

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

        def _key_down(self, _window, key, _scancode, _codepoint, _modifiers):
            if key != 282 or not self.editor.focus:  # F1
                return False
            column, row = self.editor.cursor
            lines = self.editor.text.splitlines()
            line = lines[row] if 0 <= row < len(lines) else ""
            match = next(
                (item for item in re.finditer(r"[A-Za-z_][A-Za-z0-9_]*", line)
                 if item.start() <= column <= item.end()),
                None,
            )
            if match:
                reference = self.manager.get_screen("reference")
                reference.query.text = match.group(0)
                reference.search()
                self.manager.current = "reference"
                return True
            return False

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
                    active_seconds=min(elapsed // 1000, round(self.active_seconds)),
                    response_confidence={
                        "Confiança baixa": .25,
                        "Confiança média": .5,
                        "Confiança alta": .9,
                    }[self.answer_confidence.text],
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
                name = self._active_project_name or (
                    self.selected.title if self.selected else "Projeto Python"
                )
                project = controller.save_project(
                    name, self.editor.text, self._active_project_id,
                    relative_path=self._active_project_path,
                )
                self._active_project_id = project.id
                self._active_project_name = project.name
                self._active_project_path = project.relative_path
                self.status.text = (
                    f"Projeto local guardado: {project.name} · {project.relative_path}"
                )
            except Exception as exc:
                self._show_error(str(exc))

        def load_project_file(self, project):
            self._active_project_id = project.id
            self._active_project_name = project.name
            self._active_project_path = project.relative_path
            self.editor.text = project.source_code
            self.status.text = f"A editar {project.name} · {project.relative_path}"

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
            scroll, column = scroll_column("theory-cards")
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
            due = {card_id: index for index, card_id in enumerate(controller.daily_card_ids(limit=100))}
            self.cards.sort(key=lambda card: (card.id not in due, due.get(card.id, 10_000)))
            if not self.cards:
                root.add_widget(text("Sem cards originais para este tema.", muted=True))
                self.add_widget(root); return
            self.index %= len(self.cards)
            item = self.cards[self.index]
            reason = (
                "Revisão prevista pelo teu domínio e espaçamento"
                if item.id in due else "Exploração para ampliar o teu mapa de conceitos"
            )
            root.add_widget(text(f"Sabias que? · {self.index + 1}/{len(self.cards)}", size=26, bold=True, fixed=48))
            root.add_widget(text("Porque apareceu: " + reason, muted=True, fixed=30))
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
            arrows.add_widget(action("Já sabia", lambda *_: self.navigate(-1, "already_knew")))
            arrows.add_widget(action("Útil", lambda *_: self.navigate(1, "useful")))
            arrows.add_widget(action("Confuso", lambda *_: self.navigate(-1, "confusing")))
            arrows.add_widget(action("Rever", lambda *_: self.navigate(1, "review")))
            root.add_widget(arrows)
            themes = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(7))
            themes.add_widget(action("^ tema", lambda *_: self.step_area(-1)))
            themes.add_widget(action("tema v", lambda *_: self.step_area(1)))
            root.add_widget(themes)
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

        def navigate(self, delta, feedback):
            try:
                controller.review_card(self.cards[self.index].id, feedback=feedback)
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
            paths = tuple(controller.learning_paths())
            self._tracks = {item["course_title"]: item["track_slug"] for item in paths}
            self._path_state = {item["track_slug"]: item for item in paths}
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
            self.scroll, self.column = scroll_column("curriculum"); root.add_widget(self.scroll)
            self.add_widget(root)

        def on_pre_enter(self, *_args):
            self.render()

        def render(self):
            self.column.clear_widgets()
            self._path_state = {
                item["track_slug"]: item for item in controller.learning_paths()
            }
            slug = self._tracks.get(self.track.text)
            if not slug:
                self.column.add_widget(text("Ainda não existe um percurso local."))
                return
            units = controller.units(slug)
            self.column.add_widget(text(self.track.text, size=28, bold=True))
            path_state = self._path_state.get(slug)
            if path_state:
                state = "disponível" if path_state["unlocked"] else "requer o percurso anterior"
                self.column.add_widget(text(
                    f"{path_state['completed_units']}/{path_state['total_units']} etapas · {state}",
                    muted=True, fixed=30,
                ))
                self.column.add_widget(ProgressBar(
                    max=1, value=path_state["progress"], size_hint_y=None, height=dp(14),
                ))
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
            self.scroll, self.column = scroll_column("dictionary"); root.add_widget(self.scroll)
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
                    card.add_widget(action(
                        "Experimentar no IDE",
                        lambda _button, code=entry["example"]: self._try_in_ide(code),
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

        def _try_in_ide(self, code):
            ide = self.manager.get_screen("learning")
            ide.editor.text = code
            self.manager.current = "learning"

    class SnippetAssistant(Screen):
        ACTIONS = {
            "Explicar": SnippetAction.EXPLAIN, "Ajudar a completar": SnippetAction.COMPLETE,
            "Transformar em algoritmo": SnippetAction.TO_ALGORITHM,
            "Converter para Python": SnippetAction.TO_PYTHON,
            "Encontrar problemas": SnippetAction.FIND_PROBLEMS,
            "Criar testes": SnippetAction.CREATE_TESTS,
            "Visualizar": SnippetAction.VISUALIZE, "Ligar ao curso": SnippetAction.LINK_COURSE,
        }

        def __init__(self, **kwargs):
            super().__init__(**kwargs); self.ocr_draft = None; self.result = None
            root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(7))
            top = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
            self.mode = Spinner(text="Texto", values=("Texto", "Imagem"))
            self.action = Spinner(text="Explicar", values=tuple(self.ACTIONS))
            top.add_widget(self.mode); top.add_widget(self.action)
            top.add_widget(action("Apagar histórico", self._delete_history)); root.add_widget(top)
            path_row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
            self.image_path = TextInput(hint_text="PNG/JPEG/WebP — arrasta ou indica o caminho", multiline=False)
            path_row.add_widget(self.image_path); path_row.add_widget(action("Extrair OCR", self.extract))
            root.add_widget(path_row)
            self.input = TextInput(
                hint_text="Escreve/cola código ou pseudocódigo; o texto OCR aparece aqui para confirmação.",
                multiline=True, size_hint_y=.38,
            )
            root.add_widget(self.input)
            confirmation = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
            self.confirmed = CheckBox(size_hint_x=None, width=dp(42))
            confirmation.add_widget(self.confirmed)
            confirmation.add_widget(text("Confirmei/corrigi o texto extraído (obrigatório após OCR)", muted=True, fixed=42))
            confirmation.add_widget(action("Analisar sem executar", self.analyze))
            root.add_widget(confirmation)
            self.scroll, self.column = scroll_column("snippet-analysis"); root.add_widget(self.scroll)
            self.add_widget(root)
            try: Window.bind(on_drop_file=self._drop_file)
            except Exception: pass

        def _drop_file(self, _window, value, *_args):
            try: self.image_path.text = os.fsdecode(value)
            except (TypeError, UnicodeDecodeError): return
            self.mode.text = "Imagem"

        def extract(self, *_args):
            path = self.image_path.text.strip()
            if not path: return
            self.column.clear_widgets(); self.column.add_widget(text("OCR local em processamento…", muted=True))
            threading.Thread(target=self._extract_worker, args=(Path(path),), daemon=True).start()

        def _extract_worker(self, path):
            try:
                draft = controller.extract_snippet_image(path)
                Clock.schedule_once(lambda _dt: self._ocr_ready(draft), 0)
            except Exception as exc:
                Clock.schedule_once(lambda _dt, message=str(exc): self._error(message), 0)

        def _ocr_ready(self, draft):
            self.ocr_draft = draft; self.input.text = draft.text; self.confirmed.active = False
            self.column.clear_widgets()
            self.column.add_widget(text(
                f"OCR {draft.confidence:.0%} · confirma antes de analisar.\n" + "\n".join(draft.warnings),
                muted=True,
            ))

        def analyze(self, *_args):
            if self.ocr_draft is not None and not self.confirmed.active:
                self._error("Confirma ou corrige primeiro o texto extraído da imagem."); return
            if not self.input.text.strip(): return
            request = SnippetRequestDTO(
                text=self.input.text, action=self.ACTIONS[self.action.text],
                ocr_confirmed=self.ocr_draft is None or self.confirmed.active,
            )
            self.column.clear_widgets(); self.column.add_widget(text("Análise estrutural local…", muted=True))
            threading.Thread(target=self._analysis_worker, args=(request,), daemon=True).start()

        def _analysis_worker(self, request):
            try:
                result = controller.analyze_snippet(request)
                Clock.schedule_once(lambda _dt: self._render_result(result), 0)
            except Exception as exc:
                Clock.schedule_once(lambda _dt, message=str(exc): self._error(message), 0)

        def _error(self, message):
            self.column.clear_widgets(); self.column.add_widget(text("Análise indisponível: " + message, muted=True))

        def _render_result(self, result):
            self.result = result; self.column.clear_widgets()
            card = Card(); card.add_widget(text(
                f"{result.detected_language} · confiança {result.confidence:.0%} · "
                f"tempo {result.complexity_time} · espaço {result.complexity_space}",
                bold=True, fixed=38,
            )); card.add_widget(text(result.summary, size=16))
            for title, items in (("Problemas", result.problems), ("Testes sugeridos", result.suggested_tests),
                                 ("Conceitos", result.related_concepts), ("Linha a linha", result.line_explanations)):
                if items: card.add_widget(text(title + "\n• " + "\n• ".join(items[:30]), muted=True))
            if result.proposed_code:
                card.add_widget(CodeInput(text=result.proposed_code, readonly=True, size_hint_y=None, height=dp(220)))
                card.add_widget(action("Abrir nova versão no IDE", self._open_ide))
            self.column.add_widget(card)

        def _open_ide(self, *_args):
            if not self.result or not self.result.proposed_code: return
            ide = self.manager.get_screen("learning"); ide.editor.text = self.result.proposed_code
            self.manager.current = "learning"

        def _delete_history(self, *_args):
            self._error(f"Histórico apagado: {controller.delete_snippet_history()} entrada(s).")

    class Projects(Screen):
        def on_pre_enter(self, *_args):
            self.render()

        def render(self, *_args):
            self.clear_widgets()
            root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
            root.add_widget(text("Projetos e portefólio local", size=28, bold=True, fixed=52))
            scroll, column = scroll_column("projects")
            projects = controller.projects()
            if projects:
                column.add_widget(text("Os meus projetos", size=21, bold=True, fixed=40))
                for project in projects:
                    card = Card()
                    card.add_widget(text(project.name, size=19, bold=True, fixed=34))
                    files = controller.project_files(project.id)
                    card.add_widget(text(
                        f"{len(files)} ficheiro(s) · guardado apenas neste perfil",
                        muted=True, fixed=28,
                    ))
                    for project_file in files:
                        file_row = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(6))
                        file_row.add_widget(text(project_file.relative_path, muted=True, fixed=34))
                        file_row.add_widget(action(
                            "Abrir no IDE",
                            lambda _b, item=project_file: self.open_file(item),
                        ))
                        card.add_widget(file_row)
                    card.add_widget(action(
                        "+ Novo ficheiro",
                        lambda _b, item=project: self.new_file(item),
                    ))
                    column.add_widget(card)
            entries = {item.project_id: item for item in controller.portfolio_entries()}
            if entries:
                column.add_widget(text("Em curso e concluídos", size=21, bold=True, fixed=40))
                for entry in entries.values():
                    card = Card()
                    card.add_widget(text(entry.title, size=19, bold=True))
                    card.add_widget(text(
                        f"{entry.work_mode} · {entry.status} · " +
                        (f"{entry.score:.0%}" if entry.score is not None else "por avaliar"),
                        muted=True, fixed=30,
                    ))
                    actions = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
                    actions.add_widget(action(
                        "Avaliar", lambda _b, pid=entry.project_id: self.evaluate(pid),
                    ))
                    actions.add_widget(action(
                        "Exportar ZIP", lambda _b, pid=entry.project_id: self.export(pid),
                    ))
                    card.add_widget(actions); column.add_widget(card)
            column.add_widget(text("Capstones por percurso", size=21, bold=True, fixed=44))
            for template in controller.project_templates():
                card = Card()
                card.add_widget(text(template.title, size=19, bold=True))
                card.add_widget(text(template.brief, size=15))
                card.add_widget(text(
                    f"{template.level} · {len(template.milestones)} milestones · "
                    + ("briefing profissional" if template.professional_briefing else "briefing guiado"),
                    muted=True, fixed=30,
                ))
                actions = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
                actions.add_widget(action(
                    "Começar guiado", lambda _b, tid=template.id: self.start(tid, "guided"),
                ))
                actions.add_widget(action(
                    "Começar autónomo", lambda _b, tid=template.id: self.start(tid, "autonomous"),
                ))
                card.add_widget(actions); column.add_widget(card)
            root.add_widget(scroll); self.add_widget(root)

        def start(self, template_id, mode):
            project = controller.start_guided_project(template_id, mode=mode)
            self.open_file(project)

        def open_file(self, project):
            ide = self.manager.get_screen("learning")
            ide.load_project_file(project)
            self.manager.current = "learning"

        def new_file(self, project):
            layout = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
            relative_path = TextInput(
                hint_text="Caminho, por exemplo src/calculos.py", multiline=False,
                size_hint_y=None, height=dp(44),
            )
            source = CodeInput(
                text='"""Novo módulo local."""\n', size_hint_y=1,
            )
            controls = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
            popup = Popup(
                title=f"Novo ficheiro · {project.name}", content=layout,
                size_hint=(.88, .78), auto_dismiss=False,
            )

            def save(*_args):
                try:
                    item = controller.save_project(
                        project.name, source.text, project.id,
                        relative_path=relative_path.text,
                    )
                except Exception as exc:
                    relative_path.hint_text = f"Caminho inválido: {exc}"
                    return
                popup.dismiss()
                self.open_file(item)

            controls.add_widget(action("Cancelar", lambda *_: popup.dismiss()))
            controls.add_widget(action("Criar e abrir", save))
            layout.add_widget(relative_path); layout.add_widget(source); layout.add_widget(controls)
            popup.open()

        def evaluate(self, project_id):
            result = controller.evaluate_project(project_id)
            self.render()
            Popup(
                title="Avaliação reproduzível",
                content=text(f"Pontuação {result.score:.0%}\n" + "\n".join(result.findings) or "Sem falhas."),
                size_hint=(.78, .65),
            ).open()

        def export(self, project_id):
            destination = Path.home() / "Documents" / "Aprendix Exports" / f"{project_id}.zip"
            path = controller.export_project(project_id, destination)
            Popup(title="Portefólio exportado", content=text(str(path)), size_hint=(.78, .4)).open()

    class Tutor(Screen):
        STRATEGIES = {
            "Explicar de outra forma": TutorStrategy.EXPLAIN_DIFFERENTLY,
            "Pergunta socrática": TutorStrategy.SOCRATIC,
            "Dar exemplo novo": TutorStrategy.NEW_EXAMPLE,
            "Mostrar pré-requisito": TutorStrategy.PREREQUISITE,
            "Simplificar matemática": TutorStrategy.SIMPLIFY_MATH,
            "Analisar erro": TutorStrategy.ANALYZE_ERROR,
            "Criar mini-exercício": TutorStrategy.MINI_EXERCISE,
        }

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
            root.add_widget(text("Tutor offline fundamentado", size=28, bold=True, fixed=50))
            controls = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
            self.strategy = Spinner(
                text="Explicar de outra forma", values=tuple(self.STRATEGIES),
            )
            self.locked = CheckBox(size_hint_x=None, width=dp(42))
            controls.add_widget(self.strategy)
            controls.add_widget(text("Avaliação bloqueada", muted=True, fixed=42))
            controls.add_widget(self.locked)
            controls.add_widget(action("Apagar histórico", self._delete_history))
            root.add_widget(controls)
            self.question = TextInput(
                hint_text="Escreve a dúvida, o erro ou o conceito…", multiline=True,
                size_hint_y=None, height=dp(120),
            )
            root.add_widget(self.question)
            root.add_widget(action("Pedir orientação local", self.ask))
            self.scroll, self.column = scroll_column("tutor")
            root.add_widget(self.scroll)
            self.add_widget(root)

        def ask(self, *_args):
            question = self.question.text.strip()
            if not question:
                return
            self.column.clear_widgets()
            self.column.add_widget(text("A recuperar evidência local aprovada…", muted=True))
            request = TutorRequestDTO(
                question=question, strategy=self.STRATEGIES[self.strategy.text],
                evaluation_locked=self.locked.active,
            )
            threading.Thread(target=self._ask_worker, args=(request,), daemon=True).start()

        def _ask_worker(self, request):
            try:
                response = controller.ask_tutor(request)
                Clock.schedule_once(lambda _dt: self._render_response(response), 0)
            except Exception as exc:
                Clock.schedule_once(lambda _dt, message=str(exc): self._render_error(message), 0)

        def _render_error(self, message):
            self.column.clear_widgets()
            self.column.add_widget(text("Tutor indisponível: " + message, muted=True))

        def _render_response(self, response):
            self.column.clear_widgets()
            status = "Recusa segura" if response.declined else "Resposta fundamentada"
            self.column.add_widget(text(
                f"{status} · confiança {response.confidence:.0%}" +
                (" · cache cifrada" if response.from_cache else ""),
                size=19, bold=True, fixed=40,
            ))
            card = Card()
            card.add_widget(text(response.answer, size=16))
            self.column.add_widget(card)
            for index, evidence in enumerate(response.evidence, start=1):
                source = Card()
                source.add_widget(text(f"[{index}] {evidence.title}", bold=True, fixed=34))
                source.add_widget(text(evidence.excerpt[:700], muted=True))
                self.column.add_widget(source)

        def _delete_history(self, *_args):
            count = controller.delete_tutor_history()
            self.column.clear_widgets()
            self.column.add_widget(text(f"Histórico local apagado: {count} entrada(s).", muted=True))

    class Search(Screen):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self._compare_selected = set()
            self._search_token = None
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
            search_actions = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(7))
            self.search_button = action("Pesquisar", self.start)
            self.cancel_button = action("Cancelar", self._cancel_search)
            self.cancel_button.disabled = True
            self.compare_button = action("Comparar fontes (0)", self._compare)
            search_actions.add_widget(self.search_button)
            search_actions.add_widget(self.cancel_button)
            search_actions.add_widget(self.compare_button)
            for widget in (self.query, filters, search_actions, self.status, result_scroll):
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
            self.cancel_button.disabled = False
            if self._search_token is not None:
                self._search_token.cancel()
            self._search_token = SearchCancellationToken()
            threading.Thread(
                target=self.worker, args=(request, self._search_token), daemon=True
            ).start()

        def worker(self, request, cancellation):
            try:
                response = controller.search(request, cancellation)
                Clock.schedule_once(lambda _dt: self.render(response, cancellation), 0)
            except Exception as exc:
                Clock.schedule_once(
                    lambda _dt, message=str(exc): self.render_error(message, cancellation), 0
                )

        def render_error(self, message, cancellation=None):
            if cancellation is not None and cancellation is not self._search_token:
                return
            self.search_button.disabled = False
            self.cancel_button.disabled = True
            self.status.text = f"Pesquisa indisponível: {message}"

        def render(self, response, cancellation=None):
            if cancellation is not None and cancellation is not self._search_token:
                return
            self.results.clear_widgets()
            self._compare_selected.clear()
            self.compare_button.text = "Comparar fontes (0)"
            self.search_button.disabled = False
            self.cancel_button.disabled = True
            if response.cancelled:
                self.status.text = "Pesquisa cancelada."
                return
            mode = "local + web" if response.used_web_fallback else "local"
            intent_label = response.intent.value.replace("-", " ")
            self.status.text = (
                f"Resposta {mode} · {intent_label} · confiança {response.confidence:.0%} "
                f"· {response.elapsed_ms:.0f} ms"
            )
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
                if hit.why_shown:
                    card.add_widget(text(
                        "Porque apareceu: " + " · ".join(hit.why_shown),
                        muted=True, size=13,
                    ))
                if hit.origin.value == "local":
                    selector = ToggleButton(
                        text="Selecionar para comparar", size_hint_y=None, height=dp(38)
                    )
                    selector.bind(
                        state=lambda _button, state, evidence_id=hit.id:
                        self._toggle_compare(evidence_id, state)
                    )
                    card.add_widget(selector)
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

        def _cancel_search(self, *_args):
            if self._search_token is not None:
                self._search_token.cancel()
            self.cancel_button.disabled = True
            self.status.text = "A cancelar pesquisa…"

        def _toggle_compare(self, evidence_id, state):
            if state == "down":
                if len(self._compare_selected) < 4:
                    self._compare_selected.add(evidence_id)
            else:
                self._compare_selected.discard(evidence_id)
            self.compare_button.text = f"Comparar fontes ({len(self._compare_selected)})"

        def _compare(self, *_args):
            if len(self._compare_selected) < 2:
                self.status.text = "Seleciona pelo menos duas fontes locais."
                return
            reader = self.manager.get_screen("reader")
            reader.load_comparison(tuple(self._compare_selected), self.query.text)
            self.manager.current = "reader"

        def _open_reader(self, evidence_id):
            reader = self.manager.get_screen("reader")
            reader.load(evidence_id, self.query.text)
            self.manager.current = "reader"

    class AssistedReader(Screen):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.detail = None
            self.comparison = ()
            root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(7))
            top = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
            top.add_widget(action("‹ Pesquisa", lambda *_: setattr(self.manager, "current", "search")))
            for label, mode in (("Resumo", "summary"), ("Versão simples", "simplified"), ("Conteúdo normal", "original")):
                top.add_widget(action(label, lambda _button, value=mode: self.show(value)))
            self.open_source = action("Abrir fonte", self._open_source)
            top.add_widget(self.open_source)
            top.add_widget(action("Guardar", self._toggle_bookmark))
            top.add_widget(action("Nota", self._note_popup))
            root.add_widget(top)
            self.status = text("Escolhe um resultado local.", muted=True, fixed=32)
            root.add_widget(self.status)
            self.scroll, self.column = scroll_column("reader"); root.add_widget(self.scroll)
            self.add_widget(root)

        def load(self, evidence_id, query=""):
            self.detail = None; self.comparison = (); self.column.clear_widgets()
            self.status.text = "A preparar leitura assistida local…"
            threading.Thread(target=self._worker, args=(evidence_id, query), daemon=True).start()

        def _worker(self, evidence_id, query):
            try:
                detail = controller.reading_detail(evidence_id, query=query)
                Clock.schedule_once(lambda _dt: self._loaded(detail), 0)
            except Exception as exc:
                Clock.schedule_once(lambda _dt, message=str(exc): setattr(self.status, "text", message), 0)

        def load_comparison(self, evidence_ids, query=""):
            self.detail = None; self.comparison = (); self.column.clear_widgets()
            self.status.text = "A preparar comparação local…"
            threading.Thread(
                target=self._comparison_worker, args=(evidence_ids, query), daemon=True
            ).start()

        def _comparison_worker(self, evidence_ids, query):
            try:
                details = controller.compare_readings(evidence_ids, query=query)
                Clock.schedule_once(lambda _dt: self._comparison_loaded(details), 0)
            except Exception as exc:
                Clock.schedule_once(
                    lambda _dt, message=str(exc): setattr(self.status, "text", message), 0
                )

        def _comparison_loaded(self, details):
            self.comparison = tuple(details)
            self.detail = self.comparison[0] if self.comparison else None
            self.status.text = f"Comparação entre {len(self.comparison)} fontes locais."
            self.show("summary")

        def _loaded(self, detail):
            self.detail = detail
            self.comparison = ()
            self.status.text = detail.copyright_note
            self.show("summary")

        def show(self, mode):
            self.column.clear_widgets()
            if self.detail is None:
                self.column.add_widget(text("A carregar…", muted=True)); return
            if self.comparison:
                labels = {"summary": "Resumo", "simplified": "Versão simplificada", "original": "Conteúdo normal"}
                grid = GridLayout(
                    cols=2 if Window.width >= dp(900) else 1,
                    spacing=dp(10), size_hint_y=None,
                )
                grid.bind(minimum_height=grid.setter("height"))
                for detail in self.comparison:
                    source_card = Card()
                    source_card.add_widget(text(detail.title, size=20, bold=True))
                    body = {"summary": detail.summary, "simplified": detail.simplified,
                            "original": detail.original_content}[mode]
                    source_card.add_widget(text(labels[mode], muted=True, fixed=28))
                    source_card.add_widget(TextInput(
                        text=body, readonly=True, font_size=dp(14),
                        background_color=colors["card"], foreground_color=colors["text"],
                        size_hint_y=None, height=dp(min(620, max(260, 80 + len(body) // 3))),
                    ))
                    grid.add_widget(source_card)
                self.column.add_widget(grid)
                return
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
                        f"{source.guidance_category.title()} · {source.title} · "
                        f"{source.difficulty.value} · ~{source.estimated_minutes} min",
                        lambda _button, url=source.canonical_url: webbrowser.open(url),
                    ))
                    sources.add_widget(text(
                        f"Porquê: {source.why_it_matters}\nSecções: "
                        + "; ".join(source.recommended_sections),
                        muted=True,
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

        def _toggle_bookmark(self, *_args):
            if self.detail is None:
                return
            active = controller.toggle_reading_bookmark(self.detail.evidence_id)
            self.status.text = "Marcador guardado localmente." if active else "Marcador removido."

        def _note_popup(self, *_args):
            if self.detail is None:
                return
            layout = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
            note = TextInput(
                hint_text="Escreve uma nota privada sobre esta fonte…", multiline=True,
                background_color=colors["card"], foreground_color=colors["text"],
            )
            controls = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
            popup = Popup(title="Nova nota local", content=layout,
                          size_hint=(.82, .62), auto_dismiss=False)

            def save(*_args):
                try:
                    controller.save_reading_note(self.detail.evidence_id, note.text)
                except ValueError as exc:
                    self.status.text = str(exc)
                    return
                popup.dismiss()
                self.status.text = "Nota cifrada e guardada neste dispositivo."

            controls.add_widget(action("Cancelar", lambda *_: popup.dismiss()))
            controls.add_widget(action("Guardar nota", save))
            layout.add_widget(note)
            layout.add_widget(controls)
            popup.open()

    class DataAndUpdates(Screen):
        """Explicit local profile transfer and signed content-pack controls."""

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            scroll, column = scroll_column("data")
            column.add_widget(text("Dados e atualizações", size=27, bold=True))
            column.add_widget(text(
                "Nada é enviado para a cloud. O perfil portátil é cifrado com a tua frase-passe; "
                "os packs só são ativados depois de validar assinatura, hashes e conteúdo.",
                muted=True,
            ))
            profile = Card()
            profile.add_widget(text("Transferir perfil entre PC e mobile", size=20, bold=True))
            self.profile_path = TextInput(
                text=str(Path.home() / "Documents" / "Aprendix-perfil.apxprofile"),
                multiline=False, hint_text="Caminho para .apxprofile", size_hint_y=None, height=dp(46),
            )
            self.passphrase = TextInput(
                multiline=False, password=True, hint_text="Frase-passe (mínimo 10 caracteres)",
                size_hint_y=None, height=dp(46),
            )
            profile.add_widget(self.profile_path); profile.add_widget(self.passphrase)
            buttons = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
            buttons.add_widget(action("Exportar", lambda *_: self._profile("export")))
            buttons.add_widget(action("Antever", lambda *_: self._profile("preview")))
            buttons.add_widget(action("Importar", lambda *_: self._profile("import")))
            profile.add_widget(buttons); column.add_widget(profile)

            packs = Card()
            packs.add_widget(text("Packs de conteúdo assinados", size=20, bold=True))
            self.pack_path = TextInput(
                multiline=False, hint_text="Caminho para atualização .apxpack",
                size_hint_y=None, height=dp(46),
            )
            packs.add_widget(self.pack_path)
            pack_buttons = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
            pack_buttons.add_widget(action("Inspecionar", lambda *_: self._pack("inspect")))
            pack_buttons.add_widget(action("Instalar", lambda *_: self._pack("install")))
            pack_buttons.add_widget(action("Atualizar lista", lambda *_: self.refresh_packs()))
            packs.add_widget(pack_buttons)
            self.rollback_value = TextInput(
                multiline=False, hint_text="pack-id@1.2.3 para rollback",
                size_hint_y=None, height=dp(46),
            )
            packs.add_widget(self.rollback_value)
            packs.add_widget(action("Ativar versão anterior", lambda *_: self._rollback()))
            self.pack_list = text("Nenhum pack adicional instalado.", muted=True)
            packs.add_widget(self.pack_list); column.add_widget(packs)

            remote = Card()
            remote.add_widget(text("Atualização semanal opcional", size=20, bold=True))
            remote.add_widget(text(
                "Só contacta o registo HTTPS quando pedires. Antes de instalar mostra tamanho, "
                "fontes e percursos; assinatura Ed25519 e hashes continuam obrigatórios.",
                muted=True,
            ))
            self.registry_url = TextInput(
                text=controller.load_preference("updates.registry_url", ""),
                multiline=False, hint_text="https://registo-aprendix/registry.json",
                size_hint_y=None, height=dp(46),
            )
            self.remote_identity = TextInput(
                multiline=False, hint_text="pack-id@1.2.3",
                size_hint_y=None, height=dp(46),
            )
            policy_row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
            self.weekly_enabled = CheckBox(
                active=controller.load_preference("updates.weekly_enabled", "0") == "1",
                size_hint_x=None, width=dp(40),
            )
            self.wifi_only = CheckBox(
                active=controller.load_preference("updates.wifi_only", "0") == "1",
                size_hint_x=None, width=dp(40),
            )
            self.power_only = CheckBox(
                active=controller.load_preference("updates.power_only", "0") == "1",
                size_hint_x=None, width=dp(40),
            )
            policy_row.add_widget(self.weekly_enabled)
            policy_row.add_widget(text("Semanal", muted=True, fixed=38))
            policy_row.add_widget(self.wifi_only)
            policy_row.add_widget(text("Só rede não medida", muted=True, fixed=38))
            policy_row.add_widget(self.power_only)
            policy_row.add_widget(text("Só com alimentação", muted=True, fixed=38))
            policy_row.add_widget(action("Guardar opção", self._save_update_policy))
            remote.add_widget(self.registry_url); remote.add_widget(policy_row)
            remote.add_widget(self.remote_identity)
            remote_buttons = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
            remote_buttons.add_widget(action("Ver novidades", lambda *_: self._check_remote()))
            remote_buttons.add_widget(action("Instalar seleção", lambda *_: self._install_remote()))
            remote.add_widget(remote_buttons)
            self.remote_list = text("Nenhuma consulta de rede efetuada.", muted=True)
            remote.add_widget(self.remote_list); column.add_widget(remote)
            self.status = text("Pronto.", muted=True)
            column.add_widget(self.status); self.add_widget(scroll)

        def on_pre_enter(self, *_args):
            self.refresh_packs()

        def _background(self, operation):
            self.status.text = "A validar…"
            def worker():
                try:
                    result = operation()
                    message = str(result) if result is not None else "Operação concluída."
                except Exception as exc:
                    message = f"Não foi possível concluir: {exc}"
                Clock.schedule_once(lambda *_: self._done(message), 0)
            threading.Thread(target=worker, daemon=True).start()

        def _done(self, message):
            self.status.text = message
            self.refresh_packs()

        def _profile(self, kind):
            path, secret = Path(self.profile_path.text.strip()), self.passphrase.text
            if kind == "export":
                self._background(lambda: f"Perfil exportado: {controller.export_profile(path, secret)}")
            elif kind == "preview":
                self._background(lambda: f"Antevisão segura: {controller.preview_profile(path, secret)}")
            else:
                self._background(lambda: f"Perfil importado: {controller.import_profile(path, secret)}")

        def _pack(self, kind):
            path = Path(self.pack_path.text.strip())
            operation = controller.inspect_content_pack if kind == "inspect" else controller.install_content_pack
            self._background(lambda: operation(path))

        def _rollback(self):
            try:
                pack_id, version = self.rollback_value.text.strip().split("@", 1)
            except ValueError:
                self.status.text = "Usa o formato pack-id@1.2.3."
                return
            self._background(lambda: controller.rollback_content_pack(pack_id, version))

        def _check_remote(self):
            registry = self.registry_url.text.strip()
            if not registry:
                self.status.text = "Indica o URL HTTPS do registo assinado."
                return
            self.status.text = "A consultar o registo por ação explícita…"
            def worker():
                try:
                    result = controller.check_content_updates(
                        registry, force=True, wifi_only=self.wifi_only.active,
                        external_power_only=self.power_only.active,
                    )
                    offers = result["offers"]
                    message = "\n\n".join(
                        f"{item['identity']} · {item['title']} · {item['size'] / 1048576:.1f} MB\n"
                        f"{item['summary']}\nFontes: {', '.join(item['sources'])}\n"
                        f"Percursos: {', '.join(item['affected_tracks']) or 'transversal'}"
                        for item in offers
                    ) or "O registo não anuncia atualizações novas para o canal stable."
                    Clock.schedule_once(lambda _dt: self._remote_done(message), 0)
                except Exception as exc:
                    Clock.schedule_once(
                        lambda _dt, error=str(exc): self._remote_done(f"Consulta falhou sem alterar conteúdo: {error}"), 0
                    )
            threading.Thread(target=worker, daemon=True).start()

        def _save_update_policy(self, *_args):
            registry = self.registry_url.text.strip()
            if self.weekly_enabled.active and not registry:
                self.status.text = "Indica um registo HTTPS antes de ativar a verificação semanal."
                return
            controller.save_preference("updates.registry_url", registry)
            controller.save_preference(
                "updates.weekly_enabled", "1" if self.weekly_enabled.active else "0"
            )
            controller.save_preference(
                "updates.wifi_only", "1" if self.wifi_only.active else "0"
            )
            controller.save_preference(
                "updates.power_only", "1" if self.power_only.active else "0"
            )
            self.status.text = (
                "Verificação semanal opt-in guardada; os packs nunca são instalados automaticamente."
                if self.weekly_enabled.active else "Verificação semanal desativada."
            )

        def _remote_done(self, message):
            self.remote_list.text = message
            self.status.text = "Consulta terminada. Nada foi instalado automaticamente."

        def _install_remote(self):
            registry, identity = self.registry_url.text.strip(), self.remote_identity.text.strip()
            if not registry or not identity:
                self.status.text = "Indica o registo e a seleção pack-id@versão."
                return
            self._background(lambda: controller.install_remote_content_pack(identity, registry))

        def refresh_packs(self):
            rows = controller.installed_content_packs()
            self.pack_list.text = "\n".join(
                f"{row['pack_id']} · ativo {row['active'] or 'nenhum'} · versões {', '.join(row['versions'])}"
                for row in rows
            ) or "Nenhum pack adicional instalado."

    class Games(Screen):
        """Quiet, resumable break area with no animation, network or rewards."""

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
            extras = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
            extras.add_widget(action("Retomar", self.resume_game))
            extras.add_widget(action("Desafio diário", self.daily_game))
            self.pause_minutes = Spinner(text="10 min", values=("5 min", "10 min", "15 min"))
            extras.add_widget(self.pause_minutes)
            extras.add_widget(action("Estatísticas", self.show_statistics))
            root.add_widget(extras)
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
            Clock.schedule_interval(self._tick, 1)

        def _kind_key(self):
            return "sudoku" if self.kind.text == "Sudoku" else "minesweeper"

        def new_game(self, *_args):
            self.selected_cell = None
            self.session = controller.new_game(self._kind_key(), self.difficulty.text)
            self.game = self.session.game
            self._last_tick = time.monotonic()
            self.keypad.opacity = 1 if self.kind.text == "Sudoku" else 0
            self.keypad.disabled = self.kind.text != "Sudoku"
            self.mode_button.disabled = self.kind.text == "Sudoku"
            self.status.text = f"{self.kind.text} · {self.difficulty.text} · sem animações"
            self.draw()

        def daily_game(self, *_args):
            self.session = controller.new_game(self._kind_key(), self.difficulty.text, daily=True)
            self.game = self.session.game; self.selected_cell = None; self._last_tick = time.monotonic()
            self.status.text = "Desafio diário local · sem recompensa pedagógica"
            self.draw()

        def resume_game(self, *_args):
            session = controller.resume_game(self._kind_key(), self.difficulty.text)
            if session is None:
                self.status.text = "Não existe jogo guardado nesta dificuldade."; return
            self.session, self.game = session, session.game
            self._last_tick = time.monotonic(); self.status.text = "Jogo retomado no estado guardado."
            self.draw()

        def _tick(self, _dt):
            if not hasattr(self, "session"): return True
            now = time.monotonic(); delta = max(0, int(now - self._last_tick))
            if delta:
                self.session.elapsed_seconds += delta; self._last_tick = now
            goal = int(self.pause_minutes.text.split()[0]) * 60
            if self.session.elapsed_seconds == goal:
                self.status.text = "Intervalo concluído; quando quiseres, regressa ao teu plano."
            return True

        def show_statistics(self, *_args):
            rows = controller.game_statistics()
            message = "\n".join(
                f"{row['game']} · {row['difficulty']}: {row['wins']}/{row['plays']} · "
                f"melhor {row['best_seconds'] if row['best_seconds'] is not None else '—'} s"
                for row in rows
            ) or "Ainda não existem jogos terminados."
            Popup(title="Estatísticas de pausa", content=text(message), size_hint=(.75, .55)).open()

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
                controller.save_game(self.session)
                if self.game.won: controller.finish_game(self.session)

        def play_mine(self, row, col):
            self.game.toggle_flag(row, col) if self.flag_mode else self.game.reveal(row, col)
            if self.game.lost: self.status.text = "Encontraste uma mina. Podes iniciar um novo tabuleiro."
            elif self.game.won: self.status.text = "Minesweeper concluído. Bom intervalo!"
            self.draw()
            controller.save_game(self.session)
            if self.game.lost or self.game.won: controller.finish_game(self.session)

        def toggle_mode(self, *_args):
            self.flag_mode = not self.flag_mode
            self.mode_button.text = "Modo: marcar" if self.flag_mode else "Modo: revelar"

        def on_leave(self, *_args):
            if hasattr(self, "session") and not (self.game.won or getattr(self.game, "lost", False)):
                controller.save_game(self.session)

    class LazyScreenManager(ScreenManager):
        """Create feature screens on first navigation instead of at startup."""

        def __init__(self, factories, **kwargs):
            self._factories = dict(factories)
            super().__init__(**kwargs)

        def ensure(self, name):
            if not self.has_screen(name):
                factory = self._factories.get(name)
                if factory is None:
                    raise KeyError(f"Ecrã desconhecido: {name}")
                self.add_widget(factory(name=name))
            return super().get_screen(name)

        def get_screen(self, name):
            return self.ensure(name)

        def on_current(self, _instance, value):
            if value and not self.has_screen(value):
                self.ensure(value)
            return super().on_current(_instance, value)

    class AprendixApp(App):
        def on_start(self):
            if os.name == "nt":
                from aprendix.presentation.startup_splash import close_startup_splash

                close_startup_splash()
            if controller.load_preference("updates.weekly_enabled", "0") == "1":
                registry = controller.load_preference("updates.registry_url", "").strip()
                if registry:
                    threading.Thread(
                        target=self._weekly_update_check,
                        args=(registry,), daemon=True,
                    ).start()

        def _weekly_update_check(self, registry):
            try:
                result = controller.check_content_updates(
                    registry, force=False,
                    wifi_only=controller.load_preference("updates.wifi_only", "0") == "1",
                    external_power_only=controller.load_preference("updates.power_only", "0") == "1",
                )
                offers = len(result.get("offers", ()))
                message = (
                    "Local · atualização semanal adiada"
                    if result.get("status") == "deferred" else
                    f"Local · {offers} novidade(s) de conteúdo"
                    if offers else "Local · conteúdo atualizado"
                )
            except Exception:
                message = "Local · offline · atualização adiada"
            Clock.schedule_once(
                lambda _dt: setattr(self.local_status, "text", message), 0,
            )

        def build(self):
            self.title = "Aprendix"
            self.palette_index = CommandPalette()
            stored_route = controller.load_preference(
                "last_screen", Route.DASHBOARD.value
            )
            try:
                initial_route = Route(stored_route)
                if initial_route is Route.READER:
                    initial_route = Route.DASHBOARD
            except ValueError:
                initial_route = Route.DASHBOARD
            self.history = NavigationHistory(initial_route)
            self._history_navigation = False
            self._nav_buttons = []
            self._route_titles = {
                Route.DASHBOARD: "Painel",
                Route.CURRICULUM: "Curso",
                Route.IDE: "IDE",
                Route.SEARCH: "Pesquisa",
                Route.CARDS: "Cards",
                Route.DICTIONARY: "Dicionário",
                Route.TUTOR: "Tutor",
                Route.PROJECTS: "Projetos",
                Route.ANALYZER: "Analisar trecho",
                Route.GAMES: "Games",
                Route.READER: "Leitor",
                Route.DATA: "Dados",
            }
            root = BoxLayout(orientation="horizontal")
            self.root_layout = root
            with root.canvas.before:
                root.theme_color = Color(*colors["bg"])
                root.background = RoundedRectangle(pos=root.pos, size=root.size)
            root.bind(pos=lambda *_: setattr(root.background, "pos", root.pos), size=lambda *_: setattr(root.background, "size", root.size))
            self.sidebar = BoxLayout(
                orientation="vertical", size_hint_x=None, width=dp(196),
                padding=dp(8), spacing=dp(7),
            )
            with self.sidebar.canvas.before:
                self.sidebar_color = Color(*colors["card"])
                self.sidebar_shape = RoundedRectangle(
                    pos=self.sidebar.pos, size=self.sidebar.size
                )
            self.sidebar.bind(
                pos=lambda *_: setattr(self.sidebar_shape, "pos", self.sidebar.pos),
                size=lambda *_: setattr(self.sidebar_shape, "size", self.sidebar.size),
            )
            self.collapse_button = Button(
                text="Menu  ·  Recolher", size_hint_y=None, height=dp(48),
                background_normal="", background_color=colors["card_alt"],
                color=colors["text"],
            )
            self.collapse_button.theme_role = "navigation"
            self.collapse_button.bind(
                on_release=lambda *_: self.set_sidebar_collapsed(
                    not self.sidebar_collapsed
                )
            )
            self.sidebar.add_widget(self.collapse_button)
            self.navigation_scroll = ScrollView(
                do_scroll_x=False, do_scroll_y=True,
                scroll_type=["bars", "content"], bar_width=dp(9),
                bar_color=colors["accent"],
                bar_inactive_color=(*colors["muted"][:3], .4),
            )
            self.navigation_column = BoxLayout(
                orientation="vertical", size_hint_y=None, spacing=dp(7),
            )
            self.navigation_column.bind(
                minimum_height=self.navigation_column.setter("height")
            )
            navigation = (
                (Route.DASHBOARD, "Painel", "P"),
                (Route.CURRICULUM, "Curso", "C"),
                (Route.IDE, "IDE", "IDE"),
                (Route.SEARCH, "Pesquisa", "?"),
                (Route.CARDS, "Cards", "Card"),
                (Route.DICTIONARY, "Dicionário", "Aa"),
                (Route.TUTOR, "Tutor", "T"),
                (Route.PROJECTS, "Projetos", "Pj"),
                (Route.ANALYZER, "Analisar", "<>"),
                (Route.GAMES, "Games", "G"),
                (Route.DATA, "Dados", "D"),
            )
            for route, title, icon in navigation:
                button = Button(
                    text=title, size_hint_y=None, height=dp(50),
                    background_normal="", background_color=colors["card_alt"],
                    color=colors["text"],
                )
                button.theme_role = "navigation"
                button.full_title = title
                button.compact_title = icon
                button.route = route
                button.bind(
                    on_release=lambda _button, target=route: self.go(target)
                )
                self._nav_buttons.append(button)
                self.navigation_column.add_widget(button)
            self.navigation_scroll.add_widget(self.navigation_column)
            self.sidebar.add_widget(self.navigation_scroll)
            self.local_status = Label(
                text="Local · offline", color=colors["success"],
                size_hint_y=None, height=dp(28), font_size=dp(12),
            )
            self.sidebar.add_widget(self.local_status)
            font_row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(4))
            smaller = Button(text="A−")
            smaller.bind(on_release=lambda *_: self.change_font(-0.1))
            larger = Button(text="A+")
            larger.bind(on_release=lambda *_: self.change_font(0.1))
            font_row.add_widget(smaller)
            font_row.add_widget(larger)
            self.sidebar.add_widget(font_row)
            self.theme_button = Button(
                text={
                    "dark": "Tema: escuro", "light": "Tema: claro",
                    "contrast": "Alto contraste",
                }[theme_name],
                size_hint_y=None, height=dp(44), background_normal="",
                background_color=colors["accent"], color=colors["accent_text"],
            )
            self.theme_button.theme_role = "accent"
            self.theme_button.bind(
                on_release=lambda button: self.toggle_theme(root, button)
            )
            self.sidebar.add_widget(self.theme_button)

            content = BoxLayout(orientation="vertical")
            topbar = BoxLayout(
                size_hint_y=None, height=dp(52),
                padding=(dp(8), dp(5)), spacing=dp(6),
            )
            back = Button(text="‹", size_hint_x=None, width=dp(48))
            back.bind(on_release=lambda *_: self.go_back())
            forward = Button(text="›", size_hint_x=None, width=dp(48))
            forward.bind(on_release=lambda *_: self.go_forward())
            self.page_title = Label(
                text=self._route_titles[initial_route], color=colors["text"],
                bold=True, halign="left",
            )
            self.page_title.bind(
                size=lambda item, _value: setattr(item, "text_size", item.size)
            )
            commands = Button(
                text="Ctrl+K  Comandos", size_hint_x=None, width=dp(170)
            )
            commands.bind(on_release=lambda *_: self.open_palette())
            topbar.add_widget(back)
            topbar.add_widget(forward)
            topbar.add_widget(self.page_title)
            topbar.add_widget(commands)
            factories = {
                Route.DASHBOARD.value: Dashboard,
                Route.CURRICULUM.value: Curriculum,
                Route.IDE.value: Learning,
                Route.SEARCH.value: Search,
                Route.CARDS.value: FactCards,
                Route.DICTIONARY.value: Reference,
                Route.TUTOR.value: Tutor,
                Route.PROJECTS.value: Projects,
                Route.ANALYZER.value: SnippetAssistant,
                Route.GAMES.value: Games,
                Route.READER.value: AssistedReader,
                Route.DATA.value: DataAndUpdates,
            }
            self.manager = LazyScreenManager(
                factories, transition=NoTransition()
            )
            self.manager.ensure(initial_route.value)
            self.manager.current = initial_route.value
            self.manager.bind(current=self._screen_changed)
            content.add_widget(topbar)
            content.add_widget(self.manager)
            root.add_widget(self.sidebar)
            root.add_widget(content)
            self.sidebar_collapsed = controller.load_preference(
                "sidebar_collapsed", "0"
            ) == "1"
            self.set_sidebar_collapsed(self.sidebar_collapsed, persist=False)
            Window.bind(
                on_key_down=self._key_down, width=self._responsive_sidebar
            )
            return root

        def _set_current(self, route):
            route = Route(route)
            self._history_navigation = True
            self.manager.current = route.value
            self._history_navigation = False
            self.page_title.text = self._route_titles[route]
            controller.save_preference("last_screen", route.value)

        def go(self, route):
            self._set_current(self.history.navigate(route))

        def go_back(self):
            self._set_current(self.history.back())

        def go_forward(self):
            self._set_current(self.history.forward())

        def _screen_changed(self, _manager, value):
            try:
                route = Route(value)
            except ValueError:
                return
            if not self._history_navigation:
                self.history.navigate(route)
            self.page_title.text = self._route_titles[route]
            controller.save_preference("last_screen", route.value)

        def set_sidebar_collapsed(self, collapsed, *, persist=True):
            self.sidebar_collapsed = bool(collapsed)
            self.sidebar.width = dp(72 if self.sidebar_collapsed else 196)
            self.collapse_button.text = (
                "Menu" if self.sidebar_collapsed else "Menu  ·  Recolher"
            )
            for button in self._nav_buttons:
                button.text = (
                    button.compact_title
                    if self.sidebar_collapsed else button.full_title
                )
            if persist:
                controller.save_preference(
                    "sidebar_collapsed", "1" if self.sidebar_collapsed else "0"
                )

        def _responsive_sidebar(self, _window, width):
            if width < dp(920) and not self.sidebar_collapsed:
                self.set_sidebar_collapsed(True)

        def _key_down(self, _window, key, _scancode, _codepoint, modifiers):
            if "ctrl" in modifiers and key in (75, 107):
                self.open_palette()
                return True
            if "alt" in modifiers and key == 276:
                self.go_back()
                return True
            if "alt" in modifiers and key == 275:
                self.go_forward()
                return True
            return False

        def open_palette(self):
            body = BoxLayout(
                orientation="vertical", padding=dp(12), spacing=dp(8)
            )
            query = TextInput(
                hint_text="Escreve uma ação, ecrã ou conceito…",
                multiline=False, size_hint_y=None, height=dp(46),
            )
            results = BoxLayout(orientation="vertical", spacing=dp(5))
            body.add_widget(query)
            body.add_widget(results)
            popup = Popup(
                title="Comandos Aprendix", content=body, size_hint=(.72, .72)
            )

            def select(route):
                popup.dismiss()
                self.go(route)

            def refresh(_widget=None, value=""):
                results.clear_widgets()
                for command in self.palette_index.search(value, limit=7):
                    button = Button(
                        text=command.title, size_hint_y=None, height=dp(46),
                        background_normal="",
                        background_color=colors["card_alt"], color=colors["text"],
                    )
                    button.bind(
                        on_release=lambda _button, route=command.route: select(route)
                    )
                    results.add_widget(button)

            query.bind(text=refresh)
            refresh(value="")
            popup.open()
            Clock.schedule_once(lambda *_: setattr(query, "focus", True), .05)

        def change_font(self, delta):
            nonlocal font_scale
            font_scale = min(1.5, max(0.85, round(font_scale + delta, 2)))
            controller.save_preference("font_scale", str(font_scale))
            for widget in self.root_layout.walk():
                base = getattr(widget, "aprendix_base_font_size", None)
                if base is not None:
                    widget.font_size = dp(base * font_scale)

        def toggle_theme(self, root, button):
            nonlocal theme_name
            order = ("dark", "light", "contrast")
            theme_name = order[(order.index(theme_name) + 1) % len(order)]
            colors.update(palettes[theme_name])
            controller.save_preference("theme", theme_name)
            Window.clearcolor = colors["bg"]
            root.theme_color.rgba = colors["bg"]
            self.sidebar_color.rgba = colors["card"]
            self.local_status.color = colors["success"]
            button.text = {
                "dark": "Tema: escuro", "light": "Tema: claro",
                "contrast": "Alto contraste",
            }[theme_name]
            for widget in root.walk():
                if isinstance(widget, Card):
                    widget.refresh_theme()
                role = getattr(widget, "theme_role", None)
                if isinstance(widget, Label) and role in {"text", "muted"}:
                    widget.color = colors[role]
                elif isinstance(widget, Button):
                    widget.color = colors["accent_text" if role == "accent" else "text"]
                    widget.background_color = colors[
                        "accent" if role == "accent" else
                        "card_alt" if role == "navigation" else "card"
                    ]
                elif isinstance(widget, TextInput):
                    widget.background_color = colors["card"]
                    widget.foreground_color = colors["text"]

        def on_stop(self):
            Window.unbind(
                on_key_down=self._key_down, width=self._responsive_sidebar
            )

    AprendixApp().run()
    return 0
