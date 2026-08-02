"""Application services for dashboards and privacy-aware hybrid search."""

from __future__ import annotations

import math
import re
import threading
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from uuid import UUID
from typing import Protocol

from aprendix.application.contracts import (
    Complexity,
    ContentKind,
    DashboardDTO,
    DashboardNodeDTO,
    EvidenceOrigin,
    GraphSnapshotDTO,
    KnowledgeClusterDTO,
    SearchEvidenceDTO,
    SearchRequestDTO,
    SearchResponseDTO,
    Technology,
    LearningTheme,
)


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

    def search(self, request: SearchRequestDTO) -> SearchResponseDTO:
        query_vector = self._embedder.embed(request.query)
        candidates = self._repository.search_candidates(request.filters)
        ranked = self._rank(request, candidates, query_vector)
        local = tuple(
            self._evidence(candidate, score)
            for score, candidate in ranked[: request.max_results]
            if score > 0.02
        )
        local_confidence = local[0].relevance if local else 0.0
        evidence: list[SearchEvidenceDTO] = list(local)
        if self._curated is not None:
            for score, source in self._curated.search_sources(
                request.query, request.filters.area_ids,
                limit=max(4, request.max_results // 2),
            ):
                evidence.append(SearchEvidenceDTO(
                    id=f"reference:{source.id}", origin=EvidenceOrigin.LOCAL,
                    title=source.title, excerpt=(
                        f"{source.overview}\n\nPorque importa: {source.why_it_matters}"
                    )[:4_000], source=source.canonical_url, relevance=score,
                    author=", ".join(source.authors) or None,
                    content_type=ContentKind.PAPER,
                    complexity=Complexity.INTERMEDIATE,
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
        ranked_evidence = sorted(
            evidence,
            key=lambda item: (-item.relevance, item.title.casefold(), item.id),
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
        )

    def _rank(
        self,
        request: SearchRequestDTO,
        candidates: tuple[SearchCandidate, ...],
        query_vector: tuple[int, ...],
    ) -> list[tuple[float, SearchCandidate]]:
        """BM25 + dense retrieval followed by a bounded cross-feature reranker."""

        if not candidates:
            return []
        query_tokens = tuple(dict.fromkeys(self._tokenize(request.query)))
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
        query_dimensions = tuple(
            (index, value) for index, value in enumerate(query_vector) if value
        )
        qnorm = math.sqrt(sum(value * value for value in query_vector))
        for index, candidate in enumerate(candidates):
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
        reranked: list[tuple[float, SearchCandidate]] = []
        query_set = set(query_tokens)
        query_phrase = " ".join(query_tokens)
        for index, fusion in fused.items():
            candidate = candidates[index]
            title_tokens = self._tokenize(candidate.title)
            body_tokens = self._tokenize(normalized[index])
            title_overlap = len(query_set & set(title_tokens)) / max(1, len(query_set))
            body_overlap = len(query_set & set(body_tokens)) / max(1, len(query_set))
            body_folded = " ".join(body_tokens)
            phrase = 1.0 if query_phrase and query_phrase in body_folded else 0.0
            # A compact deterministic cross-encoder: jointly observes query/title/body
            # features without downloading a heavyweight language model.
            cross = 1.0 / (1.0 + math.exp(-(
                -2.0 + 2.3 * title_overlap + 1.8 * body_overlap + 0.9 * phrase
            )))
            author_bonus = 0.08 if any(
                author.casefold() in (candidate.author or "").casefold()
                for author in request.filters.preferred_authors
            ) else 0.0
            score = min(1.0, 0.42 * (fusion / maximum) + 0.58 * cross + author_bonus)
            reranked.append((score, candidate))
        return sorted(reranked, key=lambda item: (-item[0], str(item[1].chunk_id)))

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
        return re.findall(r"[a-z0-9_+#.-]{2,}", folded)

    @staticmethod
    def _evidence(candidate: SearchCandidate, score: float) -> SearchEvidenceDTO:
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
