"""Encrypted vector store and deterministic ingestion component tests."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from aprendix.application.contracts import Complexity, ContentKind, SearchFiltersDTO
from aprendix.infrastructure.db import IndexedChunk, IndexedDocument, KnowledgeRepository
from aprendix.infrastructure.ingestion import (
    FeatureHashEmbedding,
    SpecialistPythonBookParser,
    discover_sources,
)


def test_feature_hash_embedding_is_fixed_quantized_and_deterministic() -> None:
    embedder = FeatureHashEmbedding(64)
    first = embedder.embed("classes Python e objetos")
    assert first == embedder.embed("classes Python e objetos")
    assert len(first) == 64
    assert all(-127 <= value <= 127 for value in first)
    assert any(first)


def test_specialist_parser_separates_theory_and_exercises() -> None:
    sections = SpecialistPythonBookParser().split(
        "Classes agrupam estado e comportamento.\nExercício 1: Cria uma classe Pessoa.\nSolução: não mostrar.",
        page_number=12,
    )
    assert [item.content_type for item in sections] == [
        ContentKind.THEORY, ContentKind.EXERCISE
    ]
    assert "Solução" not in sections[1].text
    assert sections[1].page_number == 12


def test_discovery_deduplicates_nested_roots_and_ignores_pickle(tmp_path: Path) -> None:
    folder = tmp_path / "docs"; folder.mkdir()
    pdf = folder / "book.pdf"; pdf.write_bytes(b"pdf")
    (folder / "unsafe.pkl").write_bytes(b"pickle")
    assert discover_sources((tmp_path, folder, pdf)) == (pdf.resolve(),)


def test_repository_atomically_stores_encrypted_chunks_cards_and_exercises(database, cipher) -> None:
    repository = KnowledgeRepository(database, cipher)
    embedder = FeatureHashEmbedding(64)
    document_id = uuid5(NAMESPACE_URL, "document:test")
    document = IndexedDocument(
        id=document_id, source_path="C:/docs/python.pdf", content_hash="a" * 64,
        title="Python", author="Autor", content_type=ContentKind.THEORY,
        complexity=Complexity.BEGINNER, published_at=None, page_count=1,
        file_size=100, modified_at=datetime.now(UTC),
    )
    chunks = (
        IndexedChunk(
            id=uuid5(NAMESPACE_URL, "chunk:theory"), ordinal=0,
            text="Uma classe modela objetos.", content_type=ContentKind.THEORY,
            embedding=embedder.embed("Uma classe modela objetos."), model_id=embedder.model_id,
            page_number=1, section="Classes",
        ),
        IndexedChunk(
            id=uuid5(NAMESPACE_URL, "chunk:exercise"), ordinal=1,
            text="Cria uma classe Pessoa.", content_type=ContentKind.EXERCISE,
            embedding=embedder.embed("Cria uma classe Pessoa."), model_id=embedder.model_id,
            page_number=1, section="Exercício 1", graph_node_slug="classes-pessoa",
        ),
    )
    created, cards, exercises = repository.store_document(document, chunks)
    assert (created, cards, exercises) == (True, 1, 1)
    assert len(repository.list_theory_cards()) == 1
    candidates = repository.search_candidates(SearchFiltersDTO())
    assert {item.text for item in candidates} == {
        "Uma classe modela objetos.", "Cria uma classe Pessoa."
    }
    assert repository.store_document(document, chunks)[0] is False

