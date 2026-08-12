"""Readable, solution-neutral presentation for executable exercises."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

from aprendix.application.editor_support import sanitize_exercise_prompt
from aprendix.application.learning_session import BriefMode


@dataclass(frozen=True, slots=True)
class ExerciseBrief:
    """A complete learner-facing statement derived from an exercise contract."""

    title: str
    context: str
    task: str
    required_names: tuple[str, ...]
    parameters: tuple[str, ...]
    constraints: tuple[str, ...]
    public_examples: tuple[str, ...] = ()
    result_contract: str = ""

    def render(self, mode: BriefMode | str = BriefMode.GUIDED) -> str:
        """Render plain UTF-8 text without icon-font or Markdown dependencies."""

        try:
            selected_mode = BriefMode(mode)
        except ValueError:
            selected_mode = BriefMode.GUIDED

        if selected_mode is BriefMode.SIMPLE:
            signature = self.required_names[0] if self.required_names else "Mantém o contrato indicado."
            steps = [
                "Lê os dados de entrada e valida-os.",
                "Implementa a transformação pedida sem alterar os argumentos.",
                "Devolve o resultado com o tipo definido no contrato.",
                "Executa exemplos simples e depois usa Corrigir.",
            ]
            sections = [
                self.title,
                f"Em poucas palavras\n{self.task}",
                f"O que tens de criar\n{signature}\n{self.result_contract}",
                "Passos sugeridos\n" + "\n".join(
                    f"{index}. {item}" for index, item in enumerate(steps, 1)
                ),
            ]
            if self.public_examples:
                sections.append("Exemplos\n" + "\n".join(self.public_examples[:3]))
            sections.append(
                "Atenção\nTrata entradas vazias, inválidas e valores de fronteira relevantes. "
                "A execução é local e não tem acesso à rede nem a ficheiros."
            )
            return "\n\n".join(item.strip() for item in sections if item.strip())

        if selected_mode is BriefMode.GUIDED:
            sections = [
                self.title,
                f"Contextualização\n{self.context}",
                f"Objetivo\n{self.task}",
            ]
            if self.required_names or self.result_contract:
                details = (*self.required_names, *((self.result_contract,) if self.result_contract else ()))
                sections.append("Contrato a respeitar\n" + "\n".join(details))
            if self.parameters:
                sections.append("Entradas e parâmetros\n" + "\n\n".join(self.parameters))
            if self.public_examples:
                sections.append("Exemplos de comportamento\n" + "\n\n".join(self.public_examples))
            priority_constraints = self.constraints[:6]
            sections.append(
                "Plano de resolução\n"
                "1. Valida as entradas sem as modificar.\n"
                "2. Resolve primeiro o caso normal mais simples.\n"
                "3. Acrescenta os casos inválidos e de fronteira.\n"
                "4. Executa, interpreta os erros e só depois usa Corrigir."
            )
            sections.append("Requisitos importantes\n" + "\n".join(f"- {item}" for item in priority_constraints))
            sections.append(
                "Como sabes que terminaste\n"
                "A solução executa sem erros, respeita o contrato e passa os casos normais e de fronteira."
            )
            return "\n\n".join(sections).strip()

        sections = [
            self.title,
            f"Contextualização\n{self.context}",
            f"Objetivo\n{self.task}",
        ]
        if self.required_names or self.result_contract:
            details = (*self.required_names, *((self.result_contract,) if self.result_contract else ()))
            sections.append("Especificação técnica\n" + "\n".join(details))
        if self.parameters:
            sections.append("Entradas e parâmetros\n" + "\n\n".join(self.parameters))
        if self.public_examples:
            sections.append("Exemplos de comportamento\n" + "\n\n".join(self.public_examples))
        sections.extend((
            "Requisitos e casos-limite\n" + "\n".join(f"- {item}" for item in self.constraints),
            (
                "Critérios de avaliação\n"
                "A solução é aceite quando:\n"
                "- Executa sem erros.\n"
                "- Respeita o contrato, incluindo os nomes, os parâmetros e os tipos.\n"
                "- Produz os resultados esperados para entradas válidas.\n"
                "- Trata corretamente os casos normais, inválidos e de fronteira do corretor local."
            ),
        ))
        return "\n\n".join(sections).strip()


_PARAMETER_DESCRIPTIONS = {
    "texto": "valor de entrada do tipo string; considera o conteúdo após remover espaços exteriores",
    "predefinido": "valor opcional devolvido quando a entrada não respeita o formato esperado",
    "valor": "valor de entrada que a função deve validar ou transformar",
    "valores": "sequência de valores que a função deve processar sem alterar a coleção recebida",
    "numero": "valor numérico sobre o qual deve ser realizada a operação",
    "numeros": "sequência de valores numéricos a processar",
    "preco": "valor numérico que representa o preço unitário",
    "quantidade": "número de unidades a considerar no cálculo",
    "alvo": "valor que a operação deve procurar, comparar ou atingir",
    "limite": "valor de fronteira que limita a operação",
    "nome": "texto que identifica o elemento tratado",
    "dados": "estrutura de dados de entrada a validar e processar",
    "itens": "coleção de elementos a percorrer ou transformar",
}


def _parameter_description(name: str, annotation: str, default: str | None) -> str:
    description = _PARAMETER_DESCRIPTIONS.get(
        name.casefold(),
        "valor de entrada necessário para cumprir o contrato da função",
    )
    type_text = f", com tipo esperado {annotation}" if annotation else ""
    default_text = f"; usa {default} por omissão" if default is not None else ""
    return f"{name}: {description}{type_text}{default_text}."


def _function_parameters(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, ...]:
    positional = (*node.args.posonlyargs, *node.args.args)
    positional_defaults: list[ast.expr | None] = [None] * (
        len(positional) - len(node.args.defaults)
    ) + list(node.args.defaults)
    descriptions: list[str] = []
    for argument, default_node in zip(positional, positional_defaults, strict=True):
        if argument.arg in {"self", "cls"}:
            continue
        annotation = ast.unparse(argument.annotation) if argument.annotation is not None else ""
        default = ast.unparse(default_node) if default_node is not None else None
        descriptions.append(_parameter_description(argument.arg, annotation, default))
    for argument, default_node in zip(
        node.args.kwonlyargs, node.args.kw_defaults, strict=True
    ):
        annotation = ast.unparse(argument.annotation) if argument.annotation is not None else ""
        default = ast.unparse(default_node) if default_node is not None else None
        descriptions.append(_parameter_description(argument.arg, annotation, default))
    if node.args.vararg:
        descriptions.append(
            _parameter_description(node.args.vararg.arg, "sequência de argumentos", None)
        )
    if node.args.kwarg:
        descriptions.append(
            _parameter_description(node.args.kwarg.arg, "dicionário de argumentos", None)
        )
    return tuple(descriptions)


def _signature_details(source: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    try:
        tree = ast.parse(source or "\n")
    except (SyntaxError, ValueError):
        return (), ()
    names: list[str] = []
    parameters: list[str] = []

    def add_function(node: ast.FunctionDef | ast.AsyncFunctionDef, owner: str = "") -> None:
        prefix = f"{owner}." if owner else ""
        try:
            signature = ast.unparse(node.args)
        except (AttributeError, ValueError):
            signature = ", ".join(item.arg for item in node.args.args)
        names.append(f"Função {prefix}{node.name}({signature})")
        parameters.extend(_function_parameters(node))

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            add_function(node)
        elif isinstance(node, ast.ClassDef):
            names.append(f"Classe {node.name}")
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    add_function(child, node.name)
    return tuple(dict.fromkeys(names)), tuple(dict.fromkeys(parameters))


def _safe_public_examples(tests: tuple[str, ...], *, limit: int = 4) -> tuple[str, ...]:
    """Extract literal input/output examples without executing test code."""

    examples: list[str] = []
    for source in tests:
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assert) or not isinstance(node.test, ast.Compare):
                continue
            comparison = node.test
            if (
                len(comparison.ops) != 1 or not isinstance(comparison.ops[0], ast.Eq)
                or len(comparison.comparators) != 1
                or not isinstance(comparison.left, ast.Call)
            ):
                continue
            try:
                for argument in (*comparison.left.args, *comparison.left.keywords):
                    value = argument.value if isinstance(argument, ast.keyword) else argument
                    ast.literal_eval(value)
                ast.literal_eval(comparison.comparators[0])
                invocation = ast.unparse(comparison.left)
                expected = ast.unparse(comparison.comparators[0])
            except (ValueError, TypeError, AttributeError):
                continue
            example = f"{invocation} -> {expected}"
            if len(example) <= 240 and example not in examples:
                examples.append(example)
            if len(examples) >= limit:
                return tuple(examples)
    return tuple(examples)


def _result_contract(examples: tuple[str, ...]) -> str:
    types: list[str] = []
    labels = {
        type(None): "None",
        bool: "booleano",
        int: "inteiro",
        float: "número real",
        str: "string",
        list: "lista",
        tuple: "tuplo",
        dict: "dicionário",
        set: "conjunto",
    }
    for example in examples:
        try:
            value = ast.literal_eval(example.rsplit(" -> ", 1)[1])
        except (ValueError, SyntaxError, IndexError):
            continue
        label = labels.get(type(value), type(value).__name__)
        if label not in types:
            types.append(label)
    if not types:
        return "Deve devolver o resultado definido pelo contrato do exercício."
    expected = " ou ".join(types)
    return f"Deve devolver um valor do tipo {expected}, conforme o contrato."


def _domain_constraints(starter_code: str) -> tuple[str, ...]:
    """Add precise edge cases only when they follow from a known public contract."""

    if re.search(r"\bdef\s+inteiro_ou\s*\(", starter_code):
        return (
            "Aceita apenas strings que, depois de strip(), representem um inteiro decimal com sinal + ou - opcional.",
            "Rejeita caracteres adicionais, números decimais e sinais isolados como '+' ou '-'.",
            "Trata explicitamente a string vazia, espaços apenas e zeros à esquerda.",
            "Quando o texto é inválido, devolve predefinido sem lançar uma exceção de conversão.",
        )
    return ()


def build_exercise_brief(exercise) -> ExerciseBrief:
    """Turn stored content into a consistent brief without inventing an answer."""

    cleaned = sanitize_exercise_prompt(exercise.prompt)
    paragraphs = tuple(
        re.sub(r"\s+", " ", part).strip()
        for part in re.split(r"\n\s*\n", cleaned)
        if part.strip()
    )
    task = paragraphs[0] if paragraphs else f"Resolve o desafio {exercise.title}."
    scenario = next(
        (part for part in paragraphs[1:] if part.casefold().startswith(("cenário", "contexto"))),
        "Neste problema vais construir uma solução local, determinística e verificável. "
        "A implementação deve transformar entradas bem definidas em resultados observáveis.",
    )
    scenario = re.sub(
        r"^(?:cenário(?: de transferência)?|contexto)\s*:\s*", "", scenario,
        flags=re.IGNORECASE,
    )
    names, parameters = _signature_details(exercise.starter_code)
    if not names:
        names = ("Mantém os nomes de variáveis e estruturas indicados no enunciado.",)
    if not parameters:
        parameters = (
            "Entradas: identifica os dados indicados no enunciado e conserva os respetivos tipos e significado.",
        )
    constraints = (
        "Implementa a solução do zero no editor fornecido.",
        "Mantém os nomes, os parâmetros e o tipo de resultado definidos pelo contrato.",
        "Valida explicitamente o formato e o domínio das entradas antes de as transformar.",
        *_domain_constraints(exercise.starter_code),
        "Considera entradas vazias, valores de fronteira e dados inválidos relevantes para o problema.",
        "Não alteres os argumentos recebidos e evita efeitos laterais desnecessários.",
        "A solução corre num sandbox local sem rede, processos ou ficheiros externos.",
    )
    examples = _safe_public_examples(tuple(exercise.tests))
    return ExerciseBrief(
        title=str(exercise.title),
        context=scenario,
        task=task,
        required_names=names,
        parameters=parameters,
        constraints=constraints,
        public_examples=examples,
        result_contract=_result_contract(examples),
    )
