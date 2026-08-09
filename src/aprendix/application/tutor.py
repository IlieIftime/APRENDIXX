"""Grounded, local-first tutoring with deterministic pedagogical strategies."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from aprendix.application.contracts import (
    SearchFiltersDTO, SearchRequestDTO, TutorRequestDTO, TutorResponseDTO, TutorStrategy,
)


class OfflineTutorService:
    VERSION = "tutor-v2-grounded-1"

    def __init__(self, *, user, search, repository, cache) -> None:
        self._user, self._search, self._repository, self._cache = user, search, repository, cache

    def answer(self, request: TutorRequestDTO) -> TutorResponseDTO:
        if request.evaluation_locked and re.search(
            r"\b(solu[cç][aã]o|resposta|resolve|faz por mim|c[oó]digo completo)\b",
            request.question, re.I,
        ):
            response = TutorResponseDTO(
                answer=("Posso ajudar a identificar o conceito, o primeiro passo ou um caso de teste, "
                        "mas não revelar a solução integral durante uma avaliação bloqueada."),
                confidence=1.0, strategy=request.strategy, declined=True,
                refusal_reason="locked_assessment_solution",
            )
            self._repository.save(self._user.id, request, response)
            return response
        cache_key = self._cache_key(request)
        cached = self._cache.get(cache_key)
        if cached:
            try:
                restored = TutorResponseDTO.model_validate_json(cached)
                return restored.model_copy(update={"from_cache": True})
            except (ValueError, TypeError):
                self._cache.delete(cache_key)
        search_response = self._search.search(SearchRequestDTO(
            query=request.question, filters=SearchFiltersDTO(),
            allow_web_fallback=False, max_results=30, local_confidence_threshold=0.45,
        ))
        evidence = tuple(
            item for item in search_response.evidence
            if item.origin.value == "local" and self._has_lexical_support(request.question, item)
        )[:8]
        supported_confidence = max((item.relevance for item in evidence), default=0.0)
        confidence = min(supported_confidence, search_response.confidence)
        if confidence < 0.34 or not evidence:
            response = TutorResponseDTO(
                answer=("Não encontro base local aprovada suficiente para responder com rigor. "
                        "Importa uma fonte legítima ou escolhe um conceito do curso/dicionário."),
                confidence=confidence, evidence=evidence, strategy=request.strategy,
                declined=True, refusal_reason="insufficient_approved_evidence",
            )
        else:
            response = TutorResponseDTO(
                answer=self._apply_strategy(request, search_response.answer, evidence),
                confidence=confidence, evidence=evidence, strategy=request.strategy,
            )
        self._repository.save(self._user.id, request, response)
        self._cache.put(cache_key, response.model_dump_json().encode("utf-8"), ttl_seconds=604_800)
        return response

    def history(self, *, limit: int = 50):
        return self._repository.history(self._user.id, limit=limit)

    def delete_history(self) -> int:
        return self._repository.delete_history(self._user.id)

    def _cache_key(self, request: TutorRequestDTO) -> str:
        digest = hashlib.sha256(
            (self.VERSION + "\0" + request.model_dump_json()).encode("utf-8")
        ).hexdigest()
        return "tutor:" + digest

    @staticmethod
    def _has_lexical_support(question: str, evidence) -> bool:
        """Reject embedding/hash collisions that share no meaningful term."""

        stopwords = {
            "como", "qual", "quais", "porque", "explica", "explicar", "sobre",
            "uma", "para", "com", "sem", "esta", "este", "isto", "resultado",
            "linguagem", "versao", "fonte", "codigo", "funciona", "significa",
            "num", "pela", "pelo", "entre", "deve", "fazer", "usar", "the",
            "and", "what", "how", "does", "from", "with",
        }

        def terms(value: str) -> set[str]:
            folded = unicodedata.normalize("NFKD", value).encode(
                "ascii", "ignore"
            ).decode().casefold()
            tokens = re.findall(r"[a-z_+#%]{3,}", folded)
            return {
                (token[:-1] if token.endswith("s") and len(token) > 4 else token)
                for token in tokens if token not in stopwords
            }

        query_terms = terms(question)
        evidence_terms = terms(f"{evidence.title} {evidence.excerpt}")
        overlap = query_terms & evidence_terms
        if len(query_terms) <= 2:
            return bool(overlap)
        return len(overlap) >= 2 or len(overlap) / len(query_terms) >= .5

    @staticmethod
    def _apply_strategy(request, grounded: str, evidence) -> str:
        core = grounded.strip()
        topic = evidence[0].title
        if request.strategy is TutorStrategy.SOCRATIC:
            return (f"Vamos descobrir a partir de {topic} [1].\n\n"
                    "1. Que inputs entram e que resultado esperas?\n"
                    "2. Que regra permanece verdadeira em cada passo?\n"
                    "3. Qual é o menor exemplo que distingue duas soluções possíveis?")
        if request.strategy is TutorStrategy.NEW_EXAMPLE:
            return (f"Ideia fundamentada:\n{core}\n\nNovo contexto: imagina uma pequena lista de "
                    "registos locais; aplica primeiro a regra a dois elementos e verifica o limite vazio.")
        if request.strategy is TutorStrategy.PREREQUISITE:
            return ("Antes de avançar, confirma: tipos e valores, controlo de fluxo, função/contrato "
                    f"e casos-limite. Depois regressa a {topic} [1].\n\n{core}")
        if request.strategy is TutorStrategy.SIMPLIFY_MATH:
            return ("Leitura matemática acessível: identifica primeiro as grandezas, unidades e o que "
                    "varia; depois lê cada operador como uma transformação local.\n\n" + core)
        if request.strategy is TutorStrategy.ANALYZE_ERROR:
            return ("Não alteres tudo de uma vez. Reproduz o erro com a menor entrada, compara esperado "
                    "e obtido e acompanha a primeira linha em que divergem.\n\n" + core)
        if request.strategy is TutorStrategy.MINI_EXERCISE:
            return (f"Mini-exercício sobre {topic}: escreve um exemplo mínimo, prevê o resultado sem "
                    "executar e cria dois casos-limite. Só depois confirma no IDE.\n\nBase: " + core)
        return "Outra forma de pensar no problema:\n\n" + core
