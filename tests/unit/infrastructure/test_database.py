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
    "glossary_aliases",
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
    "feature_flags",
    "diagnostic_events",
    "baseline_metrics",
    "learning_evidence",
    "mastery_states",
    "weekly_plan_items",
    "learning_paths",
    "learning_path_courses",
    "course_prerequisites",
    "curriculum_objectives",
    "unit_objectives",
    "curriculum_releases",
    "content_source_adapters",
    "document_provenance",
    "content_revisions",
    "content_validation_results",
    "curriculum_coverage",
    "curriculum_objective_evidence",
    "content_mapping_runs",
    "reading_bookmarks",
    "reading_notes",
    "search_quality_runs",
    "search_fts_public",
    "search_fts_public_data",
    "search_fts_public_idx",
    "search_fts_public_content",
    "search_fts_public_docsize",
    "search_fts_public_config",
    "blind_search_terms",
    "embedding_lsh_buckets",
    "private_search_index_state",
    "private_search_filters",
    "private_search_chunk_ordinals",
    "private_search_bit_slices",
    "debug_sessions",
    "editor_recovery_state",
    "project_file_versions",
    "local_test_runs",
    "card_feedback_events",
    "tutor_messages",
    "guided_project_templates",
    "portfolio_projects",
    "project_evaluations",
    "project_milestone_state",
    "snippet_analyses",
    "game_sessions",
    "game_statistics",
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


def test_migration_30_exposes_detailed_evidence_and_2pl_state(database: Database) -> None:
    with database.read_connection() as connection:
        evidence = {row["name"] for row in connection.execute("PRAGMA table_info(learning_evidence)")}
        mastery = {row["name"] for row in connection.execute("PRAGMA table_info(mastery_states)")}
    assert {
        "active_seconds", "error_category", "transfer_score", "project_quality",
        "item_difficulty", "item_discrimination", "response_confidence",
    }.issubset(evidence)
    assert {"irt_ability", "irt_information"}.issubset(mastery)


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


def test_migration_15_upgrades_a_version_14_database(database: Database) -> None:
    with database.transaction() as connection:
        connection.execute("DROP TABLE baseline_metrics")
        connection.execute("DROP TABLE diagnostic_events")
        connection.execute("DROP TABLE feature_flags")
        connection.execute("DELETE FROM schema_migrations WHERE version=15")

    database.initialize()

    with database.read_connection() as connection:
        tables = {
            row[0] for row in connection.execute(
                """SELECT name FROM sqlite_master WHERE type='table'
                   AND name IN ('feature_flags','diagnostic_events','baseline_metrics')"""
            )
        }
        migrated = connection.execute(
            "SELECT 1 FROM schema_migrations WHERE version=15"
        ).fetchone()
    assert tables == {"feature_flags", "diagnostic_events", "baseline_metrics"}
    assert migrated is not None


def test_migration_16_upgrades_a_version_15_database(database: Database) -> None:
    with database.transaction() as connection:
        connection.execute("DROP TABLE weekly_plan_items")
        connection.execute("DROP TABLE mastery_states")
        connection.execute("DROP TABLE learning_evidence")
        connection.execute("DELETE FROM schema_migrations WHERE version=16")

    database.initialize()

    with database.read_connection() as connection:
        tables = {row[0] for row in connection.execute(
            """SELECT name FROM sqlite_master WHERE type='table' AND name IN
               ('learning_evidence','mastery_states','weekly_plan_items')"""
        )}
    assert tables == {"learning_evidence", "mastery_states", "weekly_plan_items"}


def test_migration_17_upgrades_a_version_16_database(database: Database) -> None:
    new_tables = (
        "unit_objectives", "curriculum_objectives", "course_prerequisites",
        "learning_path_courses", "learning_paths", "curriculum_releases",
    )
    with database.transaction() as connection:
        for table in new_tables:
            connection.execute(f"DROP TABLE {table}")
        connection.execute("DELETE FROM schema_migrations WHERE version=17")

    database.initialize()

    with database.read_connection() as connection:
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
    assert set(new_tables).issubset(tables)


def test_migration_18_upgrades_a_version_17_database(database: Database) -> None:
    new_tables = (
        "curriculum_coverage", "content_validation_results", "content_revisions",
        "document_provenance", "content_source_adapters",
    )
    with database.read_connection() as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(documents)")}
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        migrated = connection.execute(
            "SELECT 1 FROM schema_migrations WHERE version=18"
        ).fetchone()
    assert "lifecycle" in columns
    assert set(new_tables).issubset(tables)
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
