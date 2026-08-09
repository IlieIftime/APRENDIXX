from pathlib import Path

import pytest

from aprendix_mobile.paths import PlatformPaths
from aprendix_mobile.runtime import build_mobile_runtime
from aprendix_mobile.security import HostDevelopmentKeyProvider, MissingDeviceKeyError
from aprendix_mobile.seed import build_seed


def _paths(tmp_path: Path) -> PlatformPaths:
    assets = tmp_path / "assets"; assets.mkdir()
    build_seed(assets / "knowledge-lite.db", assets / "seed-manifest.json")
    return PlatformPaths.resolve(
        user_data_dir=tmp_path / "data", cache_dir=tmp_path / "cache",
        resources_dir=assets,
    )


def test_mobile_runtime_uses_lite_content_and_persists_encrypted_attempt(tmp_path: Path) -> None:
    runtime = build_mobile_runtime(_paths(tmp_path), allow_host_development=True)
    assert len(runtime.cards()) >= 6
    result, passed = runtime.execute("hello", "print('ok')", "ok")
    assert result.status == "ok" and passed
    raw = runtime.paths.user_database.read_bytes()
    assert b"print('ok')" not in raw
    assert runtime.state.passed_attempts() == 1


def test_mobile_runtime_requires_a_learning_oracle_and_grades_quiz(tmp_path: Path) -> None:
    runtime = build_mobile_runtime(_paths(tmp_path), allow_host_development=True)
    _result, passed = runtime.execute("no-oracle", "print('anything')")
    assert passed is False
    item = next(card for card in runtime.cards(mode="free") if card["correct_option"])
    correct_index = ord(str(item["correct_option"])) - ord("a")
    quiz_passed, explanation = runtime.grade_quiz(item, correct_index)
    assert quiz_passed is True
    assert explanation
    raw = runtime.paths.user_database.read_bytes()
    assert explanation.encode() not in raw


def test_every_lite_practical_and_theory_item_is_operational(tmp_path: Path) -> None:
    runtime = build_mobile_runtime(_paths(tmp_path), allow_host_development=True)
    solutions = {
        "python-output": "print('Olá, mobile!')",
        "python-decisions": "valor = 3\nprint('positivo' if valor > 0 else 'não positivo')",
        "python-objects": (
            "class Contador:\n"
            "    def __init__(self):\n        self.valor = 0\n"
            "    def incrementar(self):\n        self.valor += 1\n"
            "c = Contador()\nc.incrementar()\nc.incrementar()\nprint(c.valor)"
        ),
        "python-collections": "valores = [2, 1, 2]\nprint(sorted(set(valores)))",
        "python-finance": "capital = 100\ntaxa = 0.05\nprint(capital * (1 + taxa))",
        "python-games": "pontos = 10\nprint('ganhou' if pontos >= 10 else 'continua')",
    }
    cards = tuple(item for item in runtime.cards(mode="free") if item["exercise_id"])
    assert set(solutions) == {str(item["id"]) for item in cards}
    for item in cards:
        result, passed = runtime.execute(
            str(item["exercise_id"]), solutions[str(item["id"])],
            str(item["expected_output"]),
        )
        assert result.status == "ok", (item["id"], result)
        assert passed is True, item["id"]
        correct = ord(str(item["correct_option"])) - ord("a")
        assert runtime.grade_quiz(item, correct)[0] is True
    assert runtime.state.passed_attempts() == 6


def test_mobile_hierarchy_search_shortcuts_and_assisted_reader(tmp_path: Path) -> None:
    runtime = build_mobile_runtime(_paths(tmp_path), allow_host_development=True)
    areas = runtime.areas()
    assert len(areas) >= 40
    assert any(item["id"] == "autonomous-agents" for item in areas)
    assert runtime.shortcuts("computer-vision")
    hits = runtime.search("transformer attention", area_id="artificial-intelligence")
    assert hits
    assert any("transform" in str(item["title"]).casefold() for item in hits)
    detail = runtime.reading(str(hits[0]["id"]), "attention")
    assert detail["summary"] and detail["simplified"] and detail["key_points"]


def test_existing_database_without_key_fails_closed(tmp_path: Path) -> None:
    database = tmp_path / "user.db"; database.write_bytes(b"existing")
    provider = HostDevelopmentKeyProvider(
        tmp_path / "missing.key", database_path=database, allow=True
    )
    with pytest.raises(MissingDeviceKeyError):
        provider.get_or_create_key()


def test_host_key_provider_requires_explicit_opt_in(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError):
        HostDevelopmentKeyProvider(
            tmp_path / "key", database_path=tmp_path / "db", allow=False
        )


def test_mobile_break_games_resume_without_affecting_course_progress(tmp_path: Path) -> None:
    runtime = build_mobile_runtime(_paths(tmp_path), allow_host_development=True)
    session = runtime.games.new("sudoku", "Fácil", daily=True)
    session.elapsed_seconds = 19
    runtime.games.save(session)
    resumed = runtime.games.new("sudoku", "Fácil", daily=True)
    assert resumed.id == session.id and resumed.elapsed_seconds == 19
    assert runtime.state.completed_units() == ()
