"""Encrypted vector store and deterministic ingestion component tests."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest

from aprendix.application.contracts import Complexity, ContentKind, SearchFiltersDTO
from aprendix.application.text_normalization import TextDecodingError
from aprendix.infrastructure.db import (
    IndexedChunk,
    IndexedDocument,
    KnowledgeRepository,
)
from aprendix.infrastructure.ingestion import (
    ContentIngestionPipeline,
    FeatureHashEmbedding,
    LocalDocumentExtractor,
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


def test_python_ingestion_honours_declared_encoding_without_replacement(tmp_path: Path) -> None:
    source = tmp_path / "legacy.py"
    source.write_bytes("# coding: cp1252\nnome = 'João'\n".encode("cp1252"))
    document = LocalDocumentExtractor().extract(source)
    assert "João" in document.sections[0].text
    assert "\ufffd" not in document.sections[0].text


def test_python_ingestion_rejects_irrecoverable_declared_encoding(tmp_path: Path) -> None:
    source = tmp_path / "damaged.py"
    source.write_bytes(b"# coding: utf-8\nname = '\xff'\n")
    with pytest.raises(TextDecodingError, match="declared Python encoding"):
        LocalDocumentExtractor().extract(source)


def test_notebook_ingestion_accepts_utf8_sig_and_rejects_cp1252(tmp_path: Path) -> None:
    notebook = tmp_path / "lesson.ipynb"
    notebook.write_bytes(
        b"\xef\xbb\xbf" + json.dumps({
            "cells": [{"cell_type": "code", "source": ["nome = 'João'\n"]}],
        }, ensure_ascii=False).encode("utf-8")
    )
    document = LocalDocumentExtractor().extract(notebook)
    assert document.sections[0].text == "nome = 'João'"
    notebook.write_bytes('{"cells": [], "nome": "João"}'.encode("cp1252"))
    with pytest.raises(TextDecodingError, match="not valid UTF-8"):
        LocalDocumentExtractor().extract(notebook)


def test_ingestion_ocr_text_is_repaired_or_rejected_before_chunking() -> None:
    extractor = LocalDocumentExtractor()
    assert extractor._normalize_ocr_result((
        (((0, 0),), "aÃ§Ã£o", .91),
    )) == "ação"
    with pytest.raises(TextDecodingError, match="replacement"):
        extractor._normalize_ocr_result((
            (((0, 0),), "valor \ufffd", .99),
        ))


def test_invalid_python_is_recorded_without_creating_searchable_chunks(
    database, cipher, tmp_path: Path
) -> None:
    source = tmp_path / "damaged.py"
    source.write_bytes(b"# coding: utf-8\nname = '\xff'\n")
    summary = ContentIngestionPipeline(
        KnowledgeRepository(database, cipher)
    ).ingest((source,))
    assert summary.failed_documents == 1
    assert summary.indexed_documents == 0
    assert "TextDecodingError" in summary.errors[0]
    with database.read_connection() as connection:
        assert connection.execute("SELECT count(*) FROM documents").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM document_chunks").fetchone()[0] == 0


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
