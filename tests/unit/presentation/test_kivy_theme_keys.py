from pathlib import Path

from aprendix.presentation.design_system import palette


def test_advanced_ui_only_indexes_declared_palette_keys() -> None:
    source = (
        Path(__file__).parents[3] / "src" / "aprendix" / "presentation" / "kivy_advanced.py"
    ).read_text(encoding="utf-8")
    for unsupported in ('colors["surface"]', 'colors["surface_alt"]'):
        assert unsupported not in source
    assert {"bg", "card", "card_alt", "accent", "text", "muted"} <= set(palette("dark"))
