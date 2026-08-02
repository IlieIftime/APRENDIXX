from aprendix.bootstrap import build_runtime


def test_curriculum_is_original_ordered_and_practice_gated(tmp_path):
    runtime = build_runtime(tmp_path / "profile")
    tracks = runtime.curriculum.tracks()
    assert [item["slug"] for item in tracks] == [
        "python-foundations", "python-oop", "python-algorithms",
        "python-data-structures",
    ]
    units = runtime.curriculum.units("python-foundations")
    assert units[0]["kind"] == "practice"
    assert units[1]["kind"] == "theory"
    assert units[1]["practice_gate"] == 1
    with runtime.database.read_connection() as connection:
        assert connection.execute("SELECT count(*) FROM learning_unit_dependencies").fetchone()[0] >= 27
        assert connection.execute("SELECT count(*) FROM assessment_items").fetchone()[0] == 27


def test_glossary_lookup_is_encrypted_at_rest(tmp_path):
    runtime = build_runtime(tmp_path / "profile")
    entries = runtime.curriculum.glossary("pri")
    assert entries[0]["term"] == "print"
    assert "output" in entries[0]["definition"]
    raw = runtime.database.path.read_bytes()
    assert entries[0]["definition"].encode("utf-8") not in raw


def test_theory_assessment_updates_adaptive_graph(tmp_path):
    runtime = build_runtime(tmp_path / "profile")
    exercise = next(item for item in runtime.exercises.list_all() if item.slug == "hello-python")
    assert runtime.desktop.evaluate(exercise, exercise.starter_code, 10).passed
    with runtime.database.read_connection() as connection:
        theory_unit = connection.execute("""
            SELECT u.id FROM learning_units u JOIN learning_chapters c ON c.id=u.chapter_id
            WHERE c.slug='visible-output' AND u.kind='theory'
        """).fetchone()[0]
        item_id = connection.execute("""
            SELECT ai.id FROM assessment_items ai
            JOIN learning_units u ON u.id=ai.unit_id
            JOIN learning_chapters c ON c.id=u.chapter_id
            WHERE ai.kind='theory' AND c.slug='visible-output'
        """).fetchone()[0]
    runtime.curriculum.complete_unit(theory_unit)
    assessment = runtime.curriculum.assessment(item_id)
    answer = next(option["id"] for option in assessment["options"] if option["id"] == "b")
    result = runtime.curriculum.answer(item_id, answer)
    assert result["passed"] is True
    snapshot = runtime.graph_snapshot_service.get_snapshot(runtime.user.id)
    assert sum(node.statistics.attempt_count for node in snapshot.nodes) == 2
    assert runtime.curriculum.answer(item_id, "resposta impossível")["passed"] is False


def test_all_practical_assessments_link_existing_exercises(tmp_path):
    runtime = build_runtime(tmp_path / "profile")
    with runtime.database.read_connection() as connection:
        missing = connection.execute("""
            SELECT count(*) FROM assessment_items ai
            JOIN learning_units u ON u.id=ai.unit_id
            WHERE ai.kind='practical' AND u.exercise_id IS NULL
        """).fetchone()[0]
    assert missing == 0
