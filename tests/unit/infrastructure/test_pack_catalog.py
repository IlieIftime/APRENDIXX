import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aprendix.application.content_governance import ContentGovernanceService
from aprendix.application.contracts import SearchFiltersDTO
from aprendix.infrastructure.content_pack import (
    ApxPackVerifier,
    ContentPackError,
    ContentPackManager,
    build_pack,
)
from aprendix.infrastructure.curriculum import CurriculumRepository
from aprendix.infrastructure.db import (
    ContentGovernanceRepository,
    KnowledgeRepository,
    KnowledgeStructureRepository,
)
from aprendix.infrastructure.pack_catalog import PackCatalogImporter
from aprendix.infrastructure.seed import seed_advanced_catalog, seed_default_catalog


def _manifest(version):
    return {
        "format": 1, "pack_id": "python-weekly", "version": version,
        "requires": [], "license": "PSF documentation licence",
        "provenance": "docs.python.org allowlisted adapter",
    }


def _catalog(body, *, reviewed=True):
    return {
        "format": 1, "title": "Python semanal", "author": "Equipa editorial Aprendix",
        "complexity": "beginner", "reviewed": reviewed,
        "source": {
            "adapter_id": "python-docs",
            "canonical_uri": "https://docs.python.org/3/tutorial/",
            "license_id": "PSF documentation licence",
            "rights_status": "permitted", "trust_score": .95,
        },
        "items": [{
            "id": "funcoes-puras", "title": "Funções puras", "body": body,
            "kind": "theory", "graph_node_slug": "pack-funcoes-puras",
        }],
    }


def _manager(tmp_path, database, cipher, key):
    seed_default_catalog(database); seed_advanced_catalog(database)
    KnowledgeStructureRepository(database, cipher).seed()
    CurriculumRepository(database, cipher).seed()
    governance = ContentGovernanceRepository(database, cipher)
    ContentGovernanceService(governance).initialize()
    knowledge = KnowledgeRepository(database, cipher)
    importer = PackCatalogImporter(database, knowledge, governance)
    manager = ContentPackManager(
        tmp_path / "packs", ApxPackVerifier((key.public_key(),)), activator=importer,
    )
    return manager, knowledge


def test_reviewed_catalog_is_searchable_and_rollback_restores_database(
    tmp_path, database, cipher,
):
    key = Ed25519PrivateKey.generate()
    manager, knowledge = _manager(tmp_path, database, cipher, key)
    v1_body = "Uma função pura devolve o mesmo resultado para os mesmos argumentos e evita efeitos externos."
    v2_body = "Uma função pura torna dependências explícitas e facilita testes determinísticos locais."
    for version, body in (("1.0.0", v1_body), ("1.1.0", v2_body)):
        pack = build_pack(
            tmp_path / f"{version}.apxpack", _manifest(version),
            {"content/catalog.json": json.dumps(_catalog(body), ensure_ascii=False).encode()}, key,
        )
        manager.install(pack, validate_staging=manager.validate_declarative_staging)

    active = knowledge.search_candidates(
        SearchFiltersDTO(sources=("apxpack://python-weekly",)), limit=20,
    )
    assert len(active) == 1 and "dependências explícitas" in active[0].text
    manager.rollback("python-weekly", "1.0.0")
    restored = knowledge.search_candidates(
        SearchFiltersDTO(sources=("apxpack://python-weekly",)), limit=20,
    )
    assert len(restored) == 1 and "mesmo resultado" in restored[0].text
    with database.read_connection() as connection:
        states = dict(connection.execute(
            "SELECT p.content_version,d.lifecycle FROM document_provenance p JOIN documents d ON d.id=p.document_id"
        ).fetchall())
    assert states["1.0.0"] == "active" and states["1.1.0"] == "retired"


def test_unreviewed_catalog_never_becomes_active(tmp_path, database, cipher):
    key = Ed25519PrivateKey.generate()
    manager, _knowledge = _manager(tmp_path, database, cipher, key)
    pack = build_pack(
        tmp_path / "unreviewed.apxpack", _manifest("1.0.0"),
        {"content/catalog.json": json.dumps(_catalog(
            "Este texto tem tamanho suficiente, mas ainda não passou revisão.", reviewed=False,
        ), ensure_ascii=False).encode()}, key,
    )
    with pytest.raises(ContentPackError, match="revisão editorial"):
        manager.install(pack, validate_staging=manager.validate_declarative_staging)
    assert manager.installed() == ()
