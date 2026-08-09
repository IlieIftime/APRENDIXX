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


class ProjectPortfolioService:
    def __init__(self, *, user, repository, desktop) -> None:
        self.user, self._repository, self._desktop = user, repository, desktop

    def templates(self): return self._repository.templates()
    def entries(self): return self._repository.entries(self.user.id)

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
        skills = tuple(sorted({type(node).__name__ for node in ast.walk(tree)} & {
            "FunctionDef", "ClassDef", "For", "While", "If", "Try", "With",
            "ListComp", "DictComp", "GeneratorExp",
        })) if tree else ()
        evaluation = ProjectEvaluationDTO(
            project_id=project_id, score=score, passed=score >= .7,
            rubric_scores=rubric, findings=tuple(findings), demonstrated_skills=skills,
        )
        self._repository.record_evaluation(self.user.id, evaluation)
        return evaluation

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
