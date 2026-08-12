"""Deterministic quality compiler for authored learning material."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from collections import Counter

from aprendix.application.contracts import (
    PedagogicalQualityAuditDTO,
    PedagogicalQualityDTO,
    QualityCheckDTO,
)


QUALITY_VERSION = "pedagogical-compiler-v2"
_CONTAMINATION = re.compile(
    r"#\s*[-*]+\s*coding\s*[:=]|\x00|\ufeff|(?:copyright|all rights reserved).{0,80}(?:isbn|publisher)",
    re.IGNORECASE | re.DOTALL,
)
_WORD = re.compile(r"[A-Za-zÀ-ÿ_][\wÀ-ÿ-]*")


def _normalized(value: str) -> str:
    return " ".join(_WORD.findall(value.casefold()))


def _check(code: str, passed: bool, detail: str, *, critical: bool = False) -> QualityCheckDTO:
    return QualityCheckDTO(code=code, passed=passed, critical=critical, detail=detail)


def _syntax_ok(source: str) -> bool:
    try:
        ast.parse(source or "\n")
        return True
    except (SyntaxError, ValueError, TypeError):
        return False


def _test_syntax_ok(raw: str) -> bool:
    value = raw.strip()
    while value.startswith("[") and "]" in value:
        _marker, value = value[1:].split("]", 1)
        value = value.lstrip()
    if value.casefold().startswith("stdout equals"):
        return True
    return _syntax_ok(value)


def _difficulty(source: str, prose: str) -> float:
    try:
        tree = ast.parse(source or "\n")
        structural = sum(
            isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.For, ast.While,
                              ast.If, ast.Try, ast.ListComp, ast.DictComp, ast.Call))
            for node in ast.walk(tree)
        )
    except SyntaxError:
        structural = 0
    score = -2.4 + min(3.6, len(_WORD.findall(prose)) / 90 + structural / 7)
    return round(max(-3.0, min(3.0, score)), 3)


def _result(item_type: str, item_id: str, checks, difficulty: float) -> PedagogicalQualityDTO:
    failures = [item for item in checks if not item.passed]
    penalty = sum(.32 if item.critical else .08 for item in failures)
    score = max(0.0, min(1.0, 1.0 - penalty))
    return PedagogicalQualityDTO(
        item_type=item_type, item_id=str(item_id), quality_score=round(score, 3),
        estimated_difficulty=difficulty,
        status="quarantined" if any(item.critical for item in failures) else "accepted",
        generator_version=QUALITY_VERSION, checks=tuple(checks),
    )


class PedagogicalQualityCompiler:
    """Compile the complete catalogue into auditable quality decisions."""

    def __init__(self, repository) -> None:
        self._repository = repository

    @staticmethod
    def fingerprint(exercises, projects, cards, units) -> str:
        payload = [("compiler", QUALITY_VERSION)]
        for item in exercises:
            payload.append(("exercise", str(item.id), item.version, item.prompt, item.starter_code, item.tests))
        for item in projects:
            payload.append(("project", item.id, item.brief, item.requirements, item.milestones, item.rubric))
        for item in cards:
            payload.append(("card", str(item.id), item.title, item.body, item.code_example, item.source_title))
        for item in units:
            payload.append(("unit", str(item["id"]), item.get("body", ""), item.get("example", "")))
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def audit(self, *, exercises, projects, cards, units) -> PedagogicalQualityAuditDTO:
        exercises, projects, cards, units = tuple(exercises), tuple(projects), tuple(cards), tuple(units)
        fingerprint = self.fingerprint(exercises, projects, cards, units)
        current = self._repository.summary(fingerprint=fingerprint)
        if current is not None:
            return current
        source_counts = self._repository.exercise_source_counts(
            tuple(str(item.id) for item in exercises)
        )
        seen: dict[str, set[str]] = {key: set() for key in ("exercise", "project", "card", "unit")}
        results: list[PedagogicalQualityDTO] = []

        for exercise in exercises:
            normalized = _normalized(exercise.prompt)
            duplicate = normalized in seen["exercise"]
            seen["exercise"].add(normalized)
            tests_ok = bool(exercise.tests) and all(_test_syntax_ok(item) for item in exercise.tests)
            checks = (
                _check("prompt.minimum", len(_WORD.findall(exercise.prompt)) >= 5,
                       "O enunciado contém contexto e objetivo suficientes.", critical=True),
                _check("prompt.clean", not _CONTAMINATION.search(exercise.prompt),
                       "O enunciado não contém cabeçalhos, bytes de controlo ou front matter.", critical=True),
                _check("prompt.unique", not duplicate, "O enunciado não é uma duplicação exata.", critical=True),
                _check("starter.syntax", _syntax_ok(exercise.starter_code),
                       "O código inicial produz uma AST Python válida.", critical=True),
                _check("tests.executable", tests_ok,
                       "Existe pelo menos um teste e todos os testes são interpretáveis.", critical=True),
                _check("bibliography.linked", source_counts.get(str(exercise.id), 0) > 0,
                       "O exercício está ligado a pelo menos uma fonte reconhecida."),
                _check("difficulty.bounded", -3 <= exercise.difficulty <= 3,
                       "A dificuldade declarada respeita a escala IRT."),
            )
            results.append(_result(
                "exercise", str(exercise.id), checks,
                _difficulty(exercise.starter_code, exercise.prompt),
            ))

        for project in projects:
            normalized = _normalized(project.brief)
            duplicate = normalized in seen["project"]
            seen["project"].add(normalized)
            checks = (
                _check("brief.minimum", len(_WORD.findall(project.brief)) >= 10,
                       "O briefing explicita um produto observável.", critical=True),
                _check("brief.clean", not _CONTAMINATION.search(project.brief),
                       "O briefing está livre de artefactos de extração.", critical=True),
                _check("brief.unique", not duplicate, "O briefing não é duplicado.", critical=True),
                _check("project.structure", min(len(project.requirements), len(project.milestones), len(project.rubric)) >= 3,
                       "Requisitos, milestones e rubrica têm pelo menos três elementos.", critical=True),
            )
            results.append(_result("project", project.id, checks, _difficulty("", project.brief)))

        for card in cards:
            normalized = _normalized(f"{card.title} {card.body}")
            duplicate = normalized in seen["card"]
            seen["card"].add(normalized)
            checks = (
                _check("card.minimum", len(_WORD.findall(card.body)) >= 7,
                       "O card contém uma afirmação útil e contextualizada.", critical=True),
                _check("card.clean", not _CONTAMINATION.search(card.body),
                       "O card está livre de contaminação editorial.", critical=True),
                _check("card.unique", not duplicate, "O card não é duplicado.", critical=True),
                _check("card.graph", card.graph_node_id is not None,
                       "O card está ligado ao grafo adaptativo."),
                _check("card.source", bool(card.source_title),
                       "O verso do card apresenta uma referência."),
                _check("card.code", not card.code_example or _syntax_ok(card.code_example),
                       "O exemplo Python, quando existe, produz uma AST válida."),
            )
            results.append(_result("card", str(card.id), checks, _difficulty(card.code_example, card.body)))

        for unit in units:
            body, example = str(unit.get("body", "")), str(unit.get("example", ""))
            normalized = _normalized(f"{body} {example}")
            duplicate = normalized in seen["unit"]
            seen["unit"].add(normalized)
            checks = (
                _check("unit.minimum", len(_WORD.findall(body)) >= 8,
                       "A explicação possui conteúdo pedagógico suficiente.", critical=True),
                _check("unit.clean", not _CONTAMINATION.search(f"{body}\n{example}"),
                       "A unidade não contém artefactos de importação.", critical=True),
                # Practice/assessment shells may intentionally reuse the same
                # concise instruction; report it without hiding the unit.
                _check("unit.unique", not duplicate, "A unidade não é uma duplicação exata."),
                _check("unit.example", bool(example.strip()), "A unidade inclui um exemplo observável."),
            )
            results.append(_result("unit", str(unit["id"]), checks, _difficulty(example, body)))

        counts = Counter(item.item_type for item in results)
        audit = PedagogicalQualityAuditDTO(
            fingerprint=fingerprint, total=len(results),
            accepted=sum(item.status == "accepted" for item in results),
            quarantined=sum(item.status == "quarantined" for item in results),
            average_score=(sum(item.quality_score for item in results) / max(1, len(results))),
            by_type=dict(sorted(counts.items())),
        )
        self._repository.replace(audit, tuple(results))
        return audit

    def summary(self) -> PedagogicalQualityAuditDTO | None:
        return self._repository.summary()

    def quarantined(self, *, limit: int = 100):
        return self._repository.results(status="quarantined", limit=limit)
