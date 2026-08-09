"""Deterministic golden-query evaluation for the offline retrieval pipeline."""

from __future__ import annotations

import math
import statistics
import time
from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from aprendix.application.contracts import SearchRequestDTO


ALGORITHM_VERSION = "hybrid-bm25f-q8-rrf-joint-reranker-mmr-v3"


@dataclass(frozen=True, slots=True)
class GoldenQuery:
    query: str
    relevant_slugs: tuple[str, ...]
    relevant_evidence_ids: tuple[str, ...] = ()

    @property
    def relevant_ids(self) -> frozenset[str]:
        authored = frozenset(
            str(uuid5(NAMESPACE_URL, f"aprendix:fact-chunk:{slug}"))
            for slug in self.relevant_slugs
        )
        return authored | frozenset(self.relevant_evidence_ids)


GOLDEN_QUERIES = (
    GoldenQuery("como testar se um número é par com módulo", ("modulo-paridade",)),
    GoldenQuery("problema do argumento predefinido mutável em Python", ("mutable-default",)),
    GoldenQuery("complexidade e funcionamento da pesquisa binária", ("binary-search",)),
    GoldenQuery("regra da cadeia e gradiente em backpropagation", ("chain-rule", "backprop")),
    GoldenQuery(
        "evitar data leakage na validação de machine learning", ("data-leakage",),
        ("reference:src-sklearn", "reference:src-esl"),
    ),
    GoldenQuery("por que a atenção divide por raiz da dimensão", ("scaled-attention",)),
    GoldenQuery("equação de Bellman recompensa e valor futuro", ("bellman",)),
    GoldenQuery("princípio de menor privilégio em sandbox", ("least-privilege",)),
    GoldenQuery("custo de escrita de um índice de base de dados", ("database-index",)),
    GoldenQuery("ciclo observar planear agir verificar de um agente", ("agent-loop",)),
    GoldenQuery("coleções vazias numa condição truthiness", ("truthiness",)),
    GoldenQuery("generator lazy não guarda toda a sequência em memória", ("generator-lazy",)),
    GoldenQuery("composição em vez de hierarquias profundas de classes", ("composition",)),
    GoldenQuery("dataclass para registos de dados e invariantes", ("dataclass",)),
    GoldenQuery("set para teste rápido de pertença", ("set-membership",)),
    GoldenQuery("colisões de hash e igualdade de chaves", ("hash-collisions",)),
    GoldenQuery("Big-O não mede sozinho o tempo real", ("big-o-constants",)),
    GoldenQuery("testes de fronteira vazio mínimo máximo", ("tests-boundaries",)),
    GoldenQuery("transação atómica confirmar tudo ou reverter", ("transaction-atomic",)),
    GoldenQuery("HTML semântico acessibilidade nav main button", ("semantic-html",)),
    GoldenQuery("asyncio concorrência não é paralelismo de CPU", ("async-not-parallel",)),
    GoldenQuery("produto interno vetores entrada de um neurónio", ("dot-product",)),
    GoldenQuery("teorema de Bayes prior verosimilhança posterior", ("bayes",)),
    GoldenQuery("taxa de aprendizagem grande aumenta a perda", ("learning-rate",)),
    GoldenQuery("A estrela heurística admissível caminho ótimo", ("a-star",)),
    GoldenQuery("cross-validation folds e teste final intocado", ("cross-validation",)),
    GoldenQuery("probabilidade prevista precisa de calibração", ("uncertainty",)),
    GoldenQuery("bagging reduz variância com vários modelos", ("bagging",)),
    GoldenQuery("neurónio pesos bias função de ativação", ("neuron",)),
    GoldenQuery("convolução partilha pesos em posições da imagem", ("cnn-sharing",)),
    GoldenQuery("portas de esquecimento escrita e leitura LSTM", ("lstm-gates",)),
    GoldenQuery("modelo de difusão remove ruído em vários passos", ("diffusion",)),
    GoldenQuery("IoU interseção sobre união em deteção", ("iou",)),
    GoldenQuery("tokenização por subpalavras antes dos embeddings", ("tokenization",)),
    GoldenQuery("memória episódica e memória semântica em agentes", ("episodic-memory",)),
    GoldenQuery("mais agentes coordenação conflitos e duplicação", ("multi-agent",)),
    GoldenQuery("precisão global esconde erros por subgrupo", ("calibration-fairness",)),
    GoldenQuery("validação temporal em finanças evita ensinar o futuro", ("finance-split",)),
    GoldenQuery("sensibilidade e especificidade em métricas clínicas", ("medical-metrics",)),
    GoldenQuery("controlador PID proporcional integral derivativo", ("pid",)),
    GoldenQuery("movimento de jogo independente do frame delta time", ("game-delta",)),
    GoldenQuery("clique é feedback implícito com viés de exposição", ("implicit-feedback",)),
    GoldenQuery("expanding window para validar séries temporais", ("time-validation",)),
    GoldenQuery("estabilidade numérica logsumexp e escalas", ("numerical-stability",)),
    GoldenQuery("quantização int8 face a float32", ("quantization",)),
    GoldenQuery("famílias de códigos HTTP 2xx 4xx 5xx", ("curriculum-http-semantics",)),
    GoldenQuery("filtrar e projetar linhas num pipeline de consulta", ("curriculum-query-pipeline",)),
    GoldenQuery("validar dimensões no produto interno", ("curriculum-vectors-and-dot-product",)),
    GoldenQuery("localizar a primeira divergência entre obtido e esperado", ("curriculum-debug-first-divergence",)),
    GoldenQuery("calcular ReLU e conservar decisão auditável", ("curriculum-neural-agents",)),
)


def evaluate_search(service, queries=GOLDEN_QUERIES, *, k: int = 10) -> dict[str, float | int | bool]:
    recalls: list[float] = []
    reciprocal_ranks: list[float] = []
    ndcgs: list[float] = []
    durations: list[float] = []
    for item in queries:
        started = time.perf_counter()
        response = service.search(SearchRequestDTO(
            query=item.query, max_results=k, allow_web_fallback=False,
        ))
        durations.append((time.perf_counter() - started) * 1000)
        result_ids = [hit.id for hit in response.evidence[:k]]
        relevant = item.relevant_ids
        found = [index for index, identity in enumerate(result_ids, start=1) if identity in relevant]
        recalls.append(len(found) / max(1, len(relevant)))
        reciprocal_ranks.append(1.0 / min(found) if found else 0.0)
        dcg = sum(1.0 / math.log2(rank + 1) for rank in found)
        ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, min(k, len(relevant)) + 1))
        ndcgs.append(dcg / ideal if ideal else 0.0)
    ordered = sorted(durations)
    p95_index = max(0, math.ceil(.95 * len(ordered)) - 1)
    result = {
        "query_count": len(queries),
        "recall_at_10": statistics.fmean(recalls) if recalls else 0.0,
        "mrr": statistics.fmean(reciprocal_ranks) if reciprocal_ranks else 0.0,
        "ndcg_at_10": statistics.fmean(ndcgs) if ndcgs else 0.0,
        "p95_ms": ordered[p95_index] if ordered else 0.0,
    }
    result["passed"] = bool(result["ndcg_at_10"] >= .80 and result["p95_ms"] < 500)
    return result
