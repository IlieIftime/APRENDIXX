"""Dashboard, hybrid retrieval, synthesis, and filter contract tests."""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from aprendix.application.contracts import (
    Complexity,
    ContentKind,
    GraphNodeSnapshotDTO,
    GraphSnapshotDTO,
    NodeStatisticsDTO,
    SearchEvidenceDTO,
    SearchFiltersDTO,
    SearchRequestDTO,
)
from aprendix.application.knowledge import (
    DashboardService,
    ExtractiveAnswerSynthesizer,
    HybridSearchService,
    SearchCandidate,
)


class Embedder:
    def embed(self, _text):
        return (100, 0, 0)


class Index:
    def __init__(self, candidates):
        self.candidates = candidates
        self.filters = None

    def search_candidates(self, filters, *, limit=5_000):
        self.filters = filters
        return self.candidates


class Web:
    def __init__(self):
        self.calls = 0

    def search(self, query, *, max_results):
        self.calls += 1
        return ()


def candidate(text="Python classes use class syntax"):
    return SearchCandidate(
        chunk_id=uuid4(), title="Python POO", source_path="C:/book.pdf",
        author="Autor", content_type=ContentKind.THEORY,
        complexity=Complexity.BEGINNER, published_at=date(2024, 1, 1),
        page_number=4, text=text, embedding=(100, 0, 0),
    )


def test_dashboard_maps_mastery_and_recommendations() -> None:
    user_id, node_id = uuid4(), uuid4()
    snapshot = GraphSnapshotDTO(
        user_id=user_id,
        nodes=(GraphNodeSnapshotDTO(
            id=node_id, slug="classes", title="Classes", difficulty=0,
            statistics=NodeStatisticsDTO(
                user_id=user_id, node_id=node_id, attempt_count=4,
                success_count=3, failure_count=1,
            ),
        ),),
    )
    dashboard = DashboardService.from_snapshot(snapshot)
    assert dashboard.overall_mastery == 0.75
    assert dashboard.total_attempts == 4
    assert dashboard.nodes[0].title == "Classes"


def test_search_is_local_first_and_applies_filters() -> None:
    index, web = Index((candidate(),)), Web()
    service = HybridSearchService(index, embedder=Embedder(), web=web)
    request = SearchRequestDTO(
        query="Python classes", local_confidence_threshold=0.2,
        filters=SearchFiltersDTO(
            content_types=(ContentKind.THEORY,),
            complexities=(Complexity.BEGINNER,),
        ),
    )
    response = service.search(request)
    assert response.local_confidence >= 0.2
    assert response.used_web_fallback is False
    assert web.calls == 0
    assert index.filters == request.filters


def test_low_confidence_respects_disabled_web_fallback() -> None:
    web = Web()
    service = HybridSearchService(Index(()), embedder=Embedder(), web=web)
    response = service.search(SearchRequestDTO(query="metaclass", allow_web_fallback=False))
    assert response.fallback_reason == "network_fallback_disabled"
    assert web.calls == 0


def test_search_filter_rejects_reversed_date_range() -> None:
    with pytest.raises(ValueError, match="published_from"):
        SearchFiltersDTO(
            published_from=date(2025, 1, 1), published_to=date(2024, 1, 1)
        )

