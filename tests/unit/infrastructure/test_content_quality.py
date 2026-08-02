from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from aprendix.application.contracts import Complexity, ContentKind, SearchFiltersDTO
from aprendix.infrastructure.db.knowledge_repository import IndexedChunk, IndexedDocument, KnowledgeRepository
from aprendix.infrastructure.db.knowledge_structure_repository import KnowledgeStructureRepository
from aprendix.infrastructure.ingestion import FeatureHashEmbedding


def test_embedded_publication_is_quarantined_without_deletion(database, cipher):
    repository = KnowledgeRepository(database, cipher); embedder = FeatureHashEmbedding(64)
    document = IndexedDocument(
        id=uuid5(NAMESPACE_URL, "quality-document"), source_path="C:/combined.pdf",
        content_hash="9" * 64, title="Livro principal", author="Autor",
        content_type=ContentKind.THEORY, complexity=Complexity.BEGINNER,
        published_at=None, page_count=100, file_size=1000, modified_at=datetime.now(UTC),
    )
    texts = (
        (1, "Conteúdo legítimo sobre funções Python."),
        (50, "First published in 2024. Copyright © Author. Publisher Example. ISBN: 123-4."),
        (51, "Texto da publicação anexada."),
    )
    chunks = tuple(IndexedChunk(
        id=uuid5(NAMESPACE_URL, f"quality-chunk-{page}"), ordinal=index,
        text=value, content_type=ContentKind.THEORY, embedding=embedder.embed(value),
        model_id=embedder.model_id, page_number=page,
    ) for index, (page, value) in enumerate(texts))
    repository.store_document(document, chunks)
    report = repository.audit_content_quality()
    assert report["quarantined_chunks"] == 2
    assert len(repository.search_candidates(SearchFiltersDTO())) == 1
    with database.read_connection() as connection:
        assert connection.execute("SELECT count(*) FROM document_chunks").fetchone()[0] == 3


def test_authored_fact_embeddings_match_the_runtime_retriever(database, cipher):
    KnowledgeStructureRepository(database, cipher).seed()
    repository = KnowledgeRepository(database, cipher)
    assert repository.seed_authored_facts() >= 48
    candidates = repository.search_candidates(SearchFiltersDTO())
    fact_candidates = [item for item in candidates if item.source_path.startswith("aprendix://")]
    assert len(fact_candidates) >= 48
    assert {len(item.embedding) for item in fact_candidates} == {384}
