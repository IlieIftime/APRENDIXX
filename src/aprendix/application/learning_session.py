"""Deterministic pedagogy for the theory-to-practice IDE journey.

This module deliberately contains no GUI or persistence code.  The same policy
can therefore be used by the Windows shell and the mobile shell, and can be
tested without starting Kivy.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from aprendix.application.contracts import ErrorCategory, SmartCorrectionResponseDTO
from aprendix.application.pedagogy_tools import staged_hints
from aprendix.domain.enums import StrEnum


class BriefMode(StrEnum):
    SIMPLE = "simple"
    GUIDED = "guided"
    TECHNICAL = "technical"


class AssistanceStage(StrEnum):
    LOCATION = "location"
    CONCEPT = "concept"
    STRATEGY = "strategy"
    ANALOGOUS_EXAMPLE = "analogous_example"


@dataclass(frozen=True, slots=True)
class AssistanceDecision:
    """A bounded help step selected from persisted failed attempts."""

    stage: AssistanceStage
    attempt_number: int
    title: str
    guidance: tuple[str, ...]
    next_action: str
    worked_example: str = ""


def classify_error(correction: SmartCorrectionResponseDTO) -> ErrorCategory:
    if correction.status == "passed":
        return ErrorCategory.NONE
    if not correction.syntax_valid or correction.status == "syntax_error":
        return ErrorCategory.SYNTAX
    if correction.status == "error":
        return ErrorCategory.RUNTIME
    return ErrorCategory.CONCEPTUAL


def assistance_for_attempt(
    correction: SmartCorrectionResponseDTO,
    *,
    failed_attempts: int,
    concepts: Iterable[str] = (),
    theory_title: str = "",
    worked_example: str = "",
    evaluation_locked: bool = False,
) -> AssistanceDecision:
    """Return progressively stronger help without leaking hidden assertions.

    ``failed_attempts`` includes the correction that has just failed. During an
    assessment the ladder is capped at a conceptual cue. In training, an
    existing curated theory example may be shown after four failed attempts;
    it is explicitly analogous and never presented as the exercise solution.
    """

    count = max(1, failed_attempts)
    ladder = staged_hints(correction, concepts=concepts)
    if evaluation_locked:
        index = min(count - 1, 1)
    else:
        index = min(count - 1, 3)
    stage = (
        AssistanceStage.LOCATION,
        AssistanceStage.CONCEPT,
        AssistanceStage.STRATEGY,
        AssistanceStage.ANALOGOUS_EXAMPLE,
    )[index]
    titles = {
        AssistanceStage.LOCATION: "Pista 1 · Localiza o problema",
        AssistanceStage.CONCEPT: "Pista 2 · Revê o conceito",
        AssistanceStage.STRATEGY: "Pista 3 · Planeia por etapas",
        AssistanceStage.ANALOGOUS_EXAMPLE: "Pista 4 · Exemplo análogo explicado",
    }
    actions = {
        AssistanceStage.LOCATION: "Corrige primeiro o caso público ou o diagnóstico indicado e volta a testar.",
        AssistanceStage.CONCEPT: "Revê a microteoria associada e explica o contrato por palavras tuas.",
        AssistanceStage.STRATEGY: "Escreve um caso mínimo, resolve-o e só depois generaliza para fronteiras.",
        AssistanceStage.ANALOGOUS_EXAMPLE: "Compara a estrutura do exemplo com o teu plano, sem o copiar literalmente.",
    }
    guidance = tuple(ladder[: index + 1])
    example = ""
    if stage is AssistanceStage.ANALOGOUS_EXAMPLE:
        if worked_example.strip():
            heading = f"Exemplo da microteoria {theory_title!r}" if theory_title else "Exemplo da microteoria"
            example = f"{heading}\n{worked_example.strip()}"
        else:
            example = (
                "Ainda não existe um exemplo curado para este tópico. Usa os exemplos públicos "
                "do contrato para construir um caso menor, sem tentar adivinhar testes ocultos."
            )
    return AssistanceDecision(
        stage=stage,
        attempt_number=count,
        title=titles[stage],
        guidance=guidance,
        next_action=actions[stage],
        worked_example=example,
    )


def render_microtheory(title: str, body: str, example: str = "") -> str:
    """Render a compact pre-practice lesson from locally curated curriculum."""

    title = title.strip() or "Preparação para a prática"
    body = body.strip()
    example = example.strip()
    sections = [f"Microteoria · {title}"]
    sections.append(body or "Lê o contrato e identifica entradas, transformação e resultado antes de programar.")
    if example:
        sections.append("Exemplo orientador\n" + example)
    sections.append(
        "Antes de programar\n"
        "1. Diz por palavras tuas o que entra e o que deve sair.\n"
        "2. Resolve manualmente um caso simples.\n"
        "3. Identifica pelo menos um caso-limite.\n"
        "4. Implementa e usa Executar antes de Corrigir."
    )
    return "\n\n".join(sections)
