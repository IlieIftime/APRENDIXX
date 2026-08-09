"""Promote a reviewed declarative pack catalogue into encrypted local search."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

from aprendix.application.contracts import Complexity, ContentKind
from aprendix.infrastructure.content_pack import ContentPackError, VerifiedPack, canonical_json
from aprendix.infrastructure.db.knowledge_repository import IndexedChunk, IndexedDocument
from aprendix.infrastructure.ingestion import FeatureHashEmbedding


class PackCatalogImporter:
    """Activate one signed catalogue as one atomic, rollback-capable document."""

    CATALOG = "content/catalog.json"
    MAX_ITEMS = 1_000
    MAX_TEXT_BYTES = 10 * 1024 * 1024

    def __init__(self, database, knowledge, governance, *, on_changed=None) -> None:
        self._database = database
        self._knowledge = knowledge
        self._governance = governance
        self._embedder = FeatureHashEmbedding()
        self._on_changed = on_changed or (lambda: None)

    def __call__(self, directory: Path, pack: VerifiedPack) -> None:
        catalog_path = directory / self.CATALOG
        if not catalog_path.is_file():
            return
        catalog = self._load(catalog_path, pack, directory)
        logical_source = f"apxpack://{pack.pack_id}"
        content_hash = hashlib.sha256(canonical_json({
            "pack_id": pack.pack_id, "version": pack.version, "catalog": catalog,
        })).hexdigest()
        with self._database.read_connection() as connection:
            existing = connection.execute(
                """SELECT r.sequence FROM content_revisions r
                   WHERE r.logical_source=? AND r.content_hash=?""",
                (logical_source, content_hash),
            ).fetchone()
        if existing is not None:
            self._governance.rollback(logical_source, int(existing["sequence"]))
            self._refresh()
            return

        source = catalog["source"]
        now = datetime.now(UTC)
        document_id = uuid5(
            NAMESPACE_URL, f"aprendix:apxpack:{pack.pack_id}:{pack.version}:{content_hash}"
        )
        document = IndexedDocument(
            id=document_id, source_path=logical_source, content_hash=content_hash,
            title=catalog["title"], author=catalog["author"],
            content_type=ContentKind.THEORY,
            complexity=Complexity(catalog["complexity"]), published_at=None,
            page_count=0, file_size=catalog_path.stat().st_size, modified_at=now,
            source_adapter_id=source["adapter_id"],
            canonical_uri=source["canonical_uri"], license_id=source["license_id"],
            rights_status="permitted", content_version=pack.version,
            trust_score=float(source["trust_score"]),
        )
        chunks = []
        for ordinal, item in enumerate(catalog["items"]):
            image_path = None
            if item.get("image"):
                image_path = str(directory.joinpath(*PurePosixPath(item["image"]).parts))
            text = f"{item['title']}\n\n{item['body']}"
            chunks.append(IndexedChunk(
                id=uuid5(
                    NAMESPACE_URL,
                    f"aprendix:apxpack-chunk:{pack.pack_id}:{pack.version}:{item['id']}",
                ),
                ordinal=ordinal, text=text, content_type=ContentKind(item["kind"]),
                embedding=self._embedder.embed(text), model_id=self._embedder.model_id,
                section=item["title"], graph_node_slug=item["graph_node_slug"],
                image_path=image_path,
            ))
        created, _cards, _exercises = self._knowledge.store_document(
            document, tuple(chunks), quarantine=False,
        )
        if not created:
            raise ContentPackError("O catálogo aprovado colide com conteúdo já instalado.")
        self._refresh()

    def _refresh(self) -> None:
        self._knowledge.invalidate_cache()
        self._knowledge.rebuild_public_fts(force=True)
        self._knowledge.rebuild_private_search_index(force=True)
        self._on_changed()

    def _load(self, path: Path, pack: VerifiedPack, directory: Path) -> dict[str, object]:
        try:
            value = json.loads(path.read_text("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ContentPackError("Catálogo declarativo inválido.") from exc
        if not isinstance(value, dict) or set(value) != {
            "format", "title", "author", "complexity", "reviewed", "source", "items"
        }:
            raise ContentPackError("Campos do catálogo não reconhecidos.")
        if value["format"] != 1 or value["reviewed"] is not True:
            raise ContentPackError("O catálogo precisa de revisão editorial explícita.")
        for field, maximum in (("title", 500), ("author", 300)):
            if not isinstance(value[field], str) or not 1 <= len(value[field].strip()) <= maximum:
                raise ContentPackError(f"Campo {field} inválido no catálogo.")
        if value["complexity"] not in {item.value for item in Complexity}:
            raise ContentPackError("Complexidade do catálogo inválida.")
        source = value["source"]
        if not isinstance(source, dict) or set(source) != {
            "adapter_id", "canonical_uri", "license_id", "rights_status", "trust_score"
        }:
            raise ContentPackError("Proveniência do catálogo inválida.")
        if source["rights_status"] != "permitted" or source["license_id"] != pack.manifest["license"]:
            raise ContentPackError("Licença/direitos do catálogo não autorizam promoção.")
        try:
            trust = float(source["trust_score"])
        except (TypeError, ValueError) as exc:
            raise ContentPackError("Confiança da fonte inválida.") from exc
        if not .5 <= trust <= 1.0:
            raise ContentPackError("Confiança da fonte fora do intervalo aprovado.")
        parsed = urlsplit(str(source["canonical_uri"]))
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ContentPackError("A origem canónica deve usar HTTPS sem credenciais.")
        with self._database.read_connection() as connection:
            adapter = connection.execute(
                "SELECT domain,enabled FROM content_source_adapters WHERE id=?",
                (str(source["adapter_id"]),),
            ).fetchone()
        if adapter is None or not adapter["enabled"] or parsed.hostname.casefold() != adapter["domain"].casefold():
            raise ContentPackError("A origem não pertence ao registo allowlisted ativo.")
        items = value["items"]
        if not isinstance(items, list) or not 1 <= len(items) <= self.MAX_ITEMS:
            raise ContentPackError("Quantidade de itens do catálogo inválida.")
        known_files = {record["path"] for record in pack.manifest["files"]}
        seen, total = set(), 0
        allowed_fields = {"id", "title", "body", "kind", "graph_node_slug", "image"}
        for item in items:
            if not isinstance(item, dict) or not set(item).issubset(allowed_fields) or not {
                "id", "title", "body", "kind", "graph_node_slug"
            }.issubset(item):
                raise ContentPackError("Item declarativo inválido.")
            identity = str(item["id"])
            if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,79}", identity) or identity in seen:
                raise ContentPackError("Identidade de item inválida ou duplicada.")
            seen.add(identity)
            if item["kind"] not in {ContentKind.THEORY.value, ContentKind.EXERCISE.value}:
                raise ContentPackError("Tipo de item não permitido.")
            if not isinstance(item["title"], str) or not 1 <= len(item["title"].strip()) <= 240:
                raise ContentPackError("Título de item inválido.")
            if not isinstance(item["body"], str) or not 20 <= len(item["body"].strip()) <= 20_000:
                raise ContentPackError("Corpo de item inválido.")
            total += len(item["body"].encode("utf-8"))
            slug = str(item["graph_node_slug"])
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,79}", slug):
                raise ContentPackError("Conceito de grafo inválido.")
            image = item.get("image")
            if image is not None:
                pure = PurePosixPath(str(image))
                if (str(image) not in known_files or not str(image).startswith("media/") or
                        pure.suffix.casefold() not in {".png", ".jpg", ".jpeg", ".webp"} or
                        not directory.joinpath(*pure.parts).is_file()):
                    raise ContentPackError("Imagem declarativa inválida.")
        if total > self.MAX_TEXT_BYTES:
            raise ContentPackError("Texto do catálogo excede o limite de promoção.")
        return value
