"""Deterministic Kivy font discovery using files already shipped by Kivy."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path


def _matplotlib_font(filename: str) -> str | None:
    """Resolve a font already bundled with Matplotlib, when available.

    The desktop package includes ``mpl-data`` for the offline formula renderer,
    so this is also a reliable packaged fallback on Kivy versions which do not
    ship Roboto Mono.
    """

    try:
        from matplotlib import get_data_path
    except (ImportError, ModuleNotFoundError):
        return None
    candidate = Path(get_data_path()) / "fonts" / "ttf" / filename
    return str(candidate) if candidate.is_file() else None


def bundled_font_paths(resource_find: Callable[[str], str | None]) -> dict[str, str]:
    """Return existing Unicode-capable sans and mono files or fail explicitly."""

    regular = resource_find("data/fonts/Roboto-Regular.ttf") or _matplotlib_font(
        "DejaVuSans.ttf"
    )
    bold = resource_find("data/fonts/Roboto-Bold.ttf") or _matplotlib_font(
        "DejaVuSans-Bold.ttf"
    ) or regular
    mono = resource_find("data/fonts/RobotoMono-Regular.ttf")
    if not mono:
        # Kivy does not consistently ship Roboto Mono. Matplotlib's DejaVu is
        # included with the formula renderer and has broad Unicode coverage.
        mono = resource_find("data/fonts/DejaVuSansMono.ttf") or resource_find(
            "data/fonts/DejaVuSans.ttf"
        ) or _matplotlib_font("DejaVuSansMono.ttf") or regular
    values = {"sans": regular, "sans_bold": bold, "mono": mono}
    missing = tuple(name for name, value in values.items() if not value or not Path(value).is_file())
    if missing:
        raise RuntimeError("Fontes locais empacotadas em falta: " + ", ".join(missing))
    return {name: str(value) for name, value in values.items() if value is not None}


def register_kivy_fonts(label_base, resource_find: Callable[[str], str | None]) -> dict[str, str]:
    """Register stable family names consumed by labels and code panes."""

    paths = bundled_font_paths(resource_find)
    label_base.register(
        name="AprendixSans", fn_regular=paths["sans"], fn_bold=paths["sans_bold"],
    )
    label_base.register(name="AprendixMono", fn_regular=paths["mono"])
    return paths
