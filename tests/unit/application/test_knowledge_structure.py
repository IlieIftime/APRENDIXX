from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from aprendix.application.contracts import (
    Complexity,
    ContentKind,
    SearchFiltersDTO,
    SearchRequestDTO,
)
from aprendix.application.knowledge import HybridSearchService
from aprendix.application.knowledge_structure import (
    PedagogicalReadingAssistant,
    classify_areas,
)
from aprendix.infrastructure.curriculum import CurriculumRepository
from aprendix.infrastructure.db import (
    IndexedChunk,
    IndexedDocument,
    KnowledgeRepository,
    KnowledgeStructureRepository,
)
from aprendix.infrastructure.ingestion import FeatureHashEmbedding


def _indexed_vision_document(repository: KnowledgeRepository) -> str:
    embedder = FeatureHashEmbedding(64)
    document_id = uuid5(NAMESPACE_URL, "structure:vision-document")
    chunk_id = uuid5(NAMESPACE_URL, "structure:vision-chunk")
    text = (
        "Uma convolutional neural network aprende filtros locais para computer vision. "
        "A matriz de entrada é combinada com um kernel e o gradiente é calculado por backpropagation. "
        "Residual connections ajudam a treinar modelos profundos."
    )
    repository.store_document(
        IndexedDocument(
            id=document_id, source_path="C:/docs/vision-local.pdf",
            content_hash="9" * 64, title="Visão computacional local",
            author="Autor local", content_type=ContentKind.THEORY,
            complexity=Complexity.INTERMEDIATE, published_at=None,
            page_count=1, file_size=500, modified_at=datetime.now(UTC),
        ),
        (IndexedChunk(
            id=chunk_id, ordinal=0, text=text, content_type=ContentKind.THEORY,
            embedding=embedder.embed(text), model_id=embedder.model_id,
            page_number=1, section="CNN e filtros residuais",
        ),),
    )
    return str(chunk_id)


def test_knowledge_tree_catalogue_sources_and_explainable_classification(database, cipher) -> None:
    structure = KnowledgeStructureRepository(database, cipher)
    structure.seed()
    areas = structure.areas()
    assert len(areas) >= 40
    by_id = {item.id: item for item in areas}
    assert by_id["artificial-intelligence"].parent_id is None
    assert by_id["agent-memory"].parent_id == "autonomous-agents"
    assert structure.shortcuts("computer-vision")
    sources = structure.sources(("autonomous-agents",), limit=30)
    assert {item.id for item in sources} >= {"src-react", "src-reflexion"}
    assigned = classify_areas("ReAct agent tool use with episodic memory")
    assert any(area_id in {"agent-architectures", "agent-memory"} for area_id, _score, _reason in assigned)


def test_area_filtered_cards_search_and_assisted_reading_are_operational(database, cipher) -> None:
    knowledge = KnowledgeRepository(database, cipher)
    chunk_id = _indexed_vision_document(knowledge)
    CurriculumRepository(database, cipher).seed()
    structure = KnowledgeStructureRepository(database, cipher)
    structure.seed()
    structure.ensure_mappings(knowledge.search_candidates(SearchFiltersDTO()))

    cards = knowledge.list_theory_cards(area_id="computer-vision")
    assert len(cards) == 1
    assert "computer-vision" in cards[0].area_ids
    filtered = knowledge.search_candidates(
        SearchFiltersDTO(area_ids=("artificial-intelligence",))
    )
    assert len(filtered) == 1

    detail = structure.reading_detail(chunk_id)
    assert detail.summary and "IDEIA CENTRAL" in detail.simplified
    assert detail.key_points
    assert any(source.id == "src-resnet" for source in detail.related_sources)
    cached = structure.reading_detail(chunk_id)
    assert cached.summary == detail.summary


def test_pedagogical_reader_preserves_math_and_adds_validation_scaffold() -> None:
    text = (
        "O gradiente mede a variação local da função de custo. "
        "A atualização w = w - taxa * gradiente reduz o objetivo quando o passo é adequado. "
        "Uma taxa excessiva pode impedir a convergência."
    )
    summary, simplified, points, math_notes = PedagogicalReadingAssistant.build(text, "gradiente")
    assert summary and points
    assert "COMO VALIDAR A COMPREENSÃO" in simplified
    assert math_notes and "w =" in math_notes[0]


def test_curated_search_respects_result_limit_and_stays_local(database, cipher) -> None:
    structure = KnowledgeStructureRepository(database, cipher)
    structure.seed()
    web = type(
        "NetworkMustNotBeUsed",
        (),
        {"search": lambda self, query, *, max_results: (_ for _ in ()).throw(
            AssertionError("curated local results must prevent Web fallback")
        )},
    )()
    service = HybridSearchService(
        KnowledgeRepository(database, cipher),
        embedder=FeatureHashEmbedding(64),
        web=web,
        curated=structure,
    )
    response = service.search(SearchRequestDTO(
        query="memÃ³ria e planeamento em agentes autÃ³nomos",
        filters=SearchFiltersDTO(area_ids=("autonomous-agents",)),
        max_results=3,
    ))
    assert len(response.evidence) == 3
    assert len({item.title.casefold() for item in response.evidence}) == 3
    assert response.used_web_fallback is False
    assert response.local_confidence > 0.0
