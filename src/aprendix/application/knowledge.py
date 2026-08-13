"""Application services for dashboards and privacy-aware hybrid search."""

from __future__ import annotations

import math
import re
import threading
import time
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import ClassVar, Protocol
from uuid import UUID

from aprendix.application.contracts import (
    Complexity,
    ContentKind,
    DashboardDTO,
    DashboardNodeDTO,
    EvidenceOrigin,
    GraphSnapshotDTO,
    LearningTheme,
    SearchEvidenceDTO,
    SearchIntent,
    SearchRequestDTO,
    SearchResponseDTO,
    Technology,
)
from aprendix.application.text_normalization import TextNormalizationService, TextProfile


@dataclass(frozen=True, slots=True)
class SearchCandidate:
    chunk_id: UUID
    title: str
    source_path: str
    author: str | None
    content_type: ContentKind
    complexity: Complexity
    published_at: date | None
    page_number: int | None
    text: str
    embedding: tuple[int, ...]
    technologies: tuple[Technology, ...] = ()
    themes: tuple[LearningTheme, ...] = ()
    cluster_id: str | None = None
    rights_status: str = "local-private"
    trust_score: float = 0.8
    entity_type: str = "reading_chunk"
    authority_tier: int | None = None


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    score: float
    candidate: SearchCandidate
    lexical: float
    semantic: float
    rerank: float
    reasons: tuple[str, ...]


class SearchCancellationToken:
    """Cooperative cancellation shared by the UI and the bounded local pipeline."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


class TechnicalQueryInterpreter:
    """Offline intent, aliases and conservative spelling repair for technical terms."""

    ALIASES: ClassVar[dict[str, tuple[str, ...]]] = {
        "poo": ("programacao orientada objetos", "classe", "objeto"),
        "oop": ("object oriented programming", "class", "object"),
        "ann": ("artificial neural network", "rede neuronal"),
        "cnn": ("convolutional neural network", "rede convolucional"),
        "rnn": ("recurrent neural network", "rede recorrente"),
        "rag": ("retrieval augmented generation", "recuperacao de informacao"),
        "bfs": ("breadth first search", "pesquisa em largura"),
        "dfs": ("depth first search", "pesquisa em profundidade"),
        "dp": ("dynamic programming", "programacao dinamica"),
        "api": ("application programming interface", "interface programacao"),
        "sql": ("structured query language", "base de dados relacional"),
        "ml": ("machine learning", "aprendizagem automatica"),
        "dl": ("deep learning", "aprendizagem profunda"),
        "cv": ("computer vision", "visao computacional"),
        "nlp": ("natural language processing", "processamento linguagem natural"),
        "big o": ("complexidade assintotica", "complexidade temporal"),
    }
    TYPO_FIXES: ClassVar[dict[str, str]] = {
        "pyhton": "python", "phyton": "python", "funçao": "funcao",
        "função": "funcao", "algoritimo": "algoritmo", "recursao": "recursao",
        "heranca": "heranca", "dicionario": "dicionario", "assynchio": "asyncio",
    }

    @classmethod
    def interpret(cls, query: str) -> tuple[SearchIntent, str, tuple[str, ...]]:
        # Queries can arrive from OCR, copied PDFs or legacy profiles with a
        # reversible UTF-8/CP1252 mojibake layer.  Repair that boundary once so
        # accents do not become unrelated tokens such as ``mema3ria``.
        normalized = TextNormalizationService().normalize(query, TextProfile.PROSE).text
        folded = HybridSearchService._fold(normalized)
        repaired = " ".join(cls.TYPO_FIXES.get(token, token) for token in folded.split())
        additions: list[str] = []
        for alias, expansion in cls.ALIASES.items():
            if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", repaired):
                additions.extend(expansion)
        if re.search(r"\b(erro|error|bug|falha|exception|traceback|corrigir)\b", repaired):
            intent = SearchIntent.DEBUG
        elif re.search(r"\b(exercicio|desafio|praticar|treinar)\b", repaired):
            intent = SearchIntent.EXERCISE
        elif re.search(r"\b(compar|diferen[cs]a|versus|\bvs\b)\w*", repaired):
            intent = SearchIntent.COMPARE
        elif re.search(r"\b(formula|equacao|derivada|gradiente|calcular)\b", repaired):
            intent = SearchIntent.FORMULA
        elif re.search(r"\b(exemplo|demonstracao)\b", repaired):
            intent = SearchIntent.EXAMPLE
        elif re.search(r"\b(como|criar|fazer|implementar)\b", repaired):
            intent = SearchIntent.HOW_TO
        elif re.search(r"\b(o que e|defin|significa|conceito)\w*", repaired):
            intent = SearchIntent.DEFINITION
        elif re.search(r"\b(documentacao|referencia|paper|livro|autor)\b", repaired):
            intent = SearchIntent.REFERENCE
        else:
            intent = SearchIntent.EXPLORE
        expanded = " ".join(dict.fromkeys((repaired, *additions))).strip()
        return intent, expanded, tuple(dict.fromkeys(additions))


class LocalKnowledgeIndex(Protocol):
    def search_candidates(
        self, filters, *, limit: int = 50_000
    ) -> tuple[SearchCandidate, ...]: ...


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> tuple[int, ...]: ...


class WebSearchProvider(Protocol):
    def search(self, query: str, *, max_results: int) -> tuple[SearchEvidenceDTO, ...]: ...


class CuratedKnowledgeCatalog(Protocol):
    def search_sources(
        self, query: str, area_ids: tuple[str, ...] = (), *, limit: int = 8
    ): ...


class AnswerSynthesizer(Protocol):
    def synthesize(
        self, query: str, evidence: Sequence[SearchEvidenceDTO]
    ) -> str: ...


class ExtractiveAnswerSynthesizer:
    """Deterministic local synthesis; retrieved text is evidence, never instructions."""

    def synthesize(
        self, query: str, evidence: Sequence[SearchEvidenceDTO]
    ) -> str:
        if not evidence:
            return "Não existe evidência suficiente para responder com segurança."
        query_terms = self._terms(query)
        selected: list[str] = []
        for index, item in enumerate(evidence[:6], start=1):
            sentences = re.split(r"(?<=[.!?])\s+|\n+", item.excerpt)
            ranked = sorted(
                (sentence.strip() for sentence in sentences if 40 <= len(sentence.strip()) <= 1_500),
                key=lambda sentence: (
                    -len(query_terms & self._terms(sentence)), -min(len(sentence), 700), sentence
                ),
            )
            if ranked:
                selected.append(f"{ranked[0][:700]} [{index}]")
        if not selected:
            return "Não existe evidência suficiente para responder com segurança."
        return "\n\n".join(selected)[:12_000]

    @staticmethod
    def _terms(text: str) -> set[str]:
        folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().casefold()
        return {term for term in re.findall(r"[a-z0-9_]{2,}", folded)}


class FallbackAnswerSynthesizer:
    """Use an optional local LLM, falling back to deterministic extraction."""

    def __init__(self, primary: AnswerSynthesizer, fallback: AnswerSynthesizer) -> None:
        self._primary = primary
        self._fallback = fallback

    def synthesize(self, query: str, evidence: Sequence[SearchEvidenceDTO]) -> str:
        try:
            answer = self._primary.synthesize(query, evidence).strip()
            if not answer or len(answer) > 20_000:
                raise ValueError("local model returned an invalid answer")
            if evidence and not re.search(r"\[\d+\]", answer):
                raise ValueError("local model answer did not cite its evidence")
            return answer
        except (OSError, TimeoutError, ValueError, RuntimeError):
            return self._fallback.synthesize(query, evidence)


class HybridSearchService:
    _INTERNAL_INTENT = re.compile(
        r"\b(?:aprendix|curso|aula|li[cç][aã]o|card|exerc[ií]cio|desafio|"
        r"projeto|dicion[aá]rio|percurso)\b",
        re.IGNORECASE,
    )
    _QUERY_STOPWORDS = frozenset({
        "a", "ao", "aos", "as", "com", "como", "da", "das", "de", "do", "dos",
        "e", "em", "entre", "explica", "explicar", "o", "os", "para", "por", "que",
        "qual", "quais", "sem", "sobre", "um", "uma", "the", "and", "for", "from",
        "how", "of", "to", "what", "with",
    })

    def __init__(
        self,
        repository: LocalKnowledgeIndex,
        *,
        embedder: EmbeddingProvider,
        web: WebSearchProvider | None = None,
        synthesizer: AnswerSynthesizer | None = None,
        curated: CuratedKnowledgeCatalog | None = None,
    ) -> None:
        self._repository = repository
        self._embedder = embedder
        self._web = web
        self._synthesizer = synthesizer or ExtractiveAnswerSynthesizer()
        self._curated = curated
        self._prepare_lock = threading.RLock()
        self._prepared_signature: tuple[int, str, str] | None = None
        self._prepared_text: tuple[str, ...] = ()
        self._prepared_lengths: tuple[int, ...] = ()
        self._prepared_norms: tuple[float, ...] = ()

    def search(
        self, request: SearchRequestDTO, cancellation: SearchCancellationToken | None = None
    ) -> SearchResponseDTO:
        started = time.perf_counter()
        intent, expanded_query, _expansions = TechnicalQueryInterpreter.interpret(request.query)
        if cancellation is not None and cancellation.cancelled:
            return self._cancelled(request, intent, expanded_query, started)
        query_vector = self._embedder.embed(expanded_query)
        shortlist_provider = getattr(self._repository, "search_candidates_for_query", None)
        if callable(shortlist_provider):
            shortlist_limit = min(100, max(40, request.max_results * 5))
            candidates, indexed_sparse = shortlist_provider(
                request.filters, expanded_query, query_vector, limit=shortlist_limit
            )
        else:
            candidates = self._repository.search_candidates(request.filters)
            indexed_sparse = {}
        if cancellation is not None and cancellation.cancelled:
            return self._cancelled(request, intent, expanded_query, started)
        ranked = self._rank(
            request, candidates, query_vector, expanded_query=expanded_query,
            intent=intent, cancellation=cancellation, indexed_sparse=indexed_sparse,
        )
        if cancellation is not None and cancellation.cancelled:
            return self._cancelled(request, intent, expanded_query, started)
        ranked = self._diversify(ranked, limit=min(90, request.max_results * 3))
        local = tuple(
            self._evidence(item)
            for item in ranked
        )
        local_confidence = local[0].relevance if local else 0.0
        evidence: list[SearchEvidenceDTO] = list(local)
        if self._curated is not None:
            for score, source in self._curated.search_sources(
                expanded_query, request.filters.area_ids,
                limit=max(4, request.max_results // 2),
            ):
                source_text = " ".join((
                    source.title, *source.authors, source.overview, source.why_it_matters,
                ))
                if not self._has_lexical_floor(expanded_query, source_text):
                    continue
                evidence.append(SearchEvidenceDTO(
                    id=f"reference:{source.id}", origin=EvidenceOrigin.LOCAL,
                    title=source.title, excerpt=(
                        f"{source.overview}\n\nPorque importa: {source.why_it_matters}"
                    )[:4_000], source=source.canonical_url, relevance=score,
                    author=(", ".join(source.authors)[:160] or None),
                    content_type=ContentKind.PAPER,
                    complexity=Complexity.INTERMEDIATE,
                    why_shown=("Referência curada compatível com a pergunta",),
                    lexical_score=score, rerank_score=score,
                ))
        # Curated references live in the encrypted local catalogue too.  They
        # must therefore contribute to local confidence and prevent an
        # unnecessary network fallback when they already answer the query.
        local_confidence = max(
            (item.relevance for item in evidence if item.origin == EvidenceOrigin.LOCAL),
            default=0.0,
        )
        used_web = False
        fallback_reason = None
        if local_confidence < request.local_confidence_threshold:
            if not request.allow_web_fallback:
                fallback_reason = "network_fallback_disabled"
            elif self._web is None:
                fallback_reason = "web_provider_unavailable"
            else:
                try:
                    if cancellation is not None and cancellation.cancelled:
                        return self._cancelled(request, intent, expanded_query, started)
                    web_hits = self._web.search(
                        request.query[:500], max_results=request.max_results
                    )
                    seen = {(item.title.casefold(), item.source.casefold()) for item in evidence}
                    for item in web_hits:
                        key = (item.title.casefold(), item.source.casefold())
                        if key not in seen:
                            evidence.append(item)
                            seen.add(key)
                    used_web = bool(web_hits)
                    if not web_hits:
                        fallback_reason = "web_returned_no_results"
                except (OSError, TimeoutError, ValueError, RuntimeError) as exc:
                    fallback_reason = f"web_error:{type(exc).__name__}"
        ranked_evidence = self._source_first_fusion(
            evidence,
            query=request.query,
            intent=intent,
        )
        # Several chunks from the same document can share a title.  Present
        # the strongest hit once so that a result list remains diverse and the
        # caller's max_results contract is respected after local/curated/Web
        # fusion.
        evidence = []
        seen_titles: set[tuple[str, ...]] = set()
        for item in ranked_evidence:
            title_key = tuple(self._tokenize(item.title))
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)
            evidence.append(item)
            if len(evidence) >= request.max_results:
                break
        confidence = max((item.relevance for item in evidence), default=0.0)
        answer = self._synthesizer.synthesize(request.query, evidence)
        cluster_provider = getattr(self._repository, "list_clusters", None)
        similar_topics = (
            tuple(cluster_provider(cluster_ids=tuple(dict.fromkeys(
                item.cluster_id for item in local if item.cluster_id
            )), limit=8))
            if callable(cluster_provider) else ()
        )
        return SearchResponseDTO(
            query=request.query, answer=answer, confidence=confidence,
            local_confidence=local_confidence, used_web_fallback=used_web,
            evidence=tuple(evidence), fallback_reason=fallback_reason,
            similar_topics=similar_topics,
            intent=intent, expanded_query=expanded_query,
            elapsed_ms=(time.perf_counter() - started) * 1000,
        )

    @classmethod
    def _source_first_fusion(
        cls,
        evidence: Sequence[SearchEvidenceDTO],
        *,
        query: str,
        intent: SearchIntent,
    ) -> list[SearchEvidenceDTO]:
        """Fuse authority pools without allowing internal examples to lead by default."""

        internal_intent = bool(cls._INTERNAL_INTENT.search(query)) or intent == SearchIntent.EXERCISE
        ordered = sorted(
            evidence,
            key=lambda item: (
                0 if internal_intent else cls._evidence_authority(item),
                -item.relevance,
                item.title.casefold(),
                item.id,
            ),
        )
        if internal_intent:
            return ordered
        # The authority sort already puts sources first.  This explicit quota
        # keeps the top-three invariant obvious and regression-testable when
        # future pools are added.
        sources = [item for item in ordered if cls._evidence_authority(item) <= 1]
        if len(sources) < 2:
            return ordered
        leading = sources[:2]
        return leading + [item for item in ordered if item not in leading]

    @staticmethod
    def _evidence_authority(item: SearchEvidenceDTO) -> int:
        source = item.source.casefold()
        if item.origin == EvidenceOrigin.WEB or item.id.startswith("reference:"):
            return 0
        if not source.startswith("aprendix://"):
            return 1
        if "authored-facts" in source or item.id.startswith("card:"):
            return 3
        return 2

    @staticmethod
    def _cancelled(request, intent, expanded_query, started) -> SearchResponseDTO:
        return SearchResponseDTO(
            query=request.query, answer="Pesquisa cancelada.", confidence=0,
            local_confidence=0, fallback_reason="cancelled", intent=intent,
            expanded_query=expanded_query,
            elapsed_ms=(time.perf_counter() - started) * 1000, cancelled=True,
        )

    def _rank(
        self,
        request: SearchRequestDTO,
        candidates: tuple[SearchCandidate, ...],
        query_vector: tuple[int, ...],
        *, expanded_query: str | None = None,
        intent: SearchIntent = SearchIntent.EXPLORE,
        cancellation: SearchCancellationToken | None = None,
        indexed_sparse: dict[str, float] | None = None,
    ) -> list[RankedCandidate]:
        """BM25F + dense RRF followed by a bounded, explainable reranker."""

        if not candidates:
            return []
        query_tokens = tuple(dict.fromkeys(self._tokenize(expanded_query or request.query)))
        normalized, lengths, norms = self._prepare(candidates)
        frequencies: list[dict[str, int]] = []
        document_frequency = Counter()
        for document in normalized:
            counts = {token: document.count(token) for token in query_tokens}
            frequencies.append(counts)
            document_frequency.update(token for token, count in counts.items() if count)
        average_length = sum(lengths) / max(1, len(lengths))
        sparse: list[tuple[float, int]] = []
        dense: list[tuple[float, int]] = []
        persistent_provider = getattr(self._repository, "public_lexical_scores", None)
        # Query-aware repositories already fused the persistent FTS signal into
        # indexed_sparse while producing the shortlist. Do not issue the same
        # FTS query a second time on the UI path.
        persistent_sparse = dict(indexed_sparse or {})
        if indexed_sparse is None and callable(persistent_provider):
            persistent_sparse = persistent_provider(expanded_query or request.query, limit=240)
        query_dimensions = tuple(
            (index, value) for index, value in enumerate(query_vector) if value
        )
        qnorm = math.sqrt(sum(value * value for value in query_vector))
        for index, candidate in enumerate(candidates):
            if cancellation is not None and cancellation.cancelled:
                return []
            bm25 = 0.0
            for token in query_tokens:
                frequency = frequencies[index][token]
                if not frequency:
                    continue
                df = document_frequency[token]
                inverse = math.log(1.0 + (len(candidates) - df + 0.5) / (df + 0.5))
                denominator = frequency + 1.2 * (
                    1.0 - 0.75 + 0.75 * lengths[index] / max(1.0, average_length)
                )
                bm25 += inverse * frequency * 2.2 / denominator
            # BM25F-style field weighting. Titles are short, high-signal fields;
            # code identifiers and formula glyphs are preserved by the tokenizer.
            title_counts = Counter(self._tokenize(candidate.title))
            bm25 += sum(1.8 * min(2, title_counts[token]) for token in query_tokens)
            if str(candidate.chunk_id) in persistent_sparse:
                bm25 += 4.0 * persistent_sparse[str(candidate.chunk_id)]
            sparse.append((bm25, index))
            dot = sum(value * candidate.embedding[dimension] for dimension, value in query_dimensions)
            dense.append((max(0.0, dot / max(1.0, qnorm * norms[index])), index))

        # Reciprocal-rank fusion is robust when BM25 and dense scores have
        # different scales. Only the union of the strongest candidates is reranked.
        shortlist = min(max(request.max_results * 12, 80), 240)
        fused: dict[int, float] = {}
        for weight, ranking in (
            (0.56, sorted(sparse, key=lambda item: (-item[0], str(candidates[item[1]].chunk_id)))),
            (0.44, sorted(dense, key=lambda item: (-item[0], str(candidates[item[1]].chunk_id)))),
        ):
            for position, (_score, index) in enumerate(ranking[:shortlist], start=1):
                fused[index] = fused.get(index, 0.0) + weight / (60 + position)
        maximum = max(fused.values(), default=1.0)
        maximum_sparse = max((item[0] for item in sparse), default=1.0)
        reranked: list[RankedCandidate] = []
        query_set = set(query_tokens)
        original_query_set = {
            token for token in self._tokenize(request.query)
            if token not in self._QUERY_STOPWORDS and len(token) >= 2
        }
        query_phrase = " ".join(query_tokens)
        for index, fusion in fused.items():
            candidate = candidates[index]
            title_tokens = self._tokenize(candidate.title)
            body_tokens = self._tokenize(normalized[index])
            title_overlap = len(query_set & set(title_tokens)) / max(1, len(query_set))
            body_overlap = len(query_set & set(body_tokens)) / max(1, len(query_set))
            original_overlap = self._lexical_coverage(
                original_query_set, set(title_tokens) | set(body_tokens)
            )
            body_folded = " ".join(body_tokens)
            phrase = 1.0 if query_phrase and query_phrase in body_folded else 0.0
            # Bounded joint-feature reranker fallback.  It observes the pair
            # query/title/body, but is deliberately not labelled as a learned
            # cross-encoder unless an actual verified model pack is present.
            cross = 1.0 / (1.0 + math.exp(-(
                -2.0 + 2.3 * title_overlap + 1.8 * body_overlap + 0.9 * phrase
            )))
            intent_bonus = self._intent_bonus(intent, candidate.text)
            author_bonus = 0.08 if any(
                author.casefold() in (candidate.author or "").casefold()
                for author in request.filters.preferred_authors
            ) else 0.0
            authority_bonus = (
                .08 if candidate.rights_status == "permitted" and candidate.trust_score >= .95
                else .03 if candidate.trust_score >= .9 else 0.0
            )
            sparse_score = min(1.0, sparse[index][0] / max(1.0, maximum_sparse))
            semantic_score = min(1.0, dense[index][0])
            # Dense similarity alone is not evidence: quantized fallback
            # embedders can collide.  Require lexical support, a trusted FTS
            # match, or a strong semantic pair that still shares a concept.
            required_overlap = min(
                1.0,
                (2.0 if len(original_query_set) >= 3 else 1.0) / max(1, len(original_query_set)),
            )
            lexical_supported = original_overlap >= required_overlap or phrase > 0
            semantic_supported = (
                semantic_score >= .82 and cross >= .50 and body_overlap >= .20
                and original_overlap >= max(.34, required_overlap * .75)
            )
            if not lexical_supported and not semantic_supported:
                continue
            score = min(1.0, 0.42 * (fusion / maximum) + 0.58 * cross + author_bonus
                        + authority_bonus + intent_bonus)
            # A minimal calibrated relevance prevents vague matches from
            # entering MMR and being promoted merely for being different.
            if score < .12:
                continue
            reasons = []
            if title_overlap:
                reasons.append("O título contém termos da pergunta")
            if body_overlap >= .5:
                reasons.append("O conteúdo cobre a maioria dos conceitos pedidos")
            if semantic_score >= .65:
                reasons.append("Correspondência semântica forte")
            if phrase:
                reasons.append("Expressão técnica encontrada no contexto")
            if original_overlap:
                reasons.append("Cobertura lexical verificável da pergunta")
            if candidate.cluster_id:
                reasons.append("Pertence a um tópico relacionado")
            if authority_bonus:
                reasons.append("Fonte local com proveniência de alta confiança")
            reranked.append(RankedCandidate(
                score, candidate, sparse_score, semantic_score, cross,
                tuple(reasons[:4]) or ("Resultado recuperado pela pesquisa híbrida",),
            ))
        return sorted(reranked, key=lambda item: (-item.score, str(item.candidate.chunk_id)))

    @staticmethod
    def _intent_bonus(intent: SearchIntent, text: str) -> float:
        folded = HybridSearchService._fold(text[:8_000])
        patterns = {
            SearchIntent.DEBUG: r"\b(error|erro|exception|traceback|debug|corrigir)\b",
            SearchIntent.HOW_TO: r"\b(exemplo|passo|def |class |como|implementar)\b",
            SearchIntent.EXAMPLE: r"\b(exemplo|def |class |print\()",
            SearchIntent.EXERCISE: r"\b(exercicio|resolve|implementar|teste|objetivo)\b",
            SearchIntent.FORMULA: r"[=∑∂√]|\b(formula|equacao|gradiente|derivada)\b",
            SearchIntent.DEFINITION: r"\b(definicao|significa|conceito|e um|e uma)\b",
            SearchIntent.COMPARE: r"\b(diferenca|compar|vantagem|desvantagem|versus)\w*",
            SearchIntent.REFERENCE: r"\b(referencia|documentacao|paper|livro|autor)\b",
        }
        pattern = patterns.get(intent)
        return .04 if pattern and re.search(pattern, folded) else 0.0

    @staticmethod
    def _cosine_pair(left: tuple[int, ...], right: tuple[int, ...]) -> float:
        dot = sum(a * b for a, b in zip(left, right))
        norm = math.sqrt(sum(a * a for a in left) * sum(b * b for b in right))
        return max(0.0, dot / max(1.0, norm))

    def _diversify(self, ranked: list[RankedCandidate], *, limit: int) -> list[RankedCandidate]:
        """MMR removes near-duplicates while retaining the most relevant evidence."""
        if not ranked:
            return []
        relevance_floor = max(.12, ranked[0].score * .42)
        remaining = [
            item for item in ranked[:max(80, limit * 10)]
            if item.score >= relevance_floor
        ]
        selected: list[RankedCandidate] = []
        while remaining and len(selected) < limit:
            best = max(
                remaining,
                key=lambda item: (
                    .82 * item.score - .18 * max(
                        (self._cosine_pair(item.candidate.embedding, chosen.candidate.embedding)
                         for chosen in selected), default=0.0,
                    ),
                    -len(item.candidate.text), str(item.candidate.chunk_id),
                ),
            )
            selected.append(best)
            remaining.remove(best)
        return selected

    def _prepare(
        self, candidates: tuple[SearchCandidate, ...]
    ) -> tuple[tuple[str, ...], tuple[int, ...], tuple[float, ...]]:
        signature = (
            len(candidates), str(candidates[0].chunk_id), str(candidates[-1].chunk_id)
        )
        with self._prepare_lock:
            if signature != self._prepared_signature:
                normalized = tuple(
                    unicodedata.normalize(
                        "NFKD", f"{item.title} {item.text}"
                    ).encode("ascii", "ignore").decode().casefold()
                    for item in candidates
                )
                self._prepared_text = normalized
                self._prepared_lengths = tuple(
                    max(1, len(re.findall(r"[a-z0-9_+#.-]{2,}", item)))
                    for item in normalized
                )
                self._prepared_norms = tuple(
                    math.sqrt(sum(value * value for value in item.embedding))
                    for item in candidates
                )
                self._prepared_signature = signature
            return self._prepared_text, self._prepared_lengths, self._prepared_norms

    def _score(
        self,
        request: SearchRequestDTO,
        candidate: SearchCandidate,
        query_vector: tuple[int, ...],
    ) -> float:
        query_terms = self._terms(request.query)
        text_terms = self._terms(f"{candidate.title} {candidate.text}")
        lexical = len(query_terms & text_terms) / max(1, len(query_terms))
        dot = sum(a * b for a, b in zip(query_vector, candidate.embedding, strict=True))
        qnorm = math.sqrt(sum(value * value for value in query_vector))
        dnorm = math.sqrt(sum(value * value for value in candidate.embedding))
        cosine = max(0.0, dot / max(1.0, qnorm * dnorm))
        score = 0.62 * lexical + 0.38 * cosine
        folded_author = (candidate.author or "").casefold()
        if any(author.casefold() in folded_author for author in request.filters.preferred_authors):
            score += 0.08
        return min(1.0, max(0.0, score))

    @staticmethod
    def _terms(text: str) -> set[str]:
        folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().casefold()
        return {term for term in re.findall(r"[a-z0-9_]{2,}", folded)}

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().casefold()
        return re.findall(
            r"__[a-z0-9_]+__|[a-z][a-z0-9_+#.-]*|==|!=|<=|>=|//|\*\*|[%+*/-]",
            folded,
        )

    @classmethod
    def _has_lexical_floor(cls, query: str, text: str) -> bool:
        query_terms = {
            token for token in cls._tokenize(query)
            if token not in cls._QUERY_STOPWORDS and len(token) >= 2
        }
        coverage = cls._lexical_coverage(query_terms, set(cls._tokenize(text)))
        required = min(1.0, (2.0 if len(query_terms) >= 3 else 1.0) / max(1, len(query_terms)))
        return coverage >= required

    @staticmethod
    def _lexical_coverage(query_terms: set[str], text_terms: set[str]) -> float:
        def related(left: str, right: str) -> bool:
            if left == right:
                return True
            shorter, longer = sorted((left, right), key=len)
            return len(shorter) >= 4 and longer.startswith(shorter)

        matched = sum(any(related(query, term) for term in text_terms) for query in query_terms)
        return matched / max(1, len(query_terms))

    @staticmethod
    def _fold(text: str) -> str:
        return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().casefold()

    @staticmethod
    def _evidence(item: RankedCandidate) -> SearchEvidenceDTO:
        candidate, score = item.candidate, item.score
        excerpt = candidate.text.strip().replace("\x00", "")[:4_000]
        return SearchEvidenceDTO(
            id=str(candidate.chunk_id), origin=EvidenceOrigin.LOCAL,
            title=candidate.title, excerpt=excerpt or "Conteúdo local",
            source=candidate.source_path, relevance=score,
            author=candidate.author, content_type=candidate.content_type,
            complexity=candidate.complexity, published_at=candidate.published_at,
            page_number=candidate.page_number,
            technologies=candidate.technologies, themes=candidate.themes,
            cluster_id=candidate.cluster_id,
            why_shown=item.reasons, lexical_score=item.lexical,
            semantic_score=item.semantic, rerank_score=item.rerank,
        )


class DashboardService:
    @staticmethod
    def from_snapshot(snapshot: GraphSnapshotDTO) -> DashboardDTO:
        recommended = {item.node_id for item in snapshot.recommendations}
        nodes = tuple(
            DashboardNodeDTO(
                node_id=node.id, title=node.title,
                mastery=node.statistics.mastery,
                attempts=node.statistics.attempt_count,
                recommended=node.id in recommended,
            )
            for node in snapshot.nodes
        )
        attempts = sum(node.attempts for node in nodes)
        overall = (
            sum(node.mastery for node in nodes) / len(nodes) if nodes else 0.0
        )
        return DashboardDTO(
            overall_mastery=overall, total_attempts=attempts,
            mastered_nodes=sum(node.mastery >= 0.8 for node in nodes), nodes=nodes,
        )
