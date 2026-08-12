from collections import Counter, defaultdict

from aprendix.application.advanced_learning_catalog import AREA_SEEDS, PRIORITY_AREAS
from aprendix.application.knowledge_structure import AREAS, SOURCES
from aprendix.application.learning_catalog import ALL_FACTS


def test_every_leaf_has_card_depth_format_diversity_and_exact_sources() -> None:
    parent_ids = {area.parent_id for area in AREAS if area.parent_id}
    leaves = {area.id for area in AREAS if area.id not in parent_ids}
    counts = Counter(fact.area_id for fact in ALL_FACTS)
    formats: dict[str, set[str]] = defaultdict(set)
    known_sources = {source.id for source in SOURCES}
    for fact in ALL_FACTS:
        formats[fact.area_id].add(fact.card_format)
        assert fact.source_ids
        assert set(fact.source_ids) <= known_sources
        if fact.slug.startswith("advanced-"):
            assert len(fact.fact.split()) >= 7
            assert len(fact.explanation.split()) >= 12
    for area_id in leaves:
        assert counts[area_id] >= 12, area_id
        assert len(formats[area_id]) >= 4, area_id
    for area_id in PRIORITY_AREAS:
        assert counts[area_id] >= 24, area_id


def test_advanced_bank_covers_every_leaf_with_original_specs() -> None:
    parent_ids = {area.parent_id for area in AREAS if area.parent_id}
    leaves = {area.id for area in AREAS if area.id not in parent_ids}
    assert set(AREA_SEEDS) == leaves
    slugs = [fact.slug for fact in ALL_FACTS]
    assert len(slugs) == len(set(slugs))
