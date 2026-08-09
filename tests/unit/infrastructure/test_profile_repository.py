from pathlib import Path

import pytest

from aprendix.application.profile_transfer import ProfileTransferError, validate_snapshot
from aprendix.bootstrap import build_runtime


def test_desktop_profile_round_trip_preserves_attempt_review_and_unit(tmp_path: Path) -> None:
    source = build_runtime(tmp_path / "source")
    exercise = next(item for item in source.exercises.list_all() if item.slug == "hello-python")
    assert source.desktop.evaluate(exercise, exercise.starter_code, 120).passed
    card = source.knowledge.list_theory_cards(authored_only=True, limit=1)[0]
    source.desktop.review_card(card.id, known=True)
    with source.database.transaction() as connection:
        unit = connection.execute(
            "SELECT id FROM learning_units WHERE kind='hybrid' ORDER BY rowid LIMIT 1"
        ).fetchone()
        connection.execute(
            "INSERT OR IGNORE INTO learning_unit_progress VALUES(?,?,datetime('now'))",
            (str(source.user.id), unit["id"]),
        )
    package = source.profile_transfer.export(
        tmp_path / "portable.apxprofile", "segredo-portatil"
    )

    target = build_runtime(tmp_path / "target")
    preview = target.profile_transfer.preview(package, "segredo-portatil")
    assert preview["incoming_attempts"] == 1
    assert preview["incoming_reviews"] == 1
    assert preview["incoming_completed_units"] == 1
    result = target.profile_transfer.import_file(package, "segredo-portatil")
    assert result["attempts"] == 1
    assert result["reviews"] == 1
    assert result["completed_units"] == 1
    assert target.attempts.list_for_user(target.user.id)[0].source_code == exercise.starter_code


def test_profile_schema_rejects_duplicate_and_nested_records() -> None:
    with pytest.raises(ProfileTransferError):
        validate_snapshot({"platform": "mobile", "reviews": [{"id": "x"}, {"id": "x"}]})
    with pytest.raises(ProfileTransferError):
        validate_snapshot({"platform": "mobile", "attempts": [{"id": "x", "bad": {"nested": True}}]})
