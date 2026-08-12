"""Guided project lifecycle, reproducible review and privacy-safe export."""

from __future__ import annotations

import ast
import json
import re
import zipfile
from pathlib import Path
from uuid import UUID

from aprendix.application.contracts import ProjectEvaluationDTO
from aprendix.application.editor_support import diagnose_python


def _project_domain_contracts(
    track_slug: str, tree: ast.AST | None, source: str, *, run_ok: bool,
) -> tuple[tuple[str, bool], ...]:
    """Return deterministic, track-aware contracts independent of IDE exercises."""

    nodes = tuple(ast.walk(tree)) if tree is not None else ()
    functions = tuple(node for node in nodes if isinstance(node, ast.FunctionDef))
    assertions = tuple(node for node in nodes if isinstance(node, ast.Assert))
    contracts: list[tuple[str, bool]] = [
        ("execucao_isolada", tree is not None and run_ok),
        ("funcoes_de_dominio", len(functions) >= 2),
        ("testes_deterministicos", bool(assertions) or bool(
            re.search(r"\b(unittest|pytest)\b", source)
        )),
        ("documentacao_do_modulo", bool(ast.get_docstring(tree)) if tree else False),
    ]
    control_flow = any(isinstance(node, (ast.For, ast.While, ast.If)) for node in nodes)
    collections = any(isinstance(
        node, (ast.List, ast.Tuple, ast.Set, ast.Dict, ast.ListComp,
               ast.SetComp, ast.DictComp, ast.GeneratorExp),
    ) for node in nodes)
    if track_slug == "logic-pseudocode":
        contracts.append(("decisao_explicita", control_flow))
    elif track_slug == "python-oop":
        contracts.append(("modelo_com_classes", any(
            isinstance(node, ast.ClassDef) for node in nodes
        )))
    elif track_slug == "python-algorithms":
        contracts.append(("fluxo_algoritmico", control_flow))
    elif track_slug == "python-data-structures":
        contracts.append(("estrutura_de_dados_explicita", collections))
    elif track_slug == "math-programming":
        contracts.append(("transformacao_matematica", any(
            isinstance(node, (ast.BinOp, ast.UnaryOp, ast.Compare)) for node in nodes
        )))
    elif track_slug == "testing-debugging":
        contracts.append(("suite_com_multiplos_casos", len(assertions) >= 2))
    elif track_slug == "python-advanced":
        contracts.append(("construcao_python_avancada", any(
            isinstance(node, (ast.Try, ast.With, ast.Lambda, ast.Yield,
                              ast.YieldFrom, ast.GeneratorExp))
            or isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and bool(node.decorator_list)
            for node in nodes
        )))
    elif track_slug == "sql-databases":
        contracts.append(("contrato_de_persistencia", bool(re.search(
            r"\b(SELECT|INSERT|UPDATE|DELETE|CREATE\s+TABLE|sqlite3)\b",
            source, re.IGNORECASE,
        ))))
    elif track_slug == "web-apis":
        contracts.append(("validacao_de_fronteira", any(
            isinstance(node, (ast.If, ast.Try)) for node in nodes
        )))
    elif track_slug == "data-ai":
        contracts.append(("transformacao_de_dados", collections and control_flow))
    return tuple(contracts)


class ProjectPortfolioService:
    def __init__(self, *, user, repository, desktop) -> None:
        self.user, self._repository, self._desktop = user, repository, desktop

    def templates(self): return self._repository.templates()
    def entries(self): return self._repository.entries(self.user.id)
    def context(self, project_id: UUID):
        """Return the project brief independently from any exercise context."""

        return self._repository.project_context(self.user.id, project_id)

    def set_milestone(self, project_id: UUID, ordinal: int, *, completed: bool = True) -> None:
        self._repository.set_milestone(
            self.user.id, project_id, ordinal, completed,
        )

    def start(self, template_id: str, *, mode: str = "guided"):
        template = next((item for item in self.templates() if item.id == template_id), None)
        if template is None:
            raise KeyError("Projeto guiado desconhecido.")
        starter = (
            '"""' + template.title + '.\n\nDefine aqui as decisões e limites do projeto.\n"""\n\n'
            "def main():\n    print('Define aqui o primeiro caso de uso do projeto.')\n\n"
            "if __name__ == '__main__':\n    main()\n"
        )
        project = self._desktop.save_project(template.title, starter)
        self._repository.start(self.user.id, project.id, template.id, mode)
        return project

    def evaluate(self, project_id: UUID) -> ProjectEvaluationDTO:
        project = next((item for item in self._desktop.projects() if item.id == project_id), None)
        if project is None:
            raise KeyError("Projeto local desconhecido.")
        context = self._repository.project_context(self.user.id, project_id)
        template = context["template"]
        work_mode = str(context["work_mode"])
        findings: list[str] = []
        try:
            tree = ast.parse(project.source_code)
            syntax = 1.0
        except SyntaxError as exc:
            tree, syntax = None, 0.0
            findings.append(f"Sintaxe inválida na linha {exc.lineno or 1}: {exc.msg}")
        run = self._desktop.run(project.source_code) if tree is not None else None
        correction = 1.0 if run and run.status == "ok" else 0.0
        if run and run.status != "ok": findings.append(run.error_message or run.status)
        diagnostics = diagnose_python(project.source_code)
        quality = max(0.0, 1.0 - 0.12 * len(diagnostics))
        functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)] if tree else []
        tests = 1.0 if re.search(r"\b(assert|unittest|pytest)\b", project.source_code) else 0.0
        documentation = 1.0 if (ast.get_docstring(tree) if tree else None) else 0.0
        structure = min(1.0, len(functions) / 2) if tree else 0.0
        rubric = {
            "correção": correction * syntax, "estrutura": structure,
            "testes": tests, "qualidade": quality, "documentação": documentation,
        }
        weights = {"correção": .35, "estrutura": .2, "testes": .2, "qualidade": .15, "documentação": .1}
        score = round(sum(rubric[name] * weights[name] for name in weights), 4)
        domain_contracts = _project_domain_contracts(
            template.track_slug, tree, project.source_code,
            run_ok=bool(run and run.status == "ok"),
        )
        missing_contracts = tuple(
            name for name, satisfied in domain_contracts if not satisfied
        )
        findings.extend(
            f"Contrato de domínio em falta: {name.replace('_', ' ')}."
            for name in missing_contracts
        )
        rubric["contratos de domínio"] = (
            1.0 if not missing_contracts else
            (len(domain_contracts) - len(missing_contracts)) / len(domain_contracts)
        )
        skills = tuple(sorted({type(node).__name__ for node in ast.walk(tree)} & {
            "FunctionDef", "ClassDef", "For", "While", "If", "Try", "With",
            "ListComp", "DictComp", "GeneratorExp",
        })) if tree else ()
        evaluation = ProjectEvaluationDTO(
            project_id=project_id, score=score,
            passed=score >= .7 and not missing_contracts,
            rubric_scores=rubric, findings=tuple(findings), demonstrated_skills=skills,
            template_id=template.id, track_slug=template.track_slug,
            work_mode=work_mode,
            domain_contracts=tuple(name for name, _satisfied in domain_contracts),
        )
        access, credit_awarded = self._repository.record_evaluation(
            self.user.id, evaluation,
        )
        return evaluation.model_copy(update={
            "access": access,
            "credit_awarded": credit_awarded,
        })

    def export_zip(self, project_id: UUID, destination: Path) -> Path:
        project = next((item for item in self._desktop.projects() if item.id == project_id), None)
        entry = next((item for item in self.entries() if item.project_id == project_id), None)
        if project is None or entry is None:
            raise KeyError("Projeto de portefólio desconhecido.")
        destination = destination.expanduser().resolve()
        if destination.suffix.casefold() != ".zip":
            raise ValueError("A exportação tem de terminar em .zip")
        destination.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "title": entry.title, "mode": entry.work_mode, "status": entry.status,
            "score": entry.score, "demonstrated_skills": entry.demonstrated_skills,
            "privacy": "Sem chaves, perfil, histórico ou base de dados Aprendix.",
        }
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for project_file in self._desktop.project_files(project_id):
                archive.writestr(project_file.relative_path, project_file.source_code)
            archive.writestr("APRENDIX-PORTFOLIO.json", json.dumps(report, ensure_ascii=False, indent=2))
        return destination
