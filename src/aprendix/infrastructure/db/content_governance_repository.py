"""SQLite source registry, revision history and curriculum coverage."""

from __future__ import annotations

import json
import math
import re
import unicodedata
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from aprendix.application.contracts import (
    BibliographyCoverageDTO,
    AuthorityLevel, ContentSourceDTO, CurriculumCoverageDTO, GapCode,
)
from aprendix.application.knowledge_structure import classify_areas
from aprendix.application.clustering import TaxonomyClassifier


class ContentGovernanceRepository:
    def __init__(self, database, cipher=None) -> None:
        self._database = database
        self._cipher = cipher

    def seed_sources(self, sources: tuple[ContentSourceDTO, ...]) -> None:
        with self._database.transaction() as connection:
            connection.executemany(
                """INSERT INTO content_source_adapters VALUES(?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET domain=excluded.domain,
                   allowed_content_types_json=excluded.allowed_content_types_json,
                   license_policy=excluded.license_policy,robots_policy=excluded.robots_policy,
                   parser_version=excluded.parser_version,change_detection=excluded.change_detection,
                   authority_level=excluded.authority_level,enabled=excluded.enabled,
                   updated_at=excluded.updated_at""",
                [(item.id, item.domain, json.dumps(item.allowed_content_types),
                  item.license_policy, item.robots_policy, item.parser_version,
                  item.change_detection, item.authority_level.value, int(item.enabled),
                  item.updated_at.isoformat()) for item in sources],
            )

    def sources(self) -> tuple[ContentSourceDTO, ...]:
        with self._database.read_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM content_source_adapters ORDER BY authority_level,domain"
            ).fetchall()
        return tuple(ContentSourceDTO(
            id=row["id"], domain=row["domain"],
            allowed_content_types=tuple(json.loads(row["allowed_content_types_json"])),
            license_policy=row["license_policy"], robots_policy=row["robots_policy"],
            parser_version=row["parser_version"], change_detection=row["change_detection"],
            authority_level=AuthorityLevel(row["authority_level"]),
            enabled=bool(row["enabled"]), updated_at=datetime.fromisoformat(row["updated_at"]),
        ) for row in rows)

    def backfill_existing_revisions(self) -> int:
        now = datetime.now(UTC).isoformat()
        with self._database.transaction() as connection:
            rows = connection.execute(
                """SELECT d.* FROM documents d LEFT JOIN content_revisions r
                   ON r.document_id=d.id WHERE r.document_id IS NULL ORDER BY d.ingested_at,d.id"""
            ).fetchall()
            for row in rows:
                logical = row["source_path"]
                revision_id = uuid5(NAMESPACE_URL, f"aprendix:revision:{row['id']}")
                sequence = int(connection.execute(
                    "SELECT COALESCE(max(sequence),0)+1 FROM content_revisions WHERE logical_source=?",
                    (logical,),
                ).fetchone()[0])
                status = row["lifecycle"]
                connection.execute(
                    "INSERT INTO content_revisions VALUES(?,?,?,?,?,?,?,?)",
                    (str(revision_id), logical, row["id"], row["content_hash"], sequence,
                     status, row["ingested_at"], row["ingested_at"] if status == "active" else None),
                )
                connection.execute(
                    """INSERT OR IGNORE INTO document_provenance VALUES(
                       ?,NULL,?,NULL,'private-local','local-private','1',0.80,?)""",
                    (row["id"], logical, now),
                )
        return len(rows)

    @staticmethod
    def _terms(value: str) -> set[str]:
        folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()
        stop = {
            "para", "uma", "com", "sem", "por", "dos", "das", "que", "num", "cada",
            "criar", "calcular", "implementar", "aplicar", "construir", "produzir",
            "validar", "local", "verificavel", "resultado", "valores", "objeto",
            "antes", "executar", "tipos", "estado", "sistemas", "dados", "testar",
            "resultados", "produzidos", "sequencia", "numa", "zero",
            "python", "web", "frameworks", "artificial", "learning", "machine",
            "partir", "rede",
        }
        terms = {term.strip(".-") for term in re.findall(r"[a-z0-9_+#.-]{3,}", folded)}
        return {term for term in terms if len(term) >= 3 and term not in stop}

    def refresh_objective_evidence(self) -> int:
        """Link approved text conservatively; area alone never proves relevance."""
        if self._cipher is None:
            return 0
        version, now = "objective-authored-lexical-v7", datetime.now(UTC).isoformat()
        with self._database.read_connection() as connection:
            document_signature = str(connection.execute(
                """SELECT count(*) || ':' || COALESCE(max(ingested_at),'')
                   FROM documents WHERE lifecycle='active'"""
            ).fetchone()[0])
            objective_signature = str(connection.execute(
                """SELECT count(*) || ':' || COALESCE(max(code),'')
                   FROM curriculum_objectives"""
            ).fetchone()[0])
            previous_run = connection.execute(
                "SELECT * FROM content_mapping_runs WHERE algorithm_version=?", (version,)
            ).fetchone()
            if (previous_run is not None and
                    previous_run["document_signature"] == document_signature and
                    previous_run["objective_signature"] == objective_signature):
                return int(previous_run["link_count"])
            objectives = connection.execute(
                """SELECT o.id,o.code,o.description,
                          group_concat(DISTINCT c.title) chapter_titles,
                          group_concat(DISTINCT t.title) track_titles,
                          group_concat(DISTINCT t.technology) track_technologies
                   FROM curriculum_objectives o
                   JOIN unit_objectives uo ON uo.objective_id=o.id
                   JOIN learning_units u ON u.id=uo.unit_id
                   JOIN learning_chapters c ON c.id=u.chapter_id
                   JOIN learning_tracks t ON t.id=c.track_id
                   GROUP BY o.id ORDER BY o.code"""
            ).fetchall()
        mappings: dict[tuple[str, str], tuple[str, str, float, str, str, str]] = {}
        candidate_term_cache: dict[str, set[str]] = {}
        for objective in objectives:
            objective_slug = objective["code"][4:].casefold()
            exact_section = f"curriculum-{objective_slug}"
            with self._database.read_connection() as connection:
                exact_rows = connection.execute(
                    """SELECT dc.id FROM document_chunks dc
                       JOIN documents d ON d.id=dc.document_id
                       LEFT JOIN chunk_quality q ON q.chunk_id=dc.id
                       WHERE dc.section=? AND d.lifecycle='active'
                         AND COALESCE(q.status,'accepted')='accepted'
                       ORDER BY dc.id""",
                    (exact_section,),
                ).fetchall()
            for row in exact_rows:
                item = (objective["id"], row["id"], 1.0,
                        "conteúdo autoral do objetivo curricular", version, now)
                mappings[(objective["id"], row["id"])] = item
            objective_terms = self._terms(objective["description"])
            context_terms = self._terms(
                f"{objective['chapter_titles'] or ''} {objective['track_titles'] or ''}"
            )
            query = " ".join((objective["description"], objective["chapter_titles"] or "",
                              objective["track_titles"] or "", objective["track_technologies"] or ""))
            query_terms = objective_terms | context_terms
            query_technologies, _query_themes = TaxonomyClassifier.classify(query)
            required_technologies = {item.value for item in query_technologies if item.value != "other"}
            area_ids = tuple(item[0] for item in classify_areas(query))
            if not query_terms or not area_ids:
                continue
            placeholders = ",".join("?" for _ in area_ids)
            with self._database.read_connection() as connection:
                rows = connection.execute(
                    f"""SELECT dc.id,dc.section,dc.text_encrypted,d.title source_title,
                               kt.technologies_json,max(k.relevance) area_relevance
                        FROM knowledge_area_chunks k
                        JOIN document_chunks dc ON dc.id=k.chunk_id
                        JOIN documents d ON d.id=dc.document_id
                        LEFT JOIN chunk_quality q ON q.chunk_id=dc.id
                        LEFT JOIN knowledge_taxonomy kt ON kt.chunk_id=dc.id
                        WHERE k.area_id IN ({placeholders}) AND d.lifecycle='active'
                        AND dc.chunk_type<>'exercise'
                        AND COALESCE(q.status,'accepted')='accepted'
                        GROUP BY dc.id ORDER BY area_relevance DESC,dc.id LIMIT 800""",
                    area_ids,
                ).fetchall()
            ranked = []
            for row in rows:
                candidate_technologies = set(json.loads(row["technologies_json"] or "[]"))
                if required_technologies and not (required_technologies & candidate_technologies):
                    continue
                source_title = unicodedata.normalize("NFKD", row["source_title"]).encode(
                    "ascii", "ignore"
                ).decode().casefold()
                objective_track_technologies = set((objective["track_technologies"] or "").split(","))
                if ("python" in objective_track_technologies and
                        any(marker in source_title for marker in ("database system", "database systems"))):
                    continue
                candidate_terms = candidate_term_cache.get(row["id"])
                if candidate_terms is None:
                    try:
                        body = self._cipher.decrypt(
                            row["text_encrypted"],
                            associated_data=f"document_chunks.text:{row['id']}".encode(),
                        ).decode("utf-8", errors="replace")
                    except (ValueError, UnicodeError):
                        continue
                    candidate_terms = self._terms(f"{row['section']} {body[:12_000]}")
                    candidate_term_cache[row["id"]] = candidate_terms
                objective_overlap = objective_terms & candidate_terms
                context_overlap = context_terms & candidate_terms
                if not objective_overlap:
                    continue
                high_signal = {
                    "output", "byte", "bytes", "relu", "neuronio", "sql", "api", "apis",
                    "debugging", "decorator", "decorador", "generator", "gerador", "list", "set",
                    "classe", "class", "invariantes", "transacao", "transaction", "centroide", "http",
                }
                if len(objective_overlap) == 1 and not (objective_overlap & high_signal):
                    continue
                objective_lexical = len(objective_overlap) / math.sqrt(
                    max(1, len(objective_terms) * len(objective_overlap | objective_terms))
                )
                context_lexical = len(context_overlap) / max(1, len(context_terms))
                score = min(1.0, 0.75 * objective_lexical + 0.10 * context_lexical +
                            0.15 * float(row["area_relevance"]))
                if score >= 0.30:
                    ranked.append((score, row["id"], sorted(objective_overlap)[:8]))
            for score, chunk_id, overlap in sorted(ranked, key=lambda x: (-x[0], x[1]))[:5]:
                key = (objective["id"], chunk_id)
                item = (objective["id"], chunk_id, score,
                        "termos técnicos: " + ", ".join(overlap), version, now)
                if key not in mappings or score > mappings[key][2]:
                    mappings[key] = item
        with self._database.transaction() as connection:
            connection.execute("DELETE FROM curriculum_objective_evidence")
            connection.executemany(
                "INSERT INTO curriculum_objective_evidence VALUES(?,?,?,?,?,?)", mappings.values(),
            )
            connection.execute(
                """INSERT INTO content_mapping_runs VALUES(?,?,?,?,?)
                   ON CONFLICT(algorithm_version) DO UPDATE SET
                   document_signature=excluded.document_signature,
                   objective_signature=excluded.objective_signature,
                   link_count=excluded.link_count,completed_at=excluded.completed_at""",
                (version, document_signature, objective_signature, len(mappings), now),
            )
        return len(mappings)

    def refresh_coverage(self) -> tuple[CurriculumCoverageDTO, ...]:
        now = datetime.now(UTC).isoformat()
        with self._database.transaction() as connection:
            rows = connection.execute(
                """SELECT o.id,o.code,o.description,
                          count(DISTINCT CASE WHEN dc.chunk_type<>'exercise'
                            AND d.lifecycle='active' AND COALESCE(q.status,'accepted')='accepted'
                            THEN dc.id END) theory_count,
                          count(DISTINCT CASE WHEN d.lifecycle='active'
                            AND COALESCE(q.status,'accepted')='accepted' THEN tc.id END) card_count,
                          count(DISTINCT e.id) exercise_count
                   FROM curriculum_objectives o
                   JOIN unit_objectives uo ON uo.objective_id=o.id
                   JOIN learning_units u ON u.id=uo.unit_id
                   JOIN learning_chapters c ON c.id=u.chapter_id
                   LEFT JOIN curriculum_objective_evidence oe ON oe.objective_id=o.id
                   LEFT JOIN document_chunks dc ON dc.id=oe.chunk_id
                   LEFT JOIN documents d ON d.id=dc.document_id
                   LEFT JOIN chunk_quality q ON q.chunk_id=dc.id
                   LEFT JOIN theory_cards tc ON tc.chunk_id=dc.id
                   LEFT JOIN exercises e ON e.graph_node_id=c.graph_node_id
                   GROUP BY o.id ORDER BY o.code"""
            ).fetchall()
            result = []
            for row in rows:
                theory, cards, exercises = (int(row["theory_count"]),
                                             int(row["card_count"]), int(row["exercise_count"]))
                score = min(1.0, (0.35 if theory else 0.0) +
                            (0.20 if cards else 0.0) + (0.45 if exercises else 0.0))
                gap = (GapCode.NONE if theory and exercises else
                       GapCode.NEEDS_THEORY if exercises else
                       GapCode.NEEDS_PRACTICE if theory else GapCode.NEEDS_BOTH)
                connection.execute(
                    """INSERT INTO curriculum_coverage VALUES(?,?,?,?,?,?,?)
                       ON CONFLICT(objective_id) DO UPDATE SET
                       theory_evidence_count=excluded.theory_evidence_count,
                       card_count=excluded.card_count,exercise_count=excluded.exercise_count,
                       coverage_score=excluded.coverage_score,gap_code=excluded.gap_code,
                       measured_at=excluded.measured_at""",
                    (row["id"], theory, cards, exercises, score, gap.value, now),
                )
                result.append(CurriculumCoverageDTO(
                    objective_id=UUID(row["id"]), objective_code=row["code"],
                    objective=row["description"], theory_evidence_count=theory,
                    card_count=cards, exercise_count=exercises,
                    coverage_score=score, gap_code=gap,
                    measured_at=datetime.fromisoformat(now),
                ))
        return tuple(result)

    def coverage(self, *, gaps_only: bool = False) -> tuple[CurriculumCoverageDTO, ...]:
        clause = "WHERE cv.gap_code<>'none'" if gaps_only else ""
        with self._database.read_connection() as connection:
            rows = connection.execute(
                f"""SELECT cv.*,o.code,o.description FROM curriculum_coverage cv
                    JOIN curriculum_objectives o ON o.id=cv.objective_id {clause}
                    ORDER BY cv.coverage_score,o.code"""
            ).fetchall()
        return tuple(CurriculumCoverageDTO(
            objective_id=UUID(row["objective_id"]), objective_code=row["code"],
            objective=row["description"], theory_evidence_count=row["theory_evidence_count"],
            card_count=row["card_count"], exercise_count=row["exercise_count"],
            coverage_score=row["coverage_score"], gap_code=GapCode(row["gap_code"]),
            measured_at=datetime.fromisoformat(row["measured_at"]),
        ) for row in rows)

    def bibliography_coverage(self) -> BibliographyCoverageDTO:
        """Measure useful source diversity per curriculum objective."""

        with self._database.read_connection() as connection:
            rows = connection.execute(
                """SELECT o.code,
                          count(DISTINCT esl.source_id) source_count,
                          count(DISTINCT CASE WHEN cs.source_type IN
                              ('documentation','book','paper') THEN cs.id END) authority_count
                   FROM curriculum_objectives o
                   LEFT JOIN unit_objectives uo ON uo.objective_id=o.id
                   LEFT JOIN learning_units u ON u.id=uo.unit_id
                   LEFT JOIN learning_chapters lc ON lc.id=u.chapter_id
                   LEFT JOIN exercises direct ON direct.id=u.exercise_id
                   LEFT JOIN exercises related
                     ON related.graph_node_id=COALESCE(direct.graph_node_id,lc.graph_node_id)
                   LEFT JOIN exercise_source_links esl ON esl.exercise_id=related.id
                   LEFT JOIN curated_sources cs ON cs.id=esl.source_id
                   GROUP BY o.id,o.code ORDER BY o.code"""
            ).fetchall()
            distinct_sources = int(connection.execute(
                "SELECT count(DISTINCT source_id) FROM exercise_source_links"
            ).fetchone()[0])
        total = len(rows)
        covered = sum(int(row["source_count"]) >= 1 for row in rows)
        triple = sum(int(row["source_count"]) >= 3 for row in rows)
        authoritative = sum(int(row["authority_count"]) >= 1 for row in rows)
        weak = tuple(row["code"] for row in rows if int(row["source_count"]) < 3)
        score = (
            .35 * covered / max(1, total)
            + .40 * triple / max(1, total)
            + .25 * authoritative / max(1, total)
        )
        return BibliographyCoverageDTO(
            objective_count=total, covered_objectives=covered,
            triple_sourced_objectives=triple,
            authoritative_objectives=authoritative,
            distinct_sources=distinct_sources, coverage_score=score,
            weak_objective_codes=weak,
        )

    def rollback(self, logical_source: str, sequence: int) -> str:
        if not logical_source.strip() or sequence < 1:
            raise ValueError("invalid rollback target")
        now = datetime.now(UTC).isoformat()
        with self._database.transaction() as connection:
            target = connection.execute(
                "SELECT * FROM content_revisions WHERE logical_source=? AND sequence=?",
                (logical_source, sequence),
            ).fetchone()
            if target is None:
                raise KeyError((logical_source, sequence))
            current = connection.execute(
                "SELECT * FROM content_revisions WHERE logical_source=? AND status='active'",
                (logical_source,),
            ).fetchone()
            if current and current["id"] == target["id"]:
                return target["document_id"]
            if current:
                connection.execute(
                    "UPDATE documents SET source_path=?,lifecycle='retired' WHERE id=?",
                    (f"aprendix://revision/{current['document_id']}", current["document_id"]),
                )
                connection.execute(
                    "UPDATE content_revisions SET status='retired' WHERE id=?", (current["id"],)
                )
            connection.execute(
                "UPDATE documents SET source_path=?,lifecycle='active' WHERE id=?",
                (logical_source, target["document_id"]),
            )
            connection.execute(
                "UPDATE content_revisions SET status='active',promoted_at=? WHERE id=?",
                (now, target["id"]),
            )
        return target["document_id"]
