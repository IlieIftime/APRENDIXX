from uuid import NAMESPACE_URL, uuid5

from aprendix.application.learning_catalog import ALL_FACTS
from aprendix.infrastructure.curriculum import CurriculumRepository
from aprendix.infrastructure.db import KnowledgeRepository, KnowledgeStructureRepository


def test_seeded_cards_and_glossary_have_explicit_provenance_and_depth(database, cipher) -> None:
    structure = KnowledgeStructureRepository(database, cipher)
    structure.seed()
    curriculum = CurriculumRepository(database, cipher)
    curriculum.seed()
    knowledge = KnowledgeRepository(database, cipher)
    assert knowledge.seed_authored_facts() == len(ALL_FACTS)
    assert knowledge.seed_authored_facts() == len(ALL_FACTS)

    with database.read_connection() as connection:
        cards = connection.execute("SELECT count(*) FROM theory_cards").fetchone()[0]
        cards_without_sources = connection.execute(
            """SELECT count(*) FROM theory_cards tc WHERE NOT EXISTS(
                 SELECT 1 FROM card_source_links csl WHERE csl.card_id=tc.id)"""
        ).fetchone()[0]
        visual_cards = connection.execute(
            "SELECT count(*) FROM card_presentation WHERE format='visual'"
        ).fetchone()[0]
        visual_assets = connection.execute(
            """SELECT count(DISTINCT asset_id) FROM card_presentation
               WHERE format='visual' AND asset_id IS NOT NULL"""
        ).fetchone()[0]
        top_glossary = connection.execute(
            """SELECT e.id,
                      (SELECT count(*) FROM glossary_examples x WHERE x.entry_id=e.id) examples,
                      (SELECT count(*) FROM glossary_source_links s WHERE s.entry_id=e.id) sources
               FROM glossary_entries e ORDER BY e.normalized_term LIMIT 500"""
        ).fetchall()
        exact_card_sources = {
            row["card_id"]: tuple(item["source_id"] for item in connection.execute(
                """SELECT source_id FROM card_source_links
                   WHERE card_id=? ORDER BY position""", (row["card_id"],)
            ))
            for row in connection.execute(
                "SELECT DISTINCT card_id FROM card_source_links"
            )
        }
    assert cards == len(ALL_FACTS)
    assert cards_without_sources == 0
    assert visual_cards > 100
    assert visual_assets >= 100
    assert len(top_glossary) == 500
    assert min(row["examples"] for row in top_glossary) >= 2
    assert min(row["sources"] for row in top_glossary) >= 2
    for fact in ALL_FACTS:
        card_id = str(uuid5(NAMESPACE_URL, f"aprendix:fact-card:{fact.slug}"))
        assert exact_card_sources[card_id] == fact.source_ids

    entry = curriculum.glossary("else", limit=1)[0]
    assert len(entry["examples"]) >= 2
    assert len(entry["references"]) >= 2
    card = knowledge.list_theory_cards(limit=1_000)[0]
    assert card.sources
    assert card.source_title == card.sources[0].title
