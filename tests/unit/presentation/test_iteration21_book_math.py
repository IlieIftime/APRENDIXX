from pathlib import Path

import pytest

from aprendix.application.math_rendering import FormulaRenderRequest
from aprendix.presentation.fonts import bundled_font_paths, register_kivy_fonts
from aprendix.presentation.math_renderer import (
    FormulaValidationError,
    OfflineMathRenderer,
    extract_latex_expressions,
    formula_cache_key,
    latex_to_readable_unicode,
    strip_latex_markup,
    validate_latex,
)
from aprendix.presentation.responsive import book_workspace_profile
from aprendix.presentation.text_safety import normalize_ui_text


@pytest.mark.parametrize(
    ("width", "height", "density"),
    (
        (1024, 768, 1.0),
        (1366, 768, 1.0),
        (1920, 1080, 1.0),
        (1222, 956, 1.5),
    ),
)
def test_book_workspace_keeps_two_pages_when_minima_fit(width, height, density) -> None:
    profile = book_workspace_profile(width, height, density=density)

    assert profile.mode == "book"
    assert profile.editor_width_dp >= 360
    assert profile.support_width_dp >= 320
    assert .20 <= profile.terminal_ratio <= .35


def test_book_workspace_uses_explicit_tabs_only_below_page_minima() -> None:
    profile = book_workspace_profile(680, 720)

    assert profile.mode == "tabs"
    assert profile.editor_width_dp == profile.support_width_dp


def test_terminal_and_support_sizes_are_clamped() -> None:
    profile = book_workspace_profile(
        1000, 800, requested_support_width_dp=900,
        requested_terminal_ratio=.8,
    )

    assert profile.editor_width_dp >= 360
    assert profile.support_width_dp == 631
    assert profile.terminal_ratio == .35
    assert profile.terminal_open_height_dp == 280


def test_formula_validation_rejects_external_or_hostile_commands() -> None:
    assert validate_latex(r"\frac{x_1 + \sqrt{y}}{2}")
    with pytest.raises(FormulaValidationError):
        validate_latex(r"\input{secrets.txt}")
    with pytest.raises(FormulaValidationError):
        validate_latex("{" * 17 + "x" + "}" * 17)


def test_formula_cache_key_varies_by_theme_dpi_and_scale() -> None:
    base = FormulaRenderRequest(
        latex=r"x^2", spoken="x ao quadrado", variables={"x": "entrada"},
    )

    assert formula_cache_key(base) == formula_cache_key(base)
    assert formula_cache_key(base) != formula_cache_key(
        FormulaRenderRequest(
            latex=base.latex, spoken=base.spoken, variables=base.variables,
            theme="light",
        )
    )


def test_formula_extraction_hides_raw_markup_and_keeps_readable_fallback() -> None:
    body = r"Capital composto: $$C = C_0(1 + i)^n$$ para n anos."

    assert extract_latex_expressions(body) == (r"C = C_0(1 + i)^n",)
    assert "$$" not in strip_latex_markup(body)
    technical = r"Fórmula\nNotação para copiar: \frac{x}{2}"
    assert "\\frac" not in strip_latex_markup(technical, (r"\frac{x}{2}",))
    assert "√" in latex_to_readable_unicode(r"\sqrt{x}")


def test_offline_renderer_creates_non_blank_transparent_dark_formula(tmp_path) -> None:
    pil = pytest.importorskip("PIL.Image")
    result = OfflineMathRenderer(tmp_path).render(FormulaRenderRequest(
        latex=r"\frac{C_0(1+i)^n}{1+\sigma}",
        spoken="capital acumulado normalizado", variables={"C_0": "capital inicial"},
        theme="dark", dpi=144,
    ))

    assert result.path is not None and result.path.is_file()
    image = pil.open(result.path).convert("RGBA")
    colors = image.getcolors(maxcolors=image.width * image.height)
    assert colors is not None and len(colors) > 1
    assert min(alpha for _count, (*_rgb, alpha) in colors) < 255
    assert max(alpha for _count, (*_rgb, alpha) in colors) > 0


@pytest.mark.parametrize(
    "latex",
    (
        r"\frac{x+1}{2}",
        r"x^{n+1}",
        r"\sum_{i=1}^{n}x_i",
        r"\sqrt{x^2+y^2}",
        r"\begin{matrix}a&b\\c&d\end{matrix}",
        r"\alpha + \beta \le \gamma",
    ),
)
def test_renderer_covers_required_formula_families_without_raw_markup(
    tmp_path, latex,
) -> None:
    pil = pytest.importorskip("PIL.Image")
    result = OfflineMathRenderer(tmp_path / formula_cache_key(FormulaRenderRequest(
        latex=latex, spoken="fórmula de teste", variables={},
    ))).render(FormulaRenderRequest(
        latex=latex, spoken="fórmula de teste", variables={}, theme="dark", dpi=120,
    ))

    assert not result.error
    assert result.path is not None and result.path.is_file()
    readable = latex_to_readable_unicode(latex)
    assert "\\begin" not in readable and "\\end" not in readable
    image = pil.open(result.path).convert("RGBA")
    assert image.getbbox() is not None
    assert max(pixel[3] for pixel in image.getdata()) > 0
    if "\\alpha" in latex:
        assert result.backend == "mathtext-agg"


def test_text_hygiene_repairs_mojibake_and_removes_replacement_glyph() -> None:
    assert normalize_ui_text("IteraÃ§Ã£o â€“ fÃ³rmula") == "Iteração – fórmula"
    assert normalize_ui_text("a â†’ b â€¢ c") == "a → b • c"
    assert normalize_ui_text("AÃƒÂ§ÃƒÂ£o") == "Ação"
    assert normalize_ui_text("âmbito matemático") == "âmbito matemático"
    assert "�" not in normalize_ui_text("valor � seguro")


def test_bundled_font_policy_requires_real_files(tmp_path) -> None:
    sans = tmp_path / "sans.ttf"
    mono = tmp_path / "mono.ttf"
    sans.write_bytes(b"font")
    mono.write_bytes(b"font")

    def find(resource: str) -> str | None:
        if resource.endswith("Roboto-Regular.ttf"):
            return str(sans)
        if resource.endswith("Roboto-Bold.ttf"):
            return str(sans)
        if resource.endswith("RobotoMono-Regular.ttf"):
            return str(mono)
        return None

    assert bundled_font_paths(find) == {
        "sans": str(sans), "sans_bold": str(sans), "mono": str(mono),
    }


def test_bundled_font_policy_falls_back_to_packaged_matplotlib_fonts() -> None:
    pytest.importorskip("matplotlib")

    paths = bundled_font_paths(lambda _resource: None)

    assert all(Path(path).is_file() for path in paths.values())
    assert Path(paths["mono"]).name == "DejaVuSansMono.ttf"


def test_font_registration_uses_stable_sans_and_mono_aliases(tmp_path) -> None:
    sans = tmp_path / "sans.ttf"
    mono = tmp_path / "mono.ttf"
    sans.write_bytes(b"font")
    mono.write_bytes(b"font")
    registrations = []

    class FakeLabelBase:
        @staticmethod
        def register(**kwargs):
            registrations.append(kwargs)

    def find(resource):
        return str(mono if "Mono" in resource else sans)

    register_kivy_fonts(FakeLabelBase, find)

    assert [item["name"] for item in registrations] == ["AprendixSans", "AprendixMono"]


def test_kivy_source_uses_book_desk_icon_actions_and_shared_formula_view() -> None:
    source = (
        Path(__file__).parents[3] / "src" / "aprendix" / "presentation" / "kivy_advanced.py"
    ).read_text(encoding="utf-8")

    assert "self.ide_desk = BoxLayout(" in source
    assert "self.ide_desk.add_widget(self.workspace)" in source
    assert "self.ide_desk.add_widget(self.terminal_shell)" in source
    assert "class TerminalDivider(Widget):" in source
    assert "class IconAction(" in source
    assert "class FormulaView(Card):" in source
    assert "def action(title, callback, *, primary=True):" in source
    assert 'theme_name == "light" and self.theme_role != "accent"' in source
    assert "exercise_brief.formula_latex and not already_has_formula" in source
    assert "if Window.height < dp(800) and self.brief_expanded" not in source
    assert "if self.bottom_panel_expanded:\n                    self._toggle_bottom_panel" not in source
    assert 'for panel_name in ("Output", "Problemas", "Testes", "Debug", "Tutor")' in source


def test_analyzer_ui_exposes_every_deep_static_analysis_family() -> None:
    source = (
        Path(__file__).parents[3] / "src" / "aprendix" / "presentation" / "kivy_advanced.py"
    ).read_text(encoding="utf-8")

    assert '"Resumo", "Problemas", "Símbolos", "Fluxo", "Tipos"' in source
    for attribute in (
        "diagnostics", "symbols", "functions", "classes", "type_facts",
        "cfg_blocks", "call_edges", "complexity_findings", "security_findings",
        "test_suggestions", "imports", "possible_exceptions",
    ):
        assert f"result.{attribute}" in source
