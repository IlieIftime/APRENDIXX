"""Card-based Kivy shell with dashboard, learning, search, and rich theory."""

from __future__ import annotations

import threading
import time
import re
import webbrowser
import ast
import ctypes
import os
import math
from datetime import UTC, date, datetime, timedelta
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
from aprendix.application.exercise_presentation import build_exercise_brief
from aprendix.application.games import DIFFICULTIES, MinesweeperGame, SudokuGame
from aprendix.application.ide_commands import search_ide_commands
from aprendix.application.knowledge import SearchCancellationToken
from aprendix.application.math_rendering import FormulaRenderRequest
from aprendix.application.navigation import CommandPalette, NavigationHistory, Route
from aprendix.application.pedagogy_tools import profile_execution, visualize_structures
from aprendix.presentation.design_system import THEMES, palette
from aprendix.presentation.fonts import register_kivy_fonts
from aprendix.presentation.math_renderer import (
    OfflineMathRenderer,
    extract_latex_expressions,
    strip_latex_markup,
)
from aprendix.presentation.responsive import (
    book_workspace_profile,
    dashboard_tab_width,
    ide_journey_header_profile,
)
from aprendix.presentation.text_safety import normalize_ui_text


def _walk_theme_widgets(branches):
    """Yield every active or cached screen widget exactly once."""

    visited = set()
    for branch in branches:
        for widget in branch.walk():
            identity = id(widget)
            if identity not in visited:
                visited.add(identity)
                yield widget


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
    from kivy.core.text import LabelBase
    from kivy.graphics import (
        Color, Line, PopMatrix, PushMatrix, Rectangle, RoundedRectangle, Scale,
        Translate,
    )
    from kivy.graphics.svg import Svg
    from kivy.metrics import dp
    from kivy.resources import resource_find
    from kivy.uix.image import AsyncImage
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.behaviors import FocusBehavior
    from kivy.uix.checkbox import CheckBox
    from kivy.uix.codeinput import CodeInput
    from kivy.uix.floatlayout import FloatLayout
    from kivy.uix.label import Label
    from kivy.uix.gridlayout import GridLayout
    from kivy.uix.progressbar import ProgressBar
    from kivy.uix.popup import Popup
    from kivy.uix.screenmanager import NoTransition, Screen, ScreenManager
    from kivy.uix.scrollview import ScrollView
    from kivy.uix.scatter import Scatter
    from kivy.uix.spinner import Spinner
    from kivy.uix.textinput import TextInput
    from kivy.uix.togglebutton import ToggleButton
    from kivy.uix.widget import Widget

    palettes = {name: palette(name) for name in THEMES}
    register_kivy_fonts(LabelBase, resource_find)
    theme_name = controller.load_preference("theme", "dark")
    if theme_name not in palettes:
        theme_name = "dark"
    colors = dict(palettes[theme_name])
    math_renderer = OfflineMathRenderer()
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

    class PaneDivider(Widget):
        """Keyboard-neutral drag handle for the adjustable IDE brief pane."""

        def __init__(self, target=None, **kwargs):
            kwargs.setdefault("size_hint_x", None)
            kwargs.setdefault("width", dp(9))
            super().__init__(**kwargs)
            self.target = target
            self._drag_origin = None
            self._target_origin = None
            with self.canvas:
                self.divider_color = Color(*colors["accent"])
                self.divider_line = Rectangle(pos=self.pos, size=self.size)
            self.bind(pos=self._sync, size=self._sync)

        def _sync(self, *_args):
            self.divider_line.pos = (self.center_x - dp(1), self.y)
            self.divider_line.size = (dp(2), self.height)

        def on_touch_down(self, touch):
            if self.collide_point(*touch.pos) and self.target is not None:
                touch.grab(self)
                self._drag_origin = touch.x
                self._target_origin = self.target.width
                return True
            return super().on_touch_down(touch)

        def on_touch_move(self, touch):
            if touch.grab_current is self and self.target is not None:
                available = max(dp(689), self.parent.width if self.parent else Window.width)
                self.target.width = min(
                    available - dp(369),
                    max(dp(320), self._target_origin - (touch.x - self._drag_origin)),
                )
                return True
            return super().on_touch_move(touch)

        def on_touch_up(self, touch):
            if touch.grab_current is self:
                touch.ungrab(self)
                if self.target is not None:
                    controller.save_preference(
                        "ide.brief_width_dp",
                        f"{self.target.width / max(dp(1), .001):.2f}",
                    )
                return True
            return super().on_touch_up(touch)


    class TerminalDivider(Widget):
        """Horizontal drag handle that preserves the book while resizing output."""

        def __init__(self, target=None, on_commit=None, **kwargs):
            kwargs.setdefault("size_hint_y", None)
            kwargs.setdefault("height", 0)
            super().__init__(**kwargs)
            self.target = target
            self.on_commit = on_commit
            self._drag_origin = None
            self._target_origin = None
            with self.canvas:
                self.divider_color = Color(*colors["accent"])
                self.divider_line = Rectangle(pos=self.pos, size=self.size)
            self.bind(pos=self._sync, size=self._sync)

        def _sync(self, *_args):
            self.divider_line.pos = (self.x, self.center_y - dp(1))
            self.divider_line.size = (self.width, dp(2) if self.height else 0)

        def on_touch_down(self, touch):
            if self.height and self.collide_point(*touch.pos) and self.target is not None:
                touch.grab(self)
                self._drag_origin = touch.y
                self._target_origin = self.target.height
                return True
            return super().on_touch_down(touch)

        def on_touch_move(self, touch):
            if touch.grab_current is self and self.target is not None:
                useful = max(dp(400), self.parent.height if self.parent else Window.height)
                self.target.height = min(
                    useful * .35,
                    max(useful * .20, self._target_origin + touch.y - self._drag_origin),
                )
                return True
            return super().on_touch_move(touch)

        def on_touch_up(self, touch):
            if touch.grab_current is self:
                touch.ungrab(self)
                if self.on_commit is not None:
                    self.on_commit(self.target.height)
                return True
            return super().on_touch_up(touch)

    class TrendChart(FloatLayout):
        """Small local canvas chart; no browser process and no network dependency."""

        def __init__(self, **kwargs):
            kwargs.setdefault("size_hint_y", None)
            kwargs.setdefault("height", dp(230))
            super().__init__(**kwargs)
            self._series = ()
            self.bind(pos=self._draw, size=self._draw)

        def set_series(self, series):
            self._series = tuple(
                (str(name), tuple(float(value or 0) for value in values))
                for name, values in series if values
            )
            self._draw()

        def refresh_theme(self):
            self._draw()

        def _draw(self, *_args):
            self.canvas.clear()
            self.clear_widgets()
            with self.canvas:
                Color(*colors["card_alt"])
                Rectangle(pos=self.pos, size=self.size)
                left, bottom = self.x + dp(42), self.y + dp(30)
                width, height = max(dp(40), self.width - dp(62)), max(dp(30), self.height - dp(70))
                Color(*(*colors["muted"][:3], .22))
                for step in range(5):
                    y = bottom + height * step / 4
                    Line(points=(left, y, left + width, y), width=1)
                palette_values = (
                    colors["accent"], colors["success"], colors["warning"], colors["muted"],
                )
                all_values = [value for _name, values in self._series for value in values]
                maximum = max(all_values, default=1.0) or 1.0
                for series_index, (_name, values) in enumerate(self._series):
                    if not values:
                        continue
                    points = []
                    for index, value in enumerate(values):
                        x = left + width * index / max(1, len(values) - 1)
                        y = bottom + height * max(0.0, value) / maximum
                        points.extend((x, y))
                    Color(*palette_values[series_index % len(palette_values)])
                    Line(points=points, width=dp(1.7))
            for index, (name, _values) in enumerate(self._series[:4]):
                legend = Label(
                    text=name, color=(
                        colors["accent"], colors["success"], colors["warning"], colors["muted"]
                    )[index % 4],
                    size_hint=(None, None), size=(dp(150), dp(26)),
                    pos=(self.x + dp(15) + index * dp(155), self.top - dp(32)),
                    halign="left",
                )
                self.add_widget(legend)

    class SvgAssetWidget(Widget):
        """Render verified local SVG assets through Kivy's native vector path."""

        def __init__(self, source, **kwargs):
            super().__init__(**kwargs)
            with self.canvas:
                PushMatrix()
                self._translate = Translate()
                self._scale = Scale(1, 1, 1)
                self._svg = Svg(source=str(source))
                PopMatrix()
            self.bind(pos=self._sync_svg, size=self._sync_svg)
            self._sync_svg()

        def _sync_svg(self, *_args):
            intrinsic_width = max(1, self._svg.width)
            intrinsic_height = max(1, self._svg.height)
            factor = min(self.width / intrinsic_width, self.height / intrinsic_height)
            rendered_width = intrinsic_width * factor
            rendered_height = intrinsic_height * factor
            self._scale.xyz = (factor, factor, 1)
            self._translate.xy = (
                self.x + (self.width - rendered_width) / 2,
                self.y + (self.height - rendered_height) / 2,
            )


    class TooltipBubble(Label):
        """Small visual tooltip that never replaces accessible metadata."""

        def __init__(self, **kwargs):
            kwargs.setdefault("size_hint", (None, None))
            kwargs.setdefault("padding", (dp(10), dp(6)))
            kwargs.setdefault("font_size", dp(13))
            kwargs.setdefault("color", colors["text"])
            kwargs.setdefault("font_name", "AprendixSans")
            super().__init__(**kwargs)
            with self.canvas.before:
                self.tooltip_color = Color(*colors["card_alt"])
                self.tooltip_shape = RoundedRectangle(
                    pos=self.pos, size=self.size, radius=[dp(7)],
                )
            self.bind(pos=self._sync, size=self._sync, texture_size=self._fit)

        def _fit(self, _widget, value):
            self.size = (min(dp(360), value[0] + dp(20)), value[1] + dp(12))

        def _sync(self, *_args):
            self.tooltip_shape.pos, self.tooltip_shape.size = self.pos, self.size


    class _IconMixin:
        """Shared SVG, tooltip and focus behaviour for compact actions."""

        icon_name = "more"
        command_title = "Ação"
        shortcut = ""

        def _init_icon(self, *, icon_name, title, shortcut="", show_label=False):
            self.icon_name = icon_name or "more"
            self.command_title = normalize_ui_text(title)
            self.full_title = self.command_title
            self.shortcut = shortcut
            self.accessible_name = self.command_title
            self.tooltip_text = self.command_title + (f" · {shortcut}" if shortcut else "")
            self._show_label = bool(show_label)
            self.text = self.command_title if self._show_label else ""
            self.padding = (dp(36), 0) if self._show_label else (0, 0)
            self.halign = "left" if self._show_label else "center"
            self.valign = "middle"
            asset = Path(__file__).resolve().parent / "assets" / f"icon-{self.icon_name}.svg"
            if not asset.is_file():
                asset = Path(__file__).resolve().parent / "assets" / "icon-more.svg"
            with self.canvas.after:
                self._icon_badge_color = Color(
                    .035, .055, .09,
                    .9 if theme_name == "light" and self.theme_role != "accent" else 0,
                )
                self._icon_badge = RoundedRectangle(radius=[dp(6)])
                Color(1, 1, 1, 1)
                PushMatrix()
                self._icon_translate = Translate()
                self._icon_scale = Scale(1, 1, 1)
                try:
                    self._icon_svg = Svg(source=str(asset))
                except Exception:
                    fallback_asset = Path(__file__).resolve().parent / "assets" / "icon-more.svg"
                    self._icon_svg = Svg(source=str(fallback_asset))
                PopMatrix()
                self._focus_color = Color(*(*colors["focus"][:3], 0))
                self._focus_line = Line(
                    rounded_rectangle=(self.x + dp(2), self.y + dp(2),
                                       max(0, self.width - dp(4)), max(0, self.height - dp(4)), dp(5)),
                    width=dp(1.4),
                )
            self.bind(pos=self._sync_icon, size=self._sync_icon, focus=self._focus_changed)
            self._tooltip_bound = False
            self._tooltip_event = None
            self._tooltip_widget = None
            self._sync_icon()

        def on_parent(self, _widget, parent):
            """Bind hover tracking only while the action belongs to a widget tree.

            Screens such as Cards and Search are rebuilt frequently.  A permanent
            Window binding would otherwise retain every discarded button and make
            tooltips progressively slower during long study sessions.
            """

            if parent is not None and not self._tooltip_bound:
                Window.bind(mouse_pos=self._tooltip_mouse)
                self._tooltip_bound = True
            elif parent is None and self._tooltip_bound:
                Window.unbind(mouse_pos=self._tooltip_mouse)
                self._tooltip_bound = False
                self._hide_tooltip()

        def set_label_visible(self, visible):
            self._show_label = bool(visible)
            self.text = self.command_title if self._show_label else ""
            self.padding = (dp(36), 0) if self._show_label else (0, 0)
            self.halign = "left" if self._show_label else "center"
            self._sync_icon()

        def _sync_icon(self, *_args):
            intrinsic_width = max(1, self._icon_svg.width)
            intrinsic_height = max(1, self._icon_svg.height)
            icon_size = min(dp(22), max(dp(14), self.height - dp(16)))
            factor = min(icon_size / intrinsic_width, icon_size / intrinsic_height)
            rendered_width = intrinsic_width * factor
            rendered_height = intrinsic_height * factor
            self._icon_scale.xyz = (factor, factor, 1)
            icon_x = self.x + dp(10) if self._show_label else self.center_x - rendered_width / 2
            self._icon_translate.xy = (icon_x, self.center_y - rendered_height / 2)
            badge_size = dp(30)
            badge_x = self.x + dp(6) if self._show_label else self.center_x - badge_size / 2
            self._icon_badge.pos = (badge_x, self.center_y - badge_size / 2)
            self._icon_badge.size = (badge_size, badge_size)
            self.text_size = (
                max(0, self.width - (dp(42) if self._show_label else 0)), self.height,
            )
            self._focus_line.rounded_rectangle = (
                self.x + dp(2), self.y + dp(2), max(0, self.width - dp(4)),
                max(0, self.height - dp(4)), dp(5),
            )

        def _focus_changed(self, _widget, focused):
            self._focus_color.rgba = (*colors["focus"][:3], 1 if focused else 0)

        def _tooltip_mouse(self, _window, position):
            inside = self.get_root_window() is not None and self.collide_point(
                *self.to_widget(*position)
            )
            if inside and not self.disabled:
                if self._tooltip_widget is None and self._tooltip_event is None:
                    self._tooltip_event = Clock.schedule_once(self._show_tooltip, .45)
            else:
                self._hide_tooltip()

        def _show_tooltip(self, *_args):
            self._tooltip_event = None
            if self.get_root_window() is None:
                return
            bubble = TooltipBubble(text=self.tooltip_text)
            bubble.texture_update()
            bubble._fit(bubble, bubble.texture_size)
            window_position = self.to_window(self.center_x, self.y)
            bubble.x = min(Window.width - bubble.width - dp(8), max(dp(8), window_position[0] - bubble.width / 2))
            bubble.y = min(Window.height - bubble.height - dp(8), window_position[1] + self.height + dp(5))
            Window.add_widget(bubble)
            self._tooltip_widget = bubble

        def _hide_tooltip(self):
            if self._tooltip_event is not None:
                self._tooltip_event.cancel()
                self._tooltip_event = None
            if self._tooltip_widget is not None:
                try:
                    Window.remove_widget(self._tooltip_widget)
                except (AttributeError, ValueError):
                    pass
                self._tooltip_widget = None

        def refresh_theme(self):
            self._focus_color.rgba = (*colors["focus"][:3], 1 if self.focus else 0)
            self._icon_badge_color.rgba = (
                .035, .055, .09,
                .9 if theme_name == "light" and self.theme_role != "accent" else 0,
            )
            if self._tooltip_widget is not None:
                self._tooltip_widget.color = colors["text"]
                self._tooltip_widget.tooltip_color.rgba = colors["card_alt"]


    class IconAction(_IconMixin, FocusBehavior, Button):
        def __init__(
            self, icon_name, title, callback, *, primary=False, width=None,
            show_label=False, shortcut="", **kwargs,
        ):
            if width is not None:
                kwargs.setdefault("size_hint_x", None)
                kwargs.setdefault("width", dp(width))
            kwargs.setdefault("size_hint_y", None)
            kwargs.setdefault("height", dp(42))
            kwargs.setdefault("background_normal", "")
            kwargs.setdefault("background_color", colors["accent" if primary else "card_alt"])
            kwargs.setdefault("color", colors["accent_text" if primary else "text"])
            kwargs.setdefault("bold", True)
            kwargs.setdefault("font_name", "AprendixSans")
            super().__init__(**kwargs)
            self.theme_role = "accent" if primary else "navigation"
            self.aprendix_base_font_size = 13
            self._init_icon(
                icon_name=icon_name, title=title, shortcut=shortcut,
                show_label=show_label,
            )
            self.bind(on_release=callback)


    class IconToggleAction(_IconMixin, FocusBehavior, ToggleButton):
        def __init__(self, icon_name, title, callback, *, group, state="normal", **kwargs):
            kwargs.setdefault("size_hint_y", None)
            kwargs.setdefault("height", dp(38))
            kwargs.setdefault("background_normal", "")
            kwargs.setdefault("background_color", colors["card_alt"])
            kwargs.setdefault("color", colors["text"])
            kwargs.setdefault("font_name", "AprendixSans")
            super().__init__(group=group, state=state, **kwargs)
            self.theme_role = "navigation"
            self.aprendix_base_font_size = 12
            self._init_icon(icon_name=icon_name, title=title)
            self.bind(on_release=callback)


    class FormulaView(Card):
        """One accessible mathematical view shared by every rich document."""

        def __init__(self, *, latex, spoken, variables=None, compact=False, **kwargs):
            self.latex = normalize_ui_text(latex)
            self.spoken = normalize_ui_text(spoken) or "Expressão matemática"
            self.variables = dict(variables or {})
            self.compact = compact
            super().__init__(**kwargs)
            self.accessible_name = self.spoken
            self.tooltip_text = "Fórmula matemática local. " + self.spoken
            self._render_formula()

        def _render_formula(self):
            self.clear_widgets()
            result = math_renderer.render(FormulaRenderRequest(
                latex=self.latex, spoken=self.spoken, variables=self.variables,
                theme=theme_name, dpi=max(96, round(96 * dp(1))), scale=font_scale,
            ))
            self.add_widget(text(result.spoken, size=14 if self.compact else 16, bold=True))
            if result.path is not None and result.path.is_file():
                image = AsyncImage(
                    source=str(result.path), size_hint_y=None,
                    height=dp(82 if self.compact else 112),
                    allow_stretch=True, keep_ratio=True,
                )
                image.accessible_name = result.spoken
                self.add_widget(image)
            else:
                self.add_widget(text(
                    result.error or "Fórmula disponível em descrição textual.",
                    muted=True,
                ))
            if result.variables:
                self.add_widget(text(
                    " · ".join(f"{name}: {meaning}" for name, meaning in result.variables),
                    muted=True,
                ))
            copy_button = IconAction(
                "copy", "Copiar expressão", lambda *_: Clipboard.copy(result.latex),
                width=52, shortcut="Ctrl+C",
            )
            copy_button.accessible_name = "Copiar fórmula em LaTeX"
            self.add_widget(copy_button)

        def refresh_theme(self):
            super().refresh_theme()
            self._render_formula()

    def local_visual(source, *, height):
        path = Path(source)
        if path.suffix.casefold() == ".svg":
            return SvgAssetWidget(source=path, size_hint_y=None, height=height)
        return AsyncImage(source=str(path), size_hint_y=None, height=height)

    class SkillGraphCanvas(FloatLayout):
        """Pan/zoom curriculum graph with typed visual relationships."""

        def __init__(self, on_node=None, on_edge=None, **kwargs):
            super().__init__(**kwargs)
            self._on_node = on_node
            self._on_edge = on_edge
            self.snapshot = None
            self.node_buttons = {}
            self.scatter = Scatter(
                do_rotation=False, scale_min=.45, scale_max=2.6,
                size_hint=(None, None), size=(dp(1500), dp(850)),
            )
            self.layer = Widget(size=self.scatter.size, size_hint=(None, None))
            self.scatter.add_widget(self.layer)
            self.add_widget(self.scatter)
            self.bind(size=self._fit_scatter, pos=self._fit_scatter)

        def _fit_scatter(self, *_args):
            if self.scatter.parent is self:
                self.scatter.pos = self.pos

        def refresh_theme(self):
            if self.snapshot is not None:
                self.set_snapshot(self.snapshot)

        def set_snapshot(self, snapshot):
            self.snapshot = snapshot
            nodes = tuple(getattr(snapshot, "nodes", ()) or ())
            edges = tuple(getattr(snapshot, "edges", ()) or ())
            self.layer.clear_widgets()
            self.layer.canvas.before.clear()
            self.node_buttons = {}
            if not nodes:
                return
            node_ids = {str(node.id) for node in nodes}
            prerequisite_edges = tuple(
                edge for edge in edges
                if str(edge.source_node_id) in node_ids and str(edge.target_node_id) in node_ids
                and str(getattr(edge.relation_type, "value", edge.relation_type))
                in {"prerequisite", "progression"}
            )
            levels = {str(node.id): 0 for node in nodes}
            for _pass in range(len(nodes)):
                changed = False
                for edge in prerequisite_edges:
                    source, target = str(edge.source_node_id), str(edge.target_node_id)
                    proposed = min(8, levels[source] + 1)
                    if proposed > levels[target]:
                        levels[target], changed = proposed, True
                if not changed:
                    break
            grouped = {}
            for node in nodes:
                grouped.setdefault(levels[str(node.id)], []).append(node)
            positions = {}
            for level, group in grouped.items():
                for index, node in enumerate(sorted(group, key=lambda item: item.title)):
                    positions[str(node.id)] = (
                        dp(80 + level * 185), dp(70 + index * 88),
                    )
            max_x = max(position[0] for position in positions.values()) + dp(210)
            max_y = max(position[1] for position in positions.values()) + dp(110)
            self.layer.size = (max(dp(900), max_x), max(dp(620), max_y))
            self.scatter.size = self.layer.size
            with self.layer.canvas.before:
                for edge in edges:
                    source = positions.get(str(edge.source_node_id))
                    target = positions.get(str(edge.target_node_id))
                    if source is None or target is None:
                        continue
                    relation = str(getattr(edge.relation_type, "value", edge.relation_type))
                    if relation == "prerequisite":
                        edge_color, width, dash = colors["accent"], dp(1.7), 0
                    elif relation == "progression":
                        edge_color, width, dash = colors["success"], dp(1.5), 0
                    elif relation == "related":
                        edge_color, width, dash = colors["warning"], dp(1.1), dp(7)
                    else:
                        edge_color, width, dash = (*colors["muted"][:3], .32), dp(.8), dp(4)
                    Color(*edge_color)
                    sx, sy = source; tx, ty = target
                    kwargs = {"points": (sx + dp(74), sy + dp(29), tx + dp(74), ty + dp(29)), "width": width}
                    if dash:
                        kwargs.update(dash_length=dash, dash_offset=dp(4))
                    Line(**kwargs)
                    if getattr(edge, "directed", False):
                        start_x, start_y = sx + dp(74), sy + dp(29)
                        end_x, end_y = tx + dp(74), ty + dp(29)
                        angle = math.atan2(end_y - start_y, end_x - start_x)
                        length = dp(11)
                        wing = .58
                        Line(points=(
                            end_x, end_y,
                            end_x - length * math.cos(angle - wing),
                            end_y - length * math.sin(angle - wing),
                        ), width=width)
                        Line(points=(
                            end_x, end_y,
                            end_x - length * math.cos(angle + wing),
                            end_y - length * math.sin(angle + wing),
                        ), width=width)
            recommended = {
                str(item.node_id) for item in getattr(snapshot, "recommendations", ()) or ()
            }
            for node in nodes:
                mastery = float(getattr(
                    getattr(node, "analytics", None), "mastery",
                    getattr(node.statistics, "mastery", 0.0),
                ))
                base = colors["card_alt"]
                success = colors["success"]
                mix = min(.8, max(0.0, mastery))
                color = tuple(base[i] * (1 - mix) + success[i] * mix for i in range(3)) + (1,)
                title = node.title if len(node.title) <= 22 else node.title[:20] + "…"
                if str(node.id) in recommended:
                    title = "> " + title
                button = Button(
                    text=f"{title}\n{mastery:.0%}", size_hint=(None, None),
                    size=(dp(148), dp(58)), pos=positions[str(node.id)],
                    background_normal="", background_color=color, color=colors["text"],
                    font_size=dp(12), halign="center",
                )
                button.node_id = node.id
                button.base_color = color
                button.bind(on_release=lambda item, identity=node.id: self._select_node(identity))
                self.layer.add_widget(button)
                self.node_buttons[str(node.id)] = button
            for edge in edges:
                source = positions.get(str(edge.source_node_id))
                target = positions.get(str(edge.target_node_id))
                if source is None or target is None:
                    continue
                midpoint = (
                    (source[0] + target[0]) / 2 + dp(64),
                    (source[1] + target[1]) / 2 + dp(19),
                )
                edge_button = Button(
                    text="i", size_hint=(None, None), size=(dp(22), dp(22)),
                    pos=midpoint, background_normal="",
                    background_color=(*colors["card"][:3], .72),
                    color=colors["muted"], font_size=dp(10),
                )
                edge_button.bind(
                    on_release=lambda _item, relation=edge: self._select_edge(relation)
                )
                self.layer.add_widget(edge_button)

        def _select_node(self, node_id):
            if self._on_node is not None:
                self._on_node(node_id)

        def _select_edge(self, edge):
            if self._on_edge is not None:
                self._on_edge(edge)

        def focus(self, query):
            term = (query or "").strip().casefold()
            found = None
            for button in self.node_buttons.values():
                button.background_color = button.base_color
                label = button.text.replace("> ", "").splitlines()[0].rstrip("…").casefold()
                if term and found is None and term in label:
                    found = button
            if found is None:
                return False
            found.background_color = colors["warning"]
            self.scatter.scale = max(.8, self.scatter.scale)
            self.scatter.pos = (
                self.center_x - found.center_x * self.scatter.scale,
                self.center_y - found.center_y * self.scatter.scale,
            )
            return True

        def reset_view(self):
            self.scatter.scale = 1
            self.scatter.pos = self.pos
            for button in self.node_buttons.values():
                button.background_color = button.base_color

        def keyboard_move(self, dx=0, dy=0, zoom=0):
            if zoom:
                self.scatter.scale = min(
                    self.scatter.scale_max,
                    max(self.scatter.scale_min, self.scatter.scale + zoom),
                )
            if dx or dy:
                self.scatter.pos = (
                    self.scatter.x + dp(dx), self.scatter.y + dp(dy),
                )

    def text(value="", *, size=16, muted=False, bold=False, fixed=None):
        widget = Label(
            text=normalize_ui_text(value), bold=bold, markup=False,
            font_name="AprendixSans",
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

    def action(title, callback, *, primary=True):
        button = Button(
            text=normalize_ui_text(title), bold=True, size_hint_y=None, height=dp(46),
            background_normal="",
            background_color=colors["accent" if primary else "card_alt"],
            color=colors["accent_text" if primary else "text"],
            font_name="AprendixSans",
        )
        button.theme_role = "accent" if primary else "navigation"
        button.aprendix_base_font_size = 14
        button.bind(on_release=callback)
        return button

    def tool_action(symbol, title, callback, *, primary=False, width=92):
        """Return an original local SVG action with tooltip and accessible name."""

        normalized = normalize_ui_text(title)
        icon_name = {
            "Run": "run", "Executar": "run", "Corrigir": "correct",
            "Debug": "debug", "Formatar": "format", "Procurar": "search",
            "Guardar": "save", "Tutor": "tutor", "Pista": "hints",
            "Erro": "problems", "CopyKate": "copykate", "Mais": "more",
            "Anterior": "previous", "Seguinte": "next", "Substituir": "replace",
            "Tudo": "replace", "Fechar": "close", "X": "close",
            "Copiar": "copy", "Teoria": "lesson", "Prática": "ide",
            "Teste": "tests", "A-": "previous", "A+": "next",
        }.get(normalized, "book" if "Enunciado" in normalized or "Aula" in normalized else "more")
        shortcut = {
            "Run": "F5", "Corrigir": "Ctrl+Shift+Enter", "Debug": "F6",
            "Formatar": "Shift+Alt+F", "Procurar": "Ctrl+F", "Guardar": "Ctrl+S",
            "Tutor": "Ctrl+I", "Fechar": "Esc",
        }.get(normalized, "")
        show_label = normalized in {
            "Corrigir", "Teoria", "Prática", "Teste",
        } or normalized.startswith(("Enunciado", "Aula"))
        return IconAction(
            icon_name, normalized, callback, primary=primary, width=width,
            show_label=show_label, shortcut=shortcut,
        )

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

    def render_pedagogical_blocks(column, blocks, *, compact=False):
        """Render typed pedagogical blocks without flattening code or formulae."""

        column.clear_widgets()
        source_catalog = None

        def source_for(source_id):
            nonlocal source_catalog
            if source_catalog is None:
                try:
                    source_catalog = {
                        item.id: item for item in controller.curated_sources(limit=5_000)
                    }
                except Exception:
                    source_catalog = {}
            return source_catalog.get(source_id)

        def open_source(target):
            if not target:
                return
            if target.startswith("https://"):
                webbrowser.open(target)
            elif target.startswith("aprendix-library://"):
                from aprendix.application.local_library import resolve_library_uri

                path = resolve_library_uri(target)
                if path is not None:
                    webbrowser.open(path.as_uri())

        for block in sorted(tuple(blocks or ()), key=lambda item: item.ordinal):
            kind = str(getattr(block.kind, "value", block.kind))
            if kind == "title":
                level = max(1, min(6, int(getattr(block, "level", 2))))
                column.add_widget(text(
                    block.text, size=max(17, 27 - level * 2), bold=True,
                    fixed=36 if compact else None,
                ))
            elif kind == "paragraph":
                column.add_widget(text(block.text, size=14 if compact else 16))
            elif kind == "list":
                body = "\n".join(
                    f"{index}. {item}" if block.ordered else f"• {item}"
                    for index, item in enumerate(block.items, 1)
                )
                column.add_widget(text(body, size=14 if compact else 16))
            elif kind in {"code", "signature"}:
                source = block.code if kind == "code" else block.signature
                caption = getattr(block, "caption", "") or getattr(block, "description", "")
                if caption:
                    column.add_widget(text(caption, muted=True, fixed=28))
                rows = min(14, max(2, source.count("\n") + 1))
                column.add_widget(CodeInput(
                    text=source, readonly=True, size_hint_y=None,
                    height=dp(20 + rows * 22), font_size=dp(14),
                    background_color=colors["card_alt"], foreground_color=colors["text"],
                ))
            elif kind == "formula":
                column.add_widget(FormulaView(
                    latex=block.latex, spoken=block.spoken,
                    variables=block.variables, compact=compact,
                ))
            elif kind == "table":
                rows = (tuple(block.headers), *tuple(block.rows))
                rendered = "\n".join("  |  ".join(row) for row in rows)
                table_card = Card()
                if block.caption:
                    table_card.add_widget(text(block.caption, bold=True, fixed=30))
                table_card.add_widget(TextInput(
                    text=rendered, readonly=True, size_hint_y=None,
                    height=dp(min(340, 38 + len(rows) * 28)),
                    background_color=colors["card_alt"], foreground_color=colors["text"],
                ))
                column.add_widget(table_card)
            elif kind in {"image", "diagram"}:
                asset_path = None
                try:
                    asset_path = controller.pedagogical_asset_path(block.asset_id)
                except Exception:
                    asset_path = None
                visual = Card()
                visual.add_widget(text(
                    getattr(block, "caption", "") or "Visual Aprendix original",
                    bold=True, fixed=30,
                ))
                if asset_path and Path(asset_path).is_file():
                    visual.add_widget(local_visual(
                        asset_path, height=dp(220 if compact else 340),
                    ))
                visual.add_widget(text(block.alt_text, muted=True))
                column.add_widget(visual)
            elif kind == "callout":
                callout = Card()
                callout.add_widget(text(block.title, bold=True, fixed=30))
                callout.add_widget(text(block.body, size=14 if compact else 16))
                column.add_widget(callout)
            elif kind == "references":
                reference_card = Card()
                reference_card.add_widget(text("Referências", size=18, bold=True, fixed=32))
                for reference in block.references:
                    source = source_for(reference.source_id)
                    label = source.title if source is not None else reference.source_id
                    target = source.canonical_url if source is not None else ""
                    reference_card.add_widget(text(
                        f"{label}" + (f" · {reference.locator}" if reference.locator else "")
                        + f"\n{reference.rationale}",
                        muted=True,
                    ))
                    if target:
                        link = action(
                            "Abrir fonte",
                            lambda _button, url=target: open_source(url),
                        )
                        link.height = dp(36)
                        reference_card.add_widget(link)
                column.add_widget(reference_card)

    def render_legacy_document(column, body, *, compact=False):
        """Readable deterministic fallback for legacy material awaiting migration."""

        column.clear_widgets()
        formulae = extract_latex_expressions(body or "")
        body = strip_latex_markup(body or "") if formulae else normalize_ui_text(body or "")
        headings = {
            "contextualização", "objetivo", "especificação técnica", "contrato",
            "entradas e parâmetros", "exemplo de comportamento", "exemplos",
            "requisitos e casos-limite", "critérios de avaliação", "pré-requisitos",
            "explicação", "verificação curta", "referências", "etapas sugeridas",
        }
        paragraphs = [item.strip() for item in re.split(r"\n\s*\n", body or "") if item.strip()]
        for paragraph in paragraphs:
            lines = paragraph.splitlines()
            first = lines[0].strip().strip("#*: ")
            if first.casefold() in headings:
                column.add_widget(text(first, size=18, bold=True, fixed=34))
                if len(lines) > 1:
                    column.add_widget(text("\n".join(lines[1:]), size=14 if compact else 16))
                continue
            if all(
                line.lstrip().startswith(("def ", "class ", "@", ">>>", "import ", "from "))
                or not line.strip() for line in lines
            ):
                column.add_widget(CodeInput(
                    text=paragraph, readonly=True, size_hint_y=None,
                    height=dp(min(300, 28 + len(lines) * 22)),
                    background_color=colors["card_alt"], foreground_color=colors["text"],
                ))
            else:
                column.add_widget(text(paragraph, size=14 if compact else 16))
        for latex in formulae:
            column.add_widget(FormulaView(
                latex=latex, spoken="Expressão matemática do conteúdo",
                compact=compact,
            ))

    class Dashboard(Screen):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.section = "Resumo"
            self.period_days = 30
            self.period_start = None
            self.period_end = None
            self.track_slug = None
            self.include_eligible = False
            self._analytics = None
            self._graph_snapshot = None

        def on_pre_enter(self, *_args):
            self.render()

        def on_enter(self, *_args):
            Window.bind(on_key_down=self._dashboard_key_down)

        def on_leave(self, *_args):
            Window.unbind(on_key_down=self._dashboard_key_down)

        def render(self, *_args):
            self.clear_widgets()
            root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(7))
            top = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(8))
            self.dashboard_tabs_scroll = ScrollView(
                do_scroll_x=True, do_scroll_y=False,
                scroll_type=["bars", "content"], bar_width=dp(4),
                bar_margin=dp(2), bar_color=colors["accent"],
                bar_inactive_color=(*colors["muted"][:3], .45),
            )
            self.dashboard_tabs = BoxLayout(
                size_hint=(None, None), height=dp(46), spacing=dp(5),
            )
            self.dashboard_tabs.bind(
                minimum_width=self.dashboard_tabs.setter("width")
            )
            for section in ("Resumo", "Atividade", "Competências", "Percursos", "Plano", "Grafo"):
                tab_width = dashboard_tab_width(section, font_scale=font_scale)
                button = ToggleButton(
                    text=section, group="dashboard-section",
                    state="down" if section == self.section else "normal",
                    size_hint_x=None, width=dp(tab_width),
                    font_size=dp(14 * font_scale),
                    text_size=(dp(tab_width - 18), dp(42)),
                    halign="center", valign="middle", shorten=True,
                    shorten_from="right", max_lines=1,
                    background_normal="", background_color=(
                        colors["accent"] if section == self.section else colors["card_alt"]
                    ), color=colors[
                        "accent_text" if section == self.section else "text"
                    ],
                )
                button.aprendix_base_font_size = 14
                button.accessible_name = section
                button.tooltip_text = section
                button.bind(on_release=lambda _button, name=section: self._select_section(name))
                self.dashboard_tabs.add_widget(button)
            self.dashboard_tabs_scroll.add_widget(self.dashboard_tabs)
            top.add_widget(self.dashboard_tabs_scroll)
            self.dashboard_period_group = BoxLayout(
                size_hint_x=None, width=dp(206), spacing=dp(6),
            )
            period_label = Label(
                text="Período", size_hint_x=None, width=dp(58),
                color=colors["muted"], halign="right", valign="middle",
                font_size=dp(13 * font_scale), text_size=(dp(58), dp(46)),
            )
            period_label.theme_role = "muted"
            period_label.aprendix_base_font_size = 13
            self.dashboard_period_group.add_widget(period_label)
            self.period_selector = Spinner(
                text=("Personalizado" if self.period_start is not None else
                      {7: "7 dias", 30: "30 dias", 90: "90 dias"}.get(
                          self.period_days, "30 dias"
                      )),
                values=("7 dias", "30 dias", "90 dias", "Personalizado"),
                size_hint_x=None, width=dp(142),
            )
            self.period_selector.bind(text=self._period_selected)
            self.dashboard_period_group.add_widget(self.period_selector)
            top.add_widget(self.dashboard_period_group)
            root.add_widget(top)
            self.dashboard_status = text(
                "Perfil local anónimo · métricas calculadas no dispositivo",
                muted=True, fixed=28,
            )
            root.add_widget(self.dashboard_status)
            scroll, column = scroll_column(f"dashboard:{self.section.casefold()}")
            self.dashboard_column = column
            root.add_widget(scroll)
            self.add_widget(root)
            try:
                self._analytics = (
                    controller.dashboard_analytics(
                        period_days=self.period_days, start=self.period_start,
                        end=self.period_end, track_slug=self.track_slug,
                    ) if hasattr(controller, "dashboard_analytics") else None
                )
                {
                    "Resumo": self._render_summary,
                    "Atividade": self._render_activity,
                    "Competências": self._render_skills,
                    "Percursos": self._render_courses,
                    "Plano": self._render_plan,
                    "Grafo": self._render_graph,
                }[self.section](column)
            except Exception as exc:
                column.add_widget(text(f"Dashboard indisponível: {exc}", muted=True))

        def _select_section(self, section):
            self.section = section
            self.render()

        def _period_selected(self, _spinner, value):
            if value == "Personalizado":
                self._open_custom_period()
                return
            self.period_days = {"7 dias": 7, "30 dias": 30, "90 dias": 90}[value]
            self.period_start = None
            self.period_end = None
            self.render()

        def _open_custom_period(self):
            content = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
            content.add_widget(text(
                "Escolhe um intervalo até 730 dias. As datas são inclusivas.",
                muted=True, fixed=36,
            ))
            fields = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
            today = date.today()
            current_start = (
                self.period_start.date() if self.period_start else today - timedelta(days=29)
            )
            current_end = (
                (self.period_end - timedelta(microseconds=1)).date()
                if self.period_end else today
            )
            start_input = TextInput(
                text=current_start.isoformat(), hint_text="Início AAAA-MM-DD",
                multiline=False,
            )
            end_input = TextInput(
                text=current_end.isoformat(), hint_text="Fim AAAA-MM-DD",
                multiline=False,
            )
            fields.add_widget(start_input)
            fields.add_widget(end_input)
            content.add_widget(fields)
            message = text("", muted=True, fixed=34)
            content.add_widget(message)
            buttons = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
            popup = Popup(
                title="Período personalizado", content=content,
                size_hint=(None, None), width=dp(min(520, Window.width * .72)),
                height=dp(250), auto_dismiss=False,
            )

            def apply_period(*_args):
                try:
                    first = date.fromisoformat(start_input.text.strip())
                    last = date.fromisoformat(end_input.text.strip())
                    if last < first:
                        raise ValueError("a data final antecede a data inicial")
                    start = datetime.combine(first, datetime.min.time(), tzinfo=UTC)
                    end = datetime.combine(last + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
                    if end - start > timedelta(days=730):
                        raise ValueError("o intervalo excede 730 dias")
                except ValueError as exc:
                    message.text = f"Intervalo inválido: {exc}"
                    return
                self.period_start, self.period_end = start, end
                popup.dismiss()
                self.render()

            buttons.add_widget(action("Cancelar", lambda *_: popup.dismiss()))
            buttons.add_widget(action("Aplicar", apply_period, primary=True))
            content.add_widget(buttons)
            popup.open()

        def _indicator_grid(self, column, analytics):
            indicators = tuple(getattr(analytics, "indicators", ()) or ())
            grid = GridLayout(
                cols=3 if Window.width >= dp(1050) else 2,
                spacing=dp(9), size_hint_y=None,
            )
            grid.bind(minimum_height=grid.setter("height"))
            for indicator in indicators:
                card = Card()
                value = indicator.value
                if indicator.unit == "%":
                    rendered = f"{value:.0f}%"
                elif indicator.unit in {"minutes", "min"}:
                    rendered = f"{value:.0f} min"
                else:
                    rendered = f"{value:g}"
                card.add_widget(text(rendered, size=27, bold=True, fixed=42))
                card.add_widget(text(indicator.label, size=15, bold=True, fixed=28))
                direction = {
                    "improving": "a melhorar", "slowing": "a abrandar",
                    "stable": "estável", "starting": "a iniciar",
                }.get(str(indicator.trend), str(indicator.trend))
                card.add_widget(text(
                    f"{direction} · {indicator.detail}", muted=True, fixed=44,
                ))
                definition = tool_action(
                    "i", "Definição",
                    lambda _button, item=indicator: self._show_metric_definition(item),
                    width=112,
                )
                card.add_widget(definition)
                grid.add_widget(card)
            column.add_widget(grid)

        def _show_metric_definition(self, indicator):
            content = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
            content.add_widget(text(indicator.label, size=22, bold=True, fixed=40))
            content.add_widget(text(indicator.definition, size=16))
            content.add_widget(text(
                "Denominador · " + indicator.denominator, muted=True,
            ))
            content.add_widget(text(
                f"Período · {self._analytics.period.label}", muted=True, fixed=30,
            ))
            popup = Popup(
                title="Como esta métrica é calculada", content=content,
                size_hint=(None, None), width=dp(min(560, Window.width * .5)),
                height=dp(min(420, Window.height * .5)),
            )
            popup.open()

        def _render_summary(self, column):
            column.add_widget(text("Resumo global", size=27, bold=True, fixed=48))
            if self._analytics is not None:
                self._indicator_grid(column, self._analytics)
                chart = TrendChart()
                chart.set_series((
                    ("Domínio", [point.mastery * 100 for point in self._analytics.series]),
                    ("Retenção", [point.retention * 100 for point in self._analytics.series]),
                    ("Autonomia", [point.autonomy * 100 for point in self._analytics.series]),
                    ("Consistência", [point.consistency * 100 for point in self._analytics.series]),
                ))
                column.add_widget(chart)
            else:
                model = controller.dashboard()
                hero = Card()
                hero.add_widget(text(f"{model.overall_mastery:.0%}", size=38, bold=True))
                hero.add_widget(text("Domínio curricular global", muted=True, fixed=30))
                hero.add_widget(ProgressBar(
                    max=1, value=model.overall_mastery, size_hint_y=None, height=dp(16),
                ))
                column.add_widget(hero)
            personal = controller.personal_progress()
            if personal.next_action:
                action_card = Card()
                action_card.add_widget(text("Fazer agora", size=18, bold=True, fixed=32))
                action_card.add_widget(text(personal.next_action.title, size=20, bold=True))
                action_card.add_widget(text(personal.next_action.explanation, muted=True))
                row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(5))
                for minutes in (10, 25, 50, 90):
                    row.add_widget(action(
                        f"{minutes} min", lambda _button, value=minutes: self._time_action(value),
                    ))
                action_card.add_widget(row)
                self.time_action_status = text("", muted=True, fixed=32)
                action_card.add_widget(self.time_action_status)
                column.add_widget(action_card)

        def _render_activity(self, column):
            column.add_widget(text("Atividade e esforço", size=27, bold=True, fixed=48))
            analytics = self._analytics
            if analytics is None:
                column.add_widget(text("Ainda não existem séries temporais locais.", muted=True))
                return
            chart = TrendChart(height=dp(270))
            chart.set_series((
                ("Minutos ativos", [point.active_minutes for point in analytics.series]),
                ("Minutos planeados", [point.planned_minutes for point in analytics.series]),
                ("Tentativas", [point.attempts for point in analytics.series]),
                ("Sucessos", [point.successes for point in analytics.series]),
            ))
            column.add_widget(chart)
            totals = Card()
            totals.add_widget(text(
                f"{sum(point.active_minutes for point in analytics.series):.0f} min ativos · "
                f"{sum(point.attempts for point in analytics.series)} tentativas · "
                f"{sum(point.evidence_count for point in analytics.series)} evidências",
                size=18, bold=True,
            ))
            column.add_widget(totals)

        def _render_skills(self, column):
            column.add_widget(text("Competências curriculares", size=27, bold=True, fixed=48))
            if self._analytics is not None:
                distribution = self._analytics.mastery_distribution
                distribution_card = Card()
                distribution_card.add_widget(text(
                    f"Dominadas {distribution.mastered} · Consolidação {distribution.consolidating} · "
                    f"Novas {distribution.new} · Em risco {distribution.at_risk} · "
                    f"Intocadas {distribution.untouched}",
                    size=17, bold=True,
                ))
                column.add_widget(distribution_card)
            model = controller.dashboard()
            visible_nodes = sorted(
                model.nodes,
                key=lambda node: (not node.recommended, -node.attempts, -node.mastery, node.title),
            )[:30]
            for node in visible_nodes:
                card = Card()
                card.add_widget(text(
                    node.title + (" · recomendado" if node.recommended else ""),
                    bold=True, fixed=34,
                ))
                card.add_widget(ProgressBar(
                    max=1, value=node.mastery, size_hint_y=None, height=dp(12),
                ))
                card.add_widget(text(
                    f"{node.mastery:.0%} · {node.attempts} tentativas",
                    muted=True, fixed=28,
                ))
                column.add_widget(card)

        def _render_courses(self, column):
            column.add_widget(text("Percursos e cobertura", size=27, bold=True, fixed=48))
            tracks = tuple(getattr(self._analytics, "tracks", ()) or ())
            if not tracks:
                column.add_widget(text("Sem métricas de percurso neste período.", muted=True))
                return
            for track in tracks:
                card = Card()
                card.add_widget(text(track.title, size=19, bold=True, fixed=34))
                card.add_widget(ProgressBar(
                    max=1, value=track.mastery, size_hint_y=None, height=dp(13),
                ))
                card.add_widget(text(
                    f"{track.mastered_nodes}/{track.curriculum_nodes} dominadas · "
                    f"{track.practiced_nodes} praticadas · domínio {track.mastery:.0%} · "
                    f"retenção {track.retention:.0%} · autonomia {track.autonomy:.0%}",
                    muted=True,
                ))
                column.add_widget(card)

        def _render_plan(self, column):
            column.add_widget(text("Plano e previsão", size=27, bold=True, fixed=48))
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
                personal = controller.personal_progress()
                forecast = controller.progress_forecast()
                weekly_report = controller.weekly_progress_report()
                if forecast and weekly_report:
                    outlook = Card()
                    outlook.add_widget(text("Previsão e relatório semanal", size=20, bold=True, fixed=36))
                    outlook.add_widget(text(
                        f"{forecast.mastered_nodes}/{forecast.total_nodes} conceitos dominados · "
                        f"capacidade estimada {forecast.weekly_capacity_nodes:.1f}/semana · "
                        f"conclusão {forecast.estimated_completion.isoformat() if forecast.estimated_completion else 'por estimar'}",
                        muted=True, fixed=34,
                    ))
                    outlook.add_widget(text(
                        f"Semana {weekly_report.week_start:%d/%m}–{weekly_report.week_end:%d/%m} · "
                        f"{weekly_report.active_minutes} min ativos · {weekly_report.evidence_count} evidências · "
                        f"tendência {weekly_report.trend}",
                        muted=True, fixed=32,
                    ))
                    outlook.add_widget(text(
                        "Próximo ajuste · " + weekly_report.recommendations[0],
                        fixed=42,
                    ))
                    quality = controller.pedagogical_quality()
                    if quality:
                        outlook.add_widget(text(
                            f"Qualidade pedagógica automática · {quality.accepted}/{quality.total} aceites · "
                            f"média {quality.average_score:.0%}",
                            muted=True, fixed=30,
                        ))
                    bibliography = controller.bibliography_coverage()
                    if bibliography:
                        outlook.add_widget(text(
                            f"Bibliografia · {bibliography.triple_sourced_objectives}/"
                            f"{bibliography.objective_count} objetivos com ≥3 fontes · "
                            f"{bibliography.distinct_sources} fontes distintas em uso",
                            muted=True, fixed=30,
                        ))
                    column.add_widget(outlook)
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

        def _render_graph(self, column):
            column.add_widget(text("Grafo curricular navegável", size=27, bold=True, fixed=48))
            column.add_widget(text(
                "Arrasta para navegar, usa a roda do rato para ampliar e clica num nó para "
                "abrir as suas métricas. Ligações sólidas são dependências; pontilhadas são relações.",
                muted=True, fixed=52,
            ))
            controls = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
            self.graph_query = TextInput(
                hint_text="Procurar competência", multiline=False,
            )
            self.graph_query.bind(on_text_validate=lambda *_: self._focus_graph_node())
            controls.add_widget(self.graph_query)
            controls.add_widget(action("Procurar", lambda *_: self._focus_graph_node()))
            controls.add_widget(action("Repor vista", lambda *_: self.graph_canvas.reset_view()))
            eligible = CheckBox(
                active=self.include_eligible, size_hint_x=None, width=dp(42),
            )
            eligible.bind(active=self._eligible_graph_changed)
            controls.add_widget(eligible)
            controls.add_widget(text("Próximos elegíveis", muted=True, fixed=40))
            column.add_widget(controls)
            snapshot = controller.visible_graph(
                period_days=self.period_days, start=self.period_start, end=self.period_end,
                include_eligible=self.include_eligible,
            )
            self._graph_snapshot = snapshot
            graph = SkillGraphCanvas(
                on_node=self._show_node_analytics, on_edge=self._show_edge_detail,
                size_hint_y=None, height=dp(610),
            )
            graph.set_snapshot(snapshot)
            self.graph_canvas = graph
            column.add_widget(graph)
            column.add_widget(text(
                "Legenda · violeta: pré-requisito dirigido · verde: progressão · "
                "âmbar pontilhado: relacionado · cinzento pontilhado: coocorrência",
                muted=True, fixed=30,
            ))
            visibility = getattr(snapshot, "visibility", None)
            if visibility:
                column.add_widget(text(
                    f"{len(snapshot.nodes)} nós visíveis · {len(snapshot.edges)} ligações · "
                    f"{visibility.omitted_nodes} nós omitidos pelo filtro · "
                    f"{visibility.frontier_nodes} na fronteira recomendada",
                    muted=True, fixed=30,
                ))
            self.node_detail = Card()
            self.node_detail.add_widget(text(
                "Seleciona um nó para ver tentativas, sucesso, tempo e retenção.", muted=True,
            ))
            column.add_widget(self.node_detail)

        def _show_node_analytics(self, node_id):
            try:
                item = controller.node_analytics(
                    node_id, period_days=self.period_days,
                    start=self.period_start, end=self.period_end,
                )
            except Exception as exc:
                self.dashboard_status.text = str(exc)
                return
            self.node_detail.clear_widgets()
            self.node_detail.add_widget(text(item.title, size=21, bold=True, fixed=38))
            self.node_detail.add_widget(text(
                f"{item.distinct_exercises} exercícios · {item.attempts} tentativas · "
                f"{item.successes} sucessos / {item.failures} falhas · "
                f"{item.active_seconds // 60} min ativos · {item.hint_count} pistas",
                size=16,
            ))
            self.node_detail.add_widget(text(
                f"Domínio {item.mastery:.0%} · retenção {item.retention:.0%} · "
                f"autonomia {item.autonomy:.0%} · sucesso {item.success_rate:.0%}",
                muted=True, fixed=32,
            ))
            if item.recommended_action:
                self.node_detail.add_widget(text(
                    "Próxima ação · " + item.recommended_action, bold=True,
                ))
            exercise = next(
                (candidate for candidate in controller.exercises()
                 if str(candidate.graph_node_id) == str(node_id)),
                None,
            )
            if exercise is not None:
                track_slug = next(
                    (path["track_slug"] for path in controller.learning_paths()
                     if any(str(journey["exercise"].id) == str(exercise.id)
                            for journey in controller.course_practice(path["track_slug"]))),
                    None,
                )
                actions = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
                actions.add_widget(action(
                    "Praticar no IDE",
                    lambda *_args, identity=exercise.id, slug=track_slug:
                    self._practice_graph_node(identity, slug),
                ))
                if track_slug:
                    actions.add_widget(action(
                        "Abrir curso",
                        lambda *_args, slug=track_slug: self._open_graph_course(slug),
                    ))
                self.node_detail.add_widget(actions)

        def _show_edge_detail(self, edge):
            relation = str(getattr(edge.relation_type, "value", edge.relation_type))
            self.node_detail.clear_widgets()
            self.node_detail.add_widget(text(
                f"Ligação · {relation.replace('_', ' ')}", size=20, bold=True, fixed=36,
            ))
            self.node_detail.add_widget(text(edge.reason, size=16))
            self.node_detail.add_widget(text(
                f"Origem: {edge.origin} · peso {edge.weight:.2f} · "
                + ("dirigida" if edge.directed else "não dirigida"),
                muted=True, fixed=30,
            ))

        def _practice_graph_node(self, exercise_id, track_slug):
            learning = self.manager.get_screen("learning")
            learning.load_exercise(exercise_id, track_slug)
            self.manager.current = "learning"

        def _open_graph_course(self, track_slug):
            curriculum = self.manager.get_screen("curriculum")
            title = next(
                (title for title, slug in curriculum._tracks.items() if slug == track_slug),
                None,
            )
            if title:
                curriculum.track.text = title
                curriculum.render()
            self.manager.current = "curriculum"

        def _eligible_graph_changed(self, _checkbox, active):
            active = bool(active)
            if active == self.include_eligible:
                return
            self.include_eligible = active
            self.render()

        def _focus_graph_node(self):
            if not getattr(self, "graph_canvas", None):
                return
            found = self.graph_canvas.focus(self.graph_query.text)
            self.dashboard_status.text = (
                "Competência destacada no grafo." if found else
                "Nenhuma competência visível coincide com a pesquisa."
            )

        def _dashboard_key_down(self, _window, key, _scancode, _codepoint, modifiers):
            if self.section != "Grafo" or not getattr(self, "graph_canvas", None):
                return False
            if key == 276:
                self.graph_canvas.keyboard_move(dx=45)
            elif key == 275:
                self.graph_canvas.keyboard_move(dx=-45)
            elif key == 273:
                self.graph_canvas.keyboard_move(dy=-45)
            elif key == 274:
                self.graph_canvas.keyboard_move(dy=45)
            elif key in (43, 61, 270):
                self.graph_canvas.keyboard_move(zoom=.15)
            elif key in (45, 269):
                self.graph_canvas.keyboard_move(zoom=-.15)
            elif key in (48, 96):
                self.graph_canvas.reset_view()
            else:
                return False
            return True

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
            paths = tuple(controller.learning_paths())
            self._course_titles = {
                item["course_title"]: item["track_slug"] for item in paths
            }
            self._course_names = {
                item["track_slug"]: item["course_title"] for item in paths
            }
            preferred_course = controller.load_preference("ide.course_slug", "")
            self.course_slug = (
                preferred_course if preferred_course in self._course_names
                else next(iter(self._course_names), "")
            )
            self.course_items = list(controller.course_practice(self.course_slug))
            first_pending = next(
                (item for item in self.course_items if not item["completed"]),
                self.course_items[0] if self.course_items else None,
            )
            self.selected = (
                first_pending["exercise"] if first_pending
                else self.catalogue[0] if self.catalogue else None
            )
            self.started = time.monotonic()
            self.previous_source = ""
            self.last_copykate_source = self.previous_source
            self.typed = self.pasted = self.deleted = 0
            self.active_seconds = 0.0
            self.hints_used = 0
            self.learning_session_state = None
            self.active_assessment = None
            self.assessment_started = 0.0
            self.transfer_context = False
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
            self._active_project_template_id = ""
            self.workspace_mode = "exercise"
            self.compact_workspace = False
            preferred_pane = controller.load_preference("ide.compact_pane", "editor")
            self.compact_pane = preferred_pane if preferred_pane in {"editor", "brief"} else "editor"
            initial_brief_expanded = controller.load_preference(
                "ide.brief_expanded", "1"
            ) != "0"
            self.brief_expanded = True
            # The terminal is a transversal drawer below both book pages.
            self.bottom_panel_expanded = controller.load_preference(
                "ide.bottom_panel_expanded", "0"
            ) == "1"
            try:
                self._terminal_ratio = min(.35, max(.20, float(
                    controller.load_preference("ide.terminal_ratio", ".28")
                )))
            except ValueError:
                self._terminal_ratio = .28
            self._active_panel = "Output"
            self._panel_buffers = {
                "Output": "Terminal local pronto.",
                "Problemas": "Sem problemas detetados.",
                "Tutor": "Escreve uma dúvida ou pede uma pista sem sair do IDE.",
                "Testes": "Os resultados da correção aparecem aqui.",
                "Debug": "Inicia o depurador para observar frames, valores e fluxo.",
            }
            self._last_evaluation_receipt = None
            root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(7))
            journey = Card()
            self.journey = journey
            self.journey_top = BoxLayout(
                size_hint_y=None, height=dp(40), spacing=dp(6),
            )
            journey_top = self.journey_top
            self.previous_exercise_button = tool_action(
                "<", "Anterior", self._previous_exercise, width=88,
            )
            self.next_exercise_button = tool_action(
                ">", "Seguinte", self._next_exercise, width=88,
            )
            journey_top.add_widget(self.previous_exercise_button)
            initial_title = self.selected.title if self.selected else "Sem exercícios"
            self.exercise_title = Label(
                text=initial_title, bold=True, markup=False,
                color=colors["text"], font_size=dp(19 * font_scale),
                size_hint=(None, 1), halign="left", valign="middle",
                shorten=True, shorten_from="right", max_lines=1,
            )
            self.exercise_title.theme_role = "text"
            self.exercise_title.aprendix_base_font_size = 19
            self.exercise_title.bind(
                size=lambda item, _value: setattr(
                    item, "text_size", (max(0, item.width - dp(8)), item.height)
                )
            )
            self._set_journey_title(initial_title)
            selected_course_title = self._course_names.get(
                self.course_slug, next(iter(self._course_titles), "Treino livre")
            )
            self.course_selector = Spinner(
                text=selected_course_title,
                values=tuple(self._course_titles) or ("Treino livre",),
                size_hint_x=None, width=dp(230), background_normal="",
                background_color=colors["card_alt"], color=colors["text"],
                halign="center", valign="middle", shorten=True,
                shorten_from="right", max_lines=1,
            )
            self.course_selector.bind(
                size=lambda item, _value: setattr(
                    item, "text_size", (max(0, item.width - dp(14)), item.height)
                )
            )
            journey_top.add_widget(self.exercise_title)
            self.workspace_pane_button = tool_action(
                "[]", "Enunciado", self._toggle_workspace_pane, width=112,
            )
            self.workspace_pane_button.width = 0
            self.workspace_pane_button.opacity = 0
            self.workspace_pane_button.disabled = True
            journey_top.add_widget(self.workspace_pane_button)
            journey_top.add_widget(self.course_selector)
            journey_top.add_widget(self.next_exercise_button)
            self.journey_meta = text("Percurso orientado no IDE", muted=True, fixed=24)
            self.journey_progress = ProgressBar(
                max=1, value=0, size_hint_y=None, height=dp(7),
            )
            journey.add_widget(journey_top)
            journey.add_widget(self.journey_meta)
            journey.add_widget(self.journey_progress)
            self.brief_cell = Card()
            brief_header_scroll = ScrollView(
                do_scroll_x=True, do_scroll_y=False, size_hint_y=None, height=dp(40),
                scroll_type=["bars", "content"], bar_width=dp(3),
            )
            brief_header = BoxLayout(
                size_hint=(None, None), height=dp(38), spacing=dp(4),
            )
            brief_header.bind(minimum_width=brief_header.setter("width"))
            self.brief_toggle = tool_action("", "Apoio [-]", self._toggle_brief, width=104)
            brief_header.add_widget(self.brief_toggle)
            self.theory_button = tool_action("", "Aula", self._show_theory, width=70)
            self.practice_button = tool_action("", "Enunciado", self._show_practice, width=108)
            self.assessment_button = tool_action("", "Teste", self._show_assessment, width=68)
            brief_header.add_widget(self.theory_button)
            brief_header.add_widget(self.practice_button)
            self.hints_button = IconAction(
                "hints", "Pistas", self._show_support_hints, width=50,
            )
            self.solution_button = IconAction(
                "solution", "Solução possível", self._show_support_solution, width=50,
            )
            self.execution_button = IconAction(
                "trace", "Execução esperada", self._show_support_execution, width=50,
            )
            self.solution_button.disabled = True
            self.execution_button.disabled = True
            brief_header.add_widget(self.hints_button)
            brief_header.add_widget(self.solution_button)
            brief_header.add_widget(self.execution_button)
            brief_header.add_widget(self.assessment_button)
            self.brief_mode = Spinner(
                text={"simple": "Simples", "guided": "Guiado", "technical": "Técnico"}.get(
                    controller.load_preference("ide.brief_mode", "guided"), "Guiado"
                ),
                values=("Simples", "Guiado", "Técnico"), size_hint_x=None,
                width=dp(104), background_normal="",
                background_color=colors["card_alt"], color=colors["text"],
            )
            brief_header.add_widget(self.brief_mode)
            brief_header.add_widget(tool_action("", "A-", lambda *_: self._resize_prompt(-dp(35)), width=48))
            brief_header.add_widget(tool_action("", "A+", lambda *_: self._resize_prompt(dp(35)), width=48))
            brief_header.add_widget(tool_action("", "Copiar", lambda *_: Clipboard.copy(self.prompt.text), width=76))
            brief_header_scroll.add_widget(brief_header)
            self.prompt = TextInput(
                text=build_exercise_brief(self.selected).render() if self.selected else "",
                readonly=True,
                background_color=colors["card"], foreground_color=colors["text"],
                size_hint_y=None, height=0, opacity=0, disabled=True,
                font_size=dp(15), padding=dp(14),
            )
            self.document_scroll = ScrollView(
                do_scroll_x=False, do_scroll_y=True, size_hint_y=1,
                scroll_type=["bars", "content"], bar_width=dp(10),
                bar_color=colors["accent"],
                bar_inactive_color=(*colors["muted"][:3], .45),
            )
            self.document_column = BoxLayout(
                orientation="vertical", size_hint_y=None, padding=dp(8), spacing=dp(8),
            )
            self.document_column.bind(minimum_height=self.document_column.setter("height"))
            self.document_scroll.add_widget(self.document_column)
            Clock.schedule_once(lambda _dt: self._reset_prompt_view(), 0)
            try:
                self.document_zoom = min(5, max(-3, int(
                    controller.load_preference("ide.document_zoom", "0")
                )))
            except ValueError:
                self.document_zoom = 0
            self.brief_view = "practice"
            self.brief_mode.bind(text=self._brief_mode_selected)
            self.learning_note = TextInput(
                hint_text="Antes de programar: como pensas transformar a entrada no resultado?",
                multiline=False, size_hint_y=None, height=dp(38),
                background_color=colors["card_alt"], foreground_color=colors["text"],
                padding=(dp(10), dp(8)),
            )
            self.assessment_controls = BoxLayout(
                size_hint_y=None, height=0, opacity=0, disabled=True, spacing=dp(5),
            )
            self.assessment_mode = Spinner(
                text="Treino", values=("Treino", "Avaliação"),
                size_hint_x=None, width=dp(120),
            )
            self.assessment_option = Spinner(
                text="Seleciona uma resposta", values=(),
            )
            self.assessment_submit = action("Validar resposta", self._submit_assessment)
            self.assessment_controls.add_widget(self.assessment_mode)
            self.assessment_controls.add_widget(self.assessment_option)
            self.assessment_controls.add_widget(self.assessment_submit)
            self.brief_cell.add_widget(brief_header_scroll)
            self.brief_cell.add_widget(self.document_scroll)
            self.brief_cell.add_widget(self.prompt)
            self.brief_cell.add_widget(self.learning_note)
            self.brief_cell.add_widget(self.assessment_controls)
            self.continue_practice_button = action(
                "Continuar para a prática  >", self._show_practice,
            )
            self.continue_practice_button.height = 0
            self.continue_practice_button.opacity = 0
            self.continue_practice_button.disabled = True
            self.brief_cell.add_widget(self.continue_practice_button)
            self.editor = CodeInput(
                text="", hint_text="Escreve a tua solução aqui…", font_size=dp(16),
                background_color=colors["card_alt"], foreground_color=colors["text"],
                size_hint_y=1, font_name="AprendixMono",
            )
            saved_editor_font = controller.load_preference("ide.editor_font_size", "")
            if saved_editor_font:
                try:
                    self.editor.font_size = max(
                        dp(12), min(dp(26), float(saved_editor_font))
                    )
                except ValueError:
                    pass
            self.editor.bind(text=self.track_edit)
            self.editor.bind(cursor=self._cursor_changed)
            self.editor.bind(on_touch_down=self._editor_double_click)
            self.code_cell = BoxLayout(
                orientation="vertical", size_hint_x=1, size_hint_y=1, spacing=dp(3),
            )
            code_header_scroll = ScrollView(
                do_scroll_x=True, do_scroll_y=False, bar_width=dp(4),
                size_hint_y=None, height=dp(42), scroll_type=["bars", "content"],
            )
            code_header = BoxLayout(
                size_hint=(None, None), height=dp(40), spacing=dp(4),
            )
            code_header.bind(minimum_width=code_header.setter("width"))
            self.file_label = text("main.py", size=15, bold=True, fixed=40)
            self.file_label.size_hint_x = None
            self.file_label.width = dp(150)
            code_header.add_widget(self.file_label)
            self.run_button = tool_action("", "Run", self.run_code, primary=True, width=50)
            self.correct_button = tool_action("", "Corrigir", self.evaluate, width=96)
            self.debug_button = tool_action("", "Debug", self.debug_setup, width=50)
            code_header.add_widget(self.run_button)
            code_header.add_widget(self.correct_button)
            code_header.add_widget(self.debug_button)
            code_header.add_widget(tool_action("", "Formatar", lambda *_: self._execute_ide_command("format"), width=50))
            code_header.add_widget(tool_action("", "Procurar", lambda *_: self._execute_ide_command("find"), width=50))
            code_header.add_widget(tool_action("", "Guardar", lambda *_: self._execute_ide_command("save"), width=50))
            code_header.add_widget(tool_action("", "Tutor", self._open_inline_tutor, width=50))
            code_header.add_widget(tool_action("", "CopyKate", self.copykate, width=50))
            code_header.add_widget(tool_action("", "Mais", self.engineering_tools, width=50))
            code_header_scroll.add_widget(code_header)

            self.find_bar = BoxLayout(
                size_hint_y=None, height=0, opacity=0, disabled=True, spacing=dp(4),
            )
            self.find_query = TextInput(
                hint_text="Procurar no ficheiro (Ctrl+F)", multiline=False,
                size_hint_x=.9, padding=(dp(8), dp(7)),
            )
            self.replace_value = TextInput(
                hint_text="Substituir por", multiline=False, size_hint_x=.8,
                padding=(dp(8), dp(7)),
            )
            self.find_status = text("", muted=True, fixed=34)
            self.find_status.size_hint_x = None
            self.find_status.width = dp(86)
            self.find_bar.add_widget(self.find_query)
            self.find_bar.add_widget(self.replace_value)
            self.find_bar.add_widget(tool_action("<", "Anterior", lambda *_: self._find_next(True), width=82))
            self.find_bar.add_widget(tool_action(">", "Seguinte", lambda *_: self._find_next(False), width=84))
            self.find_bar.add_widget(tool_action("=", "Substituir", self._replace_current, width=92))
            self.find_bar.add_widget(tool_action("*", "Tudo", self._replace_all, width=70))
            self.find_bar.add_widget(tool_action("X", "Fechar", self._close_find, width=72))
            self.find_bar.add_widget(self.find_status)
            self.find_query.bind(on_text_validate=lambda *_: self._find_next(False))
            editor_wrap = BoxLayout(size_hint_y=1, spacing=dp(3))
            self.gutter = TextInput(
                text=self._line_numbers(self.editor.text), readonly=True,
                size_hint_x=None, width=dp(52), font_size=dp(14),
                background_color=colors["card"], foreground_color=colors["muted"],
                padding=(dp(7), dp(7)), font_name="AprendixMono",
            )
            self.editor.size_hint_y = 1
            self.editor.bind(
                scroll_y=lambda _widget, value: setattr(self.gutter, "scroll_y", value)
            )
            editor_wrap.add_widget(self.gutter)
            editor_wrap.add_widget(self.editor)
            self.code_cell.add_widget(code_header_scroll)
            self.code_cell.add_widget(self.find_bar)
            self.code_cell.add_widget(editor_wrap)
            self.glossary_tip = text(
                "Dicionário: passa o rato sobre uma função ou conceito.",
                muted=True, fixed=30,
            )
            self._hover_term = ""
            self._hover_event = None
            Window.bind(mouse_pos=self._hover_dictionary)
            Window.bind(on_key_down=self._key_down)
            self.focus_duration = Spinner(text="25", values=("25", "50", "90", "120"))
            self.answer_confidence = Spinner(
                text="Confiança média",
                values=("Confiança baixa", "Confiança média", "Confiança alta"),
            )
            self.status = text("Pronto", muted=True, fixed=34)
            self.diagnostics = text("Diagnóstico local: sem erros de sintaxe.", muted=True, fixed=32)
            self.justification = TextInput(
                hint_text="Justificação conceptual (pedida apenas após colagem extensa)",
                multiline=False, size_hint_y=None, height=0, opacity=0, disabled=True,
            )
            initial_profile = book_workspace_profile(
                max(1, round(Window.width)), max(1, round(Window.height)),
                density=max(1.0, dp(1)), requested_terminal_ratio=self._terminal_ratio,
            )
            self._bottom_panel_height = dp(
                max(80, initial_profile.terminal_open_height_dp - 38)
            )
            self.terminal_shell = BoxLayout(
                orientation="vertical", size_hint_y=None, height=dp(38), spacing=dp(2),
            )
            self.bottom_panel = BoxLayout(
                orientation="vertical", size_hint_y=None,
                height=0, spacing=dp(4), opacity=0, disabled=True,
            )
            tabs = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(4))
            self.panel_tabs = {}
            panel_icons = {
                "Output": "output", "Problemas": "problems", "Testes": "tests",
                "Debug": "debug", "Tutor": "tutor",
            }
            for panel_name in ("Output", "Problemas", "Testes", "Debug", "Tutor"):
                tab = IconToggleAction(
                    panel_icons[panel_name], panel_name,
                    lambda _button, name=panel_name: self._show_panel(name),
                    group="ide-bottom-panel",
                    state="down" if panel_name == "Output" else "normal",
                )
                tab.size_hint_x = 1
                self.panel_tabs[panel_name] = tab
                tabs.add_widget(tab)
            tabs.add_widget(tool_action("", "X", self._toggle_bottom_panel, width=42))
            self.inline_tutor_controls = BoxLayout(
                size_hint_y=None, height=0, opacity=0, spacing=dp(5),
            )
            self.inline_tutor_question = TextInput(
                hint_text="Pergunta sobre o exercício ou erro atual…",
                multiline=False,
            )
            self.inline_tutor_controls.add_widget(self.inline_tutor_question)
            self.inline_tutor_controls.add_widget(tool_action(
                "?", "Pista", lambda *_: self._ask_inline_tutor(TutorStrategy.SOCRATIC), width=82,
            ))
            self.inline_tutor_controls.add_widget(tool_action(
                "!", "Erro", lambda *_: self._ask_inline_tutor(TutorStrategy.ANALYZE_ERROR), width=82,
            ))
            self.output = TextInput(
                text=self._panel_buffers["Output"], readonly=True,
                background_color=colors["card"], foreground_color=colors["text"],
                size_hint_y=1, font_size=dp(14), padding=dp(10),
                font_name="AprendixMono",
            )
            self.bottom_panel.add_widget(self.inline_tutor_controls)
            self.bottom_panel.add_widget(self.output)
            self.terminal_shell.add_widget(tabs)
            self.terminal_shell.add_widget(self.bottom_panel)

            try:
                brief_width = float(controller.load_preference(
                    "ide.brief_width_dp",
                    controller.load_preference("ide.brief_width", "430"),
                ))
            except ValueError:
                brief_width = 430
            self.brief_cell.size_hint_x = None
            self.brief_cell.size_hint_y = 1
            self.brief_cell.width = dp(min(650, max(320, brief_width)))
            self.workspace = BoxLayout(orientation="horizontal", size_hint_y=1, spacing=0)
            self.workspace_divider = PaneDivider(target=self.brief_cell)
            self.workspace.add_widget(self.code_cell)
            self.workspace.add_widget(self.workspace_divider)
            self.workspace.add_widget(self.brief_cell)
            self.workspace.bind(width=self._workspace_width_changed)
            self._apply_journey_header(Window.width)
            self.course_selector.bind(text=self._course_selected)
            self.ide_desk = BoxLayout(
                orientation="vertical", size_hint_y=1, spacing=0,
            )
            self.terminal_divider = TerminalDivider(
                target=self.terminal_shell, on_commit=self._persist_terminal_height,
            )
            self.ide_desk.add_widget(self.workspace)
            self.ide_desk.add_widget(self.terminal_divider)
            self.ide_desk.add_widget(self.terminal_shell)
            for widget in (journey, self.ide_desk, self.justification, self.status):
                root.add_widget(widget)
            self.add_widget(root)
            self._render_brief_document("exercise", self.selected.id if self.selected else "", self.prompt.text)
            if not initial_brief_expanded:
                Clock.schedule_once(lambda _dt: self._toggle_brief(persist=False), 0)
            if self.bottom_panel_expanded:
                self.bottom_panel_expanded = False
                Clock.schedule_once(lambda _dt: self._toggle_bottom_panel(persist=False), 0)
            Clock.schedule_once(lambda _dt: self._compose_practice_workspace(), 0)
            Clock.schedule_once(lambda _dt: self._activate_exercise(self.selected), 0)

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
            elif hasattr(self, "status"):
                self.status.text = (
                    f"Python local  ·  sandbox  ·  Ln {cursor[1] + 1}, "
                    f"Col {cursor[0] + 1}  ·  UTF-8"
                )

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
            if self.pasted >= 200 and self.justification.height == 0:
                self.justification.height = dp(38)
                self.justification.opacity = 1
                self.justification.disabled = False
            if hasattr(self, "file_label"):
                self.file_label.text = "•  " + (
                    self._active_project_path if self.workspace_mode == "project" else "main.py"
                )
            if self.selected or self.workspace_mode == "project":
                if self.draft_event is not None:
                    self.draft_event.cancel()
                self.draft_event = Clock.schedule_once(
                    self._persist_editor_state, 0.6
                )
            Clock.unschedule(self._update_diagnostics)
            Clock.schedule_once(self._update_diagnostics, .35)

        def _persist_editor_state(self, *_args):
            if self.workspace_mode == "project":
                self.save_project(None)
                return
            if not self.selected:
                return
            controller.save_draft(self.selected.id, self.editor.text)
            controller.save_debug_recovery(
                self.selected.id, self.editor.text,
                cursor_index=self.editor.cursor_index(),
                breakpoints=tuple(item.model_dump(mode="json") for item in self._debug_breakpoints),
                watches=self._debug_watches,
            )

        def _set_journey_title(self, title):
            """Keep the full journey title while rendering one bounded line."""

            full_title = str(title or "Sem exercícios")
            self.exercise_title.text = full_title
            self.exercise_title.full_title = full_title
            self.exercise_title.accessible_name = full_title
            self.exercise_title.tooltip_text = full_title

        def _apply_journey_header(self, width):
            profile = ide_journey_header_profile(
                max(1, round(width)), density=max(1.0, dp(1)),
            )
            self._journey_header_profile = profile
            for button in (self.previous_exercise_button, self.next_exercise_button):
                button.width = dp(profile.navigation_width_dp)
            self.course_selector.width = dp(profile.course_width_dp)
            if profile.compact:
                self.exercise_title.size_hint_x = None
                self.exercise_title.width = dp(profile.title_width_dp)
            else:
                self.exercise_title.size_hint_x = 1
            return profile

        def _brief_context_label(self):
            return "Aula" if self.brief_view == "theory" else "Enunciado"

        def _update_brief_toggle(self):
            context = self._brief_context_label()
            state = "[-]" if self.brief_expanded else "[+]"
            action_name = "Recolher" if self.brief_expanded else "Expandir"
            self.brief_toggle.command_title = f"{action_name} apoio · {context.casefold()}"
            self.brief_toggle.set_label_visible(True)
            self.brief_toggle.text = f"Apoio {state}"
            self.brief_toggle.accessible_name = self.brief_toggle.command_title
            self.brief_toggle.tooltip_text = self.brief_toggle.command_title

        def _set_workspace_layout(self, mode):
            """Keep the book visible while changing the right pedagogical page."""

            theory = mode == "theory"
            self.continue_practice_button.height = dp(46) if theory else 0
            self.continue_practice_button.opacity = 1 if theory else 0
            self.continue_practice_button.disabled = not theory
            self._compose_practice_workspace()

        def _compose_practice_workspace(self):
            """Use a two-page book whenever the actual learning desk can fit it."""

            self.workspace.clear_widgets()
            self._apply_journey_header(Window.width)
            workspace_width = max(1, round(self.workspace.width or Window.width))
            workspace_height = max(1, round(
                (self.ide_desk.height if hasattr(self, "ide_desk") else Window.height)
            ))
            requested_support = self.brief_cell.width / max(dp(1), .001)
            profile = book_workspace_profile(
                workspace_width, workspace_height, density=max(1.0, dp(1)),
                requested_support_width_dp=requested_support,
                requested_terminal_ratio=self._terminal_ratio,
            )
            self._book_workspace_profile = profile
            self.compact_workspace = profile.mode == "tabs"
            if self.compact_workspace:
                self.workspace_pane_button.width = dp(104)
                self.workspace_pane_button.opacity = 1
                self.workspace_pane_button.disabled = False
                if self.compact_pane == "brief":
                    self.brief_cell.size_hint_x = 1
                    self.workspace.add_widget(self.brief_cell)
                    self.workspace_pane_button.text = "Editor"
                    self.workspace_pane_button.command_title = "Mostrar editor"
                else:
                    self.code_cell.size_hint_x = 1
                    self.workspace.add_widget(self.code_cell)
                    self.workspace_pane_button.text = "Apoio"
                    self.workspace_pane_button.command_title = "Mostrar enunciado"
                self.workspace_pane_button.accessible_name = self.workspace_pane_button.command_title
                self.workspace_pane_button.tooltip_text = self.workspace_pane_button.command_title
                return
            self.workspace_pane_button.width = 0
            self.workspace_pane_button.opacity = 0
            self.workspace_pane_button.disabled = True
            self.brief_cell.size_hint_x = None
            self.brief_cell.width = dp(profile.support_width_dp)
            self.workspace.add_widget(self.code_cell)
            self.workspace.add_widget(self.workspace_divider)
            self.workspace.add_widget(self.brief_cell)

        def _toggle_workspace_pane(self, *_args):
            if not self.compact_workspace:
                return
            self.compact_pane = "brief" if self.compact_pane == "editor" else "editor"
            if self.compact_pane == "brief" and not self.brief_expanded:
                self._toggle_brief(persist=False)
            controller.save_preference("ide.compact_pane", self.compact_pane)
            self._compose_practice_workspace()

        def _workspace_width_changed(self, _workspace, width):
            if not hasattr(self, "ide_desk"):
                return
            profile = book_workspace_profile(
                max(1, round(width)), max(1, round(self.ide_desk.height or Window.height)),
                density=max(1.0, dp(1)),
                requested_support_width_dp=self.brief_cell.width / max(dp(1), .001),
                requested_terminal_ratio=self._terminal_ratio,
            )
            compact = profile.mode == "tabs"
            if compact == self.compact_workspace:
                if not compact:
                    maximum = max(320, profile.available_width_dp - 369)
                    current = self.brief_cell.width / max(dp(1), .001)
                    if current > maximum:
                        self.brief_cell.width = dp(maximum)
                return
            self.compact_workspace = compact
            Clock.schedule_once(lambda _dt: self._compose_practice_workspace(), 0)

        def _resize_prompt(self, delta):
            if not self.brief_expanded:
                self._toggle_brief()
            self.document_zoom = min(5, max(-3, self.document_zoom + (1 if delta > 0 else -1)))
            controller.save_preference("ide.document_zoom", str(self.document_zoom))
            self._apply_document_zoom()

        def _apply_document_zoom(self):
            for widget in self.document_column.walk():
                base = getattr(widget, "aprendix_base_font_size", None)
                if base is not None:
                    widget.font_size = dp(max(11, base + self.document_zoom) * font_scale)
                elif isinstance(widget, CodeInput):
                    widget.font_size = dp(max(11, 14 + self.document_zoom))

        def _render_brief_document(self, owner_type, owner_id, fallback):
            document = None
            exercise_brief = None
            if owner_type == "exercise" and self.selected is not None:
                exercise_brief = build_exercise_brief(self.selected)
                fallback = strip_latex_markup(
                    fallback, (exercise_brief.formula_latex,)
                    if exercise_brief.formula_latex else (),
                )
            if owner_id and hasattr(controller, "pedagogical_document"):
                try:
                    document = controller.pedagogical_document(owner_type, str(owner_id))
                except Exception:
                    document = None
            if document is not None and document.blocks:
                render_pedagogical_blocks(self.document_column, document.blocks, compact=True)
            else:
                render_legacy_document(self.document_column, fallback, compact=True)
            if exercise_brief is not None:
                already_has_formula = any(
                    isinstance(widget, FormulaView) for widget in self.document_column.walk()
                )
                if exercise_brief.formula_latex and not already_has_formula:
                    variables = {}
                    for item in exercise_brief.variables:
                        name, separator, meaning = item.partition(":")
                        variables[name.strip()] = meaning.strip() if separator else item
                    self.document_column.add_widget(FormulaView(
                        latex=exercise_brief.formula_latex,
                        spoken=exercise_brief.formula_spoken or "Fórmula do exercício",
                        variables=variables,
                        compact=True,
                    ))
            self._apply_document_zoom()
            Clock.schedule_once(lambda _dt: self._reset_prompt_view(), 0)

        def _show_support_hints(self, *_args):
            """Render progressive help on the right page without leaving the IDE."""

            receipt = self._last_evaluation_receipt
            lines = []
            if receipt is not None:
                if getattr(receipt, "prerequisite_terms", ()):
                    lines.append(
                        "Revê primeiro: " + ", ".join(receipt.prerequisite_terms)
                    )
                lines.extend(getattr(receipt, "remediation_actions", ()) or ())
                lines.extend(getattr(receipt, "assistance", ()) or ())
                if getattr(receipt, "mini_exercise", ""):
                    lines.append(receipt.mini_exercise)
            if not lines and self.selected is not None:
                for hint in tuple(getattr(self.selected, "hints", ()) or ()):
                    lines.append(normalize_ui_text(getattr(hint, "text", hint)))
            if not lines:
                lines = [
                    "Identifica entradas, transformação e resultado esperado.",
                    "Resolve primeiro o caso normal e depois os casos-limite.",
                    "Executa antes de Corrigir para observares o comportamento real.",
                ]
            self.document_column.clear_widgets()
            self.document_column.add_widget(text("Pistas graduais", size=20, bold=True, fixed=38))
            self.document_column.add_widget(text(
                "\n".join(f"{index}. {item}" for index, item in enumerate(lines[:8], 1)),
                size=15,
            ))
            self.document_scroll.scroll_y = 1
            self.hints_used += 1
            self.status.text = "Pistas abertas na página de apoio."

        def _show_support_solution(self, *_args):
            """Disclose only the server-approved local reference solution."""

            receipt = self._last_evaluation_receipt
            evaluation_locked = (
                self.brief_view == "assessment"
                and self.assessment_mode.text == "Avaliação"
            )
            if evaluation_locked:
                self.status.text = "Solução bloqueada durante a avaliação."
                return
            if receipt is None or not getattr(receipt, "reference_available", False):
                self.status.text = (
                    "A solução possível fica disponível após aprovação ou quatro tentativas "
                    "falhadas em treino."
                )
                return
            self.document_column.clear_widgets()
            self.document_column.add_widget(text(
                "Solução possível · validada localmente", size=20, bold=True, fixed=38,
            ))
            explanation = normalize_ui_text(getattr(receipt, "reference_explanation", ""))
            if explanation:
                self.document_column.add_widget(text(explanation, size=14))
            solution = str(getattr(receipt, "reference_solution", ""))
            rows = min(24, max(4, solution.count("\n") + 1))
            self.document_column.add_widget(CodeInput(
                text=solution, readonly=True, size_hint_y=None,
                height=dp(22 + rows * 22), font_size=dp(14),
                font_name="AprendixMono",
                background_color=colors["card_alt"], foreground_color=colors["text"],
            ))
            self.document_column.add_widget(text(
                "É uma solução de referência, não a única solução correta.", muted=True,
            ))
            self.document_scroll.scroll_y = 1
            self.status.text = "Solução possível aberta na página de apoio."

        def _show_support_execution(self, *_args):
            """Show successful execution separately from any real traceback."""

            receipt = self._last_evaluation_receipt
            trace = tuple(getattr(receipt, "reference_trace", ()) or ()) if receipt else ()
            expected = tuple(
                getattr(receipt, "reference_expected_output", ()) or ()
            ) if receipt else ()
            if not trace and not expected:
                self.status.text = "A execução esperada ainda não está disponível."
                return
            self.document_column.clear_widgets()
            self.document_column.add_widget(text(
                "Execução esperada", size=20, bold=True, fixed=38,
            ))
            if trace:
                self.document_column.add_widget(text(
                    "Traço estrutural\n" + "\n".join(
                        f"{index}. {step}" for index, step in enumerate(trace, 1)
                    ), size=14,
                ))
            if expected:
                self.document_column.add_widget(text(
                    "Saída esperada", size=17, bold=True, fixed=34,
                ))
                self.document_column.add_widget(CodeInput(
                    text="\n".join(expected), readonly=True, size_hint_y=None,
                    height=dp(min(320, 35 + 22 * len(expected))),
                    font_name="AprendixMono",
                    background_color=colors["card_alt"], foreground_color=colors["text"],
                ))
            self.document_column.add_widget(text(
                "Traceback é reservado a uma exceção real e aparece no terminal.",
                muted=True,
            ))
            self.document_scroll.scroll_y = 1
            self.status.text = "Execução esperada aberta na página de apoio."

        def _reset_prompt_view(self):
            """Open each exercise at the first line instead of the last cursor position."""

            self.prompt.cursor = (0, 0)
            self.prompt.scroll_x = 0
            self.prompt.scroll_y = 0
            self.document_scroll.scroll_y = 1

        def _toggle_brief(self, *_args, persist=True):
            if self.brief_expanded:
                self.document_scroll.size_hint_y = None
                self.document_scroll.height = 0
                self.document_scroll.opacity = 0
                self.document_scroll.disabled = True
                self.brief_expanded = False
            else:
                self.document_scroll.size_hint_y = 1
                self.document_scroll.opacity = 1
                self.document_scroll.disabled = False
                self.brief_expanded = True
            self._update_brief_toggle()
            if persist:
                controller.save_preference(
                    "ide.brief_expanded", "1" if self.brief_expanded else "0"
                )

        def _toggle_bottom_panel(self, *_args, persist=True):
            if self.bottom_panel_expanded:
                self.bottom_panel.height = 0
                self.bottom_panel.opacity = 0
                self.bottom_panel.disabled = True
                self.terminal_shell.height = dp(38)
                self.terminal_divider.height = 0
                self.bottom_panel_expanded = False
            else:
                available = max(400, self.ide_desk.height / max(dp(1), .001))
                profile = book_workspace_profile(
                    max(1, round(self.workspace.width)),
                    max(1, round(self.ide_desk.height)), density=max(1.0, dp(1)),
                    requested_terminal_ratio=self._terminal_ratio,
                )
                self._bottom_panel_height = dp(max(
                    80, min(available * .35, profile.terminal_open_height_dp) - 38
                ))
                self.bottom_panel.height = self._bottom_panel_height
                self.bottom_panel.opacity = 1
                self.bottom_panel.disabled = False
                self.terminal_shell.height = dp(38) + self._bottom_panel_height
                self.terminal_divider.height = dp(7)
                self.bottom_panel_expanded = True
            if persist:
                controller.save_preference(
                    "ide.bottom_panel_expanded",
                    "1" if self.bottom_panel_expanded else "0",
                )

        def _persist_terminal_height(self, height):
            useful = max(dp(400), self.ide_desk.height)
            ratio = min(.35, max(.20, height / useful))
            self._terminal_ratio = ratio
            self._bottom_panel_height = max(dp(80), height - dp(38))
            self.bottom_panel.height = self._bottom_panel_height
            controller.save_preference("ide.terminal_ratio", f"{ratio:.4f}")

        def _show_panel(self, name):
            if name not in self._panel_buffers:
                return
            self._panel_buffers[self._active_panel] = self.output.text
            self._active_panel = name
            self.output.text = self._panel_buffers[name]
            for panel_name, tab in self.panel_tabs.items():
                tab.state = "down" if panel_name == name else "normal"
            tutor_open = name == "Tutor"
            self.inline_tutor_controls.height = dp(40) if tutor_open else 0
            self.inline_tutor_controls.opacity = 1 if tutor_open else 0
            self.inline_tutor_controls.disabled = not tutor_open
            if not self.bottom_panel_expanded:
                self._toggle_bottom_panel()

        def _set_panel_text(self, name, value, *, activate=False):
            self._panel_buffers[name] = value
            if activate or self._active_panel == name:
                if activate:
                    self._show_panel(name)
                self.output.text = value

        def _zoom_editor(self, delta):
            self.editor.font_size = max(dp(12), min(dp(26), self.editor.font_size + dp(delta)))
            controller.save_preference("ide.editor_font_size", f"{self.editor.font_size:.2f}")
            self.status.text = f"Editor: {round(self.editor.font_size / max(dp(1), .001))} pt."

        def _format_editor(self):
            try:
                self.editor.text = format_python(self.editor.text)
                self.status.text = "Formatação conservadora aplicada."
            except SyntaxError as exc:
                self.status.text = f"Formatação bloqueada: sintaxe inválida na linha {exc.lineno}."

        def _set_execution_busy(self, busy):
            for button in (self.run_button, self.correct_button, self.debug_button):
                button.disabled = bool(busy)
            self.editor.readonly = bool(busy)

        def _execute_ide_command(self, command_id):
            handlers = {
                "run": lambda: self.run_code(None),
                "correct": lambda: self.evaluate(None),
                "debug": lambda: self.debug_setup(None),
                "save": self._save_draft_now,
                "find": lambda: self._open_find(False),
                "replace": lambda: self._open_find(True),
                "format": self._format_editor,
                "copy": lambda: Clipboard.copy(self.editor.text),
                "zoom_in": lambda: self._zoom_editor(1),
                "zoom_out": lambda: self._zoom_editor(-1),
                "toggle_brief": self._toggle_brief,
                "toggle_panel": self._toggle_bottom_panel,
                "tutor": self._open_inline_tutor,
                "copykate": lambda: self.copykate(None),
                "variation": lambda: self.variation(None),
                "complete": lambda: self.complete(None),
                "focus": lambda: self.toggle_focus(None),
            }
            handler = handlers.get(command_id)
            if handler is not None:
                handler()

        def _save_draft_now(self):
            if self.workspace_mode == "project":
                self.save_project(None)
                self.file_label.text = self._active_project_path
                return
            self._persist_editor_state()
            self.file_label.text = "main.py"
            self.status.text = "Rascunho guardado localmente."

        def _open_find(self, replace=False):
            self.find_bar.height = dp(40)
            self.find_bar.opacity = 1
            self.find_bar.disabled = False
            self.replace_value.opacity = 1 if replace else .45
            self.replace_value.disabled = not replace
            selection = self.editor.selection_text.strip()
            if selection and "\n" not in selection:
                self.find_query.text = selection
            self.find_status.text = ""
            Clock.schedule_once(lambda _dt: setattr(self.find_query, "focus", True), .04)

        def _close_find(self, *_args):
            self.find_bar.height = 0
            self.find_bar.opacity = 0
            self.find_bar.disabled = True
            self.editor.focus = True

        def _find_next(self, reverse=False):
            needle = self.find_query.text
            if not needle:
                self.find_status.text = "0 resultados"
                return
            source = self.editor.text
            start = self.editor.selection_from if reverse else self.editor.selection_to
            if start is None:
                start = self.editor.cursor_index()
            position = source.rfind(needle, 0, max(0, start)) if reverse else source.find(
                needle, min(len(source), start)
            )
            if position < 0:
                position = source.rfind(needle) if reverse else source.find(needle)
            if position < 0:
                self.find_status.text = "0 resultados"
                return
            self.editor.select_text(position, position + len(needle))
            self.editor.cursor = self.editor.get_cursor_from_index(position + len(needle))
            total = source.count(needle)
            ordinal = source[:position].count(needle) + 1
            self.find_status.text = f"{ordinal}/{total}"
            self.editor.focus = True

        def _replace_current(self, *_args):
            needle = self.find_query.text
            if not needle:
                self.find_status.text = "Indica texto"
                return
            if self.editor.selection_text == needle:
                start = min(self.editor.selection_from, self.editor.selection_to)
                end = max(self.editor.selection_from, self.editor.selection_to)
                self.editor.text = (
                    self.editor.text[:start] + self.replace_value.text + self.editor.text[end:]
                )
                self.editor.cursor = self.editor.get_cursor_from_index(
                    start + len(self.replace_value.text)
                )
            self._find_next(False)

        def _replace_all(self, *_args):
            needle = self.find_query.text
            if not needle:
                self.find_status.text = "Indica texto"
                return
            count = self.editor.text.count(needle)
            if count:
                self.editor.text = self.editor.text.replace(needle, self.replace_value.text)
            noun = "substituição" if count == 1 else "substituições"
            self.find_status.text = f"{count} {noun}"
            self.editor.focus = True

        def _open_inline_tutor(self, *_args):
            self._show_panel("Tutor")
            Clock.schedule_once(
                lambda _dt: setattr(self.inline_tutor_question, "focus", True), .05
            )

        def _ask_inline_tutor(self, strategy):
            if not self.selected and self.workspace_mode != "project":
                return
            if self.brief_view == "assessment" and self.assessment_mode.text == "Avaliação":
                self.status.text = "Tutor bloqueado durante a avaliação."
                self._set_panel_text(
                    "Tutor", "Conclui primeiro esta resposta de avaliação.", activate=True,
                )
                return
            self.hints_used += 1
            question = self.inline_tutor_question.text.strip()
            if not question:
                question = (
                    "Orienta-me com uma pista curta e socrática. Não reveles a solução completa."
                )
            if self.workspace_mode == "project":
                context = (
                    f"Projeto: {self._active_project_name}.\n"
                    f"Brief: {self.prompt.text[:1200]}\n"
                    f"Diagnóstico atual: {self.diagnostics.text[:500]}\n"
                    f"Código atual:\n{self.editor.text[:1600]}\n\nPergunta: {question}"
                )[:3900]
            else:
                context = (
                    f"Exercício: {self.selected.title}.\n"
                    f"Objetivo: {self.selected.prompt[:900]}\n"
                    f"Diagnóstico atual: {self.diagnostics.text[:500]}\n"
                    f"Código atual:\n{self.editor.text[:1600]}\n\nPergunta: {question}"
                )[:3900]
            request = TutorRequestDTO(
                question=context, strategy=strategy, evaluation_locked=True,
            )
            self._set_panel_text(
                "Tutor", "A recuperar evidência local e a preparar uma orientação…",
                activate=True,
            )
            threading.Thread(
                target=self._inline_tutor_worker, args=(request,), daemon=True
            ).start()

        def _inline_tutor_worker(self, request):
            try:
                response = controller.ask_tutor(request)
                Clock.schedule_once(lambda _dt: self._render_inline_tutor(response), 0)
            except Exception as exc:
                Clock.schedule_once(
                    lambda _dt, message=str(exc): self._set_panel_text(
                        "Tutor", "Tutor indisponível: " + message, activate=True,
                    ), 0,
                )

        def _render_inline_tutor(self, response):
            sources = "\n".join(
                f"[{index}] {item.title}" for index, item in enumerate(response.evidence, 1)
            )
            heading = (
                "Recusa segura" if response.declined else
                f"Orientação fundamentada · confiança {response.confidence:.0%}"
            )
            body = f"{heading}\n\n{response.answer}"
            if sources:
                body += "\n\nFontes locais\n" + sources
            self._set_panel_text("Tutor", body, activate=True)

        def _update_diagnostics(self, *_args):
            issues = diagnose_python(self.editor.text)
            if not issues:
                self.diagnostics.text = "Diagnóstico local: sintaxe válida; sem alertas imediatos."
                self._set_panel_text("Problemas", "Sem problemas detetados no código atual.")
                return
            messages = tuple(
                f"L{item.line}:{item.column} {item.severity}: {item.message}"
                + (f" Correção: {item.quick_fix}." if item.quick_fix else "")
                for item in issues[:4]
            )
            self.diagnostics.text = "  ·  ".join(messages)
            self._set_panel_text("Problemas", "\n".join(messages))

        def _apply_quick_fixes(self, *_args):
            updated, count = apply_safe_quick_fixes(self.editor.text)
            if not count:
                self.status.text = "Não existem correções automáticas seguras neste momento."
                return
            self.editor.text = updated
            self.status.text = f"{count} correção(ões) segura(s) aplicada(s); revê o resultado."
            self._update_diagnostics()

        def debug_setup(self, *_args):
            if (
                (self.workspace_mode == "exercise" and not self.selected)
                or not self.editor.text.strip()
            ):
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
                self._set_execution_busy(True)
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
                result = controller.debug_code(
                    request, self.selected.id if self.selected is not None else None,
                )
                Clock.schedule_once(lambda _dt: self._show_debugger(result), 0)
            except Exception as exc:
                Clock.schedule_once(
                    lambda _dt, message=str(exc): self._show_error(message), 0
                )

        def _show_debugger(self, result):
            self._set_execution_busy(False)
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
            analysis_controls.add_widget(action("Histórico", self._show_debug_history))
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

        def _show_debug_history(self, *_args):
            sessions = controller.debug_history(limit=20)
            tests = controller.test_history(limit=20)
            debug_lines = [
                f"{item['created_at'][:19]} · {item['status']} · "
                f"{item['coverage_percent']:.1f}% · {item['duration_ms']} ms"
                for item in sessions
            ] or ["Sem sessões de debug anteriores."]
            test_lines = [
                f"{item['created_at'][:19]} · públicos "
                f"{item['public_passed']}/{item['public_total']} · ocultos "
                f"{item['hidden_passed']}/{item['hidden_total']}"
                for item in tests
            ] or ["Sem correções anteriores."]
            self.debug_view.text = (
                "HISTÓRICO LOCAL DE DEBUG\n" + "\n".join(debug_lines)
                + "\n\nHISTÓRICO DE TESTES\n" + "\n".join(test_lines)
            )

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
                marker = ">" if line_number == frame.line else " "
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
                    self._set_panel_text("Output", message, activate=True)
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

        def _course_selected(self, _spinner, title):
            track_slug = self._course_titles.get(title)
            if track_slug and track_slug != self.course_slug:
                self.start_course(track_slug)

        def start_course(self, track_slug, exercise_id=None):
            items = list(controller.course_practice(track_slug))
            if not items:
                self.status.text = "Este percurso ainda não tem práticas disponíveis."
                return
            self.course_slug = track_slug
            self.course_items = items
            controller.save_preference("ide.course_slug", track_slug)
            course_title = self._course_names.get(track_slug)
            if course_title and self.course_selector.text != course_title:
                self.course_selector.text = course_title
            target = next(
                (item for item in items if str(item["exercise"].id) == str(exercise_id)),
                None,
            )
            if target is None:
                target = next(
                    (item for item in items if not item["completed"]), items[0]
                )
            self._activate_exercise(target["exercise"])

        def _activate_exercise(self, exercise, transition_message=""):
            if self.workspace_mode == "project" and self._active_project_id is not None:
                self.save_project(None)
            if (
                exercise is not None and self.selected is not None
                and exercise.id != self.selected.id and hasattr(self, "editor")
            ):
                if self.draft_event is not None:
                    self.draft_event.cancel()
                    self.draft_event = None
                self._persist_learning_note()
                self._persist_editor_state()
            self.selected = exercise
            if self.selected:
                self.workspace_mode = "exercise"
                self.course_selector.disabled = False
                self._active_project_id = None
                self._active_project_name = ""
                self._active_project_path = "main.py"
                self._active_project_template_id = ""
                self.learning_session_state = controller.learning_session(self.selected.id)
                self.transfer_context = False
                draft = controller.load_draft(self.selected.id)
                recovery = controller.load_debug_recovery(self.selected.id)
                self._set_journey_title(self.selected.title)
                self.prompt.text = build_exercise_brief(self.selected).render()
                Clock.schedule_once(lambda _dt: self._reset_prompt_view(), 0)
                self.editor.text = (
                    recovery["source"] if recovery is not None else
                    draft if draft is not None else ""
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
                self.hints_used = 0
                self.last_edit_at = self.started
                self.justification.text = ""
                self.file_label.text = "main.py"
                self._last_evaluation_receipt = None
                self.solution_button.disabled = True
                self.execution_button.disabled = True
                self._set_panel_text(
                    "Output", transition_message or (
                        "Terminal local pronto. Executa para observar o resultado; "
                        "usa Corrigir quando quiseres validar o contrato."
                    ),
                    activate=False,
                )
                self._update_journey()
                theory_seen = self.learning_session_state.theory_viewed
                saved_phase = str(getattr(
                    self.learning_session_state.phase, "value", self.learning_session_state.phase
                ))
                if self._current_journey_item() and (
                    not theory_seen or saved_phase == "microtheory"
                ):
                    self._show_theory()
                    self.status.text = "Começa pela microteoria e depois entra na prática."
                else:
                    self._show_practice()
                    self.status.text = "Pronto para resolver de raiz."

        def select(self, _spinner, title):
            exercise = next((item for item in self.catalogue if item.title == title), None)
            if exercise is not None:
                self._activate_exercise(exercise)

        def load_exercise(self, exercise_id, track_slug=None):
            if track_slug:
                self.start_course(track_slug, exercise_id)
                return
            for slug in self._course_names:
                items = controller.course_practice(slug)
                if any(str(item["exercise"].id) == str(exercise_id) for item in items):
                    self.start_course(slug, exercise_id)
                    return
            exercise = next(
                (item for item in self.catalogue if str(item.id) == str(exercise_id)), None
            )
            if exercise is not None:
                self.course_slug, self.course_items = "", []
                self._activate_exercise(exercise)

        def _update_journey(self):
            if not self.selected or not self.course_items:
                self.journey_meta.text = "Treino livre"
                self.journey_progress.value = 0
                self.previous_exercise_button.disabled = True
                self.next_exercise_button.disabled = True
                return
            index = next(
                (position for position, item in enumerate(self.course_items)
                 if item["exercise"].id == self.selected.id), 0,
            )
            completed = sum(bool(item["completed"]) for item in self.course_items)
            chapter = self.course_items[index]["chapter_title"]
            self.journey_meta.text = (
                f"{chapter}  ·  exercício {index + 1} de {len(self.course_items)}  ·  "
                f"{completed} concluídos"
            )
            self.journey_progress.value = completed / max(1, len(self.course_items))
            self.previous_exercise_button.disabled = index == 0
            self.next_exercise_button.disabled = index >= len(self.course_items) - 1

        def _current_journey_item(self):
            if not self.selected:
                return None
            return next(
                (item for item in self.course_items
                 if item["exercise"].id == self.selected.id), None,
            )

        def _selected_brief_mode(self):
            return {"Simples": "simple", "Guiado": "guided", "Técnico": "technical"}.get(
                self.brief_mode.text, "guided"
            )

        def _brief_mode_selected(self, _spinner, _value):
            controller.save_preference("ide.brief_mode", self._selected_brief_mode())
            if self.selected and self.brief_view == "practice":
                self.prompt.text = build_exercise_brief(self.selected).render(
                    self._selected_brief_mode()
                )
                self._render_brief_document("exercise", self.selected.id, self.prompt.text)

        def _show_theory(self, *_args):
            if not self.selected:
                return
            from aprendix.application.learning_session import render_microtheory

            item = self._current_journey_item() or {}
            self._hide_assessment_controls()
            self.brief_view = "theory"
            self._update_brief_toggle()
            self._set_workspace_layout("theory")
            self.learning_session_state = controller.update_learning_session(
                self.selected.id, phase="microtheory", theory_viewed=True,
                hint_count=self.hints_used,
                active_seconds=max(0, round(self.active_seconds)),
            )
            self.prompt.text = render_microtheory(
                str(item.get("theory_title", "")),
                str(item.get("theory_body", "")),
                str(item.get("theory_example", "")),
            )
            self._render_brief_document(
                "lesson", item.get("theory_unit_id", ""), self.prompt.text,
            )
            self.theory_button.disabled = True
            self.practice_button.disabled = False
            self.learning_note.hint_text = (
                "Previsão: que passos, validações e casos-limite vais usar?"
            )
            self.learning_note.text = self.learning_session_state.prediction
            self.status.text = "Aula ativa · continua para a prática quando estiveres preparado."
            Clock.schedule_once(lambda _dt: self._reset_prompt_view(), 0)

        def _show_practice(self, *_args):
            if not self.selected:
                return
            prediction = None
            if self.brief_view == "theory":
                prediction = self.learning_note.text
            self.brief_view = "practice"
            self._update_brief_toggle()
            self._set_workspace_layout("practice")
            self._hide_assessment_controls()
            self.learning_session_state = controller.update_learning_session(
                self.selected.id,
                phase="guided_practice" if self.hints_used else "independent_practice",
                theory_viewed=True, prediction=prediction,
                hint_count=self.hints_used,
                active_seconds=max(0, round(self.active_seconds)),
            )
            self.prompt.text = build_exercise_brief(self.selected).render(
                self._selected_brief_mode()
            )
            self._render_brief_document("exercise", self.selected.id, self.prompt.text)
            self.theory_button.disabled = False
            self.practice_button.disabled = True
            self.learning_note.hint_text = (
                "Notas de raciocínio; após aprovação, regista o que aprendeste."
            )
            self.learning_note.text = self.learning_session_state.reflection
            self.status.text = "Prática ativa · resolve de raiz e executa quando estiveres pronto."
            Clock.schedule_once(lambda _dt: self._reset_prompt_view(), 0)

        def _hide_assessment_controls(self):
            self.assessment_controls.height = 0
            self.assessment_controls.opacity = 0
            self.assessment_controls.disabled = True
            self.learning_note.height = dp(38)
            self.learning_note.opacity = 1
            self.learning_note.disabled = False
            self.assessment_button.disabled = not bool(
                (self._current_journey_item() or {}).get("assessments")
            )

        def _show_assessment(self, *_args):
            item = self._current_journey_item() or {}
            candidates = tuple(item.get("assessments", ()))
            selected = next(
                (candidate for candidate in candidates
                 if candidate["unlocked"] and not candidate["completed"]),
                next((candidate for candidate in candidates if candidate["unlocked"]), None),
            )
            if selected is None:
                self.status.text = (
                    "Conclui a prática e a microteoria deste capítulo para desbloquear o teste."
                )
                return
            try:
                assessment = controller.assessment(selected["assessment_id"])
            except (KeyError, RuntimeError, ValueError) as exc:
                self.status.text = f"Teste indisponível: {exc}"
                return
            self.active_assessment = {**selected, **assessment}
            self.assessment_started = time.monotonic()
            self.brief_view = "assessment"
            self._update_brief_toggle()
            self._set_workspace_layout("practice")
            self.prompt.text = (
                f"Teste de etapa · {selected['title']}\n\n{assessment['prompt']}\n\n"
                "Em Treino recebes explicação imediata. Em Avaliação a resposta é "
                "registada sem revelar a solução durante a tentativa."
            )
            self._render_brief_document("lesson", selected.get("unit_id", ""), self.prompt.text)
            self._assessment_options = {
                f"{option['id'].upper()}. {option['text']}": option["id"]
                for option in assessment["options"]
            }
            self.assessment_option.values = tuple(self._assessment_options)
            self.assessment_option.text = "Seleciona uma resposta"
            self.assessment_controls.height = dp(42)
            self.assessment_controls.opacity = 1
            self.assessment_controls.disabled = False
            self.learning_note.height = 0
            self.learning_note.opacity = 0
            self.learning_note.disabled = True
            self.theory_button.disabled = False
            self.practice_button.disabled = False
            self.assessment_button.disabled = True
            self.status.text = "Teste pronto · escolhe o modo e uma resposta."
            Clock.schedule_once(lambda _dt: self._reset_prompt_view(), 0)

        def _submit_assessment(self, *_args):
            if not self.active_assessment:
                return
            answer = self._assessment_options.get(self.assessment_option.text)
            if answer is None:
                self.status.text = "Seleciona primeiro uma resposta."
                return
            mode = "evaluation" if self.assessment_mode.text == "Avaliação" else "training"
            duration = max(0, round(time.monotonic() - self.assessment_started))
            try:
                result = controller.answer_assessment(
                    self.active_assessment["assessment_id"], answer,
                    duration_seconds=duration, mode=mode,
                )
            except (KeyError, RuntimeError, ValueError) as exc:
                self.status.text = f"Não foi possível avaliar: {exc}"
                return
            heading = "Resposta correta" if result["passed"] else "Resposta incorreta"
            message = result.get("feedback") or result.get("explanation") or "Resposta registada."
            self._set_panel_text(
                "Testes",
                f"{heading} · {duration}s · modo {self.assessment_mode.text}\n\n{message}",
                activate=True,
            )
            self.status.text = heading
            refreshed = list(controller.course_practice(self.course_slug))
            if refreshed:
                self.course_items = refreshed
            if result["passed"]:
                self.active_assessment = None
                self._update_journey()

        def _persist_learning_note(self):
            if (
                self.workspace_mode != "exercise" or not self.selected
                or self.learning_session_state is None
            ):
                return
            changes = {
                "hint_count": self.hints_used,
                "active_seconds": max(0, round(self.active_seconds)),
            }
            if self.brief_view == "theory":
                changes["prediction"] = self.learning_note.text
            elif self.learning_session_state.phase.value == "reflection":
                changes["reflection"] = self.learning_note.text
            self.learning_session_state = controller.update_learning_session(
                self.selected.id, **changes
            )

        def _hover_dictionary(self, _window, position):
            if self.manager is not None and self.manager.current != self.name:
                return
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
                self.status.text = self.glossary_tip.text

        def _editor_term_at(self, column, row):
            lines = self.editor.text.splitlines()
            line = lines[row] if 0 <= row < len(lines) else ""
            return next(
                (item.group(0) for item in re.finditer(r"[A-Za-z_][A-Za-z0-9_]*", line)
                 if item.start() <= column <= item.end()),
                "",
            )

        def _editor_double_click(self, widget, touch):
            if (
                not getattr(touch, "is_double_tap", False)
                or not widget.collide_point(*touch.pos)
            ):
                return False
            local_x, local_y = widget.to_widget(*touch.pos)
            try:
                column, row = widget.get_cursor_from_xy(local_x, local_y)
            except (AttributeError, ValueError):
                return False
            term = self._editor_term_at(column, row)
            if term:
                self._open_dictionary_peek(term)
                return True
            return False

        def _open_dictionary_peek(self, term):
            """Show dictionary evidence without removing the learner from the IDE."""

            try:
                entries = tuple(controller.glossary(term, limit=5))
            except Exception as exc:
                self.status.text = f"Dicionário indisponível: {exc}"
                return
            content = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(7))
            scroll, column = scroll_column()
            if not entries:
                column.add_widget(text(
                    f"Não existe ainda uma definição local para “{term}”.",
                    muted=True,
                ))
            for entry in entries:
                card = Card()
                card.add_widget(text(entry.get("term", term), size=18, bold=True, fixed=30))
                signature = entry.get("signature", "")
                if signature:
                    card.add_widget(CodeInput(
                        text=signature, readonly=True, size_hint_y=None, height=dp(52),
                        background_color=colors["card_alt"], foreground_color=colors["text"],
                    ))
                card.add_widget(text(entry.get("definition", ""), size=14))
                examples = entry.get("examples") or (
                    (entry.get("example"),) if entry.get("example") else ()
                )
                for example in tuple(examples)[:3]:
                    example_text = (
                        example.get("example", "") if isinstance(example, dict) else str(example)
                    )
                    explanation = (
                        example.get("explanation", "") if isinstance(example, dict) else ""
                    )
                    context = example.get("context", "") if isinstance(example, dict) else ""
                    difficulty = example.get("difficulty", "") if isinstance(example, dict) else ""
                    card.add_widget(CodeInput(
                        text=example_text, readonly=True, size_hint_y=None,
                        height=dp(min(120, max(48, 32 + example_text.count("\n") * 20))),
                        background_color=colors["card_alt"], foreground_color=colors["text"],
                    ))
                    if explanation or context:
                        detail = " · ".join(part for part in (difficulty, context) if part)
                        card.add_widget(text(
                            (f"{detail}\n" if detail else "") + explanation,
                            muted=True, fixed=42 if explanation else 28,
                        ))
                related = tuple(entry.get("related_terms") or ())
                if related:
                    card.add_widget(text(
                        "Relacionados · " + ", ".join(str(item) for item in related[:8]),
                        muted=True, fixed=30,
                    ))
                references = tuple(entry.get("references") or entry.get("sources") or ())
                for reference in references[:3]:
                    label, target = (
                        reference if isinstance(reference, (tuple, list)) and len(reference) >= 2
                        else (str(reference), "")
                    )
                    if target:
                        source_button = action(
                            str(label)[:44],
                            lambda _button, url=str(target): self._open_dictionary_source(url),
                        )
                        source_button.height = dp(38)
                        card.add_widget(source_button)
                source_count = len(references)
                card.add_widget(text(
                    f"{source_count} referência(s) local(is)" if source_count else
                    "Definição local curada", muted=True, fixed=26,
                ))
                column.add_widget(card)
            content.add_widget(scroll)
            close = action("Fechar e continuar no IDE", lambda *_: popup.dismiss())
            content.add_widget(close)
            popup = Popup(
                title=f"Dicionário rápido · {term}", content=content,
                size_hint=(None, None), width=dp(min(420, max(340, Window.width * .36))),
                height=dp(min(400, max(280, Window.height * .46))), auto_dismiss=True,
                background_color=(1, 1, 1, .92),
            )
            self.dictionary_popup = popup
            popup.open()

        @staticmethod
        def _open_dictionary_source(target):
            if target.startswith("https://"):
                webbrowser.open(target)
            elif target.startswith("aprendix-library://"):
                from aprendix.application.local_library import resolve_library_uri

                path = resolve_library_uri(target)
                if path is not None:
                    webbrowser.open(path.as_uri())

        def _key_down(self, _window, key, _scancode, _codepoint, modifiers):
            if self.manager is not None and self.manager.current != self.name:
                return False
            modifiers = set(modifiers)
            control = "ctrl" in modifiers
            shift = "shift" in modifiers
            alt = "alt" in modifiers
            command_id = None
            if self.find_bar.height > 0 and self.find_query.focus and key in (13, 271):
                self._find_next(reverse=shift)
                return True
            if self.editor.focus:
                if control and key in (13, 271):
                    command_id = "correct" if shift else "run"
                elif key == 286:  # F5
                    command_id = "run"
                elif key == 287:  # F6
                    command_id = "debug"
                elif control and key in (83, 115):
                    command_id = "save"
                elif control and key in (70, 102):
                    command_id = "find"
                elif control and key in (72, 104):
                    command_id = "replace"
                elif shift and alt and key in (70, 102):
                    command_id = "format"
                elif control and shift and key in (67, 99):
                    command_id = "copy"
                elif control and key in (43, 61, 270):
                    command_id = "zoom_in"
                elif control and key in (45, 269):
                    command_id = "zoom_out"
                elif control and key in (66, 98):
                    command_id = "toggle_brief"
                elif control and key in (74, 106):
                    command_id = "toggle_panel"
                elif control and key in (73, 105):
                    command_id = "tutor"
            if command_id:
                self._execute_ide_command(command_id)
                return True
            if key == 27 and self.find_bar.height > 0:
                self._close_find()
                return True
            if key != 282 or not self.editor.focus:  # F1
                return False
            term = self._editor_term_at(*self.editor.cursor)
            if term:
                self._open_dictionary_peek(term)
                return True
            return False

        def run_code(self, _button):
            if (
                (self.workspace_mode == "exercise" and not self.selected)
                or not self.editor.text.strip()
            ):
                self.status.text = "Escreve código antes de executar."
                return
            self.status.text = "A executar no subprocesso isolado…"
            self._set_execution_busy(True)
            threading.Thread(target=self._run_worker, daemon=True).start()

        def _run_worker(self):
            try:
                result = controller.run_code(self.editor.text)
                Clock.schedule_once(lambda _dt: self._show_run(result), 0)
            except Exception as exc:
                Clock.schedule_once(lambda _dt, message=str(exc): self._show_error(message), 0)

        def _show_run(self, result):
            from aprendix.application.editor_support import explain_runtime_error

            self._set_execution_busy(False)
            self.status.text = f"Execução: {result.status} · {result.duration_ms} ms"
            if result.stdout:
                rendered = result.stdout
            elif result.error_type or result.error_message:
                rendered = explain_runtime_error(
                    result.error_type, result.error_message
                )
            else:
                rendered = "Sem output."
            self._set_panel_text("Output", rendered, activate=True)

        def evaluate(self, _button):
            if not self.editor.text.strip():
                self.status.text = "Escreve código antes de corrigir."
                return
            if self.workspace_mode == "project":
                if self._active_project_id is None:
                    self.status.text = "Guarda primeiro o projeto local."
                    return
                self.save_project(None)
                self.status.text = "A avaliar o projeto pela rubrica local…"
                self._set_execution_busy(True)
                threading.Thread(target=self._evaluate_project_worker, daemon=True).start()
                return
            if not self.selected:
                self.status.text = "Seleciona um exercício antes de corrigir."
                return
            elapsed = max(0, round((time.monotonic() - self.started) * 1000))
            telemetry = EditTelemetry(self.typed, self.pasted, self.deleted)
            self.status.text = "A corrigir e persistir localmente…"
            self._set_execution_busy(True)
            threading.Thread(target=self._evaluate_worker, args=(elapsed, telemetry), daemon=True).start()

        def _evaluate_project_worker(self):
            try:
                result = controller.evaluate_project(self._active_project_id)
                Clock.schedule_once(lambda _dt: self._show_project_evaluation(result), 0)
            except Exception as exc:
                Clock.schedule_once(
                    lambda _dt, message=str(exc): self._show_error(message), 0,
                )

        def _show_project_evaluation(self, result):
            self._set_execution_busy(False)
            rubric = "\n".join(
                f"{name.title()}: {score:.0%}"
                for name, score in result.rubric_scores.items()
            )
            findings = "\n".join(f"- {item}" for item in result.findings) or (
                "- Sem problemas estruturais detetados."
            )
            access = getattr(result, "access", None)
            credit_awarded = bool(getattr(result, "credit_awarded", result.passed))
            reason = getattr(getattr(access, "reason_code", ""), "value", "")
            missing = tuple(getattr(access, "missing_prerequisite_ids", ()) or ())
            eligibility_note = (
                "Crédito curricular atribuído ao capstone correto."
                if credit_awarded else
                "Avaliação guardada sem crédito curricular"
                + (f" · {reason}" if reason else "")
                + (" · dependências: " + ", ".join(missing) if missing else "")
            )
            rendered = (
                f"Projeto {'aprovado' if result.passed else 'a rever'} · {result.score:.0%}\n\n"
                f"Rubrica\n{rubric}\n\nObservações\n{findings}"
            )
            if eligibility_note:
                rendered += f"\n\nPercurso\n{eligibility_note}"
            self.status.text = (
                "Projeto aprovado e creditado" if result.passed and credit_awarded else
                "Projeto aprovado em exploração · sem crédito" if result.passed else
                "Projeto a rever"
            )
            self._set_panel_text("Testes", rendered, activate=True)

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
                    hint_count=self.hints_used,
                    theory_title=str((self._current_journey_item() or {}).get("theory_title", "")),
                    theory_example=str((self._current_journey_item() or {}).get("theory_example", "")),
                    transfer_context=self.transfer_context,
                )
                Clock.schedule_once(lambda _dt: self._show_evaluation(receipt), 0)
            except Exception as exc:
                Clock.schedule_once(lambda _dt, message=str(exc): self._show_error(message), 0)

        def _show_evaluation(self, receipt):
            self._set_execution_busy(False)
            self._last_evaluation_receipt = receipt
            self.solution_button.disabled = not bool(
                getattr(receipt, "reference_available", False)
            )
            self.execution_button.disabled = not bool(
                tuple(getattr(receipt, "reference_trace", ()) or ())
                or tuple(getattr(receipt, "reference_expected_output", ()) or ())
            )
            credit_awarded = bool(getattr(receipt, "credit_awarded", receipt.passed))
            self.status.text = (
                "Aprovado e creditado" if receipt.passed and credit_awarded else
                "Aprovado em exploração · sem crédito" if receipt.passed else
                "Ainda não aprovado"
            )
            lines = list(receipt.feedback)
            lines.insert(0, f"Tentativa {receipt.attempt_number} · score {receipt.score:.0%}")
            if receipt.passed and not credit_awarded:
                access = getattr(receipt, "access", None)
                missing = tuple(getattr(access, "missing_prerequisite_ids", ()) or ())
                reason = getattr(getattr(access, "reason_code", ""), "value", "")
                lines.insert(1, (
                    "Exploração guardada sem XP, milestone ou progresso curricular. "
                    f"Motivo: {reason or 'pré-requisitos incompletos'}."
                    + (" Dependências: " + ", ".join(missing) if missing else "")
                ))
            if receipt.diagnosis_title:
                lines.extend((
                    "", f"Diagnóstico · {receipt.diagnosis_title}",
                    receipt.diagnosis, receipt.improvement,
                ))
            if receipt.milestone:
                lines.append(f"Milestone {receipt.milestone.rank_to.value}: {receipt.milestone.completed}/{receipt.milestone.required}")
            rendered = "\n".join(lines) or f"Score: {receipt.score:.0%}"
            self._set_panel_text("Testes", rendered, activate=True)
            self.learning_session_state = controller.learning_session(self.selected.id)
            if not receipt.passed and receipt.assistance_title:
                help_text = "Remediação focada\n\n"
                if receipt.prerequisite_terms:
                    help_text += "Pré-requisitos: " + ", ".join(receipt.prerequisite_terms) + "\n\n"
                help_text += "\n".join(
                    f"{index}. {item}" for index, item in enumerate(
                        receipt.remediation_actions, 1
                    )
                )
                if receipt.mini_exercise:
                    help_text += "\n\n" + receipt.mini_exercise
                help_text += "\n\n" + receipt.assistance_title + "\n\n"
                help_text += "\n".join(
                    f"{index}. {item}" for index, item in enumerate(receipt.assistance, 1)
                )
                if receipt.worked_example:
                    help_text += "\n\n" + receipt.worked_example
                if receipt.reference_available:
                    help_text += (
                        "\n\nSolução de referência validada (treino)\n"
                        + receipt.reference_solution
                        + "\n\nExplicação estrutural\n"
                        + receipt.reference_explanation
                        + "\n\nValidação: "
                        + receipt.reference_validation_hash[:12]
                    )
                if receipt.next_action:
                    help_text += "\n\nPróximo passo\n" + receipt.next_action
                help_text += "\n\nUsa Teoria no topo do enunciado para rever a explicação."
                self._set_panel_text("Tutor", help_text)
                self.hints_used += 1
            if receipt.passed and self.catalogue:
                item = self._current_journey_item() or {}
                if credit_awarded and item.get("theory_unit_id"):
                    try:
                        controller.complete_unit(item["theory_unit_id"])
                    except ValueError:
                        pass
                refreshed = list(controller.course_practice(self.course_slug))
                if refreshed:
                    self.course_items = refreshed
                self.learning_note.text = self.learning_session_state.reflection
                self.learning_note.hint_text = (
                    "Reflexão opcional: o que aprendeste e que erro evitarás? Depois usa Seguinte."
                )
                self.status.text = (
                    "Aprovado e creditado · regista uma reflexão ou seleciona Seguinte."
                    if credit_awarded else
                    "Aprovado em exploração; repete depois de cumprires os pré-requisitos para obter crédito."
                )

        def _next_exercise(self, *_args, transition_message=""):
            if not self.selected or not self.course_items:
                return
            self._persist_learning_note()
            if self.learning_session_state.phase.value == "reflection":
                self.learning_session_state = controller.update_learning_session(
                    self.selected.id, phase="completed",
                    reflection=self.learning_note.text,
                )
            refreshed = list(controller.course_practice(self.course_slug))
            if refreshed:
                self.course_items = refreshed
            index = next(
                (position for position, item in enumerate(self.course_items)
                 if item["exercise"].id == self.selected.id), -1,
            )
            if index + 1 >= len(self.course_items):
                self.status.text = "Percurso prático concluído. Podes rever qualquer exercício."
                self._update_journey()
                return
            self._activate_exercise(
                self.course_items[index + 1]["exercise"], transition_message
            )

        def _previous_exercise(self, *_args):
            if not self.selected or not self.course_items:
                return
            self._persist_learning_note()
            if self.learning_session_state.phase.value == "reflection":
                self.learning_session_state = controller.update_learning_session(
                    self.selected.id, phase="completed",
                    reflection=self.learning_note.text,
                )
            index = next(
                (position for position, item in enumerate(self.course_items)
                 if item["exercise"].id == self.selected.id), 0,
            )
            if index > 0:
                self._activate_exercise(self.course_items[index - 1]["exercise"])

        def variation(self, _button):
            if not self.selected:
                return
            if self.brief_view == "assessment" and self.assessment_mode.text == "Avaliação":
                self.status.text = "Variações bloqueadas durante a avaliação."
                return
            try:
                generated = controller.variation(
                    self.selected, proficiency=self._proficiency()
                )
                self.prompt.text = build_exercise_brief(generated).render()
                self._render_brief_document("", "", self.prompt.text)
                Clock.schedule_once(lambda _dt: self._reset_prompt_view(), 0)
                self.editor.text = ""
                self.transfer_context = True
                self._set_panel_text(
                    "Tutor",
                    "Dicas graduais:\n" + "\n".join(f"• {hint.text}" for hint in generated.hints),
                )
                self.status.text = "Variação A2 criada no mesmo nível; editor limpo."
            except Exception as exc:
                self._show_error(str(exc))

        def complete(self, _button):
            if self.brief_view == "assessment" and self.assessment_mode.text == "Avaliação":
                self.status.text = "Autocomplete bloqueado durante a avaliação."
                return
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
            if self.brief_view == "assessment" and self.assessment_mode.text == "Avaliação":
                self.status.text = "CopyKate bloqueado durante a avaliação."
                return
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
            self._set_panel_text("Tutor", "\n\n".join(
                f"{index}. {item.strategy}: {item.justification}\nAlterações AST: {len(item.ast_changes)}\n{item.source_code[:700]}"
                for index, item in enumerate(response.alternatives, start=1)
            ), activate=True)

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
            self.workspace_mode = "project"
            self.selected = None
            self.learning_session_state = None
            entry = next(
                (item for item in controller.portfolio_entries()
                 if str(item.project_id) == str(project.id)),
                None,
            )
            self._active_project_template_id = entry.template_id if entry else ""
            template = next(
                (item for item in controller.project_templates()
                 if entry and item.id == entry.template_id),
                None,
            )
            self.editor.text = project.source_code
            self._set_journey_title(f"Projeto · {project.name}")
            self.journey_meta.text = (
                "Portefólio guiado · a avaliação usa exclusivamente este projeto"
            )
            self.journey_progress.value = float(entry.score or 0) if entry else 0
            self.previous_exercise_button.disabled = True
            self.next_exercise_button.disabled = True
            self.course_selector.text = "Projeto local"
            self.course_selector.disabled = True
            self.file_label.text = project.relative_path
            if template is None:
                self.prompt.text = (
                    f"Projeto local\n\nObjetivo\nDesenvolve e testa {project.name}.\n\n"
                    "Usa Guardar para persistir e Corrigir para aplicar a rubrica local."
                )
            else:
                self.prompt.text = (
                    f"Contextualização\n{template.brief}\n\n"
                    "Requisitos\n" + "\n".join(
                        f"- {item}" for item in template.requirements
                    ) + "\n\nEtapas sugeridas\n" + "\n".join(
                        f"{index}. {item}" for index, item in enumerate(template.milestones, 1)
                    ) + "\n\nCritérios de avaliação\n" + "\n".join(
                        f"- {item}" for item in template.rubric
                    )
                )
            self._render_brief_document(
                "project", self._active_project_template_id, self.prompt.text,
            )
            self.brief_view = "project"
            self._update_brief_toggle()
            self.theory_button.disabled = True
            self.practice_button.disabled = True
            self.assessment_button.disabled = True
            self._set_workspace_layout("practice")
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
            self._set_execution_busy(False)
            self.status.text = "Operação indisponível."
            self._set_panel_text("Output", message, activate=True)

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
                card_formulae = (
                    (item.formula_latex,)
                    if item.formula_latex
                    else extract_latex_expressions(body)
                )
                card.add_widget(text(
                    strip_latex_markup(body) if card_formulae else body, size=15,
                ))
                for latex in card_formulae:
                    card.add_widget(FormulaView(
                        latex=latex,
                        spoken=(
                            item.formula_spoken
                            or f"Fórmula associada a {item.title}"
                        ),
                        variables=item.formula_variables,
                        compact=True,
                    ))
                if item.formula_worked_example:
                    card.add_widget(text(
                        "Exemplo resolvido · " + item.formula_worked_example,
                        muted=True,
                    ))
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

        def on_enter(self, *_args):
            Window.bind(on_key_down=self._deck_key_down)

        def on_leave(self, *_args):
            Window.unbind(on_key_down=self._deck_key_down)

        def render(self, *_args):
            self.clear_widgets()
            root = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(9))
            areas = tuple(controller.knowledge_areas())
            leaves = tuple(item for item in areas if item.depth > 0)
            filters = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
            filters.add_widget(action(
                "Fechar filtros" if self.filters_visible else "Filtros",
                self.toggle_filters,
            ))
            self._area_names = {item.title: item.id for item in leaves}
            self.area = Spinner(
                text=next((name for name, identity in self._area_names.items() if identity == self.area_id), "Todos os temas"),
                values=("Todos os temas",) + tuple(self._area_names),
            )
            self.area.bind(text=self.apply_area)
            if self.filters_visible:
                filters.add_widget(self.area)
            else:
                selected_area = next(
                    (name for name, identity in self._area_names.items()
                     if identity == self.area_id),
                    "Todos os temas",
                )
                filters.add_widget(text(selected_area, muted=True, fixed=40))
            filters.add_widget(text(
                "PC: esquerda = confuso · direita = útil · cima/baixo = tema · Enter = virar",
                muted=True, fixed=40,
            ))
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
            if not self.flipped and item.code_example:
                body += "\n\nExemplo\n" + item.code_example
            card_formulae = (
                (item.formula_latex,)
                if not self.flipped and item.formula_latex
                else extract_latex_expressions(body) if not self.flipped else ()
            )
            face = Button(
                text=normalize_ui_text(
                    strip_latex_markup(body) if card_formulae else body
                ), halign="left", valign="middle", font_size=dp(20),
                background_normal="", background_color=colors["card"], color=colors["text"],
            )
            face.bind(size=lambda widget, _value: setattr(widget, "text_size", (widget.width - dp(48), widget.height - dp(48))))
            face.bind(on_release=self.flip)
            root.add_widget(face)
            for latex in card_formulae:
                root.add_widget(FormulaView(
                    latex=latex,
                    spoken=(
                        item.formula_spoken
                        or f"Fórmula associada a {item.title}"
                    ),
                    variables=item.formula_variables,
                    compact=True,
                ))
            if not self.flipped and item.formula_worked_example:
                root.add_widget(text(
                    "Exemplo resolvido · " + item.formula_worked_example,
                    muted=True,
                ))
            asset_path = None
            if getattr(item, "asset_id", None) and hasattr(controller, "pedagogical_asset_path"):
                try:
                    asset_path = controller.pedagogical_asset_path(item.asset_id)
                except Exception:
                    asset_path = None
            if asset_path is None and item.image_path and Path(item.image_path).is_file():
                asset_path = item.image_path
            if not self.flipped and asset_path and Path(asset_path).is_file():
                root.add_widget(local_visual(asset_path, height=dp(240)))
                alt_text = getattr(item, "asset_alt_text", "")
                if alt_text:
                    root.add_widget(text(alt_text, muted=True, fixed=32))
            if self.flipped:
                links = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(5))
                for source in self._sources(item)[:4]:
                    links.add_widget(action(
                        source.title[:25],
                        lambda _b, url=source.canonical_url: self._open_card_source(url),
                    ))
                root.add_widget(links)
            arrows = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(7))
            arrows.add_widget(action("<  Confuso", lambda *_: self.navigate(-1, "confusing")))
            arrows.add_widget(action("Virar card", self.flip))
            arrows.add_widget(action("Útil  >", lambda *_: self.navigate(1, "useful")))
            root.add_widget(arrows)
            root.add_widget(text(
                "Clica no card ou pressiona Enter para consultar as referências exatas.",
                muted=True, fixed=32,
            ))
            self.add_widget(root)

        def _sources(self, item):
            exact_on_card = tuple(getattr(item, "sources", ()) or ())
            if exact_on_card:
                return exact_on_card
            if hasattr(controller, "card_sources"):
                try:
                    exact = tuple(controller.card_sources(item.id))
                    if exact:
                        return exact
                except Exception:
                    pass
            # Never infer a reference from the broad area: a card without an
            # explicit link is shown as unsourced and is rejected by the audit.
            return ()

        @staticmethod
        def _open_card_source(target):
            if target.startswith(("https://", "http://")):
                webbrowser.open(target)
            elif target.startswith("aprendix-library://"):
                from aprendix.application.local_library import resolve_library_uri

                path = resolve_library_uri(target)
                if path is not None:
                    webbrowser.open(path.as_uri())

        def reference_text(self, item):
            sources = self._sources(item)
            if not sources:
                return "Referências não disponíveis para este tema."
            return "Referências\n\n" + "\n".join(
                f"• {source.title}"
                + (f" — {', '.join(source.authors)}" if getattr(source, "authors", ()) else "")
                + (f" · {source.locator}" if getattr(source, "locator", "") else "")
                + (f"\n  {source.rationale}" if getattr(source, "rationale", "") else "")
                for source in sources
            )

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
            self.filters_visible = not self.filters_visible
            self.render()

        def _deck_key_down(self, _window, key, _scancode, _codepoint, modifiers):
            if self.manager is None or self.manager.current != self.name or not self.cards:
                return False
            if key == 276:  # esquerda: informação confusa
                self.navigate(-1, "confusing")
            elif key == 275:  # direita: informação útil
                self.navigate(1, "useful")
            elif key == 273:  # cima: tema anterior
                self.step_area(-1)
            elif key == 274:  # baixo: tema seguinte
                self.step_area(1)
            elif key in (13, 271):
                self.flip()
            else:
                return False
            return True

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
                viewable = bool(unit.get("viewable", True))
                credit_eligible = bool(unit.get(
                    "credit_eligible", unit.get("unlocked", False)
                ))
                state = "concluído" if unit["completed"] else (
                    "elegível para crédito" if credit_eligible else "exploração livre"
                )
                card.add_widget(text(
                    f"{unit['chapter_title']} · {unit['kind']} · {state}",
                    muted=True, fixed=28,
                ))
                card.add_widget(text(unit["title"], size=20, bold=True))
                if not credit_eligible:
                    reason_code = str(unit.get("reason_code", "prerequisites_incomplete"))
                    missing = tuple(unit.get("missing_prerequisite_ids", ()) or ())
                    card.add_widget(text(
                        "Podes estudar e experimentar já. A atividade só contará para o "
                        "percurso depois de concluíres as dependências indicadas. "
                        f"Estado: {reason_code}."
                        + (" Dependências: " + ", ".join(missing) if missing else ""),
                        muted=True,
                    ))
                if viewable:
                    card.add_widget(text(unit["body"], size=15))
                    if unit["example"]:
                        card.add_widget(CodeInput(
                            text=unit["example"], readonly=True, size_hint_y=None,
                            height=dp(120), background_color=colors["card"],
                            foreground_color=colors["text"],
                        ))
                if unit["kind"] == "practice" and unit["exercise_id"]:
                    label = (
                        "Realizar no percurso  >" if credit_eligible else
                        "Explorar no IDE · sem crédito por agora  >"
                    )
                    card.add_widget(action(
                        label,
                        lambda _button, exercise_id=unit["exercise_id"]: self._practice(exercise_id),
                    ))
                elif unit["assessment_id"] and unit["kind"] in {"quiz", "hybrid"}:
                    card.add_widget(action(
                        "Responder teste" if credit_eligible else
                        "Explorar teste · sem crédito por agora",
                        lambda _button, item_id=unit["assessment_id"]: self._assessment(item_id),
                    ))
                elif not unit["completed"] and credit_eligible:
                    card.add_widget(action(
                        "Marcar etapa concluída",
                        lambda _button, unit_id=unit["id"]: self._complete(unit_id),
                    ))
                self.column.add_widget(card)

        def _practice(self, exercise_id):
            learning = self.manager.get_screen("learning")
            learning.load_exercise(exercise_id, self._tracks.get(self.track.text))
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
                examples = tuple(entry.get("examples", ()) or ())
                if not examples and entry.get("example"):
                    examples = ({
                        "example": entry["example"], "explanation": "Exemplo essencial",
                        "difficulty": "beginner", "context": "general",
                    },)
                for position, example in enumerate(examples[:5]):
                    source = example.get("example", "") if isinstance(example, dict) else str(example)
                    explanation = example.get("explanation", "") if isinstance(example, dict) else ""
                    difficulty = example.get("difficulty", "") if isinstance(example, dict) else ""
                    context = example.get("context", "") if isinstance(example, dict) else ""
                    if not source:
                        continue
                    card.add_widget(text(
                        f"Exemplo {position + 1} · {difficulty} · {context}".strip(" ·"),
                        muted=True, fixed=26,
                    ))
                    card.add_widget(CodeInput(
                        text=source, readonly=True,
                        size_hint_y=None, height=dp(min(180, max(72, 48 + source.count("\n") * 22))),
                        background_color=colors["card"], foreground_color=colors["text"],
                    ))
                    if explanation:
                        card.add_widget(text(explanation, muted=True, fixed=30))
                if examples:
                    card.add_widget(action(
                        "Experimentar no IDE",
                        lambda _button, code=(examples[0].get("example", "") if isinstance(examples[0], dict) else str(examples[0])): self._try_in_ide(code),
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
                            title[:28],
                            lambda _button, target=url: self._open_reference(target),
                        ))
                    card.add_widget(links)
                self.column.add_widget(card)

        @staticmethod
        def _open_reference(target):
            if target.startswith(("https://", "http://")):
                webbrowser.open(target)
                return
            if target.startswith("aprendix-library://"):
                from aprendix.application.local_library import resolve_library_uri
                path = resolve_library_uri(target)
                if path is not None:
                    webbrowser.open(path.as_uri())

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
            self.analysis_section = "Resumo"
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
            self.analysis_tabs = BoxLayout(
                size_hint_y=None, height=dp(42), spacing=dp(4),
            )
            self.analysis_tab_buttons = {}
            for section in (
                "Resumo", "Problemas", "Símbolos", "Fluxo", "Tipos",
                "Complexidade", "Testes",
            ):
                selector = ToggleButton(
                    text=section, group="snippet-analysis-section",
                    state="down" if section == "Resumo" else "normal",
                    disabled=True, background_normal="",
                    background_color=colors["card_alt"], color=colors["text"],
                    font_name="AprendixSans", font_size=dp(12),
                )
                selector.theme_role = "navigation"
                selector.aprendix_base_font_size = 12
                selector.accessible_name = f"Análise: {section}"
                selector.bind(
                    on_release=lambda _button, name=section: self._select_analysis_section(name)
                )
                self.analysis_tab_buttons[section] = selector
                self.analysis_tabs.add_widget(selector)
            root.add_widget(self.analysis_tabs)
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
            self.result = result
            for selector in self.analysis_tab_buttons.values():
                selector.disabled = False
            self.analysis_section = "Resumo"
            self.analysis_tab_buttons["Resumo"].state = "down"
            self._render_analysis_section()

        def _select_analysis_section(self, section):
            if self.result is None:
                return
            self.analysis_section = section
            self._render_analysis_section()

        @staticmethod
        def _bullet_lines(title, items, *, limit=200):
            values = tuple(normalize_ui_text(str(item)) for item in items if str(item).strip())
            if not values:
                return None
            return title + "\n• " + "\n• ".join(values[:limit])

        def _add_analysis_text(self, card, title, lines, *, muted=True):
            body = self._bullet_lines(title, lines)
            if body:
                card.add_widget(text(body, muted=muted))

        def _render_analysis_section(self):
            result = self.result
            self.column.clear_widgets()
            if result is None:
                return
            section = self.analysis_section
            card = Card()
            card.add_widget(text(
                f"{section} · {result.detected_language} · "
                f"confiança {result.confidence:.0%} · {result.elapsed_ms:.1f} ms",
                bold=True, fixed=38,
            ))
            if section == "Resumo":
                card.add_widget(text(result.summary, size=16))
                if result.action_result:
                    card.add_widget(text(result.action_result, muted=True))
                self._add_analysis_text(card, "Entradas", result.inputs)
                self._add_analysis_text(card, "Saídas", result.outputs)
                self._add_analysis_text(card, "Invariantes", result.invariants)
                self._add_analysis_text(card, "Construções", result.constructs)
                self._add_analysis_text(card, "Conceitos relacionados", result.related_concepts)
                self._add_analysis_text(card, "Linha a linha", result.line_explanations)
                card.add_widget(text(
                    f"{result.node_count} nós AST analisados" +
                    (" · resultado truncado com segurança" if result.analysis_truncated else ""),
                    muted=True, fixed=30,
                ))
                if result.proposed_code:
                    card.add_widget(text("Versão proposta", bold=True, fixed=34))
                    proposed = CodeInput(
                        text=result.proposed_code, readonly=True,
                        size_hint_y=None, height=dp(220), font_name="AprendixMono",
                    )
                    card.add_widget(proposed)
                    card.add_widget(action("Abrir nova versão no IDE", self._open_ide))
            elif section == "Problemas":
                self._add_analysis_text(card, "Problemas detetados", result.problems)
                diagnostics = []
                for item in result.diagnostics:
                    line = (
                        f"[{item.severity.value.upper()}] L{item.line}:{item.column} "
                        f"{item.code} — {item.message}"
                    )
                    if item.evidence:
                        line += f" | evidência: {item.evidence}"
                    if item.safe_fix:
                        line += f" | correção segura: {item.safe_fix}"
                    diagnostics.append(line)
                self._add_analysis_text(card, "Diagnósticos localizados", diagnostics)
                security = (
                    f"[{item.severity.value.upper()}] L{item.line} {item.code} — "
                    f"{item.message} | evidência: {item.evidence}"
                    for item in result.security_findings
                )
                self._add_analysis_text(card, "Segurança", security)
                self._add_analysis_text(
                    card, "Exceções possíveis", result.possible_exceptions,
                )
            elif section == "Símbolos":
                symbols = (
                    f"L{item.line}:{item.column} {item.kind} {item.name} "
                    f"({item.scope}) · {item.use_count} uso(s)" +
                    (f" · tipo {item.inferred_type}" if item.inferred_type else "")
                    for item in result.symbols
                )
                self._add_analysis_text(card, "Símbolos", symbols)
                functions = (
                    f"L{item.line}–{item.end_line} {item.qualified_name}{item.signature} "
                    f"· chama: {', '.join(item.calls) or '—'} "
                    f"· pode lançar: {', '.join(item.raises) or '—'}"
                    for item in result.functions
                )
                self._add_analysis_text(card, "Funções", functions)
                classes = (
                    f"L{item.line}–{item.end_line} class {item.qualified_name} "
                    f"· bases: {', '.join(item.bases) or '—'} "
                    f"· métodos: {', '.join(item.methods) or '—'} "
                    f"· atributos: {', '.join(item.attributes) or '—'}"
                    for item in result.classes
                )
                self._add_analysis_text(card, "Classes", classes)
                self._add_analysis_text(card, "Imports", result.imports)
            elif section == "Fluxo":
                legacy_flow = (f"{source} → {target}" for source, target in result.control_flow)
                self._add_analysis_text(card, "Fluxo resumido", legacy_flow)
                blocks = (
                    f"{item.id} · L{item.line} · {item.scope}/{item.kind}: "
                    f"{item.label} → {', '.join(item.successors) or 'fim'}"
                    for item in result.cfg_blocks
                )
                self._add_analysis_text(card, "Blocos de controlo", blocks)
                edges = (
                    f"L{item.line} {item.caller} → {item.callee}" +
                    (" (chamada dinâmica)" if item.dynamic else "")
                    for item in result.call_edges
                )
                self._add_analysis_text(card, "Grafo de chamadas", edges)
            elif section == "Tipos":
                facts = (
                    f"L{item.line} {item.symbol}: {item.inferred_type} "
                    f"({item.confidence:.0%}) · {item.evidence}"
                    for item in result.type_facts
                )
                self._add_analysis_text(card, "Tipos inferidos", facts, muted=False)
            elif section == "Complexidade":
                card.add_widget(text(
                    f"Estimativa global: tempo {result.complexity_time} · "
                    f"espaço {result.complexity_space}",
                    size=16, bold=True, fixed=38,
                ))
                findings = (
                    f"{item.scope}: ciclomática {item.cyclomatic} · "
                    f"tempo {item.time} · espaço {item.space} — {item.rationale}"
                    for item in result.complexity_findings
                )
                self._add_analysis_text(card, "Por âmbito", findings)
            elif section == "Testes":
                self._add_analysis_text(card, "Testes sugeridos", result.suggested_tests)
                for item in result.test_suggestions:
                    card.add_widget(text(
                        f"{item.name} · {item.category}\n{item.rationale}",
                        bold=True,
                    ))
                    if item.code:
                        card.add_widget(CodeInput(
                            text=item.code, readonly=True, size_hint_y=None,
                            height=dp(150), font_name="AprendixMono",
                        ))
            if len(card.children) == 1:
                card.add_widget(text(
                    "Não foram encontrados elementos nesta secção.", muted=True,
                ))
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
                detail = GridLayout(
                    cols=3 if Window.width >= dp(1100) else 1,
                    spacing=dp(8), size_hint_y=None,
                )
                detail.bind(minimum_height=detail.setter("height"))
                for heading, items in (
                    ("Entregáveis e requisitos", template.requirements),
                    ("Milestones", template.milestones),
                    ("Critérios e rubrica", template.rubric),
                ):
                    section = Card()
                    section.add_widget(text(heading, size=16, bold=True, fixed=30))
                    section.add_widget(text(
                        "\n".join(f"{index}. {item}" for index, item in enumerate(items, 1)),
                        size=14,
                    ))
                    detail.add_widget(section)
                card.add_widget(detail)
                card.add_widget(text(
                    f"{template.level} · {len(template.milestones)} milestones · "
                    + ("briefing profissional" if template.professional_briefing else "briefing guiado"),
                    muted=True, fixed=30,
                ))
                actions = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
                actions.add_widget(action(
                    "Usar esqueleto guiado", lambda _b, tid=template.id: self.start(tid, "guided"),
                ))
                actions.add_widget(action(
                    "Começar vazio", lambda _b, tid=template.id: self.start(tid, "autonomous", blank=True),
                ))
                card.add_widget(actions); column.add_widget(card)
            root.add_widget(scroll); self.add_widget(root)

        def start(self, template_id, mode, blank=False):
            project = controller.start_guided_project(template_id, mode=mode)
            if blank:
                project = controller.save_project(
                    project.name, "", project.id, relative_path=project.relative_path,
                )
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
            answer_body = BoxLayout(
                orientation="vertical", size_hint_y=None, spacing=dp(6),
            )
            answer_body.bind(minimum_height=answer_body.setter("height"))
            render_legacy_document(answer_body, answer_text, compact=True)
            answer.add_widget(answer_body)
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
                excerpt_formulae = extract_latex_expressions(excerpt)
                excerpt_body = BoxLayout(
                    orientation="vertical", size_hint_y=None, spacing=dp(5),
                )
                excerpt_body.bind(minimum_height=excerpt_body.setter("height"))
                render_legacy_document(
                    excerpt_body,
                    strip_latex_markup(excerpt) if excerpt_formulae else excerpt,
                    compact=True,
                )
                for latex in excerpt_formulae:
                    excerpt_body.add_widget(FormulaView(
                        latex=latex, spoken=f"Fórmula encontrada em {hit.title}",
                        compact=True,
                    ))
                card.add_widget(excerpt_body)
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
            top.add_widget(action("Voltar à pesquisa", lambda *_: setattr(self.manager, "current", "search")))
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
                    formulae = extract_latex_expressions(body)
                    source_card.add_widget(TextInput(
                        text=normalize_ui_text(
                            strip_latex_markup(body) if formulae else body
                        ), readonly=True, font_size=dp(14),
                        background_color=colors["card"], foreground_color=colors["text"],
                        size_hint_y=None, height=dp(min(620, max(260, 80 + len(body) // 3))),
                    ))
                    for latex in formulae:
                        source_card.add_widget(FormulaView(
                            latex=latex, spoken=f"Fórmula em {detail.title}", compact=True,
                        ))
                    grid.add_widget(source_card)
                self.column.add_widget(grid)
                return
            detail = self.detail
            self.column.add_widget(text(detail.title, size=26, bold=True))
            labels = {"summary": "Resumo essencial", "simplified": "Versão simplificada com rigor", "original": "Conteúdo normal"}
            body = {"summary": detail.summary, "simplified": detail.simplified, "original": detail.original_content}[mode]
            self.column.add_widget(text(labels[mode], size=20, bold=True, fixed=36))
            block_attribute = {
                "summary": "summary_blocks", "simplified": "simplified_blocks",
                "original": "original_blocks",
            }[mode]
            blocks = tuple(getattr(detail, block_attribute, ()) or ())
            reading_card = Card()
            reading_scroll = ScrollView(
                do_scroll_x=False, do_scroll_y=True, size_hint_y=None,
                height=dp(min(720, max(260, Window.height * .68))),
                scroll_type=["bars", "content"], bar_width=dp(10),
            )
            reading_column = BoxLayout(
                orientation="vertical", size_hint_y=None, padding=dp(8), spacing=dp(8),
            )
            reading_column.bind(minimum_height=reading_column.setter("height"))
            if blocks:
                render_pedagogical_blocks(reading_column, blocks)
            else:
                render_legacy_document(reading_column, body)
            reading_scroll.add_widget(reading_column)
            reading_card.add_widget(reading_scroll)
            reading_card.bind(on_touch_down=self._concept_double_click)
            self.column.add_widget(reading_card)
            if mode == "original":
                for asset in detail.visual_assets:
                    if Path(asset).is_file():
                        visual = Card()
                        visual.add_widget(text("Visualização extraída da fonte", muted=True, fixed=30))
                        visual.add_widget(local_visual(asset, height=dp(360)))
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
            # Rich blocks do not expose a stable text cursor. Use the current
            # selection when a TextInput originated the event; otherwise open a
            # compact concept chooser drawn from the document itself.
            match = None
            if isinstance(widget, TextInput):
                local_x, local_y = widget.to_widget(*touch.pos)
                try:
                    column, row = widget.get_cursor_from_xy(local_x, local_y)
                    line = widget.text.splitlines()[row]
                    match = next((item for item in re.finditer(r"[A-Za-zÀ-ÿ_][A-Za-zÀ-ÿ0-9_-]*", line)
                                  if item.start() <= column <= item.end()), None)
                except (IndexError, AttributeError):
                    match = None
            if match is not None:
                reference = self.manager.get_screen("reference")
                reference.query.text = match.group(0)
                reference.search()
                self.manager.current = "reference"
                return True
            concepts = tuple(getattr(self.detail, "concepts", ()) or ())
            if concepts:
                self._concept_picker(concepts)
                return True
            return False

        def _concept_picker(self, concepts):
            body = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(6))
            popup = Popup(
                title="Tutor de conceitos", content=body,
                size_hint=(None, None), width=dp(min(520, Window.width * .44)),
                height=dp(min(480, Window.height * .55)),
            )
            for concept in concepts[:8]:
                button = action(concept.term, lambda _button, term=concept.term: open_term(term))
                body.add_widget(button)

            def open_term(term):
                popup.dismiss()
                reference = self.manager.get_screen("reference")
                reference.query.text = term
                reference.search()
                self.manager.current = "reference"

            popup.open()

        def _open_source(self, *_args):
            if self.detail is None:
                return
            target = self.detail.canonical_url or self.detail.source
            if target.startswith("aprendix-library://"):
                from aprendix.application.local_library import resolve_library_uri
                path = resolve_library_uri(target)
                if path is None:
                    self.status.text = (
                        "PDF local não encontrado. Confirma a biblioteca aprovada ou configura "
                        "APRENDIX_LIBRARY_ESTUDO_FERIAS/APRENDIX_LIBRARY_EBOOKS_PAPERS."
                    )
                    return
                webbrowser.open(path.as_uri())
                self.status.text = "PDF bibliográfico aberto na aplicação predefinida."
                return
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
            self._previewed_remote = ""
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
            remote_buttons.add_widget(action("Antever seleção", lambda *_: self._preview_remote()))
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
            self._previewed_remote = ""
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
            if self._previewed_remote != f"{registry}|{identity}":
                self.status.text = "Antes de instalar, usa ‘Antever seleção’ e confirma fontes, tamanho e rollback."
                return
            self._background(lambda: controller.install_remote_content_pack(identity, registry))
            self._previewed_remote = ""

        def _preview_remote(self):
            registry, identity = self.registry_url.text.strip(), self.remote_identity.text.strip()
            if not registry or not identity:
                self.status.text = "Indica o registo e a seleção pack-id@versão."
                return
            self.status.text = "A validar a antevisão sem descarregar…"
            def worker():
                try:
                    result = controller.preview_remote_content_pack(identity, registry)
                    sources = ", ".join(result["sources"]) or "não declaradas"
                    tracks = ", ".join(result["affected_tracks"]) or "transversal"
                    previous = result["replaces"] or "nenhuma"
                    message = (
                        f"{result['title']} · {result['total_bytes'] / 1048576:.1f} MB\n"
                        f"{result['summary']}\nFontes: {sources}\nPercursos: {tracks}\n"
                        f"Substitui: {previous} · rollback: "
                        f"{'disponível' if result['rollback_available'] else 'não aplicável'}\n"
                        "Privacidade: nenhum dado do utilizador é enviado. "
                        "Se concordares, usa agora ‘Instalar seleção’."
                    )
                    Clock.schedule_once(
                        lambda _dt: self._preview_done(registry, identity, message), 0,
                    )
                except Exception as exc:
                    Clock.schedule_once(
                        lambda _dt, error=str(exc): self._remote_done(
                            f"Antevisão recusada sem alterar conteúdo: {error}"
                        ), 0,
                    )
            threading.Thread(target=worker, daemon=True).start()

        def _preview_done(self, registry, identity, message):
            self._previewed_remote = f"{registry}|{identity}"
            self.remote_list.text = message
            self.status.text = "Antevisão validada; a instalação continua a exigir ação explícita."

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
            self.collapse_button = IconAction(
                "book", "Menu", lambda *_: self.set_sidebar_collapsed(
                    not self.sidebar_collapsed
                ), show_label=True,
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
                (Route.DASHBOARD, "Painel", "dashboard"),
                (Route.CURRICULUM, "Curso", "course"),
                (Route.IDE, "IDE", "ide"),
                (Route.SEARCH, "Pesquisa", "search"),
                (Route.CARDS, "Cards", "cards"),
                (Route.DICTIONARY, "Dicionário", "dictionary"),
                (Route.TUTOR, "Tutor", "tutor"),
                (Route.PROJECTS, "Projetos", "projects"),
                (Route.ANALYZER, "Analisar", "analyzer"),
                (Route.GAMES, "Games", "games"),
                (Route.DATA, "Dados", "data"),
            )
            for route, title, icon in navigation:
                button = IconAction(
                    icon, title,
                    lambda _button, target=route: self.go(target),
                    show_label=True,
                )
                button.route = route
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
            smaller = Button(text="A-")
            smaller.bind(on_release=lambda *_: self.change_font(-0.1))
            larger = Button(text="A+")
            larger.bind(on_release=lambda *_: self.change_font(0.1))
            font_row.add_widget(smaller)
            font_row.add_widget(larger)
            self.sidebar.add_widget(font_row)
            theme_title = {
                "dark": "Tema: escuro", "light": "Tema: claro",
                "contrast": "Alto contraste",
            }[theme_name]
            self.theme_button = Button(
                text=theme_title,
                size_hint_y=None, height=dp(44), background_normal="",
                background_color=colors["accent"], color=colors["accent_text"],
            )
            self.theme_button.theme_role = "accent"
            self.theme_button.full_title = theme_title
            self.theme_button.compact_title = "Tema"
            self.theme_button.accessible_name = theme_title
            self.theme_button.tooltip_text = theme_title
            self.theme_button.bind(
                on_release=lambda button: self.toggle_theme(root, button)
            )
            self.sidebar.add_widget(self.theme_button)

            content = BoxLayout(orientation="vertical")
            topbar = BoxLayout(
                size_hint_y=None, height=dp(52),
                padding=(dp(8), dp(5)), spacing=dp(6),
            )
            back = IconAction(
                "previous", "Voltar", lambda *_: self.go_back(), width=46,
                shortcut="Alt+Esquerda",
            )
            forward = IconAction(
                "next", "Avançar", lambda *_: self.go_forward(), width=46,
                shortcut="Alt+Direita",
            )
            self.page_title = Label(
                text=self._route_titles[initial_route], color=colors["text"],
                bold=True, halign="left",
            )
            self.page_title.bind(
                size=lambda item, _value: setattr(item, "text_size", item.size)
            )
            commands = IconAction(
                "more", "Comandos", lambda *_: self.open_palette(), width=170,
                show_label=True, shortcut="Ctrl+K",
            )
            self.commands_button = commands
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
            self._responsive_sidebar(Window, Window.width)
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
            self.collapse_button.set_label_visible(not self.sidebar_collapsed)
            self.collapse_button.command_title = (
                "Expandir menu" if self.sidebar_collapsed else "Recolher menu"
            )
            self.collapse_button.accessible_name = self.collapse_button.command_title
            self.collapse_button.tooltip_text = self.collapse_button.command_title
            for button in self._nav_buttons:
                button.set_label_visible(not self.sidebar_collapsed)
            self.theme_button.text = (
                self.theme_button.compact_title
                if self.sidebar_collapsed else self.theme_button.full_title
            )
            if persist:
                controller.save_preference(
                    "sidebar_collapsed", "1" if self.sidebar_collapsed else "0"
                )

        def _responsive_sidebar(self, _window, width):
            from aprendix.presentation.responsive import layout_profile

            profile = layout_profile(
                max(1, round(width)), max(1, round(Window.height)), density=max(1.0, dp(1))
            )
            if profile.navigation != "sidebar" and not self.sidebar_collapsed:
                self.set_sidebar_collapsed(True)
            self.commands_button.width = dp(profile.command_width_dp)
            self.commands_button.set_label_visible(not profile.compact_labels)

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

            def select_ide(command_id):
                popup.dismiss()
                learning = self.manager.get_screen(Route.IDE.value)
                learning._execute_ide_command(command_id)

            def refresh(_widget=None, value=""):
                results.clear_widgets()
                in_ide = self.manager.current == Route.IDE.value
                for command in self.palette_index.search(value, limit=3 if in_ide else 7):
                    button = Button(
                        text=f"Abrir: {command.title}", size_hint_y=None, height=dp(46),
                        background_normal="",
                        background_color=colors["card_alt"], color=colors["text"],
                    )
                    button.bind(
                        on_release=lambda _button, route=command.route: select(route)
                    )
                    results.add_widget(button)
                if in_ide:
                    for command in search_ide_commands(value, limit=6):
                        label = command.title
                        if command.shortcut:
                            label += f"    {command.shortcut}"
                        button = Button(
                            text=label, size_hint_y=None, height=dp(46),
                            background_normal="", background_color=colors["card"],
                            color=colors["text"],
                        )
                        button.bind(
                            on_release=lambda _button, identity=command.id: select_ide(identity)
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
            theme_title = {
                "dark": "Tema: escuro", "light": "Tema: claro",
                "contrast": "Alto contraste",
            }[theme_name]
            button.full_title = theme_title
            button.accessible_name = theme_title
            button.tooltip_text = theme_title
            button.text = button.compact_title if self.sidebar_collapsed else theme_title
            # ScreenManager keeps inactive lazy screens outside the currently
            # rendered widget branch.  Walking only ``root`` therefore left a
            # previously opened IDE with its old palette.  Include every
            # instantiated screen and de-duplicate the active branch.
            branches = (root, *self.manager.screens)
            for widget in _walk_theme_widgets(branches):
                if isinstance(widget, Card):
                    widget.refresh_theme()
                elif isinstance(widget, (TrendChart, SkillGraphCanvas)):
                    widget.refresh_theme()
                elif isinstance(widget, (PaneDivider, TerminalDivider)):
                    widget.divider_color.rgba = colors["accent"]
                elif isinstance(widget, (IconAction, IconToggleAction)):
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
                if isinstance(widget, ScrollView):
                    widget.bar_color = colors["accent"]
                    widget.bar_inactive_color = (*colors["muted"][:3], .45)

        def on_stop(self):
            Window.unbind(
                on_key_down=self._key_down, width=self._responsive_sidebar
            )

    AprendixApp().run()
    return 0
