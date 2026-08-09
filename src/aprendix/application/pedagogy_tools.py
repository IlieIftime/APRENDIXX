"""Safe, deterministic explanations derived from debugger and grading results."""

from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from aprendix.application.contracts import DebugSessionDTO, SmartCorrectionResponseDTO


@dataclass(frozen=True, slots=True)
class StructureSnapshot:
    step: int
    line: int
    name: str
    kind: str
    size: int
    shape: tuple[int, ...] = ()
    preview: str = ""


@dataclass(frozen=True, slots=True)
class ExecutionProfile:
    duration_ms: int
    trace_steps: int
    distinct_lines: int
    hottest_lines: tuple[tuple[int, int], ...]
    coverage_percent: float
    memory_note: str


def _literal(value: str):
    if len(value) > 8_192:
        return None
    try:
        return ast.literal_eval(value)
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        return None


def _matrix_shape(value: object) -> tuple[int, ...]:
    shape: list[int] = []
    current = value
    while isinstance(current, (list, tuple)) and current:
        shape.append(len(current))
        lengths = {
            len(item) for item in current if isinstance(item, (list, tuple))
        }
        if len(lengths) != 1 or not all(isinstance(item, (list, tuple)) for item in current):
            break
        current = current[0]
    return tuple(shape)


def visualize_structures(session: DebugSessionDTO, *, limit: int = 80) -> tuple[StructureSnapshot, ...]:
    """Classify only debugger-safe serialized values; never evaluate learner code."""

    snapshots: list[StructureSnapshot] = []
    for frame in session.frames:
        for name, serialized in frame.locals.items():
            value = _literal(serialized)
            if isinstance(value, dict):
                kind, size, shape = "mapa/grafo", len(value), ()
            elif isinstance(value, set):
                kind, size, shape = "conjunto", len(value), ()
            elif isinstance(value, (list, tuple)):
                shape = _matrix_shape(value)
                kind = "matriz/tensor" if len(shape) > 1 else "lista/pilha/fila"
                size = len(value)
            else:
                continue
            snapshots.append(StructureSnapshot(
                step=frame.step, line=frame.line, name=name, kind=kind,
                size=size, shape=shape, preview=serialized[:160],
            ))
            if len(snapshots) >= limit:
                return tuple(snapshots)
    return tuple(snapshots)


def profile_execution(session: DebugSessionDTO) -> ExecutionProfile:
    hits = Counter(frame.line for frame in session.frames if frame.event == "line")
    return ExecutionProfile(
        duration_ms=session.duration_ms,
        trace_steps=len(session.frames),
        distinct_lines=len(session.executed_lines),
        hottest_lines=tuple(hits.most_common(5)),
        coverage_percent=session.coverage_percent,
        memory_note=(
            "Limite de memória aplicado pelo processo isolado."
            if session.memory_limit_enforced else
            "Memória limitada por isolamento/timeout; limite rígido indisponível nesta plataforma."
        ),
    )


def staged_hints(
    correction: SmartCorrectionResponseDTO, *, concepts: Iterable[str] = (),
) -> tuple[str, ...]:
    """Produce the fixed pedagogical ladder without disclosing hidden assertions."""

    failed_public = [
        item.name for item in correction.test_outcomes
        if not item.passed and item.visibility == "public"
    ]
    failed_hidden = sum(
        not item.passed and item.visibility == "hidden"
        for item in correction.test_outcomes
    )
    location = (
        "Começa pelos testes públicos: " + ", ".join(failed_public[:3])
        if failed_public else
        (f"Há {failed_hidden} caso(s) limite oculto(s) por satisfazer." if failed_hidden
         else "Revê a zona indicada pelo diagnóstico de sintaxe ou estrutura.")
    )
    concept_list = tuple(item for item in concepts if item)[:3]
    concept = (
        "Conceitos a rever: " + ", ".join(concept_list)
        if concept_list else "Confirma inputs, outputs, invariantes e casos-limite."
    )
    return (
        location,
        concept,
        "Estratégia: resolve primeiro um exemplo mínimo, depois vazio/zero, negativos e limites.",
        "Exemplo parcial: escreve uma asserção pequena antes de alterar a implementação.",
    )
