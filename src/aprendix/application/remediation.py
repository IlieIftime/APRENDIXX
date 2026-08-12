"""Deterministic correction diagnosis and prerequisite remediation."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from difflib import SequenceMatcher

from aprendix.application.contracts import SmartCorrectionResponseDTO
from aprendix.domain.enums import StrEnum


class DiagnosticCode(StrEnum):
    SYNTAX = "syntax"
    POLICY = "policy"
    CONTRACT = "contract"
    RUNTIME = "runtime"
    LOGIC = "logic"
    EDGE_CASE = "edge_case"
    EFFICIENCY = "efficiency"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class RemediationPlan:
    code: DiagnosticCode
    title: str
    diagnosis: str
    prerequisite_terms: tuple[str, ...]
    actions: tuple[str, ...]
    mini_exercise: str
    improvement: str


_PLANS = {
    DiagnosticCode.SYNTAX: (
        "A estrutura do código ainda não pode ser interpretada",
        "Existe uma construção incompleta ou mal indentada antes de a lógica poder ser testada.",
        ("sintaxe", "indentação", "bloco"),
        (
            "Abre Problemas e corrige primeiro a linha indicada.",
            "Confirma dois pontos no fim de def/if/for/while e quatro espaços no bloco.",
            "Executa novamente antes de alterar a lógica.",
        ),
        "Mini-prática: escreve uma função com um parâmetro e um único return; confirma que executa.",
    ),
    DiagnosticCode.POLICY: (
        "A solução tentou usar uma operação indisponível no sandbox",
        "O exercício deve ser resolvido apenas com cálculo local, sem rede, processos ou ficheiros externos.",
        ("sandbox", "efeitos laterais", "função pura"),
        (
            "Remove imports ou chamadas assinaladas pela política.",
            "Transforma a solução numa função determinística de entrada para saída.",
        ),
        "Mini-prática: reescreve a transformação como uma função que só recebe argumentos e devolve um valor.",
    ),
    DiagnosticCode.CONTRACT: (
        "A implementação não respeita ainda o contrato estrutural",
        "Falta um nome, assinatura, classe ou construção obrigatória verificada pelo corretor.",
        ("assinatura", "parâmetro", "return"),
        (
            "Compara o cabeçalho da tua função ou classe com o contrato do enunciado.",
            "Mantém exatamente nomes e parâmetros antes de preencher o corpo.",
        ),
        "Mini-prática: cria apenas o cabeçalho pedido e devolve temporariamente um valor do tipo correto.",
    ),
    DiagnosticCode.RUNTIME: (
        "O programa inicia, mas termina com um erro durante a execução",
        "Uma operação recebeu um valor incompatível, acedeu a um elemento inexistente ou violou uma condição em runtime.",
        ("exceção", "tipo", "estado"),
        (
            "Usa Debug e observa a última linha executada e os valores locais.",
            "Reproduz o erro com o menor input público possível.",
            "Valida o valor imediatamente antes da operação que falha.",
        ),
        "Mini-prática: isola a expressão que falha, atribui os operandos a variáveis e imprime os respetivos tipos.",
    ),
    DiagnosticCode.LOGIC: (
        "O código executa, mas o resultado não cumpre um caso público",
        "A sequência de decisões ou cálculos ainda não implementa totalmente a transformação pedida.",
        ("invariante", "condição", "caso de teste"),
        (
            "Resolve manualmente o primeiro caso público que falha.",
            "Compara cada valor intermédio esperado com o produzido pelo código.",
            "Corrige uma condição ou transformação de cada vez.",
        ),
        "Mini-prática: cria uma asserção para o caso público mais simples e faz apenas essa asserção passar.",
    ),
    DiagnosticCode.EDGE_CASE: (
        "Os casos visíveis passam, mas falta tratar uma fronteira",
        "A solução geral está próxima; entradas vazias, sinais, duplicados, limites ou tipos inválidos ainda podem divergir do contrato.",
        ("caso-limite", "validação", "fronteira"),
        (
            "Enumera vazio/zero, mínimo, máximo, inválido e repetido quando forem relevantes.",
            "Define o comportamento esperado antes de acrescentar condições.",
            "Evita adivinhar o teste oculto; implementa a regra geral do contrato.",
        ),
        "Mini-prática: escreve três casos próprios — normal, fronteira e inválido — e explica o resultado esperado.",
    ),
    DiagnosticCode.EFFICIENCY: (
        "A resposta está funcional, mas a estrutura pode ser melhorada",
        "A solução repete trabalho ou usa uma estrutura inadequada para a dimensão prevista.",
        ("complexidade", "estrutura de dados", "invariante"),
        (
            "Identifica ciclos aninhados e cálculos repetidos.",
            "Considera set/dict para pertença ou acumulação quando o contrato o permitir.",
        ),
        "Mini-prática: estima quantas operações são feitas para 10 e para 1 000 elementos.",
    ),
    DiagnosticCode.UNKNOWN: (
        "A tentativa precisa de ser reduzida a um caso observável",
        "O corretor não encontrou ainda um padrão suficientemente específico para uma recomendação segura.",
        ("entrada", "saída", "invariante"),
        (
            "Escolhe o menor exemplo público.",
            "Escreve entrada, resultado esperado e resultado atual.",
        ),
        "Mini-prática: transforma o exemplo mínimo numa asserção local.",
    ),
}


def _diagnostic_code(
    correction: SmartCorrectionResponseDTO, current_source: str,
) -> DiagnosticCode:
    try:
        ast.parse(current_source)
    except (SyntaxError, ValueError):
        return DiagnosticCode.SYNTAX
    if not correction.syntax_valid or correction.status == "syntax_error":
        return DiagnosticCode.SYNTAX
    if not correction.policy_safe or correction.status == "rejected":
        return DiagnosticCode.POLICY
    if correction.missing_constructs:
        return DiagnosticCode.CONTRACT
    if correction.status == "error":
        return DiagnosticCode.RUNTIME
    failed_public = any(
        not item.passed and item.visibility == "public"
        for item in correction.test_outcomes
    )
    failed_hidden = any(
        not item.passed and item.visibility == "hidden"
        for item in correction.test_outcomes
    )
    if failed_public:
        return DiagnosticCode.LOGIC
    if failed_hidden:
        return DiagnosticCode.EDGE_CASE
    if any(
        item.score < 0.6 and "complex" in item.criterion.casefold()
        for item in correction.rubric
    ):
        return DiagnosticCode.EFFICIENCY
    return DiagnosticCode.UNKNOWN


def _improvement(
    current_source: str, previous_source: str, previous_score: float | None,
    current_score: float,
) -> str:
    if not previous_source:
        return "Primeira tentativa registada; esta passa a ser o ponto de comparação."
    similarity = SequenceMatcher(None, previous_source, current_source).ratio()
    changed = max(1, round((1.0 - similarity) * max(len(previous_source), len(current_source))))
    if previous_score is None:
        score_note = "Ainda não havia score comparável."
    else:
        delta = current_score - previous_score
        score_note = (
            f"O score melhorou {delta:.0%}." if delta > 0 else
            f"O score desceu {abs(delta):.0%}." if delta < 0 else
            "O score manteve-se."
        )
    syntax_note = ""
    try:
        ast.parse(current_source)
        try:
            ast.parse(previous_source)
        except SyntaxError:
            syntax_note = " A sintaxe passou a ser válida."
    except SyntaxError:
        pass
    return f"Alteraste aproximadamente {changed} carácter(es). {score_note}{syntax_note}"


def diagnose_correction(
    correction: SmartCorrectionResponseDTO,
    *, current_source: str,
    previous_source: str = "",
    previous_score: float | None = None,
) -> RemediationPlan:
    code = _diagnostic_code(correction, current_source)
    title, diagnosis, terms, actions, mini_exercise = _PLANS[code]
    return RemediationPlan(
        code=code,
        title=title,
        diagnosis=diagnosis,
        prerequisite_terms=terms,
        actions=actions,
        mini_exercise=mini_exercise,
        improvement=_improvement(
            current_source, previous_source, previous_score, correction.score,
        ),
    )
