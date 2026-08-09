"""Navigation must remain deterministic across desktop and mobile shells."""

import pytest

from aprendix.application.navigation import (
    CommandPalette,
    NavigationHistory,
    Route,
    parse_deep_link,
)


def test_navigation_history_supports_back_forward_and_branching() -> None:
    history = NavigationHistory()
    history.navigate(Route.SEARCH)
    history.navigate(Route.DICTIONARY)

    assert history.back() is Route.SEARCH
    assert history.back() is Route.DASHBOARD
    assert history.forward() is Route.SEARCH
    history.navigate(Route.IDE)
    assert history.forward() is Route.IDE
    assert history.can_go_forward is False


def test_deep_links_are_restricted_to_known_routes_and_parameters() -> None:
    link = parse_deep_link("aprendix://search?query=recurs%C3%A3o&area=algorithms")
    assert link.route is Route.SEARCH
    assert link.parameters == {"query": "recursão", "area": "algorithms"}

    with pytest.raises(ValueError):
        parse_deep_link("https://example.test/search")
    with pytest.raises(ValueError):
        parse_deep_link("aprendix://unknown")
    with pytest.raises(ValueError):
        parse_deep_link("aprendix://search?token=secret")


def test_command_palette_finds_accent_insensitive_keywords() -> None:
    palette = CommandPalette()

    assert palette.search("codigo")[0].route is Route.IDE
    assert palette.search("definicao")[0].route is Route.DICTIONARY
    assert len(palette.search("")) == 8
