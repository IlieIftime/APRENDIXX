from datetime import UTC, datetime
from uuid import uuid4

from aprendix.application.contracts import ExerciseDTO, UserDTO
from aprendix.application.exercise_presentation import build_exercise_brief
from aprendix.application.ide_commands import IDE_COMMANDS, search_ide_commands
from aprendix.presentation.gui import LearningGuiController


def _exercise(starter: str) -> ExerciseDTO:
    now = datetime.now(UTC)
    return ExerciseDTO(
        id=uuid4(), graph_node_id=uuid4(), slug="calcular-total",
        title="Calcular o total",
        prompt=(
            "Calcula o custo final de uma encomenda sem alterar os valores recebidos.\n\n"
            "Cenário de transferência: uma pequena loja local."
        ),
        starter_code=starter,
        tests=(
            "assert calcular_total(2, 3) == 6",
            "assert calcular_total(4) == 4",
        ),
        created_at=now, updated_at=now,
    )


def test_brief_exposes_complete_contract_without_solution() -> None:
    brief = build_exercise_brief(_exercise("def calcular_total(preco, quantidade=1):\n    pass\n"))
    rendered = brief.render()

    assert "Contextualização" in rendered
    assert "Objetivo" in rendered
    assert "calcular_total(preco, quantidade=1)" in rendered
    assert "preco:" in rendered and "quantidade:" in rendered
    assert "Implementa a solução do zero" in rendered
    assert "== 6" not in rendered
    assert "calcular_total(2, 3) -> 6" in rendered
    assert "calcular_total(4) -> 4" in rendered
    assert "Deve devolver um valor do tipo inteiro" in rendered
    assert rendered.startswith("Calcular o total")
    assert not any(symbol in rendered for symbol in ("→", "▶", "✓", "◉", "⎘", "✦"))


def test_brief_lists_class_and_public_method_contracts() -> None:
    brief = build_exercise_brief(_exercise(
        "class Conta:\n    def depositar(self, valor):\n        pass\n"
    ))

    assert "Classe Conta" in brief.required_names
    assert any("Conta.depositar" in item for item in brief.required_names)
    assert any(item.startswith("valor:") for item in brief.parameters)


def test_brief_supports_simple_guided_and_technical_reading_modes() -> None:
    brief = build_exercise_brief(_exercise(
        "def calcular_total(preco, quantidade=1):\n    pass\n"
    ))

    simple = brief.render("simple")
    guided = brief.render("guided")
    technical = brief.render("technical")

    assert "Em poucas palavras" in simple
    assert "Passos sugeridos" in simple
    assert "Plano de resolução" in guided
    assert "Contrato a respeitar" in guided
    assert "Especificação técnica" in technical
    assert "Critérios de avaliação" in technical
    assert len(simple) < len(technical)


def test_brief_preserves_structured_formula_but_keeps_simple_mode_readable() -> None:
    exercise = _exercise(
        "def capital_acumulado(inicial, taxa, anos):\n    pass\n"
    ).model_copy(update={
        "title": "Capital acumulado",
        "prompt": (
            "Calcula o capital ao fim do número de anos indicado.\n\n"
            "$$Capital = Inicial \\cdot (1 + Taxa / 100)^{Anos}$$\n\n"
            "Contexto: comparação local de taxas anuais."
        ),
        "tests": (
            "assert capital_acumulado(1500, 2, 1) == 1530.0",
        ),
    })

    brief = build_exercise_brief(exercise)

    assert brief.formula_latex == r"Capital = Inicial \cdot (1 + Taxa / 100)^{Anos}"
    assert "capital inicial" in brief.formula_spoken.casefold()
    assert any("fórmula" in step.casefold() for step in brief.top_down)
    assert "\\cdot" not in brief.render("simple")
    assert "\\cdot" not in brief.render("guided")
    assert "Notação para copiar" in brief.render("technical")


def test_course_practice_preserves_curriculum_order_and_metadata() -> None:
    first = _exercise("def primeiro(valor):\n    pass\n")
    second = _exercise("def segundo(valor):\n    pass\n").model_copy(
        update={"id": uuid4(), "slug": "segundo", "title": "Segundo"}
    )

    class Catalog:
        def list_all(self):
            return (first, second)

    class Curriculum:
        def units(self, _track_slug):
            return (
                {"id": "t2", "kind": "theory", "exercise_id": None,
                 "title": "Preparar B", "body": "Conceito B", "example": "Exemplo B",
                 "chapter_title": "Capítulo B", "completed": False, "unlocked": True},
                {"id": "u2", "kind": "practice", "exercise_id": str(second.id),
                 "chapter_title": "Capítulo B", "completed": False, "unlocked": True,
                 "assessment_id": "practical-b"},
                {"id": "quiz-b", "kind": "quiz", "exercise_id": None,
                 "assessment_id": "quiz-assessment-b", "title": "Verificar B",
                 "chapter_title": "Capítulo B", "completed": False, "unlocked": True},
                {"id": "theory", "kind": "theory", "exercise_id": None,
                 "chapter_title": "Teoria", "completed": False, "unlocked": False},
                {"id": "u1", "kind": "practice", "exercise_id": str(first.id),
                 "chapter_title": "Capítulo A", "completed": True, "unlocked": True},
            )

    controller = LearningGuiController(
        user=UserDTO(), exercises=Catalog(), submissions=object(),
        snapshot_provider=dict, curriculum=Curriculum(),
    )

    journey = controller.course_practice("python-foundations")

    assert tuple(item["exercise"].id for item in journey) == (second.id, first.id)
    assert journey[0]["chapter_title"] == "Capítulo B"
    assert journey[0]["theory_title"] == "Preparar B"
    assert journey[0]["theory_body"] == "Conceito B"
    assert journey[0]["theory_example"] == "Exemplo B"
    assert journey[0]["assessments"][0]["assessment_id"] == "quiz-assessment-b"
    assert journey[1]["completed"] is True


def test_ide_command_catalogue_is_unique_and_searchable() -> None:
    assert len({command.id for command in IDE_COMMANDS}) == len(IDE_COMMANDS)
    assert search_ide_commands("formatar")[0].id == "format"
    assert search_ide_commands("ctrl enter")[0].id == "run"
    assert {command.id for command in search_ide_commands("")} >= {
        "run", "correct", "debug", "tutor",
    }
    assert all(command.symbol.isascii() for command in IDE_COMMANDS)
