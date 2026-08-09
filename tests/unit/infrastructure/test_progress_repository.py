"""Persistence and idempotence tests for learning evidence."""

from datetime import UTC, datetime

from aprendix.application.contracts import LearningEvidenceDTO, MasteryStateDTO, UserDTO
from aprendix.application.progress import update_mastery_state
from aprendix.infrastructure.db import LearningProgressRepository, UserRepository
from aprendix.infrastructure.seed import seed_default_catalog


def test_evidence_is_idempotent_and_state_round_trips(database, cipher) -> None:
    seed_default_catalog(database)
    user = UserDTO(display_name="Teste")
    UserRepository(database, cipher).add(user)
    node_id = LearningProgressRepository(database).node_catalog()[0][0]
    evidence = LearningEvidenceDTO(
        user_id=user.id, node_id=node_id, source_key="attempt:stable",
        evidence_type="practice", score=0.8, duration_seconds=420,
        active_seconds=300, error_category="conceptual", item_difficulty=0.4,
        item_discrimination=1.3, response_confidence=0.8, transfer_score=0.7,
        occurred_at=datetime(2026, 8, 2, tzinfo=UTC),
    )
    state = update_mastery_state(None, evidence)
    repository = LearningProgressRepository(database)

    assert repository.commit_evidence(evidence, state) is True
    assert repository.commit_evidence(evidence, state) is False
    restored = repository.state(user.id, node_id)

    assert restored == state
    with database.read_connection() as connection:
        assert connection.execute("SELECT count(*) FROM learning_evidence").fetchone()[0] == 1
    assert repository.activity_summary(user.id) == {
        "total_seconds": 420, "active_seconds": 300,
    }
