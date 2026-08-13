"""Toolkit-neutral responsive layout policy for desktop and mobile shells."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class LayoutProfile:
    width_dp: float
    height_dp: float
    density: float
    navigation: str
    sidebar_width_dp: int
    command_width_dp: int
    columns: int
    content_width_dp: float
    compact_labels: bool
    passed: bool


@dataclass(frozen=True, slots=True)
class IdeJourneyHeaderProfile:
    """Bounded widths for the dense desktop IDE journey header."""

    compact: bool
    content_width_dp: float
    navigation_width_dp: int
    title_width_dp: int
    pane_width_dp: int
    course_width_dp: int
    occupied_width_dp: int


@dataclass(frozen=True, slots=True)
class BookWorkspaceProfile:
    """Geometry for the two-page IDE and its transversal terminal."""

    mode: str
    available_width_dp: float
    available_height_dp: float
    editor_width_dp: int
    support_width_dp: int
    divider_width_dp: int
    terminal_collapsed_height_dp: int
    terminal_open_height_dp: int
    terminal_ratio: float


def book_workspace_profile(
    width_px: int,
    height_px: int,
    *,
    density: float = 1.0,
    requested_support_width_dp: float = 430.0,
    requested_terminal_ratio: float = 0.28,
) -> BookWorkspaceProfile:
    """Choose book or explicit-tab mode from the actual workspace width.

    ``width_px`` is the learning screen itself, after the application rail has
    taken its share. This avoids the old global 1080-dp threshold and preserves
    both pages whenever the 360/320-dp page minima really fit.
    """

    if width_px <= 0 or height_px <= 0 or not 0.5 <= density <= 4.0:
        raise ValueError("workspace dimensions and density must be positive and bounded")
    width_dp, height_dp = width_px / density, height_px / density
    divider = 9
    editor_minimum, support_minimum = 360, 320
    book_mode = width_dp >= editor_minimum + support_minimum + divider
    terminal_ratio = min(.35, max(.20, float(requested_terminal_ratio)))
    terminal_height = math.floor(height_dp * terminal_ratio)
    if book_mode:
        maximum_support = max(support_minimum, math.floor(width_dp - editor_minimum - divider))
        support = round(min(maximum_support, max(support_minimum, requested_support_width_dp)))
        editor = max(editor_minimum, math.floor(width_dp - support - divider))
        mode = "book"
    else:
        support = max(0, math.floor(width_dp))
        editor = support
        mode = "tabs"
    return BookWorkspaceProfile(
        mode=mode,
        available_width_dp=round(width_dp, 2),
        available_height_dp=round(height_dp, 2),
        editor_width_dp=editor,
        support_width_dp=support,
        divider_width_dp=divider,
        terminal_collapsed_height_dp=38,
        terminal_open_height_dp=terminal_height,
        terminal_ratio=round(terminal_ratio, 3),
    )


def dashboard_tab_width(label: str, *, font_scale: float = 1.0) -> int:
    """Return a readable, non-shrinking width for one dashboard tab.

    The result is intentionally independent from Kivy.  The dashboard places
    these fixed-width tabs in a horizontal viewport, so a narrow window scrolls
    instead of asking labels to paint over neighbouring controls.
    """

    clean_label = label.strip()
    if not clean_label or not 0.85 <= font_scale <= 1.5:
        raise ValueError("label must be non-empty and font_scale must be between 0.85 and 1.5")
    readable_width = max(96.0, 30.0 + len(clean_label) * 7.5)
    return math.ceil(readable_width * font_scale)


def ide_journey_header_profile(
    width_px: int, *, density: float = 1.0,
) -> IdeJourneyHeaderProfile:
    """Budget the desktop IDE header without allowing a zero-width title.

    At compact desktop widths every control receives a fixed, bounded width.
    The title can then be shortened on one line while its complete value stays
    available through accessibility metadata and the tooltip.
    """

    if width_px <= 0 or not 0.5 <= density <= 4.0:
        raise ValueError("viewport and density must be positive and bounded")
    width_dp = width_px / density
    compact = width_dp < 1_080
    sidebar_width = 72 if width_dp < 920 else 196
    content_width = max(0.0, width_dp - sidebar_width - 24)
    navigation_width = 64 if compact else 88
    pane_width = 96 if compact else 0
    course_width = 160 if compact and content_width >= 600 else 132 if compact else 230
    # Five widgets remain in the row even while the pane switch is hidden, so
    # reserve all four inter-widget gaps used by the Kivy BoxLayout.
    spacing_width = 24
    fixed_width = navigation_width * 2 + pane_width + course_width + spacing_width
    title_width = max(0, min(250 if compact else 720, math.floor(content_width - fixed_width)))
    occupied_width = fixed_width + title_width
    return IdeJourneyHeaderProfile(
        compact=compact,
        content_width_dp=round(content_width, 2),
        navigation_width_dp=navigation_width,
        title_width_dp=title_width,
        pane_width_dp=pane_width,
        course_width_dp=course_width,
        occupied_width_dp=occupied_width,
    )


def layout_profile(width_px: int, height_px: int, *, density: float = 1.0) -> LayoutProfile:
    """Return one bounded layout decision without importing Kivy.

    The policy deliberately reasons in density-independent pixels.  It keeps a
    usable content canvas on small Windows windows while the native mobile shell
    uses bottom navigation below 600 dp.
    """

    if width_px <= 0 or height_px <= 0 or not 0.5 <= density <= 4.0:
        raise ValueError("viewport and density must be positive and bounded")
    width_dp, height_dp = width_px / density, height_px / density
    if width_dp < 600:
        navigation, sidebar, command, compact = "bottom", 0, 48, True
    elif width_dp < 920:
        navigation, sidebar, command, compact = "compact-sidebar", 72, 56, True
    else:
        navigation, sidebar, command, compact = "sidebar", 196, 170, False
    content_width = max(0.0, width_dp - sidebar)
    columns = 3 if content_width >= 1_280 else 2 if content_width >= 760 else 1
    minimum_content = 280 if navigation == "bottom" else 520
    passed = content_width >= minimum_content and height_dp >= 480
    return LayoutProfile(
        width_dp=round(width_dp, 2), height_dp=round(height_dp, 2), density=density,
        navigation=navigation, sidebar_width_dp=sidebar,
        command_width_dp=command, columns=columns,
        content_width_dp=round(content_width, 2), compact_labels=compact,
        passed=passed,
    )


RELEASE_VIEWPORTS = (
    (360, 640, 1.0, "android-compact"),
    (412, 915, 1.0, "android-large"),
    (800, 700, 1.0, "windows-compact"),
    (1024, 768, 1.0, "windows-small"),
    (1366, 768, 1.0, "windows-hd"),
    (1920, 1080, 1.0, "windows-fhd"),
    (1708, 960, 1.25, "windows-125-percent"),
    (2048, 1152, 1.5, "windows-150-percent"),
    (2389, 1344, 1.75, "windows-175-percent"),
)


def responsive_matrix() -> dict[str, object]:
    profiles = []
    for width, height, density, name in RELEASE_VIEWPORTS:
        profile = layout_profile(width, height, density=density)
        profiles.append({"name": name, **asdict(profile)})
    return {
        "profiles": profiles,
        "passed": all(item["passed"] for item in profiles),
        "minimum_desktop_content_dp": 520,
        "minimum_mobile_content_dp": 280,
    }
