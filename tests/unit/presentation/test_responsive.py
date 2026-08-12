import pytest

from aprendix.presentation.responsive import (
    dashboard_tab_width,
    ide_journey_header_profile,
    layout_profile,
    responsive_matrix,
)


def test_release_viewports_keep_a_usable_content_canvas() -> None:
    report = responsive_matrix()
    assert report["passed"] is True
    assert {item["navigation"] for item in report["profiles"]} == {
        "bottom", "compact-sidebar", "sidebar",
    }
    assert all(item["columns"] >= 1 for item in report["profiles"])


def test_layout_switches_navigation_and_columns_deterministically() -> None:
    assert layout_profile(412, 915).navigation == "bottom"
    assert layout_profile(800, 700).navigation == "compact-sidebar"
    assert layout_profile(1920, 1080).columns == 3
    assert layout_profile(1366, 768).columns == 2


@pytest.mark.parametrize("width,height,density", [(0, 700, 1), (800, 0, 1), (800, 700, 0)])
def test_invalid_viewports_are_rejected(width, height, density) -> None:
    with pytest.raises(ValueError):
        layout_profile(width, height, density=density)


def test_dashboard_tabs_keep_readable_widths_when_text_grows() -> None:
    labels = ("Resumo", "Atividade", "Competências", "Percursos", "Plano", "Grafo")
    normal = {label: dashboard_tab_width(label) for label in labels}
    enlarged = {label: dashboard_tab_width(label, font_scale=1.5) for label in labels}

    assert min(normal.values()) >= 96
    assert normal["Competências"] > normal["Resumo"]
    assert all(enlarged[label] > normal[label] for label in labels)


def test_compact_ide_header_has_a_bounded_non_overlapping_budget() -> None:
    profile = ide_journey_header_profile(1_222, density=1.5)

    assert profile.compact is True
    assert profile.title_width_dp >= 200
    assert profile.occupied_width_dp <= profile.content_width_dp
    assert profile.navigation_width_dp < 88
    assert profile.course_width_dp <= 160
