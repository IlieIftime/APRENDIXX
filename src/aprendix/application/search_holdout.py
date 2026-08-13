"""Deterministic, versioned holdout for whole-catalog retrieval quality."""

from __future__ import annotations

import math
import statistics
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from aprendix.application.advanced_learning_catalog import AREA_SEEDS


@dataclass(frozen=True, slots=True)
class SearchHoldoutQuery:
    id: str
    query: str
    expected_area_id: str
    expected_source_ids: tuple[str, ...]
    hard_negative_area_ids: tuple[str, ...]
    intent: str


def _words(text: str, count: int) -> str:
    return " ".join(text.strip(" .").split()[:count])


def build_search_holdout() -> tuple[SearchHoldoutQuery, ...]:
    """Return 120 unseen phrasings covering every authored leaf area."""

    areas = tuple(sorted(AREA_SEEDS))
    records: list[SearchHoldoutQuery] = []
    for area_index, area_id in enumerate(areas):
        seed = AREA_SEEDS[area_id]
        concept = seed.concepts[(area_index * 3 + 1) % len(seed.concepts)]
        negatives = (
            areas[(area_index + 11) % len(areas)],
            areas[(area_index + 23) % len(areas)],
        )
        queries = (
            (
                f"explica {concept.name} e {_words(concept.mechanism, 5)}",
                "definition",
            ),
            (
                f"como aplicar {concept.name} em {seed.title} com um exemplo mínimo",
                "how-to",
            ),
            (
                f"diagnosticar erro de {concept.name}: {_words(concept.boundary, 7)}",
                "debug",
            ),
        )
        for variant, (query, intent) in enumerate(queries):
            records.append(SearchHoldoutQuery(
                id=f"holdout-{area_id}-{variant + 1}",
                query=query,
                expected_area_id=area_id,
                expected_source_ids=seed.sources,
                hard_negative_area_ids=negatives,
                intent=intent,
            ))
    # Three cross-domain queries exercise disambiguation rather than exact titles.
    records.extend((
        SearchHoldoutQuery(
            id="holdout-cross-001",
            query="evitar fuga de dados ao normalizar antes de uma validação temporal",
            expected_area_id="data-practice",
            expected_source_ids=("src-sklearn", "src-pandas"),
            hard_negative_area_ids=("web", "games-app"),
            intent="debug",
        ),
        SearchHoldoutQuery(
            id="holdout-cross-002",
            query="porque dividir a atenção pelo tamanho da dimensão das keys",
            expected_area_id="transformers",
            expected_source_ids=("src-attention",),
            hard_negative_area_ids=("databases", "robotics-app"),
            intent="formula",
        ),
        SearchHoldoutQuery(
            id="holdout-cross-003",
            query="avaliar um agente verificando o ambiente e não a afirmação final",
            expected_area_id="agent-evaluation",
            expected_source_ids=("src-react",),
            hard_negative_area_ids=("web", "linear-algebra"),
            intent="compare",
        ),
    ))
    return tuple(records)


SEARCH_HOLDOUT_V2 = build_search_holdout()


def build_search_holdout_v3() -> tuple[SearchHoldoutQuery, ...]:
    """Return a 250+ query source-first holdout without changing the v2 baseline."""

    records = list(SEARCH_HOLDOUT_V2)
    areas = tuple(sorted(AREA_SEEDS))
    for area_index, area_id in enumerate(areas):
        seed = AREA_SEEDS[area_id]
        concept = seed.concepts[(area_index * 3 + 1) % len(seed.concepts)]
        negatives = (
            areas[(area_index + 11) % len(areas)],
            areas[(area_index + 23) % len(areas)],
        )
        variants = (
            (f"referências fundamentais para {concept.name} em {seed.title}", "reference"),
            (f"exemplo prático de {concept.name}: {_words(concept.mechanism, 7)}", "example"),
            (f"comparar abordagens de {concept.name}: {_words(concept.boundary, 7)}", "compare"),
            (f"exercícios para consolidar {concept.name} em {seed.title}", "exercise"),
        )
        for variant, (query, intent) in enumerate(variants, start=4):
            records.append(SearchHoldoutQuery(
                id=f"holdout-{area_id}-{variant}",
                query=query,
                expected_area_id=area_id,
                expected_source_ids=seed.sources,
                hard_negative_area_ids=negatives,
                intent=intent,
            ))
    records.extend((
        SearchHoldoutQuery(
            id="holdout-regression-capital",
            query="capital acumulado juros compostos fórmula e tabela Python",
            expected_area_id="python",
            expected_source_ids=AREA_SEEDS["python"].sources,
            hard_negative_area_ids=("computer-vision", "natural-language"),
            intent="formula",
        ),
        SearchHoldoutQuery(
            id="holdout-regression-decorators",
            query="decoradores Python função envolvente argumentos e retorno",
            expected_area_id="oop",
            expected_source_ids=AREA_SEEDS["oop"].sources,
            hard_negative_area_ids=("robotics-app", "linear-algebra"),
            intent="definition",
        ),
        SearchHoldoutQuery(
            id="holdout-regression-backprop",
            query="backpropagation regra da cadeia gradiente pesos e bias",
            expected_area_id="deep-learning",
            expected_source_ids=AREA_SEEDS["deep-learning"].sources,
            hard_negative_area_ids=("web", "databases"),
            intent="formula",
        ),
        SearchHoldoutQuery(
            id="holdout-role-ai",
            query="percurso profissional AI ML Python backpropagation treino e avaliação",
            expected_area_id="deep-learning",
            expected_source_ids=AREA_SEEDS["deep-learning"].sources,
            hard_negative_area_ids=("web", "databases"),
            intent="explore",
        ),
        SearchHoldoutQuery(
            id="holdout-role-cyber",
            query="profissional de cibersegurança Python automação menor privilégio",
            expected_area_id="cybersecurity-app",
            expected_source_ids=AREA_SEEDS["cybersecurity-app"].sources,
            hard_negative_area_ids=("health-app", "games-app"),
            intent="explore",
        ),
        SearchHoldoutQuery(
            id="holdout-role-analyst",
            query="analista de dados Python pandas validação limpeza e visualização",
            expected_area_id="data-practice",
            expected_source_ids=AREA_SEEDS["data-practice"].sources,
            hard_negative_area_ids=("robotics-app", "systems"),
            intent="explore",
        ),
        SearchHoldoutQuery(
            id="holdout-role-backend",
            query="engenheiro backend Python API FastAPI Django testes e segurança",
            expected_area_id="web",
            expected_source_ids=AREA_SEEDS["web"].sources,
            hard_negative_area_ids=("computer-vision", "calculus"),
            intent="explore",
        ),
        SearchHoldoutQuery(
            id="holdout-role-data-engineer",
            query="engenheiro de dados Python SQL transações índices e pipelines",
            expected_area_id="databases",
            expected_source_ids=AREA_SEEDS["databases"].sources,
            hard_negative_area_ids=("games-app", "convolutional-networks"),
            intent="explore",
        ),
    ))
    return tuple(records)


SEARCH_HOLDOUT_V3 = build_search_holdout_v3()


@dataclass(frozen=True, slots=True)
class SearchBenchmarkResult:
    algorithm_version: str
    query_count: int
    recall_at_10: float
    mrr: float
    ndcg_at_10: float
    hard_negative_rate_at_3: float
    p95_ms: float
    passed: bool
    measured_at: str


class CatalogSearchBenchmark:
    VERSION = "catalog-source-first-holdout-v3"

    def __init__(self, repository) -> None:
        self._repository = repository

    def run(
        self,
        holdout: tuple[SearchHoldoutQuery, ...] = SEARCH_HOLDOUT_V3,
    ) -> SearchBenchmarkResult:
        reciprocal_ranks: list[float] = []
        ndcgs: list[float] = []
        latencies: list[float] = []
        recalled = 0
        negative_intrusions = 0
        for case in holdout:
            started = time.perf_counter()
            hits = self._repository.search_catalog(case.query, limit=10)
            latencies.append((time.perf_counter() - started) * 1_000)
            relevant_rank = None
            for rank, hit in enumerate(hits, start=1):
                area_match = case.expected_area_id in hit.area_ids
                source_match = bool(set(case.expected_source_ids).intersection(hit.source_ids))
                if area_match or (source_match and hit.entity_type in {"card", "source"}):
                    relevant_rank = rank
                    break
            if relevant_rank is not None:
                recalled += 1
                reciprocal_ranks.append(1.0 / relevant_rank)
                ndcgs.append(1.0 / math.log2(relevant_rank + 1))
            else:
                reciprocal_ranks.append(0.0)
                ndcgs.append(0.0)
            # A broad reference can legitimately span both the target field
            # and a neighbouring hard-negative area (for example SQLAlchemy is
            # databases *and* software engineering).  Count an intrusion only
            # when the hit carries negative evidence without the expected area
            # or one of the expected sources.
            if any(
                set(hit.area_ids).intersection(case.hard_negative_area_ids)
                and case.expected_area_id not in hit.area_ids
                and not set(case.expected_source_ids).intersection(hit.source_ids)
                for hit in hits[:3]
            ):
                negative_intrusions += 1
        ordered = sorted(latencies)
        p95_index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * .95) - 1))
        recall = recalled / len(holdout)
        mrr = statistics.fmean(reciprocal_ranks)
        ndcg = statistics.fmean(ndcgs)
        negative_rate = negative_intrusions / len(holdout)
        p95 = ordered[p95_index]
        return SearchBenchmarkResult(
            algorithm_version=self.VERSION,
            query_count=len(holdout),
            recall_at_10=recall,
            mrr=mrr,
            ndcg_at_10=ndcg,
            hard_negative_rate_at_3=negative_rate,
            p95_ms=p95,
            passed=(
                recall >= .98 and ndcg >= .95 and negative_rate <= .02 and p95 < 150.0
            ),
            measured_at=datetime.now(UTC).isoformat(),
        )

    def persist(self, result: SearchBenchmarkResult) -> None:
        database = self._repository._database  # infrastructure-owned benchmark hook
        with database.transaction() as connection:
            connection.execute(
                """INSERT INTO search_quality_runs(
                    id,algorithm_version,query_count,recall_at_10,mrr,ndcg_at_10,
                    p95_ms,passed,measured_at
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    str(uuid5(NAMESPACE_URL, f"aprendix:{result.algorithm_version}:{result.measured_at}")),
                    result.algorithm_version, result.query_count, result.recall_at_10,
                    result.mrr, result.ndcg_at_10, result.p95_ms,
                    int(result.passed), result.measured_at,
                ),
            )
