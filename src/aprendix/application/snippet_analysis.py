"""Deterministic local analysis for code and pseudocode; never executes input."""

from __future__ import annotations

import ast
import re

from aprendix.application.editor_support import analyze_complexity, diagnose_python, sanitize_exercise_prompt


class SnippetAnalyzer:
    def __init__(self, result_type=None) -> None:
        if result_type is None:
            from aprendix.application.contracts.snippet import SnippetAnalysisDTO
            result_type = SnippetAnalysisDTO
        self._result_type = result_type

    def analyze(self, request):
        original = request.text
        normalized = sanitize_exercise_prompt(original)
        language = self._detect(normalized, request.language_hint)
        if language == "python":
            return self._python(request, original, normalized)
        return self._pseudocode(request, original, normalized, language)

    @staticmethod
    def _detect(text: str, hint: str) -> str:
        if hint != "auto": return hint
        try:
            tree = ast.parse(text)
            if any(not isinstance(node, (ast.Module, ast.Expr, ast.Constant)) for node in ast.walk(tree)):
                return "python"
        except SyntaxError:
            pass
        if re.search(r"\b(SE|ENTAO|SENAO|ENQUANTO|PARA|INICIO|FIM|LER|ESCREVER|ALGORITMO)\b", text, re.I):
            return "pseudocode"
        return "text"

    def _python(self, request, original, normalized):
        problems = [f"Linha {item.line}: {item.message}" for item in diagnose_python(normalized)]
        try:
            tree = ast.parse(normalized)
        except SyntaxError as exc:
            return self._result_type(
                original=original, normalized=normalized, detected_language="python",
                summary="O trecho parece Python, mas a árvore sintática não pôde ser construída.",
                complexity_time="indeterminada", complexity_space="indeterminada",
                problems=tuple(problems or (f"Linha {exc.lineno or 1}: {exc.msg}",)),
                suggested_tests=("Corrigir primeiro a sintaxe e validar uma entrada mínima.",),
                confidence=.45,
            )
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        assigned = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)}
        inputs = tuple(sorted(names - assigned - set(dir(__builtins__))))[:100]
        outputs = tuple(sorted({
            node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name) and node.func.id in {"print", "return"}
        }))
        constructs = tuple(sorted({type(node).__name__ for node in ast.walk(tree)}))[:100]
        flow = self._flow(tree)
        complexity = analyze_complexity(normalized)
        lines = tuple(
            f"Linha {number}: {self._line_meaning(line)}"
            for number, line in enumerate(normalized.splitlines(), 1) if line.strip()
        )
        functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
        tests = ["Caso normal com valores pequenos", "Entrada vazia ou zero", "Valor limite ou inválido"]
        for name in functions[:3]: tests.append(f"Verificar o contrato de `{name}` com uma asserção independente")
        return self._result_type(
            original=original, normalized=normalized, detected_language="python",
            summary=(f"Trecho Python com {len(constructs)} tipos de construção e "
                     f"{len(functions)} função(ões); a análise é estática e não executou o código."),
            line_explanations=lines, inputs=inputs, outputs=outputs,
            invariants=self._invariants(tree), constructs=constructs, control_flow=flow,
            complexity_time=str(complexity["time"]), complexity_space=str(complexity["space"]),
            problems=tuple(problems), suggested_tests=tuple(tests),
            proposed_code=normalized if request.action.value in {"complete", "to_python"} else "",
            related_concepts=self._concepts(constructs), confidence=.92 if not problems else .76,
        )

    def _pseudocode(self, request, original, normalized, language):
        lines = [line.strip() for line in normalized.splitlines() if line.strip()]
        constructs = []
        for line in lines:
            upper = line.upper()
            if re.match(r"^(SE|IF)\b", upper): constructs.append("condition")
            if re.match(r"^(PARA|FOR)\b", upper): constructs.append("for-loop")
            if re.match(r"^(ENQUANTO|WHILE)\b", upper): constructs.append("while-loop")
            if re.match(r"^(LER|INPUT)\b", upper): constructs.append("input")
            if re.match(r"^(ESCREVER|PRINT|RETURN)\b", upper): constructs.append("output")
        nested = sum(item in {"for-loop", "while-loop"} for item in constructs)
        proposed = self._to_python(lines) if request.action.value == "to_python" else ""
        return self._result_type(
            original=original, normalized=normalized, detected_language=language,
            summary=("Algoritmo descrito por passos sequenciais com "
                     f"{constructs.count('condition')} decisão(ões) e {nested} ciclo(s)."),
            line_explanations=tuple(f"Passo {i}: {line}" for i, line in enumerate(lines, 1)),
            inputs=tuple(line for line in lines if re.match(r"^(LER|INPUT)\b", line, re.I)),
            outputs=tuple(line for line in lines if re.match(r"^(ESCREVER|PRINT|RETURN)\b", line, re.I)),
            invariants=("O estado deve permanecer válido antes e depois de cada repetição.",) if nested else (),
            constructs=tuple(dict.fromkeys(constructs)),
            control_flow=tuple((f"passo-{i}", f"passo-{i+1}") for i in range(1, len(lines))),
            complexity_time="O(n) provável" if nested == 1 else f"O(n^{nested}) provável" if nested > 1 else "O(1) provável",
            complexity_space="O(1) provável", problems=(() if constructs else ("Não foram reconhecidas estruturas algorítmicas explícitas.",)),
            suggested_tests=("Entrada vazia", "Um único elemento", "Vários elementos", "Entrada inválida"),
            proposed_code=proposed, related_concepts=tuple(dict.fromkeys(constructs)),
            confidence=.8 if constructs else .42,
        )

    @staticmethod
    def _flow(tree):
        edges = []
        for parent in ast.walk(tree):
            children = list(ast.iter_child_nodes(parent))
            for left, right in zip(children, children[1:]):
                edges.append((f"L{getattr(left, 'lineno', 0)}:{type(left).__name__}",
                              f"L{getattr(right, 'lineno', 0)}:{type(right).__name__}"))
        return tuple(edges[:5_000])

    @staticmethod
    def _invariants(tree):
        result = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.For, ast.While)):
                result.append(f"Linha {node.lineno}: a condição/progresso do ciclo deve aproximar a terminação.")
        return tuple(result[:100])

    @staticmethod
    def _concepts(constructs):
        mapping = {"For": "iteração", "While": "ciclo e terminação", "If": "lógica booleana",
                   "FunctionDef": "função e contrato", "ClassDef": "classe e encapsulamento",
                   "Try": "exceções", "ListComp": "compreensão de listas"}
        return tuple(mapping[item] for item in constructs if item in mapping)

    @staticmethod
    def _line_meaning(line):
        stripped = line.strip()
        if stripped.startswith("def "): return "define uma função e o respetivo contrato de chamada."
        if stripped.startswith("class "): return "define um tipo e agrupa estado/comportamento."
        if stripped.startswith("if "): return "escolhe um ramo a partir de uma condição."
        if stripped.startswith(("for ", "while ")): return "repete um bloco mantendo uma condição de progresso."
        if stripped.startswith("return"): return "termina a função e entrega um resultado."
        return "calcula, atribui ou invoca uma operação neste passo."

    @staticmethod
    def _to_python(lines):
        result, indent = [], 0
        for line in lines:
            clean = line.strip(); upper = clean.upper()
            if re.match(r"^(FIM|END)\b", upper): indent = max(0, indent - 1); continue
            clean = re.sub(r"^ESCREVER\s+", "print(", clean, flags=re.I)
            if clean.startswith("print(") and not clean.endswith(")"): clean += ")"
            clean = re.sub(r"^LER\s+(\w+)", r"\1 = input()", clean, flags=re.I)
            clean = re.sub(r"^SE\s+(.+?)\s+ENTAO$", r"if \1:", clean, flags=re.I)
            clean = re.sub(r"^SENAO$", "else:", clean, flags=re.I)
            if clean == "else:": indent = max(0, indent - 1)
            result.append("    " * indent + clean)
            if clean.endswith(":"): indent += 1
        return "\n".join(result)
