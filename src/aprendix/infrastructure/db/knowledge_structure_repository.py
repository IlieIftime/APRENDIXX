"""SQLite repository for the hierarchical catalogue and assisted reader."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from aprendix.application.contracts import (
    Complexity,
    CuratedSourceDTO,
    KnowledgeAreaDTO,
    ReadingConceptDTO,
    ReadingDetailDTO,
    SearchShortcutDTO,
)
from aprendix.application.knowledge_structure import (
    AREAS,
    SOURCES,
    PedagogicalReadingAssistant,
    ancestors,
    area_depths,
    classify_areas,
    descendants,
    fold,
)


class KnowledgeStructureRepository:
    def __init__(self, database, cipher) -> None:
        self._database = database
        self._cipher = cipher

    def seed(self) -> None:
        depths = area_depths()
        with self._database.transaction() as connection:
            for order, area in enumerate(AREAS):
                connection.execute(
                    """INSERT INTO knowledge_areas(
                        id,parent_id,slug,title,description,depth,position,icon,recommended_order
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET parent_id=excluded.parent_id,
                        title=excluded.title,description=excluded.description,
                        depth=excluded.depth,position=excluded.position,icon=excluded.icon,
                        recommended_order=excluded.recommended_order""",
                    (area.id, area.parent_id, area.id, area.title, area.description,
                     depths[area.id], area.position, area.icon, order),
                )
                for shortcut_index, query in enumerate(self._shortcut_queries(area), start=0):
                    shortcut_id = f"shortcut:{area.id}:{shortcut_index}"
                    connection.execute(
                        """INSERT INTO search_shortcuts(id,area_id,label,query,position)
                        VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                        label=excluded.label,query=excluded.query,position=excluded.position""",
                        (shortcut_id, area.id, query[0], query[1], shortcut_index),
                    )
            for source in SOURCES:
                connection.execute(
                    """INSERT INTO curated_sources(
                        id,title,authors_json,publication_year,source_type,canonical_url,
                        doi,overview,why_it_matters,access_note,license_note,provenance
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET title=excluded.title,
                        authors_json=excluded.authors_json,publication_year=excluded.publication_year,
                        source_type=excluded.source_type,canonical_url=excluded.canonical_url,
                        doi=excluded.doi,overview=excluded.overview,
                        why_it_matters=excluded.why_it_matters,access_note=excluded.access_note,
                        license_note=excluded.license_note,provenance=excluded.provenance""",
                    (source.id, source.title, json.dumps(source.authors, ensure_ascii=False),
                     source.year, source.source_type, source.url, source.doi,
                     source.overview, source.why, source.access_note,
                     source.license_note, source.provenance),
                )
                for position, area_id in enumerate(source.area_ids):
                    connection.execute(
                        """INSERT INTO knowledge_area_sources(area_id,source_id,position)
                        VALUES(?,?,?) ON CONFLICT(area_id,source_id) DO UPDATE SET
                        position=excluded.position""",
                        (area_id, source.id, position),
                    )

    @staticmethod
    def _shortcut_queries(area) -> tuple[tuple[str, str], ...]:
        keyword = area.keywords[0] if area.keywords else area.title
        return (
            (f"Começar: {area.title}", f"fundamentos de {keyword} com exemplo"),
            (f"Aprofundar: {area.title}", f"algoritmos métodos e limitações de {keyword}"),
        )

    def ensure_mappings(self, candidates) -> int:
        with self._database.read_connection() as connection:
            mapped = int(connection.execute("""SELECT count(DISTINCT kac.chunk_id)
                FROM knowledge_area_chunks kac LEFT JOIN chunk_quality q ON q.chunk_id=kac.chunk_id
                WHERE COALESCE(q.status,'accepted')='accepted'""").fetchone()[0])
            total = int(connection.execute("""SELECT count(*) FROM document_chunks c
                LEFT JOIN chunk_quality q ON q.chunk_id=c.id
                WHERE COALESCE(q.status,'accepted')='accepted'""").fetchone()[0])
        if mapped == total and total > 0:
            return mapped
        assignments: list[tuple[str, str, float, str]] = []
        for item in candidates:
            text = item.text[:8_000]
            for area_id, relevance, reason in classify_areas(text):
                assignments.append((area_id, str(item.chunk_id), relevance, reason))
        with self._database.transaction() as connection:
            connection.execute("DELETE FROM knowledge_area_chunks")
            connection.executemany(
                "INSERT INTO knowledge_area_chunks(area_id,chunk_id,relevance,reason) VALUES(?,?,?,?)",
                assignments,
            )
        return total

    def mappings_current(self) -> bool:
        with self._database.read_connection() as connection:
            mapped = int(connection.execute("""SELECT count(DISTINCT kac.chunk_id)
                FROM knowledge_area_chunks kac LEFT JOIN chunk_quality q ON q.chunk_id=kac.chunk_id
                WHERE COALESCE(q.status,'accepted')='accepted'""").fetchone()[0])
            total = int(connection.execute("""SELECT count(*) FROM document_chunks c
                LEFT JOIN chunk_quality q ON q.chunk_id=c.id
                WHERE COALESCE(q.status,'accepted')='accepted'""").fetchone()[0])
        return mapped == total

    @staticmethod
    def expand_area_ids(area_ids: tuple[str, ...]) -> tuple[str, ...]:
        expanded: list[str] = []
        for area_id in area_ids:
            expanded.extend((area_id, *descendants(area_id)))
        return tuple(dict.fromkeys(expanded))

    def areas(self) -> tuple[KnowledgeAreaDTO, ...]:
        with self._database.read_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM knowledge_areas ORDER BY recommended_order,id"
            ).fetchall()
            direct_cards = dict(connection.execute(
                """SELECT kac.area_id,count(DISTINCT tc.id)
                FROM knowledge_area_chunks kac JOIN theory_cards tc ON tc.chunk_id=kac.chunk_id
                LEFT JOIN chunk_quality q ON q.chunk_id=kac.chunk_id
                WHERE COALESCE(q.status,'accepted')='accepted'
                GROUP BY kac.area_id"""
            ).fetchall())
            direct_sources = dict(connection.execute(
                "SELECT area_id,count(*) FROM knowledge_area_sources GROUP BY area_id"
            ).fetchall())
        result = []
        for row in rows:
            related = (row["id"], *descendants(row["id"]))
            result.append(KnowledgeAreaDTO(
                id=row["id"], parent_id=row["parent_id"], slug=row["slug"],
                title=row["title"], description=row["description"], depth=row["depth"],
                position=row["position"], icon=row["icon"],
                recommended_order=row["recommended_order"],
                card_count=sum(int(direct_cards.get(item, 0)) for item in related),
                source_count=sum(int(direct_sources.get(item, 0)) for item in related),
            ))
        return tuple(result)

    def shortcuts(self, area_id: str | None = None, *, limit: int = 20) -> tuple[SearchShortcutDTO, ...]:
        expanded = self.expand_area_ids((area_id,)) if area_id else ()
        parameters: list[object] = []
        where = ""
        if expanded:
            where = "WHERE area_id IN (" + ",".join("?" for _ in expanded) + ")"
            parameters.extend(expanded)
        parameters.append(max(1, min(limit, 100)))
        with self._database.read_connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM search_shortcuts {where} ORDER BY position,id LIMIT ?",
                parameters,
            ).fetchall()
        return tuple(SearchShortcutDTO(**dict(row)) for row in rows)

    def sources(self, area_ids: tuple[str, ...] = (), *, limit: int = 20) -> tuple[CuratedSourceDTO, ...]:
        expanded = self.expand_area_ids(area_ids)
        parameters: list[object] = []
        where = ""
        if expanded:
            where = "WHERE kas.area_id IN (" + ",".join("?" for _ in expanded) + ")"
            parameters.extend(expanded)
        parameters.append(max(1, min(limit, 100)))
        with self._database.read_connection() as connection:
            rows = connection.execute(
                f"""SELECT cs.*,group_concat(DISTINCT kas.area_id) area_ids
                FROM curated_sources cs JOIN knowledge_area_sources kas ON kas.source_id=cs.id
                {where} GROUP BY cs.id ORDER BY cs.publication_year DESC,cs.title LIMIT ?""",
                parameters,
            ).fetchall()
        return tuple(self._source_dto(row) for row in rows)

    def search_sources(self, query: str, area_ids: tuple[str, ...] = (), *, limit: int = 8) -> tuple[tuple[float, CuratedSourceDTO], ...]:
        terms = {fold(item) for item in re.findall(r"[\w+-]{3,}", query)}
        scored = []
        for source in self.sources(area_ids, limit=100):
            haystack = fold(" ".join((source.title, *source.authors, source.overview, source.why_it_matters)))
            hits = sum(1 for term in terms if term in haystack)
            if hits:
                scored.append((min(0.92, 0.38 + hits / max(2, len(terms)) * 0.5), source))
        return tuple(sorted(scored, key=lambda item: (-item[0], item[1].title))[:limit])

    @staticmethod
    def _source_dto(row) -> CuratedSourceDTO:
        return CuratedSourceDTO(
            id=row["id"], title=row["title"], authors=tuple(json.loads(row["authors_json"])),
            publication_year=row["publication_year"], source_type=row["source_type"],
            canonical_url=row["canonical_url"], doi=row["doi"], overview=row["overview"],
            why_it_matters=row["why_it_matters"], access_note=row["access_note"],
            license_note=row["license_note"],
            area_ids=tuple((row["area_ids"] or "").split(",")) if row["area_ids"] else (),
        )

    def reading_detail(self, evidence_id: str, *, query: str = "") -> ReadingDetailDTO:
        if evidence_id.startswith("reference:"):
            return self._reference_detail(evidence_id.removeprefix("reference:"))
        try:
            chunk_id = UUID(evidence_id)
        except ValueError as exc:
            raise KeyError("Resultado de leitura desconhecido.") from exc
        with self._database.read_connection() as connection:
            row = connection.execute(
                """SELECT c.id,c.document_id,c.ordinal,c.text_encrypted,c.page_number,
                          d.title,d.source_path
                FROM document_chunks c JOIN documents d ON d.id=c.document_id
                LEFT JOIN chunk_quality q ON q.chunk_id=c.id
                WHERE c.id=? AND COALESCE(q.status,'accepted')='accepted'""", (str(chunk_id),),
            ).fetchone()
            if row is None:
                raise KeyError("O excerto já não existe no índice local.")
            adjacent = connection.execute(
                """SELECT document_chunks.id,document_chunks.text_encrypted,tc.image_path FROM document_chunks
                LEFT JOIN chunk_quality q ON q.chunk_id=document_chunks.id
                LEFT JOIN theory_cards tc ON tc.chunk_id=document_chunks.id
                WHERE document_id=? AND ordinal BETWEEN ? AND ?
                  AND COALESCE(q.status,'accepted')='accepted' ORDER BY ordinal""",
                (row["document_id"], max(0, row["ordinal"] - 1), row["ordinal"] + 1),
            ).fetchall()
        original_parts = []
        visual_assets = []
        for part in adjacent:
            original_parts.append(self._cipher.decrypt(
                part["text_encrypted"],
                associated_data=f"document_chunks.text:{part['id']}".encode(),
            ).decode("utf-8"))
            if part["image_path"] and Path(part["image_path"]).is_file():
                visual_assets.append(str(Path(part["image_path"]).resolve()))
        original = "\n\n".join(original_parts)[:100_000]
        summary, simplified, points, math_notes = self._assistance(chunk_id, original, query)
        concepts = self._concepts(original)
        areas = self._areas_for_chunk(str(chunk_id))
        related_sources = self.sources(areas, limit=8)
        if not related_sources:
            parent_areas = tuple(dict.fromkeys(
                parent for area_id in areas for parent in ancestors(area_id)
            ))
            related_sources = self.sources(parent_areas, limit=8)
        return ReadingDetailDTO(
            evidence_id=str(chunk_id), title=row["title"], source=row["source_path"],
            original_content=original, summary=summary, simplified=simplified,
            key_points=points, math_notes=math_notes, concepts=concepts,
            visual_assets=tuple(dict.fromkeys(visual_assets)),
            related_sources=related_sources,
            copyright_note=(
                "Conteúdo apresentado a partir de um ficheiro local fornecido pelo utilizador. "
                "A versão simplificada é uma síntese automática e deve ser confrontada com o original."
            ),
        )

    def _assistance(self, chunk_id: UUID, original: str, query: str):
        with self._database.read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM reading_assistance WHERE chunk_id=? AND algorithm_version=?",
                (str(chunk_id), PedagogicalReadingAssistant.VERSION),
            ).fetchone()
        if row is not None and not query.strip():
            def decrypt(name: str) -> str:
                return self._cipher.decrypt(
                    row[f"{name}_encrypted"],
                    associated_data=f"reading_assistance.{name}:{chunk_id}".encode(),
                ).decode("utf-8")
            return (
                decrypt("summary"), decrypt("simplified"),
                tuple(json.loads(decrypt("key_points"))),
                tuple(json.loads(decrypt("math_notes"))),
            )
        result = PedagogicalReadingAssistant.build(original, query)
        if not query.strip():
            summary, simplified, points, notes = result
            def encrypt(name: str, value: str):
                return self._cipher.encrypt(
                    value.encode("utf-8"),
                    associated_data=f"reading_assistance.{name}:{chunk_id}".encode(),
                )
            with self._database.transaction() as connection:
                connection.execute(
                    """INSERT OR REPLACE INTO reading_assistance(
                    chunk_id,algorithm_version,summary_encrypted,simplified_encrypted,
                    key_points_encrypted,math_notes_encrypted,generated_at)
                    VALUES(?,?,?,?,?,?,?)""",
                    (str(chunk_id), PedagogicalReadingAssistant.VERSION,
                     encrypt("summary", summary), encrypt("simplified", simplified),
                     encrypt("key_points", json.dumps(points, ensure_ascii=False)),
                     encrypt("math_notes", json.dumps(notes, ensure_ascii=False)),
                     datetime.now(UTC).isoformat()),
                )
        return result

    def _concepts(self, text: str) -> tuple[ReadingConceptDTO, ...]:
        normalized = fold(text)
        with self._database.read_connection() as connection:
            rows = connection.execute("SELECT * FROM glossary_entries ORDER BY length(normalized_term) DESC").fetchall()
        result = []
        for row in rows:
            term = fold(row["normalized_term"])
            if not term or not re.search(rf"(?<!\w){re.escape(term)}(?!\w)", normalized):
                continue
            identity = row["id"]
            def decrypt(name: str) -> str:
                payload = row[f"{name}_encrypted"]
                return "" if payload is None else self._cipher.decrypt(
                    payload, associated_data=f"glossary_entries.{name}:{identity}".encode()
                ).decode("utf-8")
            result.append(ReadingConceptDTO(
                term=row["term"], definition=decrypt("definition"),
                signature=decrypt("signature"),
                related_terms=tuple(json.loads(row["related_terms_json"])),
            ))
            if len(result) >= 30:
                break
        return tuple(result)

    def _areas_for_chunk(self, chunk_id: str) -> tuple[str, ...]:
        with self._database.read_connection() as connection:
            rows = connection.execute(
                "SELECT area_id FROM knowledge_area_chunks WHERE chunk_id=? ORDER BY relevance DESC",
                (chunk_id,),
            ).fetchall()
        return tuple(row[0] for row in rows)

    def _reference_detail(self, source_id: str) -> ReadingDetailDTO:
        sources = [item for item in self.sources(limit=100) if item.id == source_id]
        if not sources:
            raise KeyError("Referência curada desconhecida.")
        source = sources[0]
        original = (
            f"{source.title}\nAutores: {', '.join(source.authors)}\n"
            f"Ano: {source.publication_year or 'n/d'}\nTipo: {source.source_type}\n\n"
            f"Síntese Aprendix: {source.overview}\n\nPorque importa: {source.why_it_matters}"
        )
        summary, simplified, points, notes = PedagogicalReadingAssistant.build(original)
        return ReadingDetailDTO(
            evidence_id=f"reference:{source.id}", title=source.title,
            source=source.canonical_url, original_content=original,
            summary=summary, simplified=simplified, key_points=points,
            math_notes=notes, concepts=self._concepts(original),
            related_sources=(source,), canonical_url=source.canonical_url,
            copyright_note=(
                f"{source.access_note} {source.license_note} "
                "Esta ficha é conteúdo original do Aprendix, não o texto integral da obra."
            ),
        )
