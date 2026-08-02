"""Deterministic catalogue tests for the three CLI exercises."""

from aprendix.infrastructure.db import Database, ExerciseRepository
from aprendix.infrastructure.security import AesGcmFieldCipher
from aprendix.infrastructure.seed import DEFAULT_EXERCISES, seed_default_catalog


def test_seed_creates_exactly_three_exercises_and_nodes(
    database: Database,
    cipher: AesGcmFieldCipher,
) -> None:
    seed_default_catalog(database)

    exercises = ExerciseRepository(database, cipher).list_all()
    with database.read_connection() as connection:
        node_count = connection.execute(
            "SELECT count(*) FROM graph_nodes"
        ).fetchone()[0]

    assert len(exercises) == 3
    assert node_count == 3
    assert {item.slug for item in exercises} == {
        item.slug for item in DEFAULT_EXERCISES
    }
    assert all(item.tests for item in exercises)


def test_seed_is_idempotent_with_stable_ids(
    database: Database,
    cipher: AesGcmFieldCipher,
) -> None:
    seed_default_catalog(database)
    first = ExerciseRepository(database, cipher).list_all()
    seed_default_catalog(database)
    second = ExerciseRepository(database, cipher).list_all()

    assert first == second
    assert len(second) == 3

