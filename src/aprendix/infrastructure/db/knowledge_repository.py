"""Encrypted SQLite storage for ingested knowledge and local vector search."""

from __future__ import annotations

import json
import hashlib
import math
import re
import struct
import threading
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID, uuid5, NAMESPACE_URL

from aprendix.application.contracts import (
    Complexity,
    ContentKind,
    IngestionSummaryDTO,
    KnowledgeClusterDTO,
    LearningTheme,
    SearchFiltersDTO,
    TheoryCardDTO,
    Technology,
)
from aprendix.application.clustering import ClusterAssignment, ClusterInput, TaxonomyClassifier
from aprendix.application.knowledge import SearchCandidate
from aprendix.application.knowledge_structure import classify_areas, descendants
from aprendix.application.learning_catalog import ALL_FACTS
from aprendix.infrastructure.db.database import Database
from aprendix.infrastructure.security import AesGcmFieldCipher


@dataclass(frozen=True, slots=True)
class IndexedChunk:
    id: UUID
    ordinal: int
    text: str
    content_type: ContentKind
    embedding: tuple[int, ...]
    model_id: str
    page_number: int | None = None
    section: str = ""
    graph_node_slug: str | None = None
    image_path: str | None = None


@dataclass(frozen=True, slots=True)
class IndexedDocument:
    id: UUID
    source_path: str
    content_hash: str
    title: str
    author: str | None
    content_type: ContentKind
    complexity: Complexity
    published_at: date | None
    page_count: int
    file_size: int
    modified_at: datetime
    source_adapter_id: str | None = None
    canonical_uri: str | None = None
    license_id: str = "private-local"
    rights_status: str = "local-private"
    content_version: str = "1"
    trust_score: float = 0.8


class KnowledgeRepository:
    """Persist a complete parsed document atomically with encrypted payloads."""

    def __init__(self, database: Database, cipher: AesGcmFieldCipher) -> None:
        self._database = database
        self._cipher = cipher
        self._candidate_cache_key: str | None = None
        self._candidate_cache: tuple[SearchCandidate, ...] = ()
        self._cache_lock = threading.RLock()
        self._blind_filter_cache: tuple[tuple[str, bytes, bytes], ...] = ()
        self._blind_ordinals: tuple[str, ...] = ()
        self._blind_slices: tuple[int, ...] = ()

    def contains_hash(self, content_hash: str) -> bool:
        with self._database.read_connection() as connection:
            row = connection.execute(
                "SELECT 1 FROM documents WHERE content_hash = ?", (content_hash,)
            ).fetchone()
        return row is not None

    def invalidate_cache(self) -> None:
        with self._cache_lock:
            self._candidate_cache_key = None
            self._candidate_cache = ()
            self._blind_filter_cache = ()
            self._blind_ordinals = ()
            self._blind_slices = ()

    def audit_content_quality(self) -> dict[str, int]:
        """Quarantine a second publication accidentally appended to a document.

        Some scanned collections concatenate complete books into one PDF.  A
        title-based classifier then gives every later page the first book's
        identity.  This audit detects a new copyright/front-matter block well
        inside a document.  It never deletes the user's content: quarantined
        chunks remain encrypted and can be inspected in SQLite.
        """

        version = "embedded-publication-boundary-v1"
        with self._database.read_connection() as connection:
            documents = connection.execute(
                """SELECT d.id,d.page_count FROM documents d
                   LEFT JOIN content_quality_audits a ON a.document_id=d.id
                   WHERE d.lifecycle IN ('active','staging')
                   AND (a.document_id IS NULL OR a.algorithm_version<>?)
                   ORDER BY CASE WHEN d.lifecycle='active' THEN 0 ELSE 1 END,
                            d.ingested_at,d.id""", (version,),
            ).fetchall()
        audited = quarantined = 0
        for document in documents:
            with self._database.read_connection() as connection:
                rows = connection.execute(
                    """SELECT id,page_number,text_encrypted FROM document_chunks
                       WHERE document_id=? ORDER BY ordinal""", (document["id"],),
                ).fetchall()
            pages: dict[int, list[str]] = {}
            for row in rows:
                if row["page_number"] is None:
                    continue
                value = self._cipher.decrypt(
                    row["text_encrypted"],
                    associated_data=f"document_chunks.text:{row['id']}".encode(),
                ).decode("utf-8", errors="replace")
                pages.setdefault(int(row["page_number"]), []).append(value)
            lower_bound = max(20, int(max(1, document["page_count"]) * .35))
            boundary = None
            for page_number in sorted(pages):
                if page_number < lower_bound:
                    continue
                sample = " ".join(pages[page_number])[:4_000].casefold()
                markers = sum(bool(re.search(pattern, sample)) for pattern in (
                    r"\bfirst published\b|\bprimeira edi[cç][aã]o\b",
                    r"\bcopyright\b|©|\ball rights reserved\b",
                    r"\bpublisher\b|\bpublished by\b|\beditora\b",
                    r"\b(?:e?isbn)\b\s*[:0-9-]",
                    r"\bprinted (?:and bound )?in\b",
                ))
                if markers >= 3:
                    boundary = page_number
                    break
            now = datetime.now(UTC).isoformat()
            rejected_ids = [str(row["id"]) for row in rows
                            if boundary is not None and row["page_number"] is not None
                            and int(row["page_number"]) >= boundary]
            rejected = set(rejected_ids)
            accepted = len(rows) - len(rejected)
            reason = (f"nova publicação detetada na página {boundary}"
                      if boundary else "sem fronteira de publicação anómala")
            with self._database.transaction() as connection:
                connection.execute("DELETE FROM chunk_quality WHERE chunk_id IN (SELECT id FROM document_chunks WHERE document_id=?)", (document["id"],))
                connection.executemany(
                    "INSERT INTO chunk_quality(chunk_id,status,score,reason,audited_at) VALUES(?,?,?,?,?)",
                    ((str(row["id"]), "quarantined" if str(row["id"]) in rejected else "accepted",
                      .99 if str(row["id"]) in rejected else .9, reason, now) for row in rows),
                )
                if rejected_ids:
                    marks = ",".join("?" for _ in rejected_ids)
                    connection.execute(f"DELETE FROM knowledge_area_chunks WHERE chunk_id IN ({marks})", rejected_ids)
                    connection.execute(f"DELETE FROM knowledge_cluster_members WHERE chunk_id IN ({marks})", rejected_ids)
                connection.execute(
                    """INSERT INTO content_quality_audits(document_id,algorithm_version,
                       accepted_chunks,quarantined_chunks,boundary_page,reason,audited_at)
                       VALUES(?,?,?,?,?,?,?) ON CONFLICT(document_id) DO UPDATE SET
                       algorithm_version=excluded.algorithm_version,
                       accepted_chunks=excluded.accepted_chunks,
                       quarantined_chunks=excluded.quarantined_chunks,
                       boundary_page=excluded.boundary_page,reason=excluded.reason,
                       audited_at=excluded.audited_at""",
                    (document["id"], version, accepted, len(rejected_ids), boundary, reason, now),
                )
                lifecycle = "active" if accepted else "quarantined"
                revision = connection.execute(
                    "SELECT id,logical_source FROM content_revisions WHERE document_id=?",
                    (document["id"],)
                ).fetchone()
                if revision is not None:
                    if lifecycle == "active":
                        current = connection.execute(
                            """SELECT r.id revision_id,r.document_id FROM content_revisions r
                               WHERE r.logical_source=? AND r.status='active' AND r.document_id<>?""",
                            (revision["logical_source"], document["id"]),
                        ).fetchone()
                        if current is not None:
                            connection.execute(
                                "UPDATE content_revisions SET status='retired' WHERE id=?",
                                (current["revision_id"],),
                            )
                            connection.execute(
                                "UPDATE documents SET source_path=?,lifecycle='retired' WHERE id=?",
                                (f"aprendix://revision/{current['document_id']}", current["document_id"]),
                            )
                        connection.execute(
                            "UPDATE documents SET source_path=? WHERE id=?",
                            (revision["logical_source"], document["id"]),
                        )
                    connection.execute(
                        "UPDATE documents SET lifecycle=? WHERE id=?", (lifecycle, document["id"])
                    )
                    connection.execute(
                        "UPDATE content_revisions SET status=?,promoted_at=? WHERE id=?",
                        (lifecycle, now if lifecycle == "active" else None, revision["id"]),
                    )
                    connection.execute(
                        """INSERT INTO content_validation_results VALUES(?,?,?,?,?)
                           ON CONFLICT(revision_id,check_code) DO UPDATE SET
                           status=excluded.status,detail=excluded.detail,checked_at=excluded.checked_at""",
                        (revision["id"], "publication-boundary",
                         "warning" if rejected_ids else "passed", reason[:500], now),
                    )
            audited += 1
            quarantined += len(rejected_ids)
        if audited:
            with self._cache_lock:
                self._candidate_cache_key = None
                self._candidate_cache = ()
        return {"documents": audited, "quarantined_chunks": quarantined}

    def seed_authored_facts(self) -> int:
        """Seed original, source-linked facts instead of raw PDF paragraphs."""

        document_id = uuid5(NAMESPACE_URL, "aprendix:authored-facts:v1")
        now = datetime.now(UTC).isoformat()
        with self._database.transaction() as connection:
            catalog_hash = hashlib.sha256(
                "\n".join(fact.slug for fact in ALL_FACTS).encode("utf-8")
            ).hexdigest()
            connection.execute(
                """INSERT INTO documents(id,source_path,content_hash,title,author,
                   content_type,complexity,page_count,file_size,modified_at,ingested_at)
                   VALUES(?,?,?,?,?,'theory','beginner',0,0,?,?)
                   ON CONFLICT(id) DO UPDATE SET content_hash=excluded.content_hash,
                   modified_at=excluded.modified_at""",
                (str(document_id), "aprendix://authored-facts/v1",
                 catalog_hash,
                 "Aprendix — Sabias que?", "Equipa Aprendix", now, now),
            )
            # Original Aprendix copy may safely use the persistent plaintext FTS
            # index. User-supplied PDFs retain ``local-private`` provenance and
            # are searched only after decryption in memory.
            connection.execute(
                """INSERT INTO document_provenance(
                    document_id,source_adapter_id,logical_source,canonical_uri,
                    license_id,rights_status,content_version,trust_score,reviewed_at
                ) VALUES(?,NULL,?,NULL,'aprendix-original','permitted','2',1.0,?)
                ON CONFLICT(document_id) DO UPDATE SET
                    license_id='aprendix-original',rights_status='permitted',content_version='2',
                    trust_score=1.0,reviewed_at=excluded.reviewed_at""",
                (str(document_id), "aprendix://authored-facts/v1", now),
            )
            known_areas = {row[0] for row in connection.execute("SELECT id FROM knowledge_areas")}
            for position, fact in enumerate(ALL_FACTS):
                chunk_id = uuid5(NAMESPACE_URL, f"aprendix:fact-chunk:{fact.slug}")
                card_id = uuid5(NAMESPACE_URL, f"aprendix:fact-card:{fact.slug}")
                body_text = fact.fact + "\n\n" + fact.explanation
                if fact.formula_or_code:
                    body_text += "\n\n" + fact.formula_or_code
                text_blob = self._cipher.encrypt(body_text.encode(), associated_data=f"document_chunks.text:{chunk_id}".encode())
                dimensions = 384
                raw_vector = [0.0] * dimensions
                words = re.findall(r"[\wÀ-ÿ]{2,}", unicodedata.normalize("NFKC", body_text).casefold())
                features = words + [word[i:i + 3] for word in words for i in range(max(0, len(word) - 2))]
                for feature in features[:20_000]:
                    digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
                    index = int.from_bytes(digest[:4], "little") % dimensions
                    raw_vector[index] += 1.0 if digest[4] & 1 else -1.0
                raw_norm = math.sqrt(sum(value * value for value in raw_vector)) or 1.0
                vector = tuple(max(-127, min(127, round(value / raw_norm * 100))) for value in raw_vector)
                if not any(vector): vector = (100,) + vector[1:]
                vector_blob = self._cipher.encrypt(struct.pack("<384b", *vector), associated_data=f"chunk_embeddings.vector:{chunk_id}".encode())
                connection.execute(
                    """INSERT OR IGNORE INTO document_chunks(id,document_id,ordinal,page_number,
                       section,chunk_type,text_encrypted,token_count,created_at)
                       VALUES(?,?,?,NULL,?,'theory',?,?,?)""",
                    (str(chunk_id), str(document_id), position, fact.slug, text_blob, len(body_text.split()), now),
                )
                connection.execute(
                    """INSERT INTO chunk_embeddings(chunk_id,model_id,dimensions,
                       vector_encrypted,norm,created_at) VALUES(?,'aprendix-feature-hash-v1-q8',384,?,?,?)
                       ON CONFLICT(chunk_id) DO UPDATE SET model_id=excluded.model_id,
                       dimensions=excluded.dimensions,vector_encrypted=excluded.vector_encrypted,
                       norm=excluded.norm,created_at=excluded.created_at""",
                    (str(chunk_id), vector_blob, math.sqrt(sum(v*v for v in vector)), now),
                )
                technologies, themes = TaxonomyClassifier.classify(body_text)
                connection.execute(
                    """INSERT INTO knowledge_taxonomy(chunk_id,technologies_json,themes_json,updated_at)
                       VALUES(?,?,?,?) ON CONFLICT(chunk_id) DO UPDATE SET
                       technologies_json=excluded.technologies_json,themes_json=excluded.themes_json,
                       updated_at=excluded.updated_at""",
                    (str(chunk_id), json.dumps([x.value for x in technologies]), json.dumps([x.value for x in themes]), now),
                )
                area_id = fact.area_id if fact.area_id in known_areas else "prog-foundations"
                connection.execute(
                    """INSERT INTO knowledge_area_chunks(area_id,chunk_id,relevance,reason)
                       VALUES(?,?,1.0,'facto original curado') ON CONFLICT(area_id,chunk_id)
                       DO UPDATE SET relevance=1.0,reason=excluded.reason""", (area_id, str(chunk_id)),
                )
                connection.execute(
                    """INSERT OR IGNORE INTO chunk_quality(chunk_id,status,score,reason,audited_at)
                       VALUES(?,'accepted',1.0,'conteúdo original Aprendix',?)""", (str(chunk_id), now),
                )
                card_blob = self._cipher.encrypt(body_text.encode(), associated_data=f"theory_cards.body:{card_id}".encode())
                connection.execute(
                    """INSERT OR IGNORE INTO theory_cards(id,chunk_id,title,body_encrypted,
                       complexity,created_at) VALUES(?,?,'Sabias que?',? ,?,?)""",
                    (str(card_id), str(chunk_id), card_blob, fact.complexity, now),
                )
        with self._cache_lock:
            self._candidate_cache_key = None
            self._candidate_cache = ()
        return len(ALL_FACTS)

    def rebuild_public_fts(self, *, force: bool = False) -> int:
        """Index only content explicitly licensed for plaintext full-text search."""
        with self._database.read_connection() as connection:
            indexed = int(connection.execute(
                "SELECT count(*) FROM search_fts_public"
            ).fetchone()[0])
            if not force:
                eligible = int(connection.execute(
                    """SELECT count(*) FROM document_chunks c
                       JOIN documents d ON d.id=c.document_id
                       JOIN document_provenance p ON p.document_id=d.id
                       LEFT JOIN chunk_quality q ON q.chunk_id=c.id
                       WHERE d.lifecycle='active' AND p.rights_status='permitted'
                         AND COALESCE(q.status,'accepted')='accepted'"""
                ).fetchone()[0])
                if indexed == eligible:
                    return indexed
            rows = connection.execute(
                """SELECT c.id,c.text_encrypted,
                          COALESCE(NULLIF(c.section,''),d.title) title
                   FROM document_chunks c
                   JOIN documents d ON d.id=c.document_id
                   JOIN document_provenance p ON p.document_id=d.id
                   LEFT JOIN chunk_quality q ON q.chunk_id=c.id
                   WHERE d.lifecycle='active' AND p.rights_status='permitted'
                     AND COALESCE(q.status,'accepted')='accepted'
                   ORDER BY c.id"""
            ).fetchall()
        values = []
        for row in rows:
            body = self._cipher.decrypt(
                row["text_encrypted"],
                associated_data=f"document_chunks.text:{row['id']}".encode(),
            ).decode("utf-8", errors="replace")
            values.append((row["id"], row["title"], body))
        with self._database.transaction() as connection:
            connection.execute("DELETE FROM search_fts_public")
            connection.executemany(
                "INSERT INTO search_fts_public(chunk_id,title,body) VALUES(?,?,?)", values
            )
        return len(values)

    def public_lexical_scores(self, query: str, *, limit: int = 240) -> dict[str, float]:
        """Return normalized BM25F scores from the rights-safe persistent index."""
        tokens = tuple(dict.fromkeys(re.findall(
            r"[a-z0-9_+#.-]{2,}",
            unicodedata.normalize("NFKD", query).encode("ascii", "ignore").decode().casefold(),
        )))[:24]
        if not tokens:
            return {}
        expression = " OR ".join('"' + token.replace('"', '""') + '"' for token in tokens)
        try:
            with self._database.read_connection() as connection:
                rows = connection.execute(
                    """SELECT chunk_id,bm25(search_fts_public,0.0,5.0,1.0) score
                       FROM search_fts_public WHERE search_fts_public MATCH ?
                       ORDER BY score LIMIT ?""",
                    (expression, max(1, min(limit, 1000))),
                ).fetchall()
        except Exception as exc:
            if "fts5" not in str(exc).casefold() and "syntax" not in str(exc).casefold():
                raise
            return {}
        if not rows:
            return {}
        magnitudes = [max(0.0, -float(row["score"])) for row in rows]
        maximum = max(magnitudes) or 1.0
        return {
            row["chunk_id"]: max(0.0, -float(row["score"])) / maximum
            for row in rows
        }

    @staticmethod
    def _search_tokens(text: str) -> tuple[str, ...]:
        folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().casefold()
        return tuple(re.findall(
            r"__[a-z0-9_]+__|[a-z][a-z0-9_+#.-]*|==|!=|<=|>=|//|\*\*|[%+*/-]",
            folded,
        ))

    @staticmethod
    def _lsh_signatures(vector: tuple[int, ...]) -> tuple[tuple[int, int], ...]:
        if not vector:
            return ()
        signatures = []
        for band in range(8):
            bucket = 0
            for bit in range(6):
                projection = 0
                seed = hashlib.blake2b(f"{band}:{bit}".encode(), digest_size=32).digest()
                for offset in range(0, 32, 2):
                    dimension = int.from_bytes(seed[offset:offset + 2], "little") % len(vector)
                    sign = 1 if seed[offset] & 1 else -1
                    projection += sign * vector[dimension]
                if projection >= 0:
                    bucket |= 1 << bit
            signatures.append((band, bucket))
        return tuple(signatures)

    @staticmethod
    def _bloom_filter(digests: tuple[bytes, ...]) -> bytes:
        bits = bytearray(256)
        for digest in digests:
            for offset in (0, 2, 4):
                position = int.from_bytes(digest[offset:offset + 2], "little") % 2048
                bits[position // 8] |= 1 << (position % 8)
        return bytes(bits)

    @staticmethod
    def _bloom_contains(payload: bytes, digest: bytes) -> bool:
        return all(
            payload[(position := int.from_bytes(digest[offset:offset + 2], "little") % 2048) // 8]
            & (1 << (position % 8))
            for offset in (0, 2, 4)
        )

    def rebuild_private_search_index(self, *, force: bool = False) -> int:
        """Build compact keyed Bloom filters and coarse keyed semantic buckets."""
        version = "blind-bloom-lsh-v3"
        with self._database.read_connection() as connection:
            eligible = int(connection.execute(
                """SELECT count(*) FROM document_chunks c
                   JOIN documents d ON d.id=c.document_id
                   JOIN chunk_embeddings e ON e.chunk_id=c.id
                   LEFT JOIN chunk_quality q ON q.chunk_id=c.id
                   WHERE d.lifecycle='active'
                     AND COALESCE(q.status,'accepted')='accepted'"""
            ).fetchone()[0])
            indexed = int(connection.execute(
                "SELECT count(*) FROM private_search_filters WHERE algorithm_version=?",
                (version,),
            ).fetchone()[0])
            slice_count = int(connection.execute(
                "SELECT count(*) FROM private_search_bit_slices WHERE algorithm_version=?",
                (version,),
            ).fetchone()[0])
            if not force and indexed == eligible and slice_count == 4096:
                return indexed
            rows = connection.execute(
                """SELECT c.id,c.text_encrypted,COALESCE(NULLIF(c.section,''),d.title) title,
                          e.dimensions,e.vector_encrypted
                   FROM document_chunks c JOIN documents d ON d.id=c.document_id
                   JOIN chunk_embeddings e ON e.chunk_id=c.id
                   LEFT JOIN chunk_quality q ON q.chunk_id=c.id
                   WHERE d.lifecycle='active' AND COALESCE(q.status,'accepted')='accepted'
                   ORDER BY c.id"""
            ).fetchall()
        filter_rows, bucket_rows, states = [], [], []
        slice_width = max(1, (len(rows) + 7) // 8)
        bit_slices = [bytearray(slice_width) for _ in range(4096)]
        digest_cache: dict[str, bytes] = {}
        now = datetime.now(UTC).isoformat()
        for ordinal, row in enumerate(rows):
            body = self._cipher.decrypt(
                row["text_encrypted"],
                associated_data=f"document_chunks.text:{row['id']}".encode(),
            ).decode("utf-8", errors="replace")
            body_tokens = tuple(dict.fromkeys(
                token for token in self._search_tokens(body) if len(token) <= 64
            ))
            title_tokens = tuple(dict.fromkeys(
                token for token in self._search_tokens(row["title"]) if len(token) <= 64
            ))

            def digest(token: str) -> bytes:
                if token not in digest_cache:
                    digest_cache[token] = self._cipher.blind_index(
                        token.encode(), namespace=b"knowledge-search-term:v1"
                    )
                return digest_cache[token]

            body_digests = tuple(digest(token) for token in body_tokens)
            title_digests = tuple(digest(token) for token in title_tokens)
            body_filter = self._bloom_filter(body_digests)
            title_filter = self._bloom_filter(title_digests)
            for field_offset, digests in ((0, body_digests), (2048, title_digests)):
                for value in digests:
                    for offset in (0, 2, 4):
                        position = int.from_bytes(value[offset:offset + 2], "little") % 2048
                        bit_slices[field_offset + position][ordinal // 8] |= 1 << (ordinal % 8)
            filter_rows.append((
                row["id"], body_filter, title_filter,
                len(body_tokens), version, now,
            ))
            packed = self._cipher.decrypt(
                row["vector_encrypted"],
                associated_data=f"chunk_embeddings.vector:{row['id']}".encode(),
            )
            vector = tuple(struct.unpack(f"<{row['dimensions']}b", packed))
            for band, bucket in self._lsh_signatures(vector):
                digest = self._cipher.blind_index(
                    f"{band}:{bucket}".encode(), namespace=b"embedding-lsh:v1"
                )
                bucket_rows.append((digest, band, row["id"]))
            states.append((row["id"], version, now))
        with self._database.transaction() as connection:
            connection.execute("DELETE FROM blind_search_terms")
            connection.execute("DELETE FROM private_search_filters")
            connection.execute("DELETE FROM private_search_bit_slices")
            connection.execute("DELETE FROM private_search_chunk_ordinals")
            connection.execute("DELETE FROM embedding_lsh_buckets")
            connection.execute("DELETE FROM private_search_index_state")
            connection.executemany(
                "INSERT INTO private_search_filters VALUES(?,?,?,?,?,?)", filter_rows
            )
            connection.executemany(
                "INSERT INTO embedding_lsh_buckets VALUES(?,?,?)", bucket_rows
            )
            connection.executemany(
                "INSERT INTO private_search_index_state VALUES(?,?,?)", states
            )
            connection.executemany(
                "INSERT INTO private_search_chunk_ordinals VALUES(?,?)",
                ((ordinal, row["id"]) for ordinal, row in enumerate(rows)),
            )
            connection.executemany(
                "INSERT INTO private_search_bit_slices VALUES(?,?,?,?)",
                ((field, position, bytes(bit_slices[field * 2048 + position]), version)
                 for field in (0, 1) for position in range(2048)),
            )
        with self._cache_lock:
            self._blind_filter_cache = tuple(
                (row[0], row[1], row[2]) for row in filter_rows
            )
            self._blind_ordinals = tuple(row["id"] for row in rows)
            self._blind_slices = tuple(
                int.from_bytes(value, "little") for value in bit_slices
            )
        return len(states)

    def search_candidates_for_query(
        self, filters: SearchFiltersDTO, query: str, query_vector: tuple[int, ...], *,
        limit: int = 240,
    ) -> tuple[tuple[SearchCandidate, ...], dict[str, float]]:
        tokens = tuple(dict.fromkeys(self._search_tokens(query)))[:32]
        token_digests = tuple(
            self._cipher.blind_index(token.encode(), namespace=b"knowledge-search-term:v1")
            for token in tokens
        )
        scores: dict[str, float] = {}
        with self._cache_lock:
            ordinals, slices = self._blind_ordinals, self._blind_slices
        if not ordinals or len(slices) != 4096:
            with self._database.read_connection() as connection:
                ordinal_rows = connection.execute(
                    "SELECT ordinal,chunk_id FROM private_search_chunk_ordinals ORDER BY ordinal"
                ).fetchall()
                slice_rows = connection.execute(
                    """SELECT field,position,candidates FROM private_search_bit_slices
                       WHERE algorithm_version='blind-bloom-lsh-v3'
                       ORDER BY field,position"""
                ).fetchall()
            ordinals = tuple(row["chunk_id"] for row in ordinal_rows)
            loaded = [0] * 4096
            for row in slice_rows:
                loaded[int(row["field"]) * 2048 + int(row["position"])] = int.from_bytes(
                    row["candidates"], "little"
                )
            slices = tuple(loaded)
            with self._cache_lock:
                self._blind_ordinals, self._blind_slices = ordinals, slices
        lexical_masks: list[tuple[int, int, float]] = []
        for value in token_digests:
            positions = tuple(
                int.from_bytes(value[offset:offset + 2], "little") % 2048
                for offset in (0, 2, 4)
            )
            body_mask = slices[positions[0]] & slices[positions[1]] & slices[positions[2]]
            title_mask = (
                slices[2048 + positions[0]] & slices[2048 + positions[1]]
                & slices[2048 + positions[2]]
            )
            if body_mask:
                lexical_masks.append((body_mask.bit_count(), body_mask, 1.0))
            if title_mask:
                lexical_masks.append((title_mask.bit_count(), title_mask, 5.0))
        # Expanded queries may contain dozens of very common aliases. Iterating
        # every matching bit in a large personal library creates latency without
        # improving the bounded shortlist. Rare signals carry more information,
        # so enumerate those first and retain a deterministic upper bound.
        maximum_masks = min(16, max(8, len(token_digests)))
        maximum_matches = max(2_000, limit * 24)
        for count, mask, weight in sorted(lexical_masks, key=lambda item: item[0])[:maximum_masks]:
            if count > maximum_matches:
                continue
            while mask:
                lowest = mask & -mask
                ordinal = lowest.bit_length() - 1
                if ordinal < len(ordinals):
                    identity = ordinals[ordinal]
                    scores[identity] = scores.get(identity, 0.0) + weight
                mask ^= lowest
        with self._database.read_connection() as connection:
            signatures = self._lsh_signatures(query_vector)
            if signatures:
                clauses, parameters = [], []
                for band, bucket in signatures:
                    clauses.append("(band=? AND bucket_digest=?)")
                    parameters.extend((band, self._cipher.blind_index(
                        f"{band}:{bucket}".encode(), namespace=b"embedding-lsh:v1"
                    )))
                rows = connection.execute(
                    """SELECT chunk_id,count(*) matches FROM embedding_lsh_buckets WHERE """
                    + " OR ".join(clauses)
                    + " GROUP BY chunk_id ORDER BY matches DESC LIMIT ?",
                    (*parameters, max(1, min(limit, 1000))),
                ).fetchall()
                for row in rows:
                    scores[row["chunk_id"]] = scores.get(row["chunk_id"], 0.0) + 2.0 * row["matches"]
        public = self.public_lexical_scores(query, limit=limit)
        for identity, score in public.items():
            scores[identity] = scores.get(identity, 0.0) + 8.0 * score
        ordered = sorted(scores, key=lambda identity: (-scores[identity], identity))[:limit]
        maximum = max((scores[item] for item in ordered), default=1.0)
        normalized = {item: min(1.0, scores[item] / max(1.0, maximum)) for item in ordered}
        return self.search_candidates(filters, limit=limit, candidate_ids=tuple(ordered)), normalized

    def store_document(
        self,
        document: IndexedDocument,
        chunks: tuple[IndexedChunk, ...],
        *,
        quarantine: bool = False,
    ) -> tuple[bool, int, int]:
        """Replace one path revision; return created, card count, exercise count."""

        if not chunks:
            return False, 0, 0
        if any(len(chunk.embedding) != len(chunks[0].embedding) for chunk in chunks):
            raise ValueError("all chunk embeddings must have equal dimensions")
        now = datetime.now(UTC).isoformat()
        cards = 0
        exercises = 0
        with self._database.transaction() as connection:
            known_areas = {
                row[0] for row in connection.execute("SELECT id FROM knowledge_areas")
            }
            duplicate = connection.execute(
                "SELECT id FROM documents WHERE content_hash = ?",
                (document.content_hash,),
            ).fetchone()
            if duplicate is not None:
                return False, 0, 0
            previous = connection.execute(
                "SELECT id FROM documents WHERE source_path=? AND lifecycle='active'",
                (document.source_path,),
            ).fetchone()
            stored_path = document.source_path
            if previous is not None and not quarantine:
                connection.execute(
                    "UPDATE content_revisions SET status='retired' WHERE document_id=?",
                    (previous["id"],),
                )
                connection.execute(
                    "UPDATE documents SET source_path=?,lifecycle='retired' WHERE id=?",
                    (f"aprendix://revision/{previous['id']}", previous["id"]),
                )
            elif previous is not None:
                stored_path = f"aprendix://staging/{document.id}"
            lifecycle = "staging" if quarantine else "active"
            connection.execute(
                """
                INSERT INTO documents(
                    id, source_path, content_hash, title, author, content_type,
                    complexity, published_at, page_count, file_size, modified_at,
                    ingested_at, lifecycle
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(document.id), stored_path, document.content_hash,
                    document.title, document.author, document.content_type.value,
                    document.complexity.value,
                    document.published_at.isoformat() if document.published_at else None,
                    document.page_count, document.file_size,
                    document.modified_at.astimezone(UTC).isoformat(), now, lifecycle,
                ),
            )
            sequence = int(connection.execute(
                "SELECT COALESCE(max(sequence),0)+1 FROM content_revisions WHERE logical_source=?",
                (document.source_path,),
            ).fetchone()[0])
            revision_id = uuid5(NAMESPACE_URL, f"aprendix:revision:{document.id}")
            connection.execute(
                "INSERT INTO content_revisions VALUES(?,?,?,?,?,?,?,?)",
                (str(revision_id), document.source_path, str(document.id),
                 document.content_hash, sequence, lifecycle, now,
                 now if lifecycle == "active" else None),
            )
            connection.execute(
                """INSERT INTO document_provenance VALUES(?,?,?,?,?,?,?,?,?)""",
                (str(document.id), document.source_adapter_id, document.source_path,
                 document.canonical_uri, document.license_id, document.rights_status,
                 document.content_version, document.trust_score, now),
            )
            for chunk in chunks:
                vector_bytes = struct.pack(f"<{len(chunk.embedding)}b", *chunk.embedding)
                norm = math.sqrt(sum(value * value for value in chunk.embedding))
                if norm <= 0 or not math.isfinite(norm):
                    raise ValueError("embedding must have a positive finite norm")
                text_blob = self._cipher.encrypt(
                    chunk.text.encode("utf-8"),
                    associated_data=f"document_chunks.text:{chunk.id}".encode(),
                )
                vector_blob = self._cipher.encrypt(
                    vector_bytes,
                    associated_data=f"chunk_embeddings.vector:{chunk.id}".encode(),
                )
                graph_node_id = None
                if chunk.graph_node_slug:
                    graph_node_id = str(
                        uuid5(NAMESPACE_URL, f"aprendix:ingested-node:{chunk.graph_node_slug}")
                    )
                    difficulty = {
                        Complexity.BEGINNER: -1.0,
                        Complexity.INTERMEDIATE: 0.25,
                        Complexity.ADVANCED: 1.25,
                    }[document.complexity]
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO graph_nodes(
                            id, slug, title, description, difficulty, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            graph_node_id, chunk.graph_node_slug,
                            chunk.section[:160] or document.title[:160],
                            f"Conteúdo local: {document.title}"[:4000],
                            difficulty, now, now,
                        ),
                    )
                connection.execute(
                    """
                    INSERT INTO document_chunks(
                        id, document_id, ordinal, page_number, section, chunk_type,
                        text_encrypted, token_count, graph_node_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(chunk.id), str(document.id), chunk.ordinal,
                        chunk.page_number, chunk.section[:500], chunk.content_type.value,
                        text_blob, max(1, len(chunk.text.split())), graph_node_id, now,
                    ),
                )
                technologies, themes = TaxonomyClassifier.classify(
                    f"{chunk.section} {chunk.text}"
                )
                connection.execute(
                    """
                    INSERT INTO knowledge_taxonomy(chunk_id, technologies_json, themes_json, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        str(chunk.id),
                        json.dumps([item.value for item in technologies], separators=(",", ":")),
                        json.dumps([item.value for item in themes], separators=(",", ":")),
                        now,
                    ),
                )
                for area_id, relevance, reason in classify_areas(
                    f"{chunk.section} {chunk.text}"
                ):
                    if area_id not in known_areas:
                        continue
                    connection.execute(
                        """INSERT INTO knowledge_area_chunks(area_id,chunk_id,relevance,reason)
                        VALUES(?,?,?,?) ON CONFLICT(area_id,chunk_id) DO UPDATE SET
                        relevance=excluded.relevance,reason=excluded.reason""",
                        (area_id, str(chunk.id), relevance, reason),
                    )
                connection.execute(
                    """
                    INSERT INTO chunk_embeddings(
                        chunk_id, model_id, dimensions, vector_encrypted, norm, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(chunk.id), chunk.model_id, len(chunk.embedding),
                        vector_blob, norm, now,
                    ),
                )
                if chunk.content_type is ContentKind.EXERCISE and graph_node_id:
                    exercise_id = uuid5(NAMESPACE_URL, f"aprendix:ingested-exercise:{chunk.id}")
                    slug = f"local-{chunk.id.hex[:20]}"
                    title = (chunk.section or chunk.text.splitlines()[0])[:160]
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO exercises(
                            id, graph_node_id, slug, title, prompt, starter_code,
                            tests_json, difficulty, version, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, '', '[]', ?, 1, ?, ?)
                        """,
                        (
                            str(exercise_id), graph_node_id, slug, title,
                            chunk.text[:20000],
                            {
                                Complexity.BEGINNER: -1.0,
                                Complexity.INTERMEDIATE: 0.25,
                                Complexity.ADVANCED: 1.25,
                            }[document.complexity],
                            now, now,
                        ),
                    )
                    connection.execute(
                        "INSERT OR IGNORE INTO exercise_sources(exercise_id, chunk_id) VALUES (?, ?)",
                        (str(exercise_id), str(chunk.id)),
                    )
                    exercises += 1
                else:
                    card_id = uuid5(NAMESPACE_URL, f"aprendix:theory-card:{chunk.id}")
                    body = self._cipher.encrypt(
                        chunk.text[:20000].encode("utf-8"),
                        associated_data=f"theory_cards.body:{card_id}".encode(),
                    )
                    connection.execute(
                        """
                        INSERT INTO theory_cards(
                            id, chunk_id, graph_node_id, title, body_encrypted,
                            image_path, complexity, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(card_id), str(chunk.id), graph_node_id,
                            (chunk.section or document.title)[:240], body,
                            chunk.image_path,
                            document.complexity.value, now,
                        ),
                    )
                    cards += 1
        with self._cache_lock:
            self._candidate_cache_key = None
            self._candidate_cache = ()
        return True, cards, exercises

    def search_candidates(
        self,
        filters: SearchFiltersDTO,
        *,
        limit: int = 50_000,
        candidate_ids: tuple[str, ...] = (),
    ) -> tuple[SearchCandidate, ...]:
        cache_key = filters.model_dump_json()
        with self._cache_lock:
            if not candidate_ids and self._candidate_cache_key == cache_key:
                return self._candidate_cache[: max(1, min(limit, 100_000))]
        clauses: list[str] = [
            "d.lifecycle = 'active'", "COALESCE(q.status, 'accepted') = 'accepted'"
        ]
        parameters: list[object] = []
        if candidate_ids:
            placeholders = ",".join("?" for _ in candidate_ids)
            clauses.append(f"c.id IN ({placeholders})")
            parameters.extend(candidate_ids)
        if filters.content_types:
            placeholders = ",".join("?" for _ in filters.content_types)
            clauses.append(f"c.chunk_type IN ({placeholders})")
            parameters.extend(item.value for item in filters.content_types)
        if filters.complexities:
            placeholders = ",".join("?" for _ in filters.complexities)
            clauses.append(f"d.complexity IN ({placeholders})")
            parameters.extend(item.value for item in filters.complexities)
        if filters.published_from:
            clauses.append("d.published_at >= ?")
            parameters.append(filters.published_from.isoformat())
        if filters.published_to:
            clauses.append("d.published_at <= ?")
            parameters.append(filters.published_to.isoformat())
        if filters.technologies:
            placeholders = ",".join("?" for _ in filters.technologies)
            clauses.append(
                f"EXISTS (SELECT 1 FROM json_each(COALESCE(t.technologies_json, '[]')) "
                f"WHERE value IN ({placeholders}))"
            )
            parameters.extend(item.value for item in filters.technologies)
        if filters.themes:
            placeholders = ",".join("?" for _ in filters.themes)
            clauses.append(
                f"EXISTS (SELECT 1 FROM json_each(COALESCE(t.themes_json, '[]')) "
                f"WHERE value IN ({placeholders}))"
            )
            parameters.extend(item.value for item in filters.themes)
        if filters.cluster_ids:
            placeholders = ",".join("?" for _ in filters.cluster_ids)
            clauses.append(f"cm.cluster_id IN ({placeholders})")
            parameters.extend(filters.cluster_ids)
        if filters.area_ids:
            area_ids = tuple(dict.fromkeys(
                area for selected in filters.area_ids
                for area in (selected, *descendants(selected))
            ))
            placeholders = ",".join("?" for _ in area_ids)
            clauses.append(
                f"EXISTS (SELECT 1 FROM knowledge_area_chunks kac "
                f"WHERE kac.chunk_id=c.id AND kac.area_id IN ({placeholders}))"
            )
            parameters.extend(area_ids)
        if filters.sources:
            source_clauses = []
            for source in filters.sources:
                source_clauses.append("(d.source_path LIKE ? OR p.logical_source LIKE ?)")
                pattern = f"%{source.strip()}%"
                parameters.extend((pattern, pattern))
            clauses.append("(" + " OR ".join(source_clauses) + ")")
        if filters.content_versions:
            placeholders = ",".join("?" for _ in filters.content_versions)
            clauses.append(f"p.content_version IN ({placeholders})")
            parameters.extend(filters.content_versions)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        # The knowledge fields are encrypted at rest, so ranking must happen
        # after decryption in the application layer.  Keep the default large
        # enough to cover a realistically populated personal library instead
        # of silently excluding the newest imported material.
        parameters.append(max(1, min(limit, 100_000)))
        with self._database.read_connection() as connection:
            rows = connection.execute(
                f"""
                SELECT c.id, c.text_encrypted, c.page_number, d.title, c.section, d.source_path,
                       d.author, d.content_type, d.complexity, d.published_at,
                       e.dimensions, e.vector_encrypted,
                       t.technologies_json, t.themes_json, cm.cluster_id,
                       COALESCE(p.rights_status,'local-private') rights_status,
                       COALESCE(p.trust_score,0.8) trust_score
                FROM document_chunks c
                JOIN documents d ON d.id = c.document_id
                JOIN chunk_embeddings e ON e.chunk_id = c.id
                LEFT JOIN knowledge_taxonomy t ON t.chunk_id = c.id
                LEFT JOIN knowledge_cluster_members cm ON cm.chunk_id = c.id
                LEFT JOIN document_provenance p ON p.document_id = d.id
                LEFT JOIN chunk_quality q ON q.chunk_id = c.id
                {where}
                ORDER BY d.title, c.ordinal
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        candidates: list[SearchCandidate] = []
        for row in rows:
            chunk_id = UUID(row["id"])
            text = self._cipher.decrypt(
                row["text_encrypted"],
                associated_data=f"document_chunks.text:{chunk_id}".encode(),
            ).decode("utf-8")
            packed = self._cipher.decrypt(
                row["vector_encrypted"],
                associated_data=f"chunk_embeddings.vector:{chunk_id}".encode(),
            )
            embedding = struct.unpack(f"<{row['dimensions']}b", packed)
            technologies = tuple(Technology(item) for item in json.loads(row["technologies_json"] or "[]"))
            themes = tuple(LearningTheme(item) for item in json.loads(row["themes_json"] or "[]"))
            if not technologies or not themes:
                inferred_technologies, inferred_themes = TaxonomyClassifier.classify(
                    f"{row['title']} {text}"
                )
                technologies = technologies or inferred_technologies
                themes = themes or inferred_themes
            candidates.append(
                SearchCandidate(
                    chunk_id=chunk_id,
                    title=(
                        f"{row['title']} · {row['section']}"[:500]
                        if row["section"] else row["title"]
                    ), source_path=row["source_path"],
                    author=row["author"],
                    content_type=ContentKind(row["content_type"]),
                    complexity=Complexity(row["complexity"]),
                    published_at=date.fromisoformat(row["published_at"])
                    if row["published_at"] else None,
                    page_number=row["page_number"], text=text,
                    embedding=tuple(embedding),
                    technologies=technologies, themes=themes,
                    cluster_id=row["cluster_id"],
                    rights_status=row["rights_status"], trust_score=row["trust_score"],
                )
            )
        result = tuple(candidates)
        if not candidate_ids:
            with self._cache_lock:
                self._candidate_cache_key = cache_key
                self._candidate_cache = result
        return result

    def list_theory_cards(
        self, *, limit: int = 30, technology: Technology | None = None,
        theme: LearningTheme | None = None, cluster_id: str | None = None,
        area_id: str | None = None, authored_only: bool = False,
    ) -> tuple[TheoryCardDTO, ...]:
        clauses: list[str] = [
            "d.lifecycle = 'active'", "COALESCE(q.status, 'accepted') = 'accepted'"
        ]
        parameters: list[object] = []
        if authored_only:
            clauses.append("d.source_path = 'aprendix://authored-facts/v1'")
        if technology is not None:
            clauses.append("EXISTS (SELECT 1 FROM json_each(COALESCE(kt.technologies_json, '[]')) WHERE value = ?)")
            parameters.append(technology.value)
        if theme is not None:
            clauses.append("EXISTS (SELECT 1 FROM json_each(COALESCE(kt.themes_json, '[]')) WHERE value = ?)")
            parameters.append(theme.value)
        if cluster_id:
            clauses.append("cm.cluster_id = ?")
            parameters.append(cluster_id)
        if area_id:
            area_ids = (area_id, *descendants(area_id))
            placeholders = ",".join("?" for _ in area_ids)
            clauses.append(
                f"EXISTS (SELECT 1 FROM knowledge_area_chunks kac "
                f"WHERE kac.chunk_id=dc.id AND kac.area_id IN ({placeholders}))"
            )
            parameters.extend(area_ids)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.append(max(1, min(limit, 200)))
        with self._database.read_connection() as connection:
            rows = connection.execute(
                f"""
                SELECT tc.*, d.title AS source_title, dc.page_number,
                       kt.technologies_json, kt.themes_json, cm.cluster_id,
                       (SELECT group_concat(area_id) FROM knowledge_area_chunks
                        WHERE chunk_id=dc.id) AS area_ids
                FROM theory_cards tc
                JOIN document_chunks dc ON dc.id = tc.chunk_id
                JOIN documents d ON d.id = dc.document_id
                LEFT JOIN knowledge_taxonomy kt ON kt.chunk_id = dc.id
                LEFT JOIN knowledge_cluster_members cm ON cm.chunk_id = dc.id
                LEFT JOIN chunk_quality q ON q.chunk_id = dc.id
                {where}
                ORDER BY tc.created_at DESC, tc.id
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        cards: list[TheoryCardDTO] = []
        for row in rows:
            card_id = UUID(row["id"])
            body = self._cipher.decrypt(
                row["body_encrypted"],
                associated_data=f"theory_cards.body:{card_id}".encode(),
            ).decode("utf-8")
            code = ""
            if row["code_example_encrypted"] is not None:
                code = self._cipher.decrypt(
                    row["code_example_encrypted"],
                    associated_data=f"theory_cards.code:{card_id}".encode(),
                ).decode("utf-8")
            cards.append(
                TheoryCardDTO(
                    id=card_id, title=row["title"], body=body,
                    complexity=Complexity(row["complexity"]),
                    code_example=code, image_path=row["image_path"],
                    source_title=row["source_title"], source_page=row["page_number"],
                    graph_node_id=UUID(row["graph_node_id"])
                    if row["graph_node_id"] else None,
                    technologies=tuple(Technology(item) for item in json.loads(row["technologies_json"] or "[]")),
                    themes=tuple(LearningTheme(item) for item in json.loads(row["themes_json"] or "[]")),
                    cluster_id=row["cluster_id"],
                    area_ids=tuple((row["area_ids"] or "").split(",")) if row["area_ids"] else (),
                )
            )
        return tuple(cards)

    def cluster_inputs(self) -> tuple[ClusterInput, ...]:
        with self._database.read_connection() as connection:
            rows = connection.execute(
                """
                SELECT c.id, c.text_encrypted, d.title, e.dimensions, e.vector_encrypted
                FROM document_chunks c
                JOIN documents d ON d.id = c.document_id
                JOIN chunk_embeddings e ON e.chunk_id = c.id
                LEFT JOIN chunk_quality q ON q.chunk_id = c.id
                WHERE d.lifecycle = 'active'
                  AND COALESCE(q.status, 'accepted') = 'accepted'
                ORDER BY c.id
                """
            ).fetchall()
        result = []
        for row in rows:
            chunk_id = UUID(row["id"])
            body = self._cipher.decrypt(
                row["text_encrypted"],
                associated_data=f"document_chunks.text:{chunk_id}".encode(),
            ).decode("utf-8")
            packed = self._cipher.decrypt(
                row["vector_encrypted"],
                associated_data=f"chunk_embeddings.vector:{chunk_id}".encode(),
            )
            result.append(ClusterInput(
                chunk_id=chunk_id, title=row["title"], text=body,
                embedding=tuple(struct.unpack(f"<{row['dimensions']}b", packed)),
            ))
        return tuple(result)

    def replace_clusters(
        self, assignments: tuple[ClusterAssignment, ...], labels: dict[str, str]
    ) -> None:
        now = datetime.now(UTC).isoformat()
        counts = Counter(item.cluster_id for item in assignments)
        with self._database.transaction() as connection:
            connection.execute("DELETE FROM knowledge_cluster_members")
            connection.execute("DELETE FROM knowledge_clusters")
            for cluster_id in sorted(labels):
                connection.execute(
                    """INSERT INTO knowledge_clusters(
                        id, label, model_id, member_count, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)""",
                    (cluster_id, labels[cluster_id], "aprendix-hdbscan-v1", counts[cluster_id], now, now),
                )
            for item in assignments:
                connection.execute(
                    """INSERT INTO knowledge_cluster_members(chunk_id, cluster_id, probability)
                    VALUES (?, ?, ?)""",
                    (str(item.chunk_id), item.cluster_id, item.probability),
                )
                connection.execute(
                    """INSERT INTO knowledge_taxonomy(chunk_id, technologies_json, themes_json, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(chunk_id) DO UPDATE SET technologies_json=excluded.technologies_json,
                        themes_json=excluded.themes_json, updated_at=excluded.updated_at""",
                    (
                        str(item.chunk_id),
                        json.dumps([value.value for value in item.technologies], separators=(",", ":")),
                        json.dumps([value.value for value in item.themes], separators=(",", ":")), now,
                    ),
                )
        with self._cache_lock:
            self._candidate_cache_key = None
            self._candidate_cache = ()

    def list_clusters(
        self, *, cluster_ids: tuple[str, ...] = (), limit: int = 30
    ) -> tuple[KnowledgeClusterDTO, ...]:
        clauses = ""
        parameters: list[object] = []
        if cluster_ids:
            placeholders = ",".join("?" for _ in cluster_ids)
            clauses = f"WHERE id IN ({placeholders})"
            parameters.extend(cluster_ids)
        parameters.append(max(1, min(limit, 100)))
        with self._database.read_connection() as connection:
            rows = connection.execute(
                f"SELECT id, label, member_count FROM knowledge_clusters {clauses} ORDER BY member_count DESC, id LIMIT ?",
                parameters,
            ).fetchall()
        return tuple(KnowledgeClusterDTO(
            id=row["id"], label=row["label"], member_count=row["member_count"]
        ) for row in rows)

    def record_run(self, summary: IngestionSummaryDTO) -> None:
        errors = json.dumps(summary.errors, ensure_ascii=False).encode("utf-8")
        encrypted = self._cipher.encrypt(
            errors, associated_data=f"ingestion_runs.errors:{summary.run_id}".encode()
        ) if errors else None
        status = "completed" if summary.failed_documents == 0 else "partial"
        with self._database.transaction() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO ingestion_runs(
                    id, started_at, completed_at, status, discovered_files,
                    indexed_documents, skipped_documents, failed_documents,
                    chunks, theory_cards, exercises, errors_encrypted
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(summary.run_id), summary.started_at.isoformat(),
                    summary.completed_at.isoformat() if summary.completed_at else None,
                    status, summary.discovered_files, summary.indexed_documents,
                    summary.skipped_documents, summary.failed_documents,
                    summary.chunks, summary.theory_cards, summary.exercises, encrypted,
                ),
            )
