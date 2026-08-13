"""Persistence and catalogue search for structured pedagogical content."""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256

from pydantic import TypeAdapter

from aprendix.application.contracts.models import ExerciseDTO
from aprendix.application.contracts.pedagogy import (
    CalloutBlockDTO,
    CodeBlockDTO,
    DiagramBlockDTO,
    FormulaBlockDTO,
    ListBlockDTO,
    ParagraphBlockDTO,
    PedagogicalAssetDTO,
    PedagogicalBlockDTO,
    PedagogicalDocumentDTO,
    PedagogicalOwnerType,
    PedagogicalSourceLinkDTO,
    ReferencesBlockDTO,
    SignatureBlockDTO,
    TableBlockDTO,
    TitleBlockDTO,
)
from aprendix.application.exercise_presentation import build_exercise_brief
from aprendix.application.pedagogical_documents import (
    block_fingerprint,
    block_plain_text,
    build_pedagogical_document,
    deterministic_card_svg,
    normalize_pedagogical_text,
)
from aprendix.infrastructure.db.database import Database
from aprendix.infrastructure.security import AesGcmFieldCipher

_BLOCK_ADAPTER = TypeAdapter(PedagogicalBlockDTO)
_SVG_FORBIDDEN = re.compile(
    r"<(?:script|foreignObject|iframe|object|embed)\b|\bon[a-z]+\s*=|"
    r"\b(?:href|xlink:href)\s*=\s*['\"](?:https?:|data:|file:|//)",
    re.IGNORECASE,
)
_FTS_TERM = re.compile(r"[\w+#.-]{2,}", re.UNICODE)
_CATALOG_DOCUMENT_VERSION = 1
_CATALOG_STOPWORDS = frozenset({
    "a", "as", "ao", "aos", "com", "como", "da", "das", "de", "do", "dos",
    "e", "em", "entre", "explica", "explicar", "exemplo", "funciona", "mais",
    "na", "nas", "no", "nos", "o", "os", "ou", "para", "por", "porque",
    "qual", "que", "sem", "sobre", "uma", "um", "usar", "the", "and", "how",
    "what", "with", "from", "erro", "erros", "mínimo", "minimo",
    "aplicar", "avaliação", "avaliacao", "abordagens", "comparar", "consolidar",
    "diagnosticar", "exercício", "exercicios", "exercícios", "fundamentais",
    "prático", "pratico", "profissional", "referência", "referências",
    "referencia", "referencias", "percurso", "treino",
})
_CATALOG_QUERY_ALIASES = {
    "acumulado": ("acumulada", "accumulated", "compound"),
    "backpropagation": ("backprop", "autograd", "gradient"),
    "cadeia": ("chain",),
    "compostos": ("composto", "compound"),
    "ciberseguranca": ("cybersecurity", "security"),
    "automacao": ("automation",),
    "decorador": ("decorator", "decorators"),
    "decoradores": ("decorador", "decorator", "decorators"),
    "juros": ("juro", "interest"),
    "ml": ("learning",),
    "privilegio": ("privilege",),
    "regra": ("rule",),
    "robotica": ("robotics",),
}
_INTERNAL_CATALOG_INTENT = re.compile(
    r"\b(?:exerc[ií]cio|projeto|card|dicion[aá]rio|gloss[aá]rio|curso|li[cç][aã]o)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class CatalogSearchHit:
    id: str
    entity_type: str
    entity_id: str
    title: str
    excerpt: str
    area_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    score: float


class PedagogicalRepository:
    """Store immutable assets, typed documents and a rights-safe public index."""

    def __init__(self, database: Database, cipher: AesGcmFieldCipher) -> None:
        self._database = database
        self._cipher = cipher
        self._catalog_search_ready = False
        self._catalog_search_cache: dict[
            tuple[str, tuple[str, ...], tuple[str, ...], int],
            tuple[CatalogSearchHit, ...],
        ] = {}

    @staticmethod
    def _validate_asset_payload(asset: PedagogicalAssetDTO) -> None:
        if sha256(asset.content).hexdigest() != asset.id:
            raise ValueError("asset content hash mismatch")
        if asset.mime_type == "image/svg+xml":
            try:
                svg = asset.content.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError("SVG assets must be valid UTF-8") from exc
            if not svg.lstrip().startswith("<svg") or _SVG_FORBIDDEN.search(svg):
                raise ValueError("SVG contains an unsafe or external construct")

    def save_asset(self, asset: PedagogicalAssetDTO) -> None:
        self._validate_asset_payload(asset)
        with self._database.transaction() as connection:
            existing = connection.execute(
                "SELECT content FROM pedagogical_assets WHERE id=?", (asset.id,)
            ).fetchone()
            if existing is not None and bytes(existing["content"]) != asset.content:
                raise ValueError("content-addressed asset collision")
            connection.execute(
                """INSERT INTO pedagogical_assets(
                    id,mime_type,content,storage_uri,byte_size,width,height,alt_text,
                    provenance,license,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    alt_text=excluded.alt_text,provenance=excluded.provenance,
                    license=excluded.license""",
                (
                    asset.id, asset.mime_type, asset.content, asset.storage_uri,
                    asset.byte_size, asset.width, asset.height, asset.alt_text,
                    asset.provenance, asset.license, asset.created_at.isoformat(),
                ),
            )

    def get_asset(self, asset_id: str) -> PedagogicalAssetDTO | None:
        with self._database.read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM pedagogical_assets WHERE id=?", (asset_id,)
            ).fetchone()
        if row is None:
            return None
        return PedagogicalAssetDTO(
            id=row["id"], mime_type=row["mime_type"], content=bytes(row["content"]),
            storage_uri=row["storage_uri"], byte_size=row["byte_size"],
            width=row["width"], height=row["height"], alt_text=row["alt_text"],
            provenance=row["provenance"], license=row["license"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def save_document(self, document: PedagogicalDocumentDTO) -> None:
        with self._database.transaction() as connection:
            for block in document.blocks:
                asset_id = getattr(block, "asset_id", None)
                if asset_id is not None and connection.execute(
                    "SELECT 1 FROM pedagogical_assets WHERE id=?", (asset_id,)
                ).fetchone() is None:
                    raise ValueError(f"pedagogical asset does not exist: {asset_id}")
            connection.execute(
                """INSERT INTO pedagogical_documents(
                    id,owner_type,owner_id,title,summary,locale,version,provenance,
                    license,fingerprint,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,summary=excluded.summary,locale=excluded.locale,
                    provenance=excluded.provenance,license=excluded.license,
                    fingerprint=excluded.fingerprint,updated_at=excluded.updated_at""",
                (
                    document.id, document.owner_type.value, document.owner_id,
                    document.title, document.summary, document.locale, document.version,
                    document.provenance, document.license, document.fingerprint,
                    document.created_at.isoformat(), document.updated_at.isoformat(),
                ),
            )
            connection.execute(
                "DELETE FROM pedagogical_blocks WHERE document_id=?", (document.id,)
            )
            for block in document.blocks:
                payload = block.model_dump(mode="json", exclude={"schema_version"})
                connection.execute(
                    """INSERT INTO pedagogical_blocks(
                        id,document_id,ordinal,kind,payload_json,plain_text,fingerprint,
                        asset_id,provenance,license
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        block.id, document.id, block.ordinal, block.kind,
                        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                        block_plain_text(block), block_fingerprint(block),
                        getattr(block, "asset_id", None), block.provenance, block.license,
                    ),
                )
            connection.execute(
                "DELETE FROM pedagogical_document_sources WHERE document_id=?", (document.id,)
            )
            for source in document.sources:
                inserted = connection.execute(
                    """INSERT INTO pedagogical_document_sources(
                        document_id,source_id,position,locator,rationale,source_version
                    ) SELECT ?,id,?,?,?,? FROM curated_sources WHERE id=?""",
                    (
                        document.id, source.position, source.locator, source.rationale,
                        source.source_version, source.source_id,
                    ),
                ).rowcount
                if inserted != 1:
                    raise ValueError(f"curated source does not exist: {source.source_id}")

    def get_document(self, owner_type: str, owner_id: str) -> PedagogicalDocumentDTO | None:
        with self._database.read_connection() as connection:
            row = connection.execute(
                """SELECT * FROM pedagogical_documents
                   WHERE owner_type=? AND owner_id=? ORDER BY version DESC LIMIT 1""",
                (owner_type, owner_id),
            ).fetchone()
            if row is None:
                return None
            block_rows = connection.execute(
                """SELECT payload_json FROM pedagogical_blocks
                   WHERE document_id=? ORDER BY ordinal""",
                (row["id"],),
            ).fetchall()
            source_rows = connection.execute(
                """SELECT source_id,position,locator,rationale,source_version
                   FROM pedagogical_document_sources WHERE document_id=? ORDER BY position""",
                (row["id"],),
            ).fetchall()
        blocks = tuple(
            _BLOCK_ADAPTER.validate_python(json.loads(item["payload_json"]))
            for item in block_rows
        )
        sources = tuple(PedagogicalSourceLinkDTO(**dict(item)) for item in source_rows)
        return PedagogicalDocumentDTO(
            id=row["id"], owner_type=row["owner_type"], owner_id=row["owner_id"],
            title=row["title"], summary=row["summary"], locale=row["locale"],
            version=row["version"], provenance=row["provenance"], license=row["license"],
            fingerprint=row["fingerprint"], blocks=blocks, sources=sources,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _decrypt(self, blob: bytes | None, context: str) -> str:
        if blob is None:
            return ""
        return self._cipher.decrypt(blob, associated_data=context.encode()).decode("utf-8")

    @staticmethod
    def _block_common(owner_type: str, owner_id: str, ordinal: int) -> dict[str, object]:
        return {
            "id": sha256(
                f"aprendix:block:{owner_type}:{owner_id}:{ordinal}".encode("utf-8")
            ).hexdigest(),
            "ordinal": ordinal,
            "provenance": "Aprendix original; cobertura orientada por fontes curadas.",
            "license": "MIT",
        }

    @staticmethod
    def _source_links(
        source_ids: Iterable[str], *, advanced: bool, rationale: str,
    ) -> tuple[PedagogicalSourceLinkDTO, ...]:
        unique = tuple(dict.fromkeys(str(item) for item in source_ids if item))
        target = 3 if advanced and len(unique) >= 3 else min(2, len(unique))
        return tuple(
            PedagogicalSourceLinkDTO(
                source_id=source_id, position=position, locator="",
                rationale=rationale, source_version="stable",
            )
            for position, source_id in enumerate(unique[:target])
        )

    def seed_catalog_documents(self) -> dict[str, int]:
        """Materialize the course spine into typed, source-linked documents.

        The compiler is deterministic and idempotent.  It never copies book
        prose: local Aprendix explanations remain the body; curated sources
        identify where a learner can validate or deepen that original lesson.
        """

        with self._database.read_connection() as connection:
            expected_counts = {
                "lesson": int(connection.execute(
                    "SELECT count(*) FROM learning_units WHERE kind='theory'"
                ).fetchone()[0]),
                "exercise": int(connection.execute(
                    "SELECT count(DISTINCT exercise_id) FROM learning_units "
                    "WHERE kind='practice' AND exercise_id IS NOT NULL"
                ).fetchone()[0]),
                "project": int(connection.execute(
                    "SELECT count(*) FROM guided_project_templates"
                ).fetchone()[0]),
            }
            missing_or_incomplete = int(connection.execute(
                """WITH expected(owner_type,owner_id) AS (
                       SELECT 'lesson',id FROM learning_units WHERE kind='theory'
                       UNION ALL
                       SELECT 'exercise',exercise_id FROM learning_units
                        WHERE kind='practice' AND exercise_id IS NOT NULL
                       UNION ALL
                       SELECT 'project',id FROM guided_project_templates
                   )
                   SELECT count(*) FROM expected e
                   WHERE NOT EXISTS (
                       SELECT 1 FROM pedagogical_documents p
                       WHERE p.owner_type=e.owner_type AND p.owner_id=e.owner_id
                         AND p.version=?
                         AND (SELECT count(*) FROM pedagogical_blocks b
                              WHERE b.document_id=p.id) >= 5
                         AND (SELECT count(*) FROM pedagogical_document_sources s
                              WHERE s.document_id=p.id) >= 2
                   )""",
                (_CATALOG_DOCUMENT_VERSION,),
            ).fetchone()[0])
            broken_assets = int(connection.execute(
                """SELECT count(*) FROM pedagogical_blocks b
                   LEFT JOIN pedagogical_assets a ON a.id=b.asset_id
                   WHERE b.asset_id IS NOT NULL AND a.id IS NULL"""
            ).fetchone()[0])
            if missing_or_incomplete == 0 and broken_assets == 0 and sum(expected_counts.values()):
                return {
                    "total": sum(expected_counts.values()), "updated": 0, "assets": 0,
                    **expected_counts,
                }
            lesson_rows = connection.execute(
                """SELECT theory.id,theory.title,theory.body_encrypted,
                          theory.example_encrypted,c.id chapter_id,c.title chapter_title,
                          c.objective,t.slug track_slug,t.position track_position,
                          practice.exercise_id,
                          (SELECT a.id FROM assessment_items a
                           JOIN learning_units quiz ON quiz.id=a.unit_id
                           WHERE quiz.chapter_id=c.id AND a.kind='theory'
                           ORDER BY a.id LIMIT 1) assessment_id
                   FROM learning_units theory
                   JOIN learning_chapters c ON c.id=theory.chapter_id
                   JOIN learning_tracks t ON t.id=c.track_id
                   LEFT JOIN learning_units practice
                     ON practice.chapter_id=c.id AND practice.kind='practice'
                   WHERE theory.kind='theory'
                   ORDER BY t.position,c.position,theory.position"""
            ).fetchall()
            exercise_rows = connection.execute(
                """SELECT DISTINCT e.*,t.slug track_slug,t.position track_position,
                          c.title chapter_title,c.objective
                   FROM learning_units u
                   JOIN learning_chapters c ON c.id=u.chapter_id
                   JOIN learning_tracks t ON t.id=c.track_id
                   JOIN exercises e ON e.id=u.exercise_id
                   WHERE u.kind='practice'
                   ORDER BY t.position,c.position,e.slug"""
            ).fetchall()
            project_rows = connection.execute(
                "SELECT * FROM guided_project_templates ORDER BY track_slug,id"
            ).fetchall()
            source_rows = connection.execute(
                "SELECT exercise_id,source_id FROM exercise_source_links ORDER BY exercise_id,source_id"
            ).fetchall()
            track_source_rows = connection.execute(
                """SELECT DISTINCT t.slug track_slug,esl.source_id
                   FROM learning_tracks t
                   JOIN learning_chapters c ON c.track_id=t.id
                   JOIN learning_units u ON u.chapter_id=c.id AND u.kind='practice'
                   JOIN exercise_source_links esl ON esl.exercise_id=u.exercise_id
                   ORDER BY t.slug,esl.source_id"""
            ).fetchall()
            assessment_rows = connection.execute(
                "SELECT id,prompt_encrypted FROM assessment_items"
            ).fetchall()
            existing = {
                (row["owner_type"], row["owner_id"]): row["fingerprint"]
                for row in connection.execute(
                    """SELECT p.owner_type,p.owner_id,p.fingerprint
                       FROM pedagogical_documents p
                       JOIN (SELECT owner_type,owner_id,max(version) version
                             FROM pedagogical_documents GROUP BY owner_type,owner_id) latest
                         ON latest.owner_type=p.owner_type AND latest.owner_id=p.owner_id
                        AND latest.version=p.version"""
                )
            }

        sources_by_exercise: dict[str, list[str]] = {}
        for row in source_rows:
            sources_by_exercise.setdefault(str(row["exercise_id"]), []).append(
                str(row["source_id"])
            )
        sources_by_track: dict[str, list[str]] = {}
        for row in track_source_rows:
            sources_by_track.setdefault(str(row["track_slug"]), []).append(
                str(row["source_id"])
            )
        assessment_prompts = {
            str(row["id"]): self._decrypt(
                row["prompt_encrypted"], f"assessment_items.prompt:{row['id']}"
            )
            for row in assessment_rows
        }

        documents: list[PedagogicalDocumentDTO] = []
        new_assets: dict[str, PedagogicalAssetDTO] = {}
        previous_lesson: dict[str, str] = {}

        def common(kind: str, identity: str, blocks: list[PedagogicalBlockDTO]):
            return self._block_common(kind, identity, len(blocks))

        for row in lesson_rows:
            identity = str(row["id"])
            track_slug = str(row["track_slug"])
            advanced = int(row["track_position"]) >= 6
            body = self._decrypt(
                row["body_encrypted"], f"learning_units.body:{identity}"
            )
            example = self._decrypt(
                row["example_encrypted"], f"learning_units.example:{identity}"
            )
            source_ids = sources_by_exercise.get(str(row["exercise_id"]), ())
            if len(source_ids) < (3 if advanced else 2):
                source_ids = tuple(dict.fromkeys((*source_ids, *sources_by_track.get(track_slug, ()))))
            links = self._source_links(
                source_ids, advanced=advanced,
                rationale="Valida os conceitos e a terminologia desta aula original Aprendix.",
            )
            prerequisites = previous_lesson.get(
                track_slug,
                "Nenhum pré-requisito curricular; basta reconhecer entradas, transformações e saídas.",
            )
            blocks: list[PedagogicalBlockDTO] = []
            blocks.append(TitleBlockDTO(
                **common("lesson", identity, blocks), level=1,
                text=str(row["chapter_title"]),
            ))
            blocks.append(TitleBlockDTO(
                **common("lesson", identity, blocks), level=2, text="Objetivos",
            ))
            blocks.append(ListBlockDTO(
                **common("lesson", identity, blocks), items=(
                    str(row["objective"]),
                    "Explicar o contrato com palavras próprias antes de programar.",
                    "Verificar pelo menos um caso normal e um caso-limite.",
                ),
            ))
            blocks.append(TitleBlockDTO(
                **common("lesson", identity, blocks), level=2, text="Pré-requisitos",
            ))
            blocks.append(ParagraphBlockDTO(
                **common("lesson", identity, blocks), text=prerequisites,
            ))
            blocks.append(TitleBlockDTO(
                **common("lesson", identity, blocks), level=2, text="Explicação essencial",
            ))
            blocks.append(ParagraphBlockDTO(
                **common("lesson", identity, blocks), text=body,
            ))
            if example.strip():
                blocks.append(TitleBlockDTO(
                    **common("lesson", identity, blocks), level=2, text="Exemplo orientador",
                ))
                blocks.append(CodeBlockDTO(
                    **common("lesson", identity, blocks), language="python", code=example,
                    caption="Exemplo para observar e modificar; não é a solução do exercício.",
                ))
            blocks.append(TitleBlockDTO(
                **common("lesson", identity, blocks), level=2, text="Casos-limite",
            ))
            blocks.append(ListBlockDTO(
                **common("lesson", identity, blocks), items=(
                    "Entrada vazia ou ausente quando o contrato a admite.",
                    "Valor mínimo, fronteira de mudança e valor imediatamente superior.",
                    "Repetições, ordem ou tipos inválidos que possam alterar o resultado.",
                ),
            ))
            question = assessment_prompts.get(str(row["assessment_id"]), "")
            if question:
                blocks.append(CalloutBlockDTO(
                    **common("lesson", identity, blocks), tone="definition",
                    title="Verificação curta", body=question,
                ))
            if track_slug == "math-programming":
                blocks.append(FormulaBlockDTO(
                    **common("lesson", identity, blocks),
                    latex=r"y=\sum_{i=1}^{n} x_i w_i+b",
                    spoken="O resultado linear soma cada entrada vezes o respetivo peso e acrescenta o viés.",
                    variables={"x_i": "entrada i", "w_i": "peso i", "b": "viés"},
                ))
            if advanced and len(documents) % 7 == 0:
                asset = deterministic_card_svg(
                    area_title=str(row["chapter_title"]), fact=body,
                    format_name="diagrama de aula",
                )
                new_assets[asset.id] = asset
                blocks.append(DiagramBlockDTO(
                    **common("lesson", identity, blocks), asset_id=asset.id,
                    diagram_kind="concept-map", alt_text=asset.alt_text,
                    caption="Mapa conceptual original Aprendix desta aula.",
                ))
            if links:
                blocks.append(ReferencesBlockDTO(
                    **common("lesson", identity, blocks), references=links,
                ))
            documents.append(build_pedagogical_document(
                owner_type=PedagogicalOwnerType.LESSON, owner_id=identity,
                title=str(row["chapter_title"]), summary=str(row["objective"]),
                blocks=blocks, sources=links, version=_CATALOG_DOCUMENT_VERSION,
            ))
            previous_lesson[track_slug] = (
                f"A aula anterior deste percurso, {row['chapter_title']}, e os respetivos casos-limite."
            )

        for row in exercise_rows:
            identity = str(row["id"])
            track_slug = str(row["track_slug"])
            advanced = int(row["track_position"]) >= 6
            exercise = ExerciseDTO(
                id=row["id"], graph_node_id=row["graph_node_id"], slug=row["slug"],
                title=row["title"], prompt=row["prompt"], starter_code=row["starter_code"],
                tests=tuple(json.loads(row["tests_json"])), difficulty=row["difficulty"],
                version=row["version"], created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
            brief = build_exercise_brief(exercise)
            source_ids = sources_by_exercise.get(identity, ())
            if len(source_ids) < (3 if advanced else 2):
                source_ids = tuple(dict.fromkeys((*source_ids, *sources_by_track.get(track_slug, ()))))
            links = self._source_links(
                source_ids, advanced=advanced,
                rationale="Sustenta o contrato técnico; enunciado e testes são originais Aprendix.",
            )
            blocks: list[PedagogicalBlockDTO] = [
                TitleBlockDTO(**self._block_common("exercise", identity, 0), level=1, text=brief.title),
                TitleBlockDTO(**self._block_common("exercise", identity, 1), level=2, text="Contextualização"),
                ParagraphBlockDTO(**self._block_common("exercise", identity, 2), text=brief.context),
                TitleBlockDTO(**self._block_common("exercise", identity, 3), level=2, text="Objetivo"),
                ParagraphBlockDTO(**self._block_common("exercise", identity, 4), text=brief.task),
            ]
            for signature in brief.required_names:
                blocks.append(SignatureBlockDTO(
                    **common("exercise", identity, blocks), signature=signature,
                    language="python", description=brief.result_contract,
                ))
            blocks.append(TitleBlockDTO(
                **common("exercise", identity, blocks), level=2, text="Entradas e parâmetros",
            ))
            blocks.append(ListBlockDTO(
                **common("exercise", identity, blocks), items=brief.parameters,
            ))
            if brief.public_examples:
                blocks.append(TitleBlockDTO(
                    **common("exercise", identity, blocks), level=2,
                    text="Exemplos de comportamento",
                ))
                blocks.append(CodeBlockDTO(
                    **common("exercise", identity, blocks), language="python",
                    code="\n".join(brief.public_examples),
                    caption="Exemplos públicos; o corretor também verifica casos de fronteira.",
                ))
            blocks.append(TitleBlockDTO(
                **common("exercise", identity, blocks), level=2,
                text="Requisitos e casos-limite",
            ))
            blocks.append(ListBlockDTO(
                **common("exercise", identity, blocks), items=brief.constraints,
            ))
            blocks.append(CalloutBlockDTO(
                **common("exercise", identity, blocks), tone="tip",
                title="Critérios de aceitação",
                body=("Executa sem erros, respeita a assinatura, preserva os argumentos e "
                      "passa os casos normais e de fronteira do corretor local."),
            ))
            if links:
                blocks.append(ReferencesBlockDTO(
                    **common("exercise", identity, blocks), references=links,
                ))
            documents.append(build_pedagogical_document(
                owner_type=PedagogicalOwnerType.EXERCISE, owner_id=identity,
                title=brief.title, summary=brief.task, blocks=blocks, sources=links,
                version=_CATALOG_DOCUMENT_VERSION,
            ))

        for row in project_rows:
            identity = str(row["id"])
            track_slug = str(row["track_slug"])
            requirements = tuple(json.loads(row["requirements_json"]))
            milestones = tuple(json.loads(row["milestones_json"]))
            rubric = tuple(json.loads(row["rubric_json"]))
            advanced = str(row["level"]) == "advanced"
            links = self._source_links(
                sources_by_track.get(track_slug, ()), advanced=advanced,
                rationale="Orienta a arquitetura e os critérios deste projeto original Aprendix.",
            )
            blocks: list[PedagogicalBlockDTO] = [
                TitleBlockDTO(**self._block_common("project", identity, 0), level=1, text=str(row["title"])),
                TitleBlockDTO(**self._block_common("project", identity, 1), level=2, text="Contexto e objetivo"),
                ParagraphBlockDTO(**self._block_common("project", identity, 2), text=str(row["brief"])),
                TitleBlockDTO(**self._block_common("project", identity, 3), level=2, text="Entregáveis e requisitos"),
                ListBlockDTO(**self._block_common("project", identity, 4), items=requirements),
                TitleBlockDTO(**self._block_common("project", identity, 5), level=2, text="Milestones"),
                ListBlockDTO(**self._block_common("project", identity, 6), items=milestones, ordered=True),
                TitleBlockDTO(**self._block_common("project", identity, 7), level=2, text="Rubrica e aceitação"),
                TableBlockDTO(
                    **self._block_common("project", identity, 8),
                    headers=("Critério", "Evidência esperada"),
                    rows=tuple((criterion, "Demonstrado por código e testes locais") for criterion in rubric),
                    caption="A correção avalia cada critério de forma independente.",
                ),
                CalloutBlockDTO(
                    **self._block_common("project", identity, 9), tone="warning",
                    title="Execução local segura",
                    body="O projeto deve funcionar no sandbox sem rede, subprocessos ou ficheiros externos.",
                ),
            ]
            if links:
                blocks.append(ReferencesBlockDTO(
                    **common("project", identity, blocks), references=links,
                ))
            documents.append(build_pedagogical_document(
                owner_type=PedagogicalOwnerType.PROJECT, owner_id=identity,
                title=str(row["title"]), summary=str(row["brief"])[:500],
                blocks=blocks, sources=links, version=_CATALOG_DOCUMENT_VERSION,
            ))

        for asset in new_assets.values():
            self.save_asset(asset)
        updated = 0
        for document in documents:
            key = (document.owner_type.value, document.owner_id)
            if existing.get(key) != document.fingerprint:
                self.save_document(document)
                updated += 1
        counts = {"lesson": 0, "exercise": 0, "project": 0}
        for document in documents:
            counts[document.owner_type.value] += 1
        return {"total": len(documents), "updated": updated, "assets": len(new_assets), **counts}

    def rebuild_catalog_search(self) -> dict[str, int]:
        """Index authored catalogue content and only explicitly permitted readings."""

        records: dict[tuple[str, str], dict[str, object]] = {}

        def put(
            entity_type: str,
            entity_id: str,
            title: str,
            body: str,
            *,
            keywords: str = "",
            area_ids: Iterable[str] = (),
            source_ids: Iterable[str] = (),
            prefer: bool = False,
        ) -> None:
            key = (entity_type, entity_id)
            previous = records.get(key)
            if previous is not None and not prefer:
                return
            if previous is not None:
                # A structured pedagogical document enriches the searchable
                # prose, but it must not erase the catalogue relationships
                # already collected from the canonical owner record.
                area_ids = tuple(area_ids) or tuple(previous["area_ids"])
                source_ids = tuple(source_ids) or tuple(previous["source_ids"])
                keywords = keywords or str(previous["keywords"])
            records[key] = {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "title": normalize_pedagogical_text(title) or entity_id,
                "body": normalize_pedagogical_text(body),
                "keywords": normalize_pedagogical_text(keywords),
                "area_ids": tuple(dict.fromkeys(str(item) for item in area_ids if item)),
                "source_ids": tuple(dict.fromkeys(str(item) for item in source_ids if item)),
            }

        with self._database.read_connection() as connection:
            source_links: dict[str, list[str]] = {}
            for link in connection.execute(
                "SELECT card_id,source_id FROM card_source_links ORDER BY card_id,position"
            ):
                source_links.setdefault(link["card_id"], []).append(link["source_id"])
            card_areas: dict[str, list[str]] = {}
            for link in connection.execute(
                """SELECT tc.id card_id,kac.area_id FROM theory_cards tc
                   JOIN knowledge_area_chunks kac ON kac.chunk_id=tc.chunk_id
                   ORDER BY tc.id,kac.area_id"""
            ):
                card_areas.setdefault(link["card_id"], []).append(link["area_id"])
            for row in connection.execute(
                """SELECT tc.id,tc.title,tc.body_encrypted,tc.code_example_encrypted,
                          COALESCE(cp.format,'concept') format
                   FROM theory_cards tc LEFT JOIN card_presentation cp ON cp.card_id=tc.id
                   WHERE EXISTS(
                       SELECT 1 FROM content_catalog_items ci
                       JOIN content_catalog_releases cr ON cr.id=ci.release_id
                       WHERE cr.status='active' AND ci.item_type='card'
                         AND ci.item_id=tc.id AND ci.content_type='editorial'
                         AND ci.status='active'
                   )"""
            ):
                card_id = row["id"]
                body = self._decrypt(row["body_encrypted"], f"theory_cards.body:{card_id}")
                code = self._decrypt(row["code_example_encrypted"], f"theory_cards.code:{card_id}")
                put(
                    "card", card_id, row["title"], f"{body}\n{code}",
                    keywords=row["format"], area_ids=card_areas.get(card_id, ()),
                    source_ids=source_links.get(card_id, ()),
                )

            glossary_sources: dict[str, list[str]] = {}
            for link in connection.execute(
                "SELECT entry_id,source_id FROM glossary_source_links ORDER BY entry_id,position"
            ):
                glossary_sources.setdefault(link["entry_id"], []).append(link["source_id"])
            alias_map: dict[str, list[str]] = {}
            for alias in connection.execute(
                "SELECT entry_id,alias FROM glossary_aliases ORDER BY entry_id,normalized_alias"
            ):
                alias_map.setdefault(alias["entry_id"], []).append(alias["alias"])
            for row in connection.execute("SELECT * FROM glossary_entries"):
                entry_id = row["id"]
                # Definitions/examples are deliberately encrypted fields.  The
                # public catalogue may index the non-sensitive term, aliases
                # and technology, but must never create a plaintext shadow of
                # those encrypted values in an FTS table.
                put(
                    "glossary", entry_id, row["term"], row["term"],
                    keywords=" ".join((*alias_map.get(entry_id, ()), row["technology"])),
                    source_ids=glossary_sources.get(entry_id, ()),
                )

            unit_sources: dict[str, list[str]] = {}
            for link in connection.execute(
                """SELECT u.id unit_id,esl.source_id FROM learning_units u
                   JOIN exercise_source_links esl ON esl.exercise_id=u.exercise_id
                   ORDER BY u.id,esl.source_id"""
            ):
                unit_sources.setdefault(link["unit_id"], []).append(link["source_id"])
            unit_areas: dict[str, list[str]] = {}
            for link in connection.execute(
                """SELECT u.id unit_id,ka.id area_id FROM learning_units u
                   JOIN learning_chapters c ON c.id=u.chapter_id
                   JOIN graph_nodes gn ON gn.id=c.graph_node_id
                   JOIN knowledge_areas ka ON ka.slug=gn.slug
                   ORDER BY u.id,ka.id"""
            ):
                unit_areas.setdefault(link["unit_id"], []).append(link["area_id"])
            for row in connection.execute(
                """SELECT u.*,c.title chapter_title,t.title track_title,t.technology
                   FROM learning_units u JOIN learning_chapters c ON c.id=u.chapter_id
                   JOIN learning_tracks t ON t.id=c.track_id"""
            ):
                unit_id = row["id"]
                body = self._decrypt(row["body_encrypted"], f"learning_units.body:{unit_id}")
                example = self._decrypt(row["example_encrypted"], f"learning_units.example:{unit_id}")
                entity_type = "project" if row["kind"] == "project" else "lesson"
                put(
                    entity_type, unit_id, row["title"], f"{body}\n{example}",
                    keywords=f"{row['chapter_title']} {row['track_title']} {row['technology']} {row['kind']}",
                    area_ids=unit_areas.get(unit_id, ()), source_ids=unit_sources.get(unit_id, ()),
                )

            exercise_sources: dict[str, list[str]] = {}
            for link in connection.execute(
                "SELECT exercise_id,source_id FROM exercise_source_links ORDER BY exercise_id,source_id"
            ):
                exercise_sources.setdefault(link["exercise_id"], []).append(link["source_id"])
            for row in connection.execute(
                """SELECT e.*,gn.slug node_slug,gn.title node_title FROM exercises e
                   JOIN graph_nodes gn ON gn.id=e.graph_node_id"""
            ):
                put(
                    "exercise", row["id"], row["title"],
                    f"{row['prompt']}\n{row['starter_code']}\n{row['tests_json']}",
                    keywords=f"{row['slug']} {row['node_slug']} {row['node_title']}",
                    area_ids=(row["node_slug"],), source_ids=exercise_sources.get(row["id"], ()),
                )

            for row in connection.execute("SELECT * FROM guided_project_templates"):
                put(
                    "project", row["id"], row["title"],
                    f"{row['brief']}\n{row['requirements_json']}\n{row['milestones_json']}\n{row['rubric_json']}",
                    keywords=f"{row['track_slug']} {row['level']} projeto capstone",
                )

            source_areas: dict[str, list[str]] = {}
            for link in connection.execute(
                "SELECT source_id,area_id FROM knowledge_area_sources ORDER BY source_id,position"
            ):
                source_areas.setdefault(link["source_id"], []).append(link["area_id"])
            for row in connection.execute("SELECT * FROM curated_sources"):
                authors = " ".join(json.loads(row["authors_json"]))
                put(
                    "source", row["id"], row["title"],
                    f"{authors}\n{row['overview']}\n{row['why_it_matters']}\n{row['access_note']}",
                    keywords=f"{row['source_type']} {row['doi'] or ''}",
                    area_ids=source_areas.get(row["id"], ()), source_ids=(row["id"],),
                )

            permitted_documents = connection.execute(
                """SELECT d.id,d.title,d.author FROM documents d
                   JOIN document_provenance p ON p.document_id=d.id
                   WHERE p.rights_status='permitted' AND d.lifecycle='active'
                     AND d.source_path<>'aprendix://authored-facts/v1'"""
            ).fetchall()
            for document in permitted_documents:
                chunks = connection.execute(
                    """SELECT id,text_encrypted,section FROM document_chunks
                       WHERE document_id=? ORDER BY ordinal""", (document["id"],)
                ).fetchall()
                body_parts = []
                for chunk in chunks:
                    body_parts.append(chunk["section"])
                    body_parts.append(self._decrypt(
                        chunk["text_encrypted"], f"document_chunks.text:{chunk['id']}"
                    ))
                put(
                    "reading", document["id"], document["title"], "\n".join(body_parts),
                    keywords=document["author"] or "",
                )

            active_editorial_cards = {
                row["item_id"] for row in connection.execute(
                    """SELECT ci.item_id FROM content_catalog_items ci
                       JOIN content_catalog_releases cr ON cr.id=ci.release_id
                       WHERE cr.status='active' AND ci.item_type='card'
                         AND ci.content_type='editorial' AND ci.status='active'"""
                )
            }
            for row in connection.execute("SELECT * FROM pedagogical_documents ORDER BY version"):
                if row["owner_type"] == "card" and row["owner_id"] not in active_editorial_cards:
                    continue
                blocks = connection.execute(
                    """SELECT plain_text FROM pedagogical_blocks
                       WHERE document_id=? ORDER BY ordinal""", (row["id"],)
                ).fetchall()
                links = connection.execute(
                    """SELECT source_id FROM pedagogical_document_sources
                       WHERE document_id=? ORDER BY position""", (row["id"],)
                ).fetchall()
                entity_type = {
                    "lesson": "lesson", "exercise": "exercise", "project": "project",
                    "reading": "reading", "card": "card", "glossary": "glossary",
                    "source": "source",
                }[row["owner_type"]]
                put(
                    entity_type, row["owner_id"], row["title"],
                    f"{row['summary']}\n" + "\n".join(item["plain_text"] for item in blocks),
                    source_ids=(item["source_id"] for item in links), prefer=True,
                )

        now = datetime.now(UTC).isoformat()
        with self._database.transaction() as connection:
            connection.execute("DELETE FROM catalog_search_fts")
            connection.execute("DELETE FROM catalog_search_entries")
            by_type: dict[str, int] = {}
            for key in sorted(records):
                record = records[key]
                canonical = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                entry_id = sha256(f"catalog:{key[0]}:{key[1]}".encode()).hexdigest()
                fingerprint = sha256(canonical.encode()).hexdigest()
                connection.execute(
                    """INSERT INTO catalog_search_entries(
                        id,entity_type,entity_id,title,body,keywords,area_ids_json,
                        source_ids_json,fingerprint,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        entry_id, record["entity_type"], record["entity_id"], record["title"],
                        record["body"], record["keywords"],
                        json.dumps(record["area_ids"], ensure_ascii=False),
                        json.dumps(record["source_ids"], ensure_ascii=False), fingerprint, now,
                    ),
                )
                connection.execute(
                    "INSERT INTO catalog_search_fts(entry_id,title,body,keywords) VALUES(?,?,?,?)",
                    (entry_id, record["title"], record["body"], record["keywords"]),
                )
                entity_type = str(record["entity_type"])
                by_type[entity_type] = by_type.get(entity_type, 0) + 1
        self._catalog_search_ready = True
        self._catalog_search_cache.clear()
        return {"total": len(records), **by_type}

    @staticmethod
    def _fts_term_groups(query: str) -> tuple[tuple[str, ...], ...]:
        """Return bounded synonym groups, one group per user concept."""

        groups: list[tuple[str, ...]] = []
        seen: set[str] = set()
        for raw in _FTS_TERM.findall(normalize_pedagogical_text(query).casefold()):
            escaped = raw.replace('"', '""')
            if (
                escaped not in _CATALOG_STOPWORDS
                and not escaped.isdigit()
                and escaped not in seen
            ):
                alternatives = [escaped]
                seen.add(escaped)
                for alias in _CATALOG_QUERY_ALIASES.get(escaped, ()):
                    if alias not in seen:
                        alternatives.append(alias)
                        seen.add(alias)
                groups.append(tuple(alternatives))
        return tuple(groups[:8])

    @staticmethod
    def _fts_token(term: str) -> str:
        return f'"{term}"*' if len(term) >= 5 else f'"{term}"'

    @classmethod
    def _fts_query(cls, query: str) -> str:
        groups = cls._fts_term_groups(query)
        if not groups:
            return ""
        # Prefixes are useful for Portuguese inflection, but very short prefixes
        # make FTS visit most of the catalogue.  Keep the query discriminative.
        return " OR ".join(
            cls._fts_token(term)
            for group in groups for term in group
        )

    @classmethod
    def _focused_fts_query(cls, query: str) -> str:
        """Require two concepts in FTS; the broad form remains a no-hit fallback."""

        groups = cls._fts_term_groups(query)
        if not groups:
            return ""
        expressions = [
            "(" + " OR ".join(cls._fts_token(term) for term in group) + ")"
            for group in groups[:2]
        ]
        return " AND ".join(expressions)

    @staticmethod
    def _lexical_coverage(query: str, text: str) -> tuple[int, int]:
        """Count original query concepts supported by text or a bounded alias."""

        def fold(value: str) -> str:
            return unicodedata.normalize("NFKD", value).encode(
                "ascii", "ignore"
            ).decode().casefold()

        query_terms = tuple(dict.fromkeys(
            fold(raw)
            for raw in _FTS_TERM.findall(normalize_pedagogical_text(query))
            if fold(raw) not in _CATALOG_STOPWORDS and not raw.isdigit()
        ))
        text_terms = set(_FTS_TERM.findall(fold(text)))

        def related(left: str, right: str) -> bool:
            if left == right:
                return True
            shorter, longer = sorted((left, right), key=len)
            return len(shorter) >= 4 and longer.startswith(shorter)

        matched = 0
        for term in query_terms:
            alternatives = (term, *_CATALOG_QUERY_ALIASES.get(term, ()))
            if any(related(alternative, candidate)
                   for alternative in alternatives for candidate in text_terms):
                matched += 1
        return matched, len(query_terms)

    def search_catalog(
        self,
        query: str,
        *,
        entity_types: tuple[str, ...] = (),
        area_ids: tuple[str, ...] = (),
        limit: int = 20,
    ) -> tuple[CatalogSearchHit, ...]:
        cache_key = (
            normalize_pedagogical_text(query).casefold(),
            tuple(entity_types), tuple(area_ids), max(1, min(limit, 100)),
        )
        cached = self._catalog_search_cache.get(cache_key)
        if cached is not None:
            return cached
        if not self._catalog_search_ready:
            with self._database.read_connection() as connection:
                indexed = connection.execute(
                    "SELECT 1 FROM catalog_search_entries LIMIT 1"
                ).fetchone()
            if indexed is None:
                self.rebuild_catalog_search()
            else:
                self._catalog_search_ready = True
        fts_query = self._fts_query(query)
        if not fts_query:
            return ()
        clauses = ["catalog_search_fts MATCH ?"]
        parameters: list[object] = [fts_query]
        if entity_types:
            allowed = {"lesson", "exercise", "project", "card", "glossary", "source", "reading"}
            values = tuple(value for value in entity_types if value in allowed)
            if not values:
                return ()
            clauses.append(f"e.entity_type IN ({','.join('?' for _ in values)})")
            parameters.extend(values)
        requested_limit = max(1, min(limit, 100))
        # A modest evidence pool lets us promote the canonical references
        # linked to the best topical records.  This is still a bounded FTS
        # query and avoids a second search pass.
        fetch_limit = min(500, max(requested_limit, 8))
        parameters.append(fetch_limit)
        with self._database.read_connection() as connection:
            search_sql = f"""SELECT e.*,bm25(catalog_search_fts,8.0,2.0,4.0) rank,
                                      snippet(catalog_search_fts,2,'','',' … ',28) excerpt
                               FROM catalog_search_fts JOIN catalog_search_entries e
                                 ON e.id=catalog_search_fts.entry_id
                               WHERE {' AND '.join(clauses)}
                               ORDER BY rank,e.entity_type,e.title LIMIT ?"""
            rows = connection.execute(search_sql, parameters).fetchall()
            hits: list[CatalogSearchHit] = []
            requested_areas = set(area_ids)
            for row in rows:
                entry_areas = tuple(json.loads(row["area_ids_json"]))
                if requested_areas and not requested_areas.intersection(entry_areas):
                    continue
                matched, concepts = self._lexical_coverage(
                    query,
                    (
                        f"{row['title']} {row['body']} {row['keywords']} "
                        f"{' '.join(entry_areas)}"
                    ),
                )
                required = min(concepts, 2) if concepts else 0
                if matched < required:
                    continue
                rank = float(row["rank"])
                hits.append(CatalogSearchHit(
                    id=row["id"], entity_type=row["entity_type"], entity_id=row["entity_id"],
                    title=row["title"], excerpt=row["excerpt"] or row["body"][:500],
                    area_ids=entry_areas,
                    source_ids=tuple(json.loads(row["source_ids_json"])),
                    score=1.0 / (1.0 + abs(rank)),
                ))

            source_allowed = not entity_types or "source" in entity_types
            source_first = source_allowed and not _INTERNAL_CATALOG_INTENT.search(query)
            if source_first:
                support: dict[str, float] = {}
                for position, hit in enumerate(hits[: max(12, requested_limit)]):
                    # SQLite's BM25 value is negative and rows are already in
                    # strongest-first order.  Use that stable order directly;
                    # a reciprocal transform of ``abs(rank)`` would invert the
                    # evidence and let a weak late match sponsor the sources.
                    positional = 1.0 / (1.0 + position)
                    for source_id in hit.source_ids:
                        support[source_id] = max(support.get(source_id, 0.0), positional)
                source_hits = {hit.entity_id: hit for hit in hits if hit.entity_type == "source"}
                missing = tuple(source_id for source_id in support if source_id not in source_hits)
                if missing:
                    placeholders = ",".join("?" for _ in missing)
                    for row in connection.execute(
                        f"""SELECT * FROM catalog_search_entries
                            WHERE entity_type='source' AND entity_id IN ({placeholders})""",
                        missing,
                    ):
                        source_hits[row["entity_id"]] = CatalogSearchHit(
                            id=row["id"], entity_type="source", entity_id=row["entity_id"],
                            title=row["title"], excerpt=row["body"][:500],
                            area_ids=tuple(json.loads(row["area_ids_json"])),
                            source_ids=tuple(json.loads(row["source_ids_json"])),
                            score=support[row["entity_id"]],
                        )
                promoted = sorted(
                    source_hits.values(),
                    key=lambda hit: (-support.get(hit.entity_id, hit.score), hit.title.casefold()),
                )[:2]
                if promoted:
                    promoted_ids = {item.entity_id for item in promoted}
                    hits = promoted + [
                        item for item in hits
                        if not (item.entity_type == "source" and item.entity_id in promoted_ids)
                    ]
        result = tuple(hits[:requested_limit])
        if len(self._catalog_search_cache) >= 512:
            self._catalog_search_cache.clear()
        self._catalog_search_cache[cache_key] = result
        return result
