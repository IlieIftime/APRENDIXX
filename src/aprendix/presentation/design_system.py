"""Shared visual tokens without importing a desktop or mobile GUI toolkit."""

from __future__ import annotations

from dataclasses import dataclass


Rgba = tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class ThemeTokens:
    background: Rgba
    surface: Rgba
    surface_alt: Rgba
    accent: Rgba
    accent_text: Rgba
    accent_hover: Rgba
    text: Rgba
    muted: Rgba
    border: Rgba
    success: Rgba
    warning: Rgba
    danger: Rgba
    focus: Rgba


THEMES: dict[str, ThemeTokens] = {
    "dark": ThemeTokens(
        background=(0.025, 0.04, 0.075, 1), surface=(0.065, 0.095, 0.15, 1),
        surface_alt=(0.09, 0.125, 0.19, 1), accent=(0.43, 0.32, 0.90, 1),
        accent_text=(1, 1, 1, 1),
        accent_hover=(0.51, 0.42, 0.96, 1), text=(0.94, 0.97, 1, 1),
        muted=(0.66, 0.74, 0.85, 1), border=(0.20, 0.27, 0.38, 1),
        success=(0.20, 0.75, 0.52, 1), warning=(0.96, 0.70, 0.22, 1),
        danger=(0.94, 0.32, 0.38, 1), focus=(0.36, 0.82, 1, 1),
    ),
    "light": ThemeTokens(
        background=(0.94, 0.96, 0.985, 1), surface=(1, 1, 1, 1),
        surface_alt=(0.90, 0.93, 0.97, 1), accent=(0.28, 0.20, 0.72, 1),
        accent_text=(1, 1, 1, 1),
        accent_hover=(0.35, 0.26, 0.82, 1), text=(0.07, 0.09, 0.14, 1),
        muted=(0.31, 0.36, 0.45, 1), border=(0.70, 0.75, 0.83, 1),
        success=(0.08, 0.52, 0.31, 1), warning=(0.72, 0.43, 0.03, 1),
        danger=(0.75, 0.12, 0.18, 1), focus=(0.05, 0.39, 0.78, 1),
    ),
    "contrast": ThemeTokens(
        background=(0, 0, 0, 1), surface=(0.04, 0.04, 0.04, 1),
        surface_alt=(0.10, 0.10, 0.10, 1), accent=(1, 0.82, 0, 1),
        accent_text=(0, 0, 0, 1),
        accent_hover=(1, 0.92, 0.35, 1), text=(1, 1, 1, 1),
        muted=(0.88, 0.88, 0.88, 1), border=(1, 1, 1, 1),
        success=(0.2, 1, 0.5, 1), warning=(1, 0.82, 0, 1),
        danger=(1, 0.25, 0.25, 1), focus=(0, 0.92, 1, 1),
    ),
}


def palette(name: str) -> dict[str, Rgba]:
    tokens = THEMES.get(name, THEMES["dark"])
    return {
        "bg": tokens.background, "card": tokens.surface,
        "card_alt": tokens.surface_alt, "accent": tokens.accent,
        "accent_text": tokens.accent_text,
        "accent_hover": tokens.accent_hover, "text": tokens.text,
        "muted": tokens.muted, "border": tokens.border,
        "success": tokens.success, "warning": tokens.warning,
        "danger": tokens.danger, "focus": tokens.focus,
    }


def _linear_channel(value: float) -> float:
    """Convert an sRGB channel to linear light for WCAG contrast."""

    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def relative_luminance(color: Rgba) -> float:
    red, green, blue = (_linear_channel(channel) for channel in color[:3])
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(first: Rgba, second: Rgba) -> float:
    lighter, darker = sorted((relative_luminance(first), relative_luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


DPI_SCALES = (1.0, 1.25, 1.5, 1.75, 2.0)
MINIMUM_TOUCH_TARGET_DP = 44


def accessibility_matrix() -> dict[str, object]:
    """Return deterministic theme and DPI checks shared by release tooling."""

    themes: dict[str, dict[str, float | bool]] = {}
    for name in THEMES:
        colors = palette(name)
        ratios = {
            "body_background": contrast_ratio(colors["text"], colors["bg"]),
            "body_surface": contrast_ratio(colors["text"], colors["card"]),
            "muted_background": contrast_ratio(colors["muted"], colors["bg"]),
            "accent_button": contrast_ratio(colors["accent_text"], colors["accent"]),
            "focus_background": contrast_ratio(colors["focus"], colors["bg"]),
        }
        themes[name] = {
            **{key: round(value, 3) for key, value in ratios.items()},
            "passed": all(
                value >= (3.0 if key == "focus_background" else 4.5)
                for key, value in ratios.items()
            ),
        }
    dpi = [
        {
            "scale_percent": round(scale * 100),
            "minimum_touch_target_px": round(MINIMUM_TOUCH_TARGET_DP * scale),
            "desktop_action_px": round(46 * scale),
            "desktop_navigation_px": round(50 * scale),
            "mobile_action_px": round(44 * scale),
        }
        for scale in DPI_SCALES
    ]
    return {
        "wcag_normal_text_ratio": 4.5,
        "wcag_non_text_focus_ratio": 3.0,
        "minimum_touch_target_dp": MINIMUM_TOUCH_TARGET_DP,
        "themes": themes,
        "dpi_profiles": dpi,
        "passed": all(bool(item["passed"]) for item in themes.values()),
    }
