"""Transactional Iteration-21 catalogue, career DAG and editorial audit."""

from __future__ import annotations

import ast
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, UUID, uuid5

from aprendix.application.career_catalog import CAREER_ROLES, validate_career_definitions
from aprendix.application.editorial_catalog import (
    CATALOG_GENERATOR,
    CATALOG_VERSION,
    EDITORIAL_EXERCISES,
    EDITORIAL_PROJECTS,
)
from aprendix.application.learning_catalog import ALL_FACTS
from aprendix.application.knowledge_structure import SOURCES
from aprendix.application.official_catalog import (
    OFFICIAL_CARD_BUCKET_QUOTAS,
    OFFICIAL_CONCEPTS,
    OFFICIAL_GLOSSARY_BUCKET_QUOTAS,
    OFFICIAL_SOURCE_QUOTAS,
    OFFICIAL_SOURCES,
)


_ZERO_HASH = "0" * 64
_SOURCE_HOST_ALLOWLIST = frozenset({
    "ai.stanford.edu", "aima.cs.berkeley.edu", "arxiv.org",
    "developer.mozilla.org", "docs.djangoproject.com", "docs.docker.com",
    "docs.pytest.org", "docs.python.org", "docs.sqlalchemy.org",
    "fastapi.tiangolo.com", "flask.palletsprojects.com", "git-scm.com",
    "hai.stanford.edu", "hastie.su.domains", "mitpress.mit.edu",
    "numpy.org", "packaging.python.org", "pandas.pydata.org",
    "probml.github.io", "pytorch.org", "docs.pytorch.org", "scikit-learn.org",
    "www.deeplearningbook.org", "www.mongodb.com", "www.oreilly.com",
    "www.postgresql.org",
    "cheatsheetseries.owasp.org", "www.nist.gov",
    "xlinux.nist.gov", "docs.kernel.org", "www.mongodb.com",
    "spark.apache.org", "www.tensorflow.org", "docs.opencv.org",
    "spacy.io", "mlflow.org", "attack.mitre.org", "kubernetes.io",
    "www.w3.org", "airc.nist.gov", "raw.githubusercontent.com",
})
_TOTAL_MINIMUMS = {
    "source": 1_620, "card": 2_827, "glossary": 4_343,
    "exercise": 3_563, "project": 70,
}
_DELTA_MINIMUMS = {
    "source": 500, "card": 1_000, "glossary": 1_000,
    "exercise": 500, "project": 50,
}


def _id(kind: str, slug: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"aprendix:iteration21:{kind}:{slug}"))


def _hash(*values: object) -> str:
    return hashlib.sha256(json.dumps(
        values, ensure_ascii=False, sort_keys=True, default=str,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def _solution_hash(solution: str, tests: tuple[str, ...]) -> str:
    return hashlib.sha256(json.dumps(
        {"source": solution, "tests": tests}, ensure_ascii=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


_SEED_SIGNATURE = _hash(
    CATALOG_VERSION,
    tuple((item.id, item.title, item.url) for item in SOURCES),
    tuple(repr(item) for item in ALL_FACTS),
    tuple(repr(item) for item in OFFICIAL_CONCEPTS),
    tuple((item.slug, item.prompt, item.tests, item.solution) for item in EDITORIAL_EXERCISES),
    EDITORIAL_PROJECTS,
    CAREER_ROLES,
)


class _StructuralNormalizer(ast.NodeTransformer):
    """Erase incidental names/literals while retaining algorithmic structure."""

    def visit_Name(self, node: ast.Name):  # noqa: N802 - AST protocol
        node.id = "name"
        return self.generic_visit(node)

    def visit_arg(self, node: ast.arg):  # noqa: N802 - AST protocol
        node.arg = "argument"
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef):  # noqa: N802 - AST protocol
        node.name = "function"
        return self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant):  # noqa: N802 - AST protocol
        node.value = type(node.value).__name__
        return node


def _exercise_diversity() -> dict[str, object]:
    contracts = {
        _hash(item.prompt, item.starter_code) for item in EDITORIAL_EXERCISES
    }
    solution_asts = {
        ast.dump(ast.parse(item.solution), include_attributes=False)
        for item in EDITORIAL_EXERCISES
    }
    normalized_asts = {
        ast.dump(
            _StructuralNormalizer().visit(ast.parse(item.solution)),
            include_attributes=False,
        )
        for item in EDITORIAL_EXERCISES
    }
    test_suites = {_hash(item.tests) for item in EDITORIAL_EXERCISES}
    role_counts = {
        role.slug: sum(item.role_slug == role.slug for item in EDITORIAL_EXERCISES)
        for role in CAREER_ROLES
    }
    return {
        "contracts": len(contracts), "solution_asts": len(solution_asts),
        "normalized_structures": len(normalized_asts),
        "test_suites": len(test_suites), "role_counts": role_counts,
    }


class EditorialCatalogRepository:
    """Own one idempotent catalogue release without deleting user history."""

    def __init__(self, database, cipher) -> None:
        self._database = database
        self._cipher = cipher

    def _encrypt(self, table_field: str, identity: str, value: str) -> bytes:
        return self._cipher.encrypt(
            value.encode("utf-8"),
            associated_data=f"{table_field}:{identity}".encode("utf-8"),
        )

    def seed(self) -> dict[str, object]:
        fast = self._fast_path()
        if fast is not None:
            return fast
        validate_career_definitions()
        for exercise in EDITORIAL_EXERCISES:
            ast.parse(exercise.starter_code)
            ast.parse(exercise.solution)
            for test in exercise.tests:
                ast.parse(test)
        now = datetime.now(UTC).isoformat()
        release_id = _id("catalog-release", CATALOG_VERSION)
        with self._database.transaction() as connection:
            previous_release = connection.execute(
                "SELECT checksum FROM content_catalog_releases WHERE id=?", (release_id,)
            ).fetchone()
            previous_checksum = previous_release["checksum"] if previous_release else None
            connection.execute(
                """INSERT INTO content_catalog_releases(
                       id,version,status,schema_version,counts_json,checksum,
                       created_at,activated_at
                   ) VALUES(?,?,'draft',38,'{}',?,?,NULL)
                   ON CONFLICT(id) DO UPDATE SET status='draft',schema_version=38""",
                (release_id, CATALOG_VERSION, _ZERO_HASH, now),
            )
            self._seed_exercises(connection, release_id, now)
            self._seed_projects(connection, now)
            self._seed_careers(connection)
            existing_created = {
                (row["item_type"], row["item_id"]): row["created_at"]
                for row in connection.execute(
                    """SELECT item_type,item_id,created_at FROM content_catalog_items
                       WHERE release_id=?""", (release_id,),
                )
            }
            items = self._catalog_items(
                connection, release_id, now, existing_created=existing_created,
            )
            connection.execute(
                "DELETE FROM content_catalog_items WHERE release_id=?", (release_id,)
            )
            connection.executemany(
                """INSERT INTO content_catalog_items(
                       release_id,item_type,item_id,content_type,status,
                       provenance,fingerprint,created_at
                   ) VALUES(?,?,?,?,?,?,?,?)""",
                items,
            )
            counts: dict[str, object] = {
                item_type: sum(row[1] == item_type and row[4] == "active" for row in items)
                for item_type in (
                    "source", "card", "glossary", "exercise", "project",
                    "lesson", "reading_chunk", "user_project",
                )
            }
            delta = self._delta_counts(connection, release_id)
            counts["delta"] = delta
            counts["seed_signature"] = _SEED_SIGNATURE
            missing_total = {
                key: (int(counts[key]), minimum)
                for key, minimum in _TOTAL_MINIMUMS.items()
                if int(counts[key]) < minimum
            }
            missing_delta = {
                key: (int(delta[key]), expected)
                for key, expected in _DELTA_MINIMUMS.items()
                if int(delta[key]) != expected
            }
            if missing_total or missing_delta:
                raise ValueError(
                    "catalogue population targets not met: "
                    f"totals={missing_total}, deltas={missing_delta}"
                )
            checksum = _hash(tuple(
                (row[1], row[2], row[4], row[6]) for row in sorted(items)
            ))
            connection.execute(
                """UPDATE content_catalog_releases SET status='retired'
                   WHERE status='active' AND id<>?""", (release_id,),
            )
            connection.execute(
                """UPDATE content_catalog_releases SET status='active',counts_json=?,
                       checksum=?,activated_at=CASE
                           WHEN checksum=? AND activated_at IS NOT NULL THEN activated_at
                           ELSE ? END WHERE id=?""",
                (json.dumps(counts, sort_keys=True), checksum, checksum, now, release_id),
            )
        return {"changed": previous_checksum != checksum, **counts}

    def _fast_path(self) -> dict[str, object] | None:
        """Avoid AST, encryption and a full item rebuild on normal startups."""

        release_id = _id("catalog-release", CATALOG_VERSION)
        with self._database.read_connection() as connection:
            row = connection.execute(
                """SELECT counts_json FROM content_catalog_releases
                   WHERE id=? AND version=? AND status='active'""",
                (release_id, CATALOG_VERSION),
            ).fetchone()
            if row is None:
                return None
            try:
                counts = json.loads(row["counts_json"])
            except (json.JSONDecodeError, TypeError):
                return None
            if counts.get("seed_signature") != _SEED_SIGNATURE:
                return None
            if any(
                int(counts.get(key, 0)) < minimum
                for key, minimum in _TOTAL_MINIMUMS.items()
            ):
                return None
            delta = self._delta_counts(connection, release_id)
            if any(
                int(delta.get(key, 0)) != expected
                for key, expected in _DELTA_MINIMUMS.items()
            ):
                return None
            stored_delta = counts.get("delta")
            if not isinstance(stored_delta, dict) or any(
                int(stored_delta.get(key, -1)) != int(delta[key])
                for key in _DELTA_MINIMUMS
            ):
                return None
            roles = int(connection.execute(
                "SELECT count(*) FROM career_roles WHERE active=1"
            ).fetchone()[0])
            policies = int(connection.execute(
                """SELECT count(*) FROM exercise_guidance_policies g
                   JOIN exercise_catalog_provenance p ON p.exercise_id=g.exercise_id
                   WHERE p.release_id=?""", (release_id,),
            ).fetchone()[0])
            if roles != 5 or policies != 500:
                return None
        return {"changed": False, **counts}

    @staticmethod
    def _delta_counts(connection, release_id: str) -> dict[str, int]:
        return {
            "source": int(connection.execute(
                """SELECT count(*) FROM content_catalog_items i
                   JOIN curated_sources s ON s.id=i.item_id
                   WHERE i.release_id=? AND i.item_type='source' AND i.status='active'
                     AND s.provenance LIKE 'official-sitemap-metadata-%'""",
                (release_id,),
            ).fetchone()[0]),
            "card": int(connection.execute(
                """SELECT count(*) FROM theory_cards tc
                   JOIN document_chunks dc ON dc.id=tc.chunk_id
                   WHERE dc.section LIKE 'official-%'"""
            ).fetchone()[0]),
            "glossary": int(connection.execute(
                """SELECT count(DISTINCT e.id) FROM glossary_entries e
                   JOIN glossary_source_links l ON l.entry_id=e.id
                   WHERE l.source_id LIKE 'src-official-%'"""
            ).fetchone()[0]),
            "exercise": int(connection.execute(
                """SELECT count(*) FROM exercise_catalog_provenance
                   WHERE release_id=? AND generator_version=?""",
                (release_id, CATALOG_GENERATOR),
            ).fetchone()[0]),
            "project": int(connection.execute(
                "SELECT count(*) FROM guided_project_templates WHERE id LIKE 'career-project-%'"
            ).fetchone()[0]),
        }

    def _seed_exercises(self, connection, release_id: str, now: str) -> None:
        graph_nodes = {
            row["slug"]: row["id"]
            for row in connection.execute("SELECT id,slug FROM graph_nodes")
        }
        known_sources = {
            row["id"] for row in connection.execute("SELECT id FROM curated_sources")
        }
        for item in EDITORIAL_EXERCISES:
            node_id = graph_nodes.get(item.graph_node_slug)
            if node_id is None:
                raise ValueError(f"missing graph node for editorial exercise: {item.graph_node_slug}")
            source_ids = tuple(dict.fromkeys((item.source_id, *item.supporting_source_ids)))
            missing_sources = tuple(source_id for source_id in source_ids if source_id not in known_sources)
            if missing_sources:
                raise ValueError(f"missing source for editorial exercise: {missing_sources}")
            exercise_id = _id("exercise", item.slug)
            fingerprint = _hash(
                item.slug, item.prompt, item.starter_code, item.tests,
                item.solution, item.expected_trace,
            )
            connection.execute(
                """INSERT INTO exercises(
                       id,graph_node_id,slug,title,prompt,starter_code,tests_json,
                       difficulty,version,created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,1,?,?)
                   ON CONFLICT(id) DO UPDATE SET graph_node_id=excluded.graph_node_id,
                       title=excluded.title,prompt=excluded.prompt,
                       starter_code=excluded.starter_code,tests_json=excluded.tests_json,
                       difficulty=excluded.difficulty,updated_at=excluded.updated_at""",
                (
                    exercise_id, node_id, item.slug, item.title, item.prompt,
                    item.starter_code,
                    json.dumps(item.tests, ensure_ascii=False, separators=(",", ":")),
                    item.difficulty, now, now,
                ),
            )
            for source_id in source_ids:
                connection.execute(
                    """INSERT INTO exercise_source_links(exercise_id,source_id,rationale)
                       VALUES(?,?,?) ON CONFLICT(exercise_id,source_id) DO UPDATE SET
                       rationale=excluded.rationale""",
                    (
                        exercise_id, source_id,
                        "Fonte técnica reconhecida para o conceito; enunciado, solução e testes são originais Aprendix.",
                    ),
                )
            solution_hash = _solution_hash(item.solution, item.tests)
            current_solution = connection.execute(
                "SELECT validation_hash FROM exercise_reference_solutions WHERE exercise_id=?",
                (exercise_id,),
            ).fetchone()
            if current_solution is None or current_solution["validation_hash"] != solution_hash:
                connection.execute(
                    """INSERT INTO exercise_reference_solutions(
                           exercise_id,solution_encrypted,explanation_encrypted,
                           validation_hash,validator_version,validated_at
                       ) VALUES(?,?,?,?,?,?)
                       ON CONFLICT(exercise_id) DO UPDATE SET
                           solution_encrypted=excluded.solution_encrypted,
                           explanation_encrypted=excluded.explanation_encrypted,
                           validation_hash=excluded.validation_hash,
                           validator_version=excluded.validator_version,
                           validated_at=excluded.validated_at""",
                    (
                        exercise_id,
                        self._encrypt("exercise_reference_solutions.solution", exercise_id, item.solution),
                        self._encrypt("exercise_reference_solutions.explanation", exercise_id, item.explanation),
                        solution_hash, "editorial-static-validation-v1", now,
                    ),
                )
            policy = connection.execute(
                "SELECT exercise_id FROM exercise_guidance_policies WHERE exercise_id=?",
                (exercise_id,),
            ).fetchone()
            if policy is None:
                walkthrough = json.dumps({
                    "steps": item.expected_trace,
                    "principle": item.explanation,
                }, ensure_ascii=False, separators=(",", ":"))
                trace = json.dumps(item.expected_trace, ensure_ascii=False, separators=(",", ":"))
                connection.execute(
                    """INSERT INTO exercise_guidance_policies(
                           exercise_id,reveal_mode,failed_attempts_before_walkthrough,
                           failed_attempts_before_solution,walkthrough_encrypted,
                           expected_trace_encrypted,provenance,updated_at
                       ) VALUES(?,?,?,?,?,?,?,?)""",
                    (
                        exercise_id, item.reveal_mode, item.walkthrough_after,
                        item.solution_after,
                        self._encrypt("exercise_guidance_policies.walkthrough", exercise_id, walkthrough),
                        self._encrypt("exercise_guidance_policies.trace", exercise_id, trace),
                        "Política progressiva original Aprendix; nunca revela solução antes do limiar.",
                        now,
                    ),
                )
            connection.execute(
                """INSERT INTO exercise_catalog_provenance(
                       exercise_id,release_id,generator_version,source_id,rationale,
                       test_count,fingerprint,created_at
                   ) VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(exercise_id) DO UPDATE SET release_id=excluded.release_id,
                       generator_version=excluded.generator_version,
                       source_id=excluded.source_id,rationale=excluded.rationale,
                       test_count=excluded.test_count,fingerprint=excluded.fingerprint""",
                (
                    exercise_id, release_id, CATALOG_GENERATOR, item.source_id,
                    "Cobertura orientada ao papel profissional, com contrato, solução e casos de fronteira originais.",
                    len(item.tests), fingerprint, now,
                ),
            )

    @staticmethod
    def _seed_projects(connection, now: str) -> None:
        known_tracks = {
            row["slug"] for row in connection.execute("SELECT slug FROM learning_tracks")
        }
        for item in EDITORIAL_PROJECTS:
            if item.track_slug not in known_tracks:
                raise ValueError(f"missing track for editorial project: {item.track_slug}")
            connection.execute(
                """INSERT INTO guided_project_templates(
                       id,track_slug,title,brief,requirements_json,milestones_json,
                       rubric_json,level,capstone,professional_briefing,created_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,1,?)
                   ON CONFLICT(id) DO UPDATE SET track_slug=excluded.track_slug,
                       title=excluded.title,brief=excluded.brief,
                       requirements_json=excluded.requirements_json,
                       milestones_json=excluded.milestones_json,
                       rubric_json=excluded.rubric_json,level=excluded.level,
                       capstone=excluded.capstone,professional_briefing=1""",
                (
                    item.id, item.track_slug, item.title, item.brief,
                    json.dumps(item.requirements, ensure_ascii=False),
                    json.dumps(item.milestones, ensure_ascii=False),
                    json.dumps(item.rubric, ensure_ascii=False),
                    item.level, int(item.capstone), now,
                ),
            )

    @staticmethod
    def _seed_careers(connection) -> None:
        tracks = {
            row["slug"]: row["id"]
            for row in connection.execute("SELECT id,slug FROM learning_tracks")
        }
        areas = {row["id"] for row in connection.execute("SELECT id FROM knowledge_areas")}
        projects_by_role: dict[str, list[str]] = {}
        for project in EDITORIAL_PROJECTS:
            projects_by_role.setdefault(project.role_slug, []).append(project.id)
        for role_position, role in enumerate(CAREER_ROLES):
            role_id = _id("career-role", role.slug)
            connection.execute(
                """INSERT INTO career_roles(id,slug,title,summary,outcome,position,active)
                   VALUES(?,?,?,?,?,?,1) ON CONFLICT(id) DO UPDATE SET
                   title=excluded.title,summary=excluded.summary,outcome=excluded.outcome,
                   position=excluded.position,active=1""",
                (role_id, role.slug, role.title, role.summary, role.outcome, role_position),
            )
            connection.execute("DELETE FROM career_role_areas WHERE role_id=?", (role_id,))
            previous_node_id = None
            for position, stage in enumerate(role.stages):
                node_id = _id("career-node", f"{role.slug}:{stage.slug}")
                connection.execute(
                    """INSERT INTO career_nodes(
                           id,role_id,slug,title,objective,stage,position
                       ) VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                       title=excluded.title,objective=excluded.objective,
                       stage=excluded.stage,position=excluded.position""",
                    (
                        node_id, role_id, stage.slug, stage.title,
                        stage.objective, stage.stage, position,
                    ),
                )
                connection.execute("DELETE FROM career_node_tracks WHERE node_id=?", (node_id,))
                for track_position, track_slug in enumerate(stage.track_slugs):
                    if track_slug not in tracks:
                        raise ValueError(f"unknown career track: {track_slug}")
                    connection.execute(
                        "INSERT INTO career_node_tracks VALUES(?,?,1,?,?)",
                        (node_id, tracks[track_slug], 1.0, track_position),
                    )
                connection.execute("DELETE FROM career_node_dependencies WHERE node_id=?", (node_id,))
                if previous_node_id is not None:
                    connection.execute(
                        "INSERT INTO career_node_dependencies VALUES(?,?,0.70)",
                        (node_id, previous_node_id),
                    )
                previous_node_id = node_id
            for position, area_id in enumerate(role.area_ids):
                if area_id not in areas:
                    raise ValueError(f"unknown career area: {area_id}")
                connection.execute(
                    "INSERT INTO career_role_areas VALUES(?,?,1,?,?)",
                    (role_id, area_id, 1.0, position),
                )
            connection.execute("DELETE FROM career_role_projects WHERE role_id=?", (role_id,))
            for position, project_id in enumerate(projects_by_role.get(role.slug, ())):
                connection.execute(
                    "INSERT INTO career_role_projects VALUES(?,?,?,?,?)",
                    (role_id, project_id, min(4, position // 2), int(position >= 7), position),
                )

    @staticmethod
    def _catalog_items(
        connection, release_id: str, now: str, *,
        existing_created: dict[tuple[str, str], str] | None = None,
    ) -> list[tuple[object, ...]]:
        rows: list[tuple[object, ...]] = []
        existing_created = existing_created or {}
        active_source_ids = {item.id for item in SOURCES}

        def add(item_type: str, item_id: str, content_type: str, status: str,
                provenance: str, *payload: object) -> None:
            rows.append((
                release_id, item_type, item_id, content_type, status,
                provenance, _hash(item_type, item_id, *payload),
                existing_created.get((item_type, item_id), now),
            ))

        for row in connection.execute(
            """SELECT id,title,authors_json,publication_year,source_type,
                      canonical_url,doi,canonical_key,provenance FROM curated_sources"""
        ):
            add(
                "source", row["id"],
                "curated" if row["id"] in active_source_ids else "imported",
                "active" if row["id"] in active_source_ids else "archived",
                (
                    row["provenance"] if row["id"] in active_source_ids else
                    "Metadado de uma release anterior preservado para ligações históricas."
                ),
                row["title"], row["authors_json"], row["publication_year"],
                row["source_type"], row["canonical_url"], row["doi"], row["canonical_key"],
            )
        for row in connection.execute(
            """SELECT tc.id,tc.title,tc.body_encrypted,d.source_path,dc.section,
                      cp.format,
                      EXISTS(SELECT 1 FROM card_source_links l WHERE l.card_id=tc.id) sourced
                 FROM theory_cards tc
                 JOIN document_chunks dc ON dc.id=tc.chunk_id
                 JOIN documents d ON d.id=dc.document_id
                 LEFT JOIN card_presentation cp ON cp.card_id=tc.id"""
        ):
            editorial = (
                row["source_path"] == "aprendix://authored-facts/v1"
                and bool(row["format"]) and bool(row["sourced"])
            )
            add(
                "card", row["id"], "editorial" if editorial else "imported",
                "active" if editorial else "archived",
                (
                    ("Delta editorial baseado em metadados de documentação oficial; "
                     "texto original Aprendix e fonte explícita.")
                    if str(row["section"]).startswith("official-") else
                    "Card editorial Aprendix com apresentação e fontes explícitas."
                    if editorial else
                    "Card legado preservado para histórico e excluído do catálogo pesquisável."
                ),
                row["title"], bytes(row["body_encrypted"]).hex(), row["format"],
            )
        for row in connection.execute(
            """SELECT e.id,e.term,e.normalized_term,e.technology,e.definition_encrypted,
                      EXISTS(SELECT 1 FROM glossary_source_links l
                             WHERE l.entry_id=e.id AND l.source_id LIKE 'src-official-%') official
                 FROM glossary_entries e"""
        ):
            add(
                "glossary", row["id"], "editorial", "active",
                (
                    "Delta editorial original ligado a uma página de documentação oficial."
                    if row["official"] else
                    "Definição local original ou metadado oficial da biblioteca Python."
                ),
                row["term"], row["normalized_term"], row["technology"],
                bytes(row["definition_encrypted"]).hex(),
            )
        generated_ids = {
            _id("exercise", item.slug) for item in EDITORIAL_EXERCISES
        }
        for row in connection.execute(
            "SELECT id,title,prompt,starter_code,tests_json,version FROM exercises"
        ):
            add(
                "exercise", row["id"],
                "generated" if row["id"] in generated_ids else "editorial", "active",
                "Exercício Aprendix com contrato e testes locais; referências guardadas em tabela N:N.",
                row["title"], row["prompt"], row["starter_code"], row["tests_json"], row["version"],
            )
        generated_projects = {item.id for item in EDITORIAL_PROJECTS}
        for row in connection.execute(
            """SELECT id,title,brief,requirements_json,milestones_json,
                      rubric_json,level FROM guided_project_templates"""
        ):
            add(
                "project", row["id"],
                "generated" if row["id"] in generated_projects else "editorial", "active",
                "Projeto original Aprendix com requisitos, etapas e rubrica verificável.",
                row["title"], row["brief"], row["requirements_json"],
                row["milestones_json"], row["rubric_json"], row["level"],
            )
        for row in connection.execute(
            """SELECT id,title,kind,body_encrypted,example_encrypted
                 FROM learning_units
                WHERE kind IN ('theory','quiz','hybrid','reference')"""
        ):
            add(
                "lesson", row["id"], "editorial", "active",
                "Unidade pedagógica original Aprendix, distinta de prática e projeto.",
                row["title"], row["kind"], bytes(row["body_encrypted"]).hex(),
                bytes(row["example_encrypted"] or b"").hex(),
            )
        for row in connection.execute(
            """SELECT c.id,c.section,c.token_count,d.id document_id,d.title,
                      d.source_path,d.lifecycle,
                      COALESCE(q.status,'accepted') quality_status,
                      COALESCE(p.rights_status,'local-private') rights_status
                 FROM document_chunks c JOIN documents d ON d.id=c.document_id
                 LEFT JOIN chunk_quality q ON q.chunk_id=c.id
                 LEFT JOIN document_provenance p ON p.document_id=d.id
                WHERE d.source_path<>'aprendix://authored-facts/v1'"""
        ):
            status = (
                "quarantined" if row["quality_status"] == "quarantined" else
                "active" if row["lifecycle"] == "active" else "archived"
            )
            content_type = "user" if row["rights_status"] == "local-private" else "imported"
            add(
                "reading_chunk", row["id"], content_type, status,
                "Chunk de leitura preservado independentemente de cards editoriais.",
                row["document_id"], row["title"], row["section"], row["token_count"],
                row["rights_status"],
            )
        for row in connection.execute(
            "SELECT id,name_encrypted,technology,updated_at FROM local_projects"
        ):
            add(
                "user_project", row["id"], "user", "active",
                "Projeto privado do utilizador; apenas metadados cifrados são catalogados.",
                bytes(row["name_encrypted"]).hex(), row["technology"], row["updated_at"],
            )
        return rows

    def roles(self) -> tuple[dict[str, object], ...]:
        with self._database.read_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM career_roles WHERE active=1 ORDER BY position,slug"
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def role_path(self, role_slug: str) -> tuple[dict[str, object], ...]:
        with self._database.read_connection() as connection:
            rows = connection.execute(
                """SELECT n.*,
                          group_concat(DISTINCT t.slug) track_slugs,
                          group_concat(DISTINCT d.prerequisite_node_id) prerequisites
                   FROM career_nodes n JOIN career_roles r ON r.id=n.role_id
                   LEFT JOIN career_node_tracks nt ON nt.node_id=n.id
                   LEFT JOIN learning_tracks t ON t.id=nt.track_id
                   LEFT JOIN career_node_dependencies d ON d.node_id=n.id
                   WHERE r.slug=? AND r.active=1
                   GROUP BY n.id ORDER BY n.stage,n.position,n.id""",
                (role_slug,),
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def guidance_policy(self, exercise_id: UUID | str) -> dict[str, object] | None:
        identity = str(exercise_id)
        with self._database.read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM exercise_guidance_policies WHERE exercise_id=?",
                (identity,),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["walkthrough"] = json.loads(self._cipher.decrypt(
            row["walkthrough_encrypted"],
            associated_data=f"exercise_guidance_policies.walkthrough:{identity}".encode(),
        ).decode("utf-8"))
        result["expected_trace"] = tuple(json.loads(self._cipher.decrypt(
            row["expected_trace_encrypted"],
            associated_data=f"exercise_guidance_policies.trace:{identity}".encode(),
        ).decode("utf-8")))
        del result["walkthrough_encrypted"]
        del result["expected_trace_encrypted"]
        return result

    def audit(self) -> dict[str, object]:
        diversity = _exercise_diversity()
        card_buckets = Counter(item.card_bucket for item in OFFICIAL_CONCEPTS)
        glossary_buckets = Counter(item.glossary_bucket for item in OFFICIAL_CONCEPTS)
        with self._database.read_connection() as connection:
            releases = int(connection.execute(
                "SELECT count(*) FROM content_catalog_releases WHERE status='active'"
            ).fetchone()[0])
            release = connection.execute(
                "SELECT id,counts_json,checksum FROM content_catalog_releases WHERE status='active'"
            ).fetchone()
            counts = json.loads(release["counts_json"]) if release else {}
            duplicate_source_keys = int(connection.execute(
                """SELECT count(*) FROM (
                       SELECT canonical_key FROM curated_sources
                       WHERE canonical_key<>'' GROUP BY canonical_key HAVING count(*)>1
                   )"""
            ).fetchone()[0])
            empty_source_keys = int(connection.execute(
                "SELECT count(*) FROM curated_sources WHERE trim(canonical_key)=''"
            ).fetchone()[0])
            source_rows = connection.execute(
                """SELECT s.id,s.title,s.canonical_url FROM curated_sources s
                   JOIN content_catalog_items i ON i.item_id=s.id
                   WHERE i.release_id=? AND i.item_type='source' AND i.status='active'""",
                (release["id"] if release else "",),
            ).fetchall()
            archived_cards_visible = int(connection.execute(
                """SELECT count(*) FROM catalog_search_entries e
                   WHERE e.entity_type='card' AND EXISTS(
                       SELECT 1 FROM content_catalog_items i
                       JOIN content_catalog_releases r ON r.id=i.release_id
                       WHERE r.status='active' AND i.item_type='card'
                         AND i.item_id=e.entity_id AND i.status<>'active')"""
            ).fetchone()[0])
            career_counts = {
                "roles": int(connection.execute("SELECT count(*) FROM career_roles WHERE active=1").fetchone()[0]),
                "nodes": int(connection.execute("SELECT count(*) FROM career_nodes").fetchone()[0]),
                "track_links": int(connection.execute("SELECT count(*) FROM career_node_tracks").fetchone()[0]),
                "area_links": int(connection.execute("SELECT count(*) FROM career_role_areas").fetchone()[0]),
                "project_links": int(connection.execute("SELECT count(*) FROM career_role_projects").fetchone()[0]),
            }
            dag_cycles = int(connection.execute(
                """WITH RECURSIVE reach(node_id,ancestor_id) AS (
                       SELECT node_id,prerequisite_node_id FROM career_node_dependencies
                       UNION
                       SELECT reach.node_id,d.prerequisite_node_id
                       FROM reach JOIN career_node_dependencies d
                         ON d.node_id=reach.ancestor_id
                   ) SELECT count(*) FROM reach WHERE node_id=ancestor_id"""
            ).fetchone()[0])
            generated_integrity = dict(connection.execute(
                """SELECT
                   (SELECT count(*) FROM exercise_catalog_provenance WHERE release_id=?) total,
                   (SELECT count(*) FROM exercise_catalog_provenance p
                      WHERE p.release_id=? AND NOT EXISTS(
                        SELECT 1 FROM exercise_source_links s WHERE s.exercise_id=p.exercise_id)) missing_source,
                   (SELECT count(*) FROM exercise_catalog_provenance p
                      WHERE p.release_id=? AND NOT EXISTS(
                        SELECT 1 FROM exercise_reference_solutions s WHERE s.exercise_id=p.exercise_id)) missing_solution,
                   (SELECT count(*) FROM exercise_catalog_provenance p
                      WHERE p.release_id=? AND NOT EXISTS(
                        SELECT 1 FROM exercise_guidance_policies g WHERE g.exercise_id=p.exercise_id)) missing_policy""",
                (release["id"],) * 4 if release else ("",) * 4,
            ).fetchone())
            release_id = release["id"] if release else ""
            measured_delta = self._delta_counts(connection, release_id)
            card_source_minimum = int(connection.execute(
                """SELECT min(total) FROM (
                       SELECT tc.id,count(DISTINCT l.source_id) total
                       FROM theory_cards tc
                       JOIN document_chunks dc ON dc.id=tc.chunk_id
                       LEFT JOIN card_source_links l ON l.card_id=tc.id
                       WHERE dc.section LIKE 'official-%' GROUP BY tc.id
                   )"""
            ).fetchone()[0] or 0)
            glossary_source_minimum = int(connection.execute(
                """SELECT min(source_total) FROM (
                       SELECT e.id,count(DISTINCT l.source_id) source_total
                       FROM glossary_entries e
                       JOIN glossary_source_links marker ON marker.entry_id=e.id
                        AND marker.source_id LIKE 'src-official-%'
                       LEFT JOIN glossary_source_links l ON l.entry_id=e.id
                       GROUP BY e.id
                   )"""
            ).fetchone()[0] or 0)
            glossary_example_minimum = int(connection.execute(
                """SELECT min(example_total) FROM (
                       SELECT e.id,count(DISTINCT x.id) example_total
                       FROM glossary_entries e
                       JOIN glossary_source_links marker ON marker.entry_id=e.id
                        AND marker.source_id LIKE 'src-official-%'
                       LEFT JOIN glossary_examples x ON x.entry_id=e.id
                       GROUP BY e.id
                   )"""
            ).fetchone()[0] or 0)
            formula_source_minimum = int(connection.execute(
                """SELECT min(source_total) FROM (
                       SELECT tc.id,count(DISTINCT l.source_id) source_total
                       FROM theory_cards tc
                       JOIN document_chunks dc ON dc.id=tc.chunk_id
                       JOIN card_presentation cp ON cp.card_id=tc.id AND cp.format='formula'
                       LEFT JOIN card_source_links l ON l.card_id=tc.id
                       WHERE dc.section LIKE 'official-%' GROUP BY tc.id
                   )"""
            ).fetchone()[0] or 0)
            formula_detail_count = int(connection.execute(
                "SELECT count(*) FROM card_formula_details"
            ).fetchone()[0])
            missing_formula_details = int(connection.execute(
                """SELECT count(*) FROM card_presentation cp
                   JOIN theory_cards tc ON tc.id=cp.card_id
                   JOIN document_chunks dc ON dc.id=tc.chunk_id
                   WHERE cp.format='formula' AND dc.section LIKE 'official-%'
                     AND NOT EXISTS(
                         SELECT 1 FROM card_formula_details f WHERE f.card_id=cp.card_id
                     )"""
            ).fetchone()[0])
            official_family_counts = {
                family: int(connection.execute(
                    """SELECT count(*) FROM content_catalog_items
                       WHERE release_id=? AND item_type='source' AND status='active'
                         AND item_id LIKE ?""",
                    (release_id, f"src-official-{family}-%"),
                ).fetchone()[0])
                for family in OFFICIAL_SOURCE_QUOTAS
            }
        bad_sources = []
        for source in source_rows:
            parsed = urlsplit(source["canonical_url"])
            folded_title = " ".join(source["title"].casefold().split())
            bad_title = (
                folded_title in {"placeholder", "example source", "untitled"}
                or "lorem ipsum" in folded_title
            )
            allowed_url = (
                parsed.scheme == "aprendix-library"
                or (parsed.scheme in {"http", "https"} and parsed.netloc.casefold() in _SOURCE_HOST_ALLOWLIST)
            )
            if bad_title or not allowed_url:
                bad_sources.append(source["id"])
        passed = all((
            releases == 1,
            bool(release and len(release["checksum"]) == 64),
            all(int(counts.get(key, 0)) >= value for key, value in _TOTAL_MINIMUMS.items()),
            all(int(measured_delta.get(key, 0)) == value for key, value in _DELTA_MINIMUMS.items()),
            duplicate_source_keys == 0,
            empty_source_keys == 0,
            not bad_sources,
            archived_cards_visible == 0,
            career_counts["roles"] == 5,
            career_counts["track_links"] >= career_counts["nodes"],
            career_counts["project_links"] == 50,
            dag_cycles == 0,
            official_family_counts == OFFICIAL_SOURCE_QUOTAS,
            dict(card_buckets) == OFFICIAL_CARD_BUCKET_QUOTAS,
            dict(glossary_buckets) == OFFICIAL_GLOSSARY_BUCKET_QUOTAS,
            card_source_minimum >= 2,
            glossary_source_minimum >= 2,
            glossary_example_minimum >= 2,
            formula_detail_count > 0,
            formula_source_minimum >= 3,
            missing_formula_details == 0,
            int(generated_integrity.get("total", 0)) == 500,
            int(diversity["contracts"]) == 500,
            int(diversity["solution_asts"]) == 500,
            int(diversity["test_suites"]) == 500,
            int(diversity["normalized_structures"]) >= 25,
            all(int(total) == 100 for total in diversity["role_counts"].values()),
            all(int(generated_integrity.get(key, 0)) == 0 for key in (
                "missing_source", "missing_solution", "missing_policy",
            )),
        ))
        return {
            "passed": passed, "release": dict(release) if release else None,
            "counts": counts, "duplicate_source_keys": duplicate_source_keys,
            "delta": measured_delta,
            "empty_source_keys": empty_source_keys, "bad_sources": tuple(bad_sources),
            "archived_cards_visible": archived_cards_visible,
            "career": career_counts, "dag_cycles": dag_cycles,
            "generated_exercises": generated_integrity,
            "exercise_diversity": diversity,
            "official_source_families": official_family_counts,
            "official_card_buckets": dict(card_buckets),
            "official_glossary_buckets": dict(glossary_buckets),
            "card_source_minimum": card_source_minimum,
            "glossary_source_minimum": glossary_source_minimum,
            "glossary_example_minimum": glossary_example_minimum,
            "formula_detail_count": formula_detail_count,
            "formula_source_minimum": formula_source_minimum,
            "missing_formula_details": missing_formula_details,
        }
