from datetime import date
from uuid import uuid4

import pytest

from aprendix.application.contracts import (
    Complexity,
    ContentKind,
    SearchRequestDTO,
)
from aprendix.application.knowledge import HybridSearchService, SearchCandidate
from aprendix.application.search_holdout import SEARCH_HOLDOUT_V2, SEARCH_HOLDOUT_V3
from aprendix.infrastructure.db.pedagogical_repository import PedagogicalRepository


class ConstantEmbedder:
    def embed(self, _text):
        return (100, 0, 0)


class MemoryIndex:
    def __init__(self, candidates):
        self.candidates = tuple(candidates)

    def search_candidates(self, _filters, *, limit=50_000):
        return self.candidates[:limit]


def hit(title, text, source, *, trust=.9):
    return SearchCandidate(
        chunk_id=uuid4(),
        title=title,
        source_path=source,
        author="Autor",
        content_type=ContentKind.THEORY,
        complexity=Complexity.INTERMEDIATE,
        published_at=date(2024, 1, 1),
        page_number=1,
        text=text,
        embedding=(100, 0, 0),
        trust_score=trust,
        rights_status="permitted",
    )


def test_general_search_places_real_sources_before_internal_examples() -> None:
    service = HybridSearchService(MemoryIndex((
        hit("Card: Decoradores Python", "decoradores Python função envolvente", "aprendix://authored-facts/v1", trust=.99),
        hit("Python documentation", "decoradores Python e funções", "C:/docs/python.pdf"),
        hit("Fluent Python", "decoradores Python função envolvente e retorno", "https://example.org/fluent"),
    )), embedder=ConstantEmbedder())
    response = service.search(SearchRequestDTO(
        query="decoradores Python função envolvente",
        allow_web_fallback=False,
    ))
    assert len(response.evidence) == 3
    assert all(not item.source.startswith("aprendix://") for item in response.evidence[:2])
    assert response.evidence[2].source.startswith("aprendix://")


def test_explicit_internal_intent_may_lead_with_aprendix_content() -> None:
    service = HybridSearchService(MemoryIndex((
        hit("Exercício Aprendix: decoradores", "exercício Aprendix decoradores Python", "aprendix://exercise/decorator", trust=.99),
        hit("Documentation", "decoradores Python exercício", "C:/docs/python.pdf"),
    )), embedder=ConstantEmbedder())
    response = service.search(SearchRequestDTO(
        query="exercício Aprendix de decoradores Python",
        allow_web_fallback=False,
    ))
    assert response.evidence[0].source.startswith("aprendix://")


def test_dense_collision_does_not_invent_a_vague_answer() -> None:
    service = HybridSearchService(MemoryIndex((
        hit("Redes neuronais", "gradiente e pesos", "C:/book.pdf"),
    )), embedder=ConstantEmbedder())
    response = service.search(SearchRequestDTO(
        query="zxqv termo inexistente 91731",
        allow_web_fallback=False,
    ))
    assert response.evidence == ()
    assert response.confidence == 0
    assert "evidência suficiente" in response.answer
    assert response.fallback_reason == "network_fallback_disabled"


@pytest.mark.parametrize("query,term", (
    ("capital acumulado juros compostos", "capital"),
    ("decoradores Python função envolvente", "decoradores"),
    ("backpropagation regra da cadeia", "backpropagation"),
))
def test_mandatory_regressions_retain_lexical_evidence(query, term) -> None:
    service = HybridSearchService(MemoryIndex((
        hit(term.title(), f"Explicação técnica de {query} com exemplo.", f"C:/sources/{term}.pdf"),
        hit("Hard negative", "HTML cores e layout sem relação", "C:/sources/web.pdf"),
    )), embedder=ConstantEmbedder())
    response = service.search(SearchRequestDTO(query=query, allow_web_fallback=False))
    assert response.evidence
    assert term in (response.evidence[0].title + response.evidence[0].excerpt).casefold()
    assert response.evidence[0].title != "Hard negative"


def test_v3_holdout_expands_v2_without_mutating_the_iteration20_baseline() -> None:
    assert len(SEARCH_HOLDOUT_V2) == 120
    assert len(SEARCH_HOLDOUT_V3) >= 250
    assert len({item.id for item in SEARCH_HOLDOUT_V3}) == len(SEARCH_HOLDOUT_V3)
    assert {"holdout-regression-capital", "holdout-regression-decorators", "holdout-regression-backprop"} <= {
        item.id for item in SEARCH_HOLDOUT_V3
    }


def test_authored_fact_aggregate_is_not_duplicated_as_a_reading_in_rebuild_source() -> None:
    """The 2,827 governed cards represent this corpus in catalogue search.

    Indexing their decrypted aggregate once more as a 1.4 MB reading both
    duplicates editorial content and makes lexical qualification unbounded.
    """

    constants = PedagogicalRepository.rebuild_catalog_search.__code__.co_consts
    sql = "\n".join(value for value in constants if isinstance(value, str))
    assert "d.source_path<>'aprendix://authored-facts/v1'" in sql
