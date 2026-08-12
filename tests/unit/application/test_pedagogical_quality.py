from uuid import uuid4

from aprendix.application.contracts import ExerciseDTO, ProjectTemplateDTO, TheoryCardDTO
from aprendix.application.pedagogical_quality import PedagogicalQualityCompiler


class Repository:
    def __init__(self):
        self.audit = None
        self.items = ()

    def summary(self, *, fingerprint=None):
        if self.audit is not None and (fingerprint is None or self.audit.fingerprint == fingerprint):
            return self.audit
        return None

    def exercise_source_counts(self, ids):
        return {identity: 1 for identity in ids}

    def replace(self, audit, items):
        self.audit, self.items = audit, items

    def results(self, *, status=None, limit=100):
        return tuple(item for item in self.items if status is None or item.status == status)[:limit]


def _catalog(prompt="Implementa uma função dobro que devolve duas vezes o argumento."):
    node = uuid4()
    exercise = ExerciseDTO(
        graph_node_id=node, slug="dobro-seguro", title="Dobro seguro", prompt=prompt,
        starter_code="def dobro(x):\n    return x * 2\n", tests=("assert dobro(3) == 6",),
    )
    project = ProjectTemplateDTO(
        id="project-quality", track_slug="python-foundations", title="Projeto",
        brief="Constrói um programa local verificável com entradas, resultados, limites e testes determinísticos.",
        requirements=("Entrada", "Saída", "Testes"), milestones=("Contrato", "Código", "Revisão"),
        rubric=("Correção", "Estrutura", "Testes"), level="beginner",
    )
    card = TheoryCardDTO(
        title="Sabias que: funções", body="Uma função pequena torna o contrato mais fácil de testar e reutilizar.",
        code_example="def dobro(x):\n    return 2 * x\n", source_title="Python Documentation",
        graph_node_id=node,
    )
    unit = {"id": "unit-quality", "body": "Primeiro observa o contrato e depois implementa uma solução pequena verificável.",
            "example": "dobro(3) == 6"}
    return exercise, project, card, unit


def test_quality_compiler_accepts_clean_catalog_and_is_idempotent() -> None:
    repository = Repository()
    compiler = PedagogicalQualityCompiler(repository)
    exercise, project, card, unit = _catalog()
    report = compiler.audit(
        exercises=(exercise,), projects=(project,), cards=(card,), units=(unit,),
    )
    assert report.total == report.accepted == 4
    assert report.quarantined == 0
    assert compiler.audit(
        exercises=(exercise,), projects=(project,), cards=(card,), units=(unit,),
    ) == report


def test_quality_compiler_quarantines_contaminated_prompt() -> None:
    repository = Repository()
    compiler = PedagogicalQualityCompiler(repository)
    exercise, project, card, unit = _catalog("# -*- coding: utf-8 -*-\nFaz x.")
    report = compiler.audit(
        exercises=(exercise,), projects=(project,), cards=(card,), units=(unit,),
    )
    assert report.quarantined == 1
    bad = compiler.quarantined()
    assert bad[0].item_type == "exercise"
    assert {item.code for item in bad[0].checks if not item.passed} >= {"prompt.clean"}
