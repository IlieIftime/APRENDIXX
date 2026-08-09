"""Deterministic practice bank for the four Windows-MVP core tracks.

The canonical contracts live in :mod:`academy_catalog`.  Variants change the
learning context and review lens while preserving complexity and executable
acceptance tests.  This supports spaced repetition without copying exercises
from the approved bibliography.
"""

from __future__ import annotations

from dataclasses import dataclass

from aprendix.application.academy_catalog import VERTICAL_CORE_MODULES


@dataclass(frozen=True, slots=True)
class PracticeVariant:
    slug: str
    module_slug: str
    track_slug: str
    title: str
    prompt: str
    starter_code: str
    test_code: str
    difficulty: float
    source_ids: tuple[str, ...]


CONTEXTS = (
    "uma biblioteca pessoal", "um inventário local", "um sensor doméstico",
    "um orçamento familiar", "um jogo de tabuleiro", "uma agenda de estudo",
    "um catálogo de música", "um registo de transportes", "uma oficina",
    "uma pequena clínica", "um arquivo científico", "um clube desportivo",
    "um sistema de reservas",
)

REVIEW_LENSES = (
    "o caso normal e o resultado observável",
    "a entrada vazia e o valor neutro",
    "a fronteira mínima permitida pelo contrato",
    "valores repetidos e estabilidade",
    "valores negativos quando pertencem ao domínio",
    "a ausência de mutações nos argumentos",
    "erros específicos para entradas inválidas",
    "nomes claros e uma única responsabilidade",
    "o custo dominante de tempo e memória",
    "a transferência do mesmo raciocínio para dados novos",
)

_TRACK_DIFFICULTY = {
    "python-foundations": -0.65,
    "python-oop": 0.45,
    "python-algorithms": 0.75,
    "python-data-structures": 0.85,
}

TRACK_SOURCE_IDS = {
    "python-foundations": (
        "src-python-docs", "src-fluent-python", "local-43fd8801f5c6dd400aa4",
    ),
    "python-oop": (
        "src-fluent-python", "local-d4338f501fdb02a1b303",
        "local-51dee136c4143612c893", "local-e0b56cc8fbcbcb449047",
    ),
    "python-algorithms": (
        "src-clrs", "local-390a0d48a0e684dfaf50",
        "local-476258b04903fa208b48",
    ),
    "python-data-structures": (
        "src-clrs", "local-476258b04903fa208b48",
        "local-c58a09b2d9cea75ac449",
    ),
}


def generate_core_practice_variants() -> tuple[PracticeVariant, ...]:
    variants = []
    for module_slug, track_slug, title, objective, theory, starter, test in VERTICAL_CORE_MODULES:
        base_difficulty = _TRACK_DIFFICULTY[track_slug]
        ordinal = 0
        for context_index, context in enumerate(CONTEXTS):
            for lens_index, lens in enumerate(REVIEW_LENSES):
                ordinal += 1
                difficulty = max(-3.0, min(3.0,
                    base_difficulty + (lens_index - 4.5) * 0.025
                ))
                prompt = (
                    f"{objective}\n\n"
                    f"Cenário de transferência: {context}. Nesta prática, mantém o contrato "
                    f"independente do cenário e concentra a validação em {lens}.\n\n"
                    "Requisitos verificáveis:\n"
                    "1. Completa apenas o contrato iniciado no editor.\n"
                    "2. Não uses rede, processos, relógio nem ficheiros externos.\n"
                    "3. Preserva os argumentos salvo indicação explícita.\n"
                    "4. Trata casos normais, limites e inválidos de forma determinística.\n\n"
                    f"Pista conceptual: {theory}"
                )
                variants.append(PracticeVariant(
                    slug=f"core-{module_slug}-{ordinal:03d}",
                    module_slug=module_slug,
                    track_slug=track_slug,
                    title=f"{title} · prática {ordinal:03d}",
                    prompt=prompt,
                    starter_code=starter,
                    test_code=test,
                    difficulty=difficulty,
                    source_ids=TRACK_SOURCE_IDS[track_slug],
                ))
    return tuple(variants)


CORE_PRACTICE_VARIANTS = generate_core_practice_variants()
