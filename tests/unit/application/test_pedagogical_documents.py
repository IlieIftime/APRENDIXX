from __future__ import annotations

import pytest

from aprendix.application.contracts.pedagogy import PedagogicalSourceLinkDTO
from aprendix.application.pedagogical_documents import (
    ManagedAssetStore,
    PedagogicalDocumentService,
    build_pedagogical_document,
    deterministic_card_svg,
    legacy_text_to_blocks,
    normalize_pedagogical_text,
)
from aprendix.application.search_holdout import SEARCH_HOLDOUT_V2
from aprendix.infrastructure.db.pedagogical_repository import PedagogicalRepository


def _seed_source(database) -> None:
    with database.transaction() as connection:
        connection.execute(
            """INSERT INTO curated_sources(
                id,title,authors_json,publication_year,source_type,canonical_url,doi,
                overview,why_it_matters,access_note,license_note,provenance
            ) VALUES('source:test','Referência técnica','["Aprendix"]',2026,
                'documentation','https://example.invalid/docs',NULL,'Visão geral.',
                'Valida conceitos.','Metadados locais.','CC-BY metadata','test')"""
        )


def test_normalizer_removes_repeated_margins_and_repairs_wrapped_prose() -> None:
    source = "Cabeçalho\nUma transfor-\nmação segura.\nRodapé\fCabeçalho\nOutro texto.\nRodapé"
    assert normalize_pedagogical_text(source) == "Uma transformação segura.\n\nOutro texto."
    code = "valor = nome-\n    outro"
    assert normalize_pedagogical_text(code, preserve_code=True) == code


def test_structured_document_asset_roundtrip_and_catalog_search(
    database, cipher, tmp_path
) -> None:
    _seed_source(database)
    repository = PedagogicalRepository(database, cipher)
    service = PedagogicalDocumentService(repository)
    asset = deterministic_card_svg(
        area_title="Álgebra linear",
        fact="O produto interno combina componentes correspondentes.",
        format_name="visual",
    )
    service.save_asset(asset)
    assert service.get_asset(asset.id) == asset
    materialized = ManagedAssetStore(tmp_path / "assets").materialize(asset)
    assert materialized.read_bytes() == asset.content

    blocks = legacy_text_to_blocks(
        "## Produto interno\n\nSoma produtos correspondentes.\n\n$$x\\cdot w=\\sum_i x_iw_i$$",
        document_id="lesson:dot-product",
    )
    document = build_pedagogical_document(
        owner_type="lesson", owner_id="dot-product", title="Produto interno",
        summary="Relação entre vetores.", blocks=blocks,
        sources=(PedagogicalSourceLinkDTO(
            source_id="source:test", position=0,
            rationale="Referência técnica de validação.",
        ),),
    )
    service.save(document)
    loaded = service.get("lesson", "dot-product")
    assert loaded is not None
    assert loaded.fingerprint == document.fingerprint
    assert [block.kind for block in loaded.blocks] == ["title", "paragraph", "formula"]
    counts = repository.rebuild_catalog_search()
    assert counts["lesson"] == 1
    # Explicit lesson intent tests the internal-document path; a general
    # technical query is intentionally source-first since Iteration 21.
    hits = service.search_catalog("lição produto interno vetores")
    assert hits and hits[0].entity_id == "dot-product"


def test_repository_rejects_svg_with_script(database, cipher) -> None:
    repository = PedagogicalRepository(database, cipher)
    safe = deterministic_card_svg(area_title="Teste", fact="Fluxo seguro.", format_name="visual")
    unsafe_content = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    from hashlib import sha256
    digest = sha256(unsafe_content).hexdigest()
    unsafe = safe.model_copy(update={
        "id": digest, "content": unsafe_content,
        "storage_uri": f"aprendix-asset://{digest}", "byte_size": len(unsafe_content),
    })
    with pytest.raises(ValueError, match="unsafe"):
        repository.save_asset(unsafe)


def test_search_holdout_has_120_unique_queries_and_hard_negatives() -> None:
    assert len(SEARCH_HOLDOUT_V2) == 120
    assert len({case.id for case in SEARCH_HOLDOUT_V2}) == 120
    assert len({case.query.casefold() for case in SEARCH_HOLDOUT_V2}) == 120
    assert all(case.hard_negative_area_ids for case in SEARCH_HOLDOUT_V2)


def test_runtime_materializes_the_complete_typed_learning_spine(tmp_path) -> None:
    from aprendix.bootstrap import build_runtime

    runtime = build_runtime(tmp_path / "profile")
    with runtime.database.read_connection() as connection:
        owners = {
            row["owner_type"]: int(row["total"])
            for row in connection.execute(
                """SELECT owner_type,count(*) total FROM pedagogical_documents
                   GROUP BY owner_type"""
            )
        }
        block_kinds = {
            row["kind"] for row in connection.execute(
                "SELECT DISTINCT kind FROM pedagogical_blocks"
            )
        }
        unsourced = int(connection.execute(
            """SELECT count(*) FROM pedagogical_documents d WHERE NOT EXISTS(
                 SELECT 1 FROM pedagogical_document_sources s
                 WHERE s.document_id=d.id)"""
        ).fetchone()[0])
        under_sourced = int(connection.execute(
            """SELECT count(*) FROM pedagogical_documents d WHERE
                 (SELECT count(*) FROM pedagogical_document_sources s
                  WHERE s.document_id=d.id)<2"""
        ).fetchone()[0])
        broken_assets = int(connection.execute(
            """SELECT count(*) FROM pedagogical_blocks b
               LEFT JOIN pedagogical_assets a ON a.id=b.asset_id
               WHERE b.asset_id IS NOT NULL AND a.id IS NULL"""
        ).fetchone()[0])
        insecure_glossary_shadow = int(connection.execute(
            """SELECT count(*) FROM catalog_search_entries
               WHERE entity_type='glossary' AND trim(body)<>trim(title)"""
        ).fetchone()[0])
    assert owners["exercise"] == 59
    assert owners["lesson"] == 59
    assert owners["project"] >= 70
    assert {
        "title", "paragraph", "list", "code", "signature", "formula",
        "table", "diagram", "callout", "references",
    } <= block_kinds
    assert unsourced == under_sourced == broken_assets == 0
    assert insecure_glossary_shadow == 0
