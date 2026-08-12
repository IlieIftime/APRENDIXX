"""Iteration 20 credit integrity and project-domain regression tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from aprendix.bootstrap import build_runtime


BOOLEAN_SOURCE = """def contar_verdadeiros(condicoes):
    return sum(1 for valor in condicoes if valor is True)
"""

BYTE_SOURCE = """def limitar_byte(valor):
    return max(0, min(255, valor))
"""

RESOURCE_SOURCE = """def classificar_recurso(descricao):
    texto = descricao.casefold()
    if 'guardar' in texto:
        return 'armazenamento'
    if 'tempor' in texto:
        return 'memoria'
    return 'cpu'
"""

DECOMPOSITION_SOURCE = """def decompor(pedido):
    if pedido == 'somar dois valores':
        return ['ler valores', 'somar valores', 'mostrar resultado']
    raise ValueError('pedido desconhecido')
"""

CAPSTONE_SOURCE = '''"""Classificador local verificável de recursos."""

def classificar(descricao):
    texto = descricao.casefold()
    if "guardar" in texto:
        return "armazenamento"
    if "tempor" in texto:
        return "memoria"
    return "cpu"

def main():
    assert classificar("guardar ficheiro") == "armazenamento"
    assert classificar("estado temporario") == "memoria"

main()
'''


def _exercise(runtime, slug):
    return next(item for item in runtime.exercises.list_all() if item.slug == slug)


def _complete_literacy_course(runtime) -> None:
    solutions = (
        ("academy-resources-and-files", RESOURCE_SOURCE),
        ("academy-problem-decomposition", DECOMPOSITION_SOURCE),
        ("academy-data-representation", BYTE_SOURCE),
    )
    for exercise_slug, source in solutions:
        exercise = _exercise(runtime, exercise_slug)
        receipt = runtime.desktop.evaluate(exercise, source, 100)
        assert receipt.passed and receipt.credit_awarded
        units = runtime.curriculum.units("computer-literacy")
        practice = next(
            item for item in units
            if str(item.get("exercise_id")) == str(exercise.id)
        )
        stage = [
            item for item in units
            if item["chapter_title"] == practice["chapter_title"]
        ]
        theory = next(item for item in stage if item["kind"] == "theory")
        quiz = next(item for item in stage if item["kind"] == "quiz")
        hybrid = next(item for item in stage if item["kind"] == "hybrid")
        runtime.curriculum.complete_unit(theory["id"])
        quiz_result = runtime.curriculum.answer(quiz["assessment_id"], "b")
        hybrid_result = runtime.curriculum.answer(
            hybrid["assessment_id"], "validar"
        )
        assert quiz_result["credit_awarded"] is True
        assert hybrid_result["credit_awarded"] is True


def _complete_literacy_capstone(runtime):
    template = next(
        item for item in runtime.portfolio.templates()
        if item.track_slug == "computer-literacy" and item.capstone
    )
    project = runtime.portfolio.start(template.id, mode="autonomous")
    runtime.desktop.save_project(project.name, CAPSTONE_SOURCE, project.id)
    for ordinal in range(len(template.milestones)):
        runtime.portfolio.set_milestone(project.id, ordinal)
    evaluation = runtime.portfolio.evaluate(project.id)
    assert evaluation.passed is True
    assert evaluation.track_slug == "computer-literacy"
    assert evaluation.work_mode == "autonomous"
    assert evaluation.credit_awarded is True
    assert evaluation.access.completed is True
    return evaluation


def test_early_pass_is_evidence_only_and_requires_a_new_eligible_pass(tmp_path):
    runtime = build_runtime(tmp_path / "profile")
    exercise = _exercise(runtime, "academy-boolean-reasoning")

    early = runtime.desktop.evaluate(exercise, BOOLEAN_SOURCE, 100)

    assert early.passed is True
    assert early.access.viewable is True
    assert early.access.credit_eligible is False
    assert early.access.reason_code.value == "prerequisites_incomplete"
    assert early.credit_awarded is False
    assert early.milestone is None
    assert runtime.desktop.gamification()["xp"] == 0
    with runtime.database.read_connection() as connection:
        assert connection.execute(
            "SELECT count(*) FROM attempts WHERE exercise_id=? AND status='passed'",
            (str(exercise.id),),
        ).fetchone()[0] == 1
        assert connection.execute(
            """SELECT count(*) FROM learning_unit_progress p
               JOIN learning_units u ON u.id=p.unit_id
               WHERE p.user_id=? AND u.exercise_id=?""",
            (str(runtime.user.id), str(exercise.id)),
        ).fetchone()[0] == 0

    _complete_literacy_course(runtime)
    _complete_literacy_capstone(runtime)
    unlocked = next(
        item for item in runtime.curriculum.paths()
        if item["track_slug"] == "logic-pseudocode"
    )
    assert unlocked["viewable"] and unlocked["credit_eligible"]

    eligible = runtime.desktop._workspace.practice_access(
        runtime.user.id, exercise.id,
    )
    assert eligible.credit_eligible is True
    with runtime.database.read_connection() as connection:
        before_xp = connection.execute(
            "SELECT xp FROM profiles WHERE user_id=?", (str(runtime.user.id),)
        ).fetchone()[0]

    credited = runtime.desktop.evaluate(exercise, BOOLEAN_SOURCE, 100)
    assert credited.passed and credited.credit_awarded
    assert credited.access.completed
    assert credited.attempt_number == 2
    after_once = runtime.desktop.gamification()["xp"]
    assert after_once == before_xp + 10

    repeated = runtime.desktop.evaluate(exercise, BOOLEAN_SOURCE, 100)
    assert repeated.passed and repeated.credit_awarded is False
    assert repeated.access.completed
    assert repeated.milestone is None
    assert runtime.desktop.gamification()["xp"] == after_once


def test_locked_assessment_is_recorded_without_progress_or_retroactive_credit(tmp_path):
    runtime = build_runtime(tmp_path / "profile")
    unit = next(
        item for item in runtime.curriculum.units("logic-pseudocode")
        if item["kind"] == "quiz"
    )

    result = runtime.curriculum.answer(unit["assessment_id"], "b")

    assert result["passed"] is True
    assert result["credit_awarded"] is False
    assert result["viewable"] is True
    assert result["completed"] is False
    assert result["reason_code"] == "prerequisites_incomplete"
    with runtime.database.read_connection() as connection:
        assert connection.execute(
            "SELECT count(*) FROM assessment_attempts WHERE item_id=?",
            (unit["assessment_id"],),
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT count(*) FROM learning_unit_progress WHERE user_id=? AND unit_id=?",
            (str(runtime.user.id), unit["id"]),
        ).fetchone()[0] == 0


def test_project_credit_requires_matching_capstone_milestones_and_fresh_evaluation(tmp_path):
    runtime = build_runtime(tmp_path / "profile")
    non_capstone = next(
        item for item in runtime.portfolio.templates()
        if item.track_slug == "python-foundations" and not item.capstone
    )
    exploratory = runtime.portfolio.start(non_capstone.id, mode="guided")
    runtime.desktop.save_project(exploratory.name, CAPSTONE_SOURCE, exploratory.id)
    exploratory_result = runtime.portfolio.evaluate(exploratory.id)
    assert exploratory_result.passed
    assert exploratory_result.credit_awarded is False
    assert exploratory_result.access.reason_code.value == "project_not_capstone"

    _complete_literacy_course(runtime)
    template = next(
        item for item in runtime.portfolio.templates()
        if item.track_slug == "computer-literacy" and item.capstone
    )
    project = runtime.portfolio.start(template.id, mode="autonomous")
    runtime.desktop.save_project(project.name, CAPSTONE_SOURCE, project.id)

    before_milestones = runtime.portfolio.evaluate(project.id)
    assert before_milestones.passed
    assert before_milestones.credit_awarded is False
    assert before_milestones.access.reason_code.value == "project_milestones_incomplete"
    for ordinal in range(len(template.milestones)):
        runtime.portfolio.set_milestone(project.id, ordinal)
    credited = runtime.portfolio.evaluate(project.id)
    assert credited.passed and credited.credit_awarded
    assert credited.access.track_slug == template.track_slug

    with runtime.database.read_connection() as connection:
        project_unit = connection.execute(
            """SELECT u.id FROM learning_units u
               JOIN learning_chapters c ON c.id=u.chapter_id
               JOIN learning_tracks t ON t.id=c.track_id
               WHERE t.slug=? AND u.kind='project'""",
            (template.track_slug,),
        ).fetchone()[0]
        assert connection.execute(
            "SELECT count(*) FROM learning_unit_progress WHERE user_id=? AND unit_id=?",
            (str(runtime.user.id), project_unit),
        ).fetchone()[0] == 1
    with pytest.raises(ValueError, match="approved matching capstone"):
        runtime.curriculum.complete_unit(project_unit)


def test_legacy_progress_is_preserved_but_excluded_from_unlocking(tmp_path):
    runtime = build_runtime(tmp_path / "profile")
    exercise = _exercise(runtime, "academy-boolean-reasoning")
    with runtime.database.transaction() as connection:
        unit_id = connection.execute(
            "SELECT id FROM learning_units WHERE exercise_id=? AND kind='practice'",
            (str(exercise.id),),
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO learning_unit_progress VALUES(?,?,?)",
            (str(runtime.user.id), unit_id, datetime.now(UTC).isoformat()),
        )

    audit = runtime.curriculum.progress_integrity_audit()
    unit = next(
        item for item in runtime.curriculum.units("logic-pseudocode")
        if item["id"] == unit_id
    )
    assert audit == {
        "recorded": 1,
        "valid": 0,
        "suspicious": 1,
        "suspicious_by_kind": {"practice": 1},
        "history_preserved": True,
        "used_for_unlocking": False,
    }
    assert unit["viewable"] is True
    assert unit["completed"] is False
    assert unit["credit_eligible"] is False
    with runtime.database.read_connection() as connection:
        assert connection.execute(
            "SELECT count(*) FROM learning_unit_progress WHERE user_id=? AND unit_id=?",
            (str(runtime.user.id), unit_id),
        ).fetchone()[0] == 1
