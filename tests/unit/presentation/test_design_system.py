from aprendix.presentation.design_system import (
    DPI_SCALES,
    THEMES,
    accessibility_matrix,
    contrast_ratio,
    palette,
)


def test_design_system_has_complete_accessible_palettes() -> None:
    assert set(THEMES) == {"dark", "light", "contrast"}
    for name in THEMES:
        colors = palette(name)
        assert set(colors) >= {"bg", "card", "accent", "accent_text", "text", "focus", "danger"}
        assert all(len(color) == 4 for color in colors.values())
    assert palette("unknown") == palette("dark")


def test_theme_pairs_meet_wcag_contrast_targets() -> None:
    report = accessibility_matrix()
    assert report["passed"] is True
    assert tuple(item["scale_percent"] for item in report["dpi_profiles"]) == (
        100, 125, 150, 175, 200,
    )
    assert DPI_SCALES == (1.0, 1.25, 1.5, 1.75, 2.0)
    for name in THEMES:
        colors = palette(name)
        assert contrast_ratio(colors["accent_text"], colors["accent"]) >= 4.5
        assert contrast_ratio(colors["focus"], colors["bg"]) >= 3.0
