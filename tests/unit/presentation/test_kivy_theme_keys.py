from pathlib import Path

from aprendix.presentation.design_system import palette
from aprendix.presentation.kivy_advanced import _walk_theme_widgets


def test_advanced_ui_only_indexes_declared_palette_keys() -> None:
    source = (
        Path(__file__).parents[3] / "src" / "aprendix" / "presentation" / "kivy_advanced.py"
    ).read_text(encoding="utf-8")
    for unsupported in ('colors["surface"]', 'colors["surface_alt"]'):
        assert unsupported not in source
    assert {"bg", "card", "card_alt", "accent", "text", "muted"} <= set(palette("dark"))
    assert "branches = (root, *self.manager.screens)" in source
    assert "_walk_theme_widgets(branches)" in source
    assert 'widget.bar_color = colors["accent"]' in source


def test_theme_walk_includes_inactive_screens_without_duplicates() -> None:
    class Widget:
        def __init__(self, name, *children):
            self.name = name
            self.children = children

        def walk(self):
            yield self
            for child in self.children:
                yield from child.walk()

    active = Widget("active")
    root = Widget("root", active)
    cached_ide = Widget("cached-ide", Widget("editor"))

    names = [item.name for item in _walk_theme_widgets((root, active, cached_ide))]

    assert names == ["root", "active", "cached-ide", "editor"]


def test_ide_uses_course_journey_and_starts_with_blank_source() -> None:
    source = (
        Path(__file__).parents[3] / "src" / "aprendix" / "presentation" / "kivy_advanced.py"
    ).read_text(encoding="utf-8")

    assert "controller.course_practice" in source
    assert 'text="", hint_text="Escreve a tua solução aqui…"' in source
    assert "Aprovado e creditado · regista uma reflexão ou seleciona Seguinte." in source
    assert "build_exercise_brief(self.selected).render()" in source
    assert 'for panel_name in ("Output", "Problemas", "Tutor", "Testes")' in source
    assert 'self.terminal_shell = BoxLayout(' in source
    assert 'orientation="horizontal"' in source
    assert '"find": lambda: self._open_find(False)' in source
    assert '"replace": lambda: self._open_find(True)' in source
    assert "self._open_dictionary_peek(term)" in source
    assert 'self.workspace_mode = "project"' in source
    assert "search_ide_commands" in source
    assert 'evaluation_locked=True' in source
    assert 'command_id = "correct" if shift else "run"' in source
    assert 'tool_action("", "Corrigir", self.evaluate' in source
    assert 'tool_action("", "Testar", self.evaluate' not in source
    assert 'values=("Simples", "Guiado", "Técnico")' in source
    assert 'self.theory_button = tool_action("", "Teoria"' in source
    assert 'self.practice_button = tool_action("", "Prática"' in source
    assert "controller.learning_session(self.selected.id)" in source
    assert 'phase="microtheory", theory_viewed=True' in source
    assert "hint_count=self.hints_used" in source
    assert 'self.assessment_button = tool_action("", "Teste"' in source
    assert 'values=("Treino", "Avaliação")' in source
    assert 'self.brief_view == "assessment"' in source
    assert "Tutor bloqueado durante a avaliação." in source
    assert 'self.theme_button.compact_title = "Tema"' in source
    assert "button.text = button.compact_title if self.sidebar_collapsed else theme_title" in source
    assert "Prática ativa · resolve de raiz e executa quando estiveres pronto." in source


def test_dashboard_tabs_scroll_instead_of_compressing_their_labels() -> None:
    source = (
        Path(__file__).parents[3] / "src" / "aprendix" / "presentation" / "kivy_advanced.py"
    ).read_text(encoding="utf-8")

    assert "self.dashboard_tabs_scroll = ScrollView(" in source
    assert "do_scroll_x=True, do_scroll_y=False" in source
    assert 'minimum_width=self.dashboard_tabs.setter("width")' in source
    assert "dashboard_tab_width(section, font_scale=font_scale)" in source
    assert "self.dashboard_period_group = BoxLayout(" in source
    assert 'shorten_from="right", max_lines=1' in source


def test_ide_header_and_lesson_toggle_preserve_context_at_compact_widths() -> None:
    source = (
        Path(__file__).parents[3] / "src" / "aprendix" / "presentation" / "kivy_advanced.py"
    ).read_text(encoding="utf-8")

    assert "profile = self._apply_journey_header(width)" in source
    assert "self.exercise_title.size_hint_x = None" in source
    assert "self.exercise_title.width = dp(profile.title_width_dp)" in source
    assert 'return "Aula" if self.brief_view == "theory" else "Enunciado"' in source
    assert 'state = "[-]" if self.brief_expanded else "[+]"' in source
    assert "self._set_journey_title(self.selected.title)" in source
    assert "self._responsive_sidebar(Window, Window.width)" in source
