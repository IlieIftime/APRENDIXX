"""Revision safety, provenance, source policy and coverage tests."""

from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from aprendix.application.content_governance import (
    DEFAULT_TRUSTED_SOURCES,
    ContentGovernanceService,
)
from aprendix.application.contracts import Complexity, ContentKind, SearchFiltersDTO
from aprendix.infrastructure.curriculum import CurriculumRepository
from aprendix.infrastructure.db import (
    ContentGovernanceRepository, KnowledgeRepository, KnowledgeStructureRepository,
)
from aprendix.infrastructure.db.knowledge_repository import IndexedChunk, IndexedDocument
from aprendix.infrastructure.ingestion import FeatureHashEmbedding
from aprendix.infrastructure.seed import seed_advanced_catalog, seed_default_catalog


def _revision(number: int, text: str):
    embedder = FeatureHashEmbedding(64)
    document = IndexedDocument(
        id=uuid5(NAMESPACE_URL, f"revision-document:{number}"),
        source_path="C:/local/manual.pdf", content_hash=str(number) * 64,
        title=f"Manual v{number}", author="Autor local",
        content_type=ContentKind.THEORY, complexity=Complexity.BEGINNER,
        published_at=None, page_count=1, file_size=100,
        modified_at=datetime(2026, 8, number, tzinfo=UTC), content_version=str(number),
    )
    chunk = IndexedChunk(
        id=uuid5(NAMESPACE_URL, f"revision-chunk:{number}"), ordinal=0,
        text=text, content_type=ContentKind.THEORY,
        embedding=embedder.embed(text), model_id=embedder.model_id,
        page_number=1, section="Conceito",
    )
    return document, (chunk,)


def test_staging_keeps_active_revision_and_rollback_restores_old_content(database, cipher):
    knowledge = KnowledgeRepository(database, cipher)
    governance = ContentGovernanceService(
        ContentGovernanceRepository(database), on_content_changed=knowledge.invalidate_cache
    )
    governance.initialize()
    first, chunks1 = _revision(1, "conteúdo antigo verificável")
    second, chunks2 = _revision(2, "conteúdo novo validado")
    knowledge.store_document(first, chunks1)
    knowledge.store_document(second, chunks2, quarantine=True)

    assert [item.text for item in knowledge.search_candidates(SearchFiltersDTO())] == [
        "conteúdo antigo verificável"
    ]
    knowledge.audit_content_quality()
    assert [item.text for item in knowledge.search_candidates(SearchFiltersDTO())] == [
        "conteúdo novo validado"
    ]

    governance.rollback(first.source_path, 1)
    assert [item.text for item in knowledge.search_candidates(SearchFiltersDTO())] == [
        "conteúdo antigo verificável"
    ]
    with database.read_connection() as connection:
        states = connection.execute(
            "SELECT sequence,status FROM content_revisions ORDER BY sequence"
        ).fetchall()
        provenance = connection.execute(
            "SELECT rights_status,license_id FROM document_provenance ORDER BY document_id"
        ).fetchall()
    assert [(row[0], row[1]) for row in states] == [(1, "active"), (2, "retired")]
    assert {(row[0], row[1]) for row in provenance} == {("local-private", "private-local")}


def test_trusted_registry_and_curriculum_coverage_are_deterministic(database, cipher):
    seed_default_catalog(database); seed_advanced_catalog(database)
    CurriculumRepository(database, cipher).seed()
    service = ContentGovernanceService(ContentGovernanceRepository(database))
    service.initialize()

    coverage = service.refresh_coverage()

    assert len(service.sources()) == len(DEFAULT_TRUSTED_SOURCES) == 18
    assert len(coverage) == 71
    assert all(item.exercise_count >= 1 for item in coverage)
    assert all(item.gap_code.value == "needs-theory" for item in coverage)


def test_objective_links_require_technical_overlap_and_feed_coverage(database, cipher):
    seed_default_catalog(database); seed_advanced_catalog(database)
    KnowledgeStructureRepository(database, cipher).seed()
    CurriculumRepository(database, cipher).seed()
    knowledge = KnowledgeRepository(database, cipher)
    document, _old_chunks = _revision(
        7, "Em Python, um byte representa dados num intervalo limitado de inteiros."
    )
    embedder = FeatureHashEmbedding(64)
    chunk = IndexedChunk(
        id=uuid5(NAMESPACE_URL, "byte-evidence"), ordinal=0,
        text="Em Python, um byte representa dados num intervalo limitado de inteiros.",
        content_type=ContentKind.THEORY,
        embedding=embedder.embed("Python byte intervalo representação"),
        model_id=embedder.model_id, page_number=1, section="Representação por byte",
    )
    knowledge.store_document(document, (chunk,))
    service = ContentGovernanceService(ContentGovernanceRepository(database, cipher))
    service.initialize()

    assert service.refresh_objective_evidence() >= 1
    coverage = service.refresh_coverage()
    represented = next(item for item in coverage if item.objective_code == "OBJ-DATA-REPRESENTATION")
    assert represented.theory_evidence_count == 1
    assert represented.gap_code.value == "none"
