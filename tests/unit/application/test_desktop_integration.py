"""Acceptance tests for desktop Sprints 12.1 through 12.4."""

from datetime import date
from uuid import uuid4

import pytest

from aprendix.application.clustering import (
    ClusterAssignment, ClusterInput, HdbscanClusterService, TaxonomyClassifier,
)
from aprendix.application.contracts import (
    Complexity, ContentKind, DebugBreakpointDTO, DebugRequestDTO, LearningTheme,
    SearchRequestDTO, Technology,
)
from aprendix.application.knowledge import HybridSearchService, SearchCandidate
from aprendix.bootstrap import build_runtime


class _Embedder:
    def embed(self, _text):
        return (100, 0, 0)


class _Index:
    def __init__(self, candidates):
        self.candidates = candidates

    def search_candidates(self, _filters, *, limit=50_000):
        return self.candidates


def _candidate(title, text, embedding):
    return SearchCandidate(
        chunk_id=uuid4(), title=title, source_path="C:/local.pdf", author=None,
        content_type=ContentKind.THEORY, complexity=Complexity.BEGINNER,
        published_at=date(2026, 1, 1), page_number=1, text=text,
        embedding=embedding, technologies=(Technology.PYTHON,),
        themes=(LearningTheme.OOP,),
    )


def test_bm25_dense_fusion_and_reranker_prioritize_exact_context():
    exact = _candidate("Herança Python", "classes python herança métodos objetos", (70, 30, 0))
    dense_only = _candidate("Outro", "conteúdo distante", (100, 0, 0))
    service = HybridSearchService(_Index((dense_only, exact)), embedder=_Embedder())

    response = service.search(SearchRequestDTO(
        query="classes python herança", allow_web_fallback=False, max_results=2,
    ))

    assert response.evidence[0].id == str(exact.chunk_id)
    assert 0.0 <= response.evidence[0].relevance <= 1.0


def test_taxonomy_supports_requested_language_and_python_ecosystem():
    technologies, themes = TaxonomyClassifier.classify(
        "Django e pandas em Python com SQL, React, Bootstrap, Java, MongoDB e Go para web"
    )
    assert {
        Technology.PYTHON, Technology.DJANGO, Technology.PANDAS,
        Technology.SQL, Technology.REACT, Technology.BOOTSTRAP,
        Technology.JAVA, Technology.NOSQL, Technology.GO,
    }.issubset(technologies)
    assert LearningTheme.WEB in themes


class _ClusterStore:
    def __init__(self):
        self.saved: tuple[ClusterAssignment, ...] = ()
        points = ((100, 0), (98, 2), (96, 4), (-100, 0), (-98, -2), (-96, -4))
        self.items = tuple(
            ClusterInput(uuid4(), f"Python grupo {index}", "algoritmos python", point)
            for index, point in enumerate(points)
        )

    def cluster_inputs(self):
        return self.items

    def replace_clusters(self, assignments, _labels):
        self.saved = assignments


def test_hdbscan_assigns_every_chunk_once():
    store = _ClusterStore()
    result = HdbscanClusterService(store, min_cluster_size=2).rebuild()
    assert len(result) == len(store.items)
    assert {item.chunk_id for item in result} == {item.chunk_id for item in store.items}
    assert store.saved == result


def test_ide_evaluation_updates_graph_and_fixed_milestone(tmp_path):
    runtime = build_runtime(tmp_path / "profile")
    exercise = runtime.exercises.list_all()[0]

    receipt = runtime.desktop.evaluate(exercise, exercise.starter_code, 100)

    assert receipt.passed is True
    assert receipt.milestone is not None
    assert receipt.milestone.completed == 1
    snapshot = runtime.graph_snapshot_service.get_snapshot(runtime.user.id)
    assert sum(node.statistics.attempt_count for node in snapshot.nodes) == 1


def test_projects_are_encrypted_and_round_trip(tmp_path):
    runtime = build_runtime(tmp_path / "profile")
    project = runtime.desktop.save_project("Meu projeto", "print('segredo-local')")
    assert runtime.desktop.projects()[0] == project
    raw = runtime.database.path.read_bytes()
    assert b"segredo-local" not in raw
    assert b"Meu projeto" not in raw


def test_debug_state_and_project_versions_survive_locally_encrypted(tmp_path):
    runtime = build_runtime(tmp_path / "profile")
    exercise = runtime.exercises.list_all()[0]
    request = DebugRequestDTO(
        source_code="x = 2\nprint(x)",
        breakpoints=(DebugBreakpointDTO(line=2),), watches=("x",),
    )
    result = runtime.desktop.debug(request, exercise.id)
    assert result.status == "completed" and result.token_verified
    runtime.desktop.save_debug_recovery(
        exercise.id, request.source_code, cursor_index=4,
        breakpoints=tuple(item.model_dump(mode="json") for item in request.breakpoints),
        watches=request.watches,
    )
    recovered = runtime.desktop.load_debug_recovery(exercise.id)
    assert recovered["source"] == request.source_code
    assert recovered["watches"] == ("x",)

    project = runtime.desktop.save_project("Versões", "valor = 1")
    runtime.desktop.save_project("Versões", "valor = 2", project.id)
    versions = runtime.desktop.project_versions(project.id)
    assert [item["source_code"] for item in versions] == ["valor = 2", "valor = 1"]
    raw = runtime.database.path.read_bytes()
    assert b"valor = 2" not in raw and b"x = 2" not in raw


def test_project_workspace_supports_encrypted_nested_files_without_duplicate_projects(tmp_path):
    runtime = build_runtime(tmp_path / "profile")
    project = runtime.desktop.save_project("Pacote", "from src.calculos import soma")
    module = runtime.desktop.save_project(
        "Pacote", "SEGREDO_MULTIFILE_94721 = 42\n", project.id,
        relative_path="src/calculos.py",
    )

    assert len(runtime.desktop.projects()) == 1
    files = runtime.desktop.project_files(project.id)
    assert [item.relative_path for item in files] == ["main.py", "src/calculos.py"]
    assert files[1].source_code == module.source_code
    assert b"SEGREDO_MULTIFILE_94721" not in runtime.database.path.read_bytes()

    with pytest.raises(ValueError):
        runtime.desktop.save_project(
            "Pacote", "segredo", project.id, relative_path="../segredo.py",
        )


def test_local_onboarding_streak_xp_badge_and_certificate(tmp_path):
    runtime = build_runtime(tmp_path / "profile")
    solutions = {
        "hello-python": 'print("Olá, Python!")',
        "sum-two-values": "a = 7\nb = 5\nprint(a + b)",
        "even-or-odd": "numero = 9\nprint('par' if numero % 2 == 0 else 'ímpar')",
    }
    exercises = {
        item.slug: item for item in runtime.exercises.list_all()
        if item.slug in solutions
    }
    for slug, source in solutions.items():
        assert runtime.desktop.evaluate(exercises[slug], source, 100).passed

    game = runtime.desktop.gamification()
    assert game["xp"] == 30
    assert game["streak_days"] == 1
    assert game["onboarding"]["status"] == "completed"
    assert game["onboarding"]["assessed_level"] == "proficient"
    assert {item["kind"] for item in game["achievements"]} == {
        "badge", "certificate"
    }
    assert any(item["code"] == "badge:first-pass" for item in game["achievements"])


def test_oop_catalog_runs_and_grades_classes_end_to_end(tmp_path):
    runtime = build_runtime(tmp_path / "profile")
    exercise = next(
        item for item in runtime.exercises.list_all() if item.slug == "oop-account"
    )
    source = """class Conta:
    def __init__(self, saldo):
        self.saldo = saldo
    def depositar(self, valor):
        self.saldo += valor
"""
    assert runtime.desktop.run(source).status == "ok"
    receipt = runtime.desktop.evaluate(exercise, source, 100)
    assert receipt.passed is True
    assert receipt.milestone.theme is LearningTheme.OOP
    assert receipt.milestone.completed == 1
    assert receipt.milestone.required == 10
    with runtime.database.read_connection() as connection:
        assert connection.execute("SELECT count(*) FROM editor_sessions").fetchone()[0] == 1


def test_a2_variations_are_persisted_encrypted(tmp_path):
    runtime = build_runtime(tmp_path / "profile")
    exercise = runtime.exercises.list_all()[0]
    generated = runtime.desktop.variation(exercise, proficiency=0.4)
    with runtime.database.read_connection() as connection:
        row = connection.execute(
            "SELECT variation,payload_encrypted FROM generated_exercises"
        ).fetchone()
    assert row["variation"] == 1
    assert generated.prompt.encode("utf-8") not in bytes(row["payload_encrypted"])


def test_daily_cards_and_four_feedback_actions_are_persisted(tmp_path):
    runtime = build_runtime(tmp_path / "profile")
    cards = runtime.knowledge.list_theory_cards(authored_only=True)
    assert cards
    card = cards[0]
    assert card.id in runtime.desktop.daily_card_ids(limit=100)

    for feedback in ("already_knew", "useful", "confusing", "review"):
        runtime.desktop.review_card(card.id, feedback=feedback)

    with runtime.database.read_connection() as connection:
        rows = connection.execute(
            "SELECT feedback FROM card_feedback_events WHERE card_id=? ORDER BY created_at,id",
            (str(card.id),),
        ).fetchall()
    assert {row["feedback"] for row in rows} == {
        "already_knew", "useful", "confusing", "review",
    }
