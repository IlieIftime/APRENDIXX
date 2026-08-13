from collections import Counter

from aprendix.application.editorial_catalog import (
    EDITORIAL_EXERCISES,
    EDITORIAL_PROJECTS,
)
from aprendix.application.learning_catalog import ALL_FACTS
from aprendix.application.official_catalog import (
    OFFICIAL_CARD_BUCKET_QUOTAS,
    OFFICIAL_CONCEPTS,
    OFFICIAL_GLOSSARY_ALIASES,
    OFFICIAL_GLOSSARY_BUCKET_QUOTAS,
    OFFICIAL_GLOSSARY_SOURCE_IDS,
    OFFICIAL_SOURCE_QUOTAS,
    OFFICIAL_SOURCES,
)
from aprendix.presentation.math_renderer import validate_latex


def test_iteration21_official_source_snapshot_is_exact_and_balanced() -> None:
    assert len(OFFICIAL_SOURCES) == 500
    assert Counter(item.family for item in OFFICIAL_SOURCES) == OFFICIAL_SOURCE_QUOTAS
    assert len({item.url for item in OFFICIAL_SOURCES}) == 500
    assert all(".corp." not in item.url for item in OFFICIAL_SOURCES)


def test_iteration21_card_and_glossary_buckets_meet_exact_release_quotas() -> None:
    assert len(OFFICIAL_CONCEPTS) == 1_000
    assert Counter(item.card_bucket for item in OFFICIAL_CONCEPTS) == OFFICIAL_CARD_BUCKET_QUOTAS
    assert Counter(item.glossary_bucket for item in OFFICIAL_CONCEPTS) == OFFICIAL_GLOSSARY_BUCKET_QUOTAS
    assert min(len(set(ids)) for ids in OFFICIAL_GLOSSARY_SOURCE_IDS.values()) >= 2
    assert min(len(set(aliases)) for _, aliases in OFFICIAL_GLOSSARY_ALIASES) >= 2
    official_facts = tuple(fact for fact in ALL_FACTS if fact.slug.startswith("official-"))
    normalized_bodies = {
        " ".join(f"{fact.fact} {fact.explanation} {fact.formula_or_code}".casefold().split())
        for fact in official_facts
    }
    assert len(official_facts) == len(normalized_bodies) == 1_000


def test_iteration21_formula_cards_are_structured_unique_and_render_safe() -> None:
    formulas = tuple(item for item in ALL_FACTS if item.card_format == "formula")
    assert len(formulas) == len({item.formula_latex for item in formulas}) == 10
    for item in formulas:
        assert validate_latex(item.formula_latex) == item.formula_latex
        assert item.formula_spoken and item.formula_variables and item.formula_worked_example
        assert len(set(item.source_ids)) >= 3


def test_iteration21_exercises_projects_and_capital_contract_are_complete() -> None:
    assert len(EDITORIAL_EXERCISES) == 500
    assert len(EDITORIAL_PROJECTS) == 50
    assert set(Counter(item.role_slug for item in EDITORIAL_EXERCISES).values()) == {100}
    capital = next(item for item in EDITORIAL_EXERCISES if item.slug == "career-capital-acumulado")
    assert "capital_inicial * (1 + t / 100) ** n" in capital.prompt
    assert "2021 -> 1530.00, 1537.50, 1545.00" in capital.prompt
    assert len({capital.source_id, *capital.supporting_source_ids}) >= 3
    namespace: dict[str, object] = {}
    exec(
        capital.solution,
        {"__builtins__": {"round": round, "range": range, "any": any, "tuple": tuple}},
        namespace,
    )
    result = namespace["tabela_capital_acumulado"](1500, 2020, (2, 2.5, 3), 3)
    assert result[-1] == (2023, (1591.81, 1615.34, 1639.09))
