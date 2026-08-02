"""Schema creation, integrity, and transaction tests."""

import sqlite3
from uuid import uuid4

import pytest

from aprendix.infrastructure.db import Database
from aprendix.infrastructure.db.schema import SCHEMA_VERSION

EXPECTED_TABLES = {
    "attempts",
    "events",
    "documents",
    "document_chunks",
    "chunk_embeddings",
    "exercises",
    "exercise_sources",
    "exercise_test_cases",
    "graph_edges",
    "graph_nodes",
    "graph_processed_events",
    "profiles",
    "grading_results",
    "ingestion_runs",
    "schema_migrations",
    "user_node_stats",
    "users",
    "theory_cards",
    "knowledge_taxonomy",
    "knowledge_clusters",
    "knowledge_cluster_members",
    "milestone_definitions",
    "user_milestones",
    "local_projects",
    "project_files",
    "generated_exercises",
    "focus_sessions",
    "attempt_justifications",
    "editor_sessions",
    "learning_tracks",
    "learning_chapters",
    "learning_units",
    "learning_unit_dependencies",
    "learning_unit_progress",
    "assessment_items",
    "assessment_options",
    "assessment_attempts",
    "glossary_entries",
    "bibliography_links",
    "study_days",
    "onboarding_state",
    "local_achievements",
    "card_review_state",
    "knowledge_areas",
    "knowledge_area_chunks",
    "curated_sources",
    "knowledge_area_sources",
    "search_shortcuts",
    "reading_assistance",
    "content_quality_audits",
    "chunk_quality",
    "study_plans",
}


def test_initialize_creates_complete_schema(database: Database) -> None:
    with database.read_connection() as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                """
            )
        }
        migration = connection.execute(
            "SELECT max(version) AS version FROM schema_migrations"
        ).fetchone()
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]

    assert tables == EXPECTED_TABLES
    assert migration["version"] == SCHEMA_VERSION
    assert foreign_keys == 1


def test_initialize_is_idempotent(database: Database) -> None:
    database.initialize()
    database.initialize()

    with database.read_connection() as connection:
        count = connection.execute(
            "SELECT count(*) FROM schema_migrations"
        ).fetchone()[0]

    assert count == SCHEMA_VERSION


def test_migration_10_repairs_existing_version_9_database(database: Database) -> None:
    with database.transaction() as connection:
        connection.execute("DROP TABLE learning_unit_progress")
        connection.execute("DELETE FROM schema_migrations WHERE version=10")

    database.initialize()

    with database.read_connection() as connection:
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='learning_unit_progress'"
        ).fetchone()
        migrated = connection.execute(
            "SELECT 1 FROM schema_migrations WHERE version=10"
        ).fetchone()
    assert table is not None
    assert migrated is not None


def test_foreign_keys_reject_orphan_events(database: Database) -> None:
    with pytest.raises(sqlite3.IntegrityError), database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO events(
                id, idempotency_key, user_id, event_type, payload_encrypted,
                occurred_at, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                str(uuid4()),
                str(uuid4()),
                "exercise.opened",
                b"encrypted",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )


def test_transaction_rolls_back_every_statement(database: Database) -> None:
    user_id = str(uuid4())

    with pytest.raises(RuntimeError, match="abort"):
        with database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO users(id, consent_sync, created_at, updated_at)
                VALUES (?, 0, ?, ?)
                """,
                (
                    user_id,
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-01T00:00:00+00:00",
                ),
            )
            raise RuntimeError("abort")

    with database.read_connection() as connection:
        count = connection.execute(
            "SELECT count(*) FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()[0]

    assert count == 0


def test_connection_enables_safety_and_concurrency_pragmas(
    database: Database,
) -> None:
    with database.read_connection() as connection:
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        trusted_schema = connection.execute("PRAGMA trusted_schema").fetchone()[0]
        temp_store = connection.execute("PRAGMA temp_store").fetchone()[0]
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()

    assert foreign_keys == 1
    assert trusted_schema == 0
    assert temp_store == 2
    assert journal_mode == "wal"
    assert integrity == "ok"
    assert foreign_key_errors == []


def test_database_constraints_reject_invalid_profile(database: Database) -> None:
    user_id = str(uuid4())
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO users(id, consent_sync, created_at, updated_at)
            VALUES (?, 0, ?, ?)
            """,
            (
                user_id,
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )

    with pytest.raises(sqlite3.IntegrityError), database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO profiles(
                user_id, theta, xp, streak_days, preferences_encrypted,
                created_at, updated_at
            ) VALUES (?, 0.0, -1, 0, ?, ?, ?)
            """,
            (
                user_id,
                b"encrypted",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )
