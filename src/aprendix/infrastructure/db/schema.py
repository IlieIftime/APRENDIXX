"""Versioned SQLite schema for the local-first learning platform."""

SCHEMA_VERSION = 33

MIGRATIONS: dict[int, tuple[str, ...]] = {
    1: (
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY NOT NULL,
            display_name_encrypted BLOB,
            consent_sync INTEGER NOT NULL DEFAULT 0
                CHECK (consent_sync IN (0, 1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
                CHECK (updated_at >= created_at)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS graph_nodes (
            id TEXT PRIMARY KEY NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL CHECK (length(trim(title)) > 0),
            description TEXT NOT NULL DEFAULT '',
            difficulty REAL NOT NULL DEFAULT 0.0
                CHECK (difficulty BETWEEN -3.0 AND 3.0),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
                CHECK (updated_at >= created_at)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS exercises (
            id TEXT PRIMARY KEY NOT NULL,
            graph_node_id TEXT NOT NULL,
            slug TEXT NOT NULL,
            title TEXT NOT NULL CHECK (length(trim(title)) > 0),
            prompt TEXT NOT NULL CHECK (length(trim(prompt)) > 0),
            starter_code TEXT NOT NULL DEFAULT '',
            tests_json TEXT NOT NULL DEFAULT '[]'
                CHECK (json_valid(tests_json)),
            difficulty REAL NOT NULL DEFAULT 0.0
                CHECK (difficulty BETWEEN -3.0 AND 3.0),
            version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
                CHECK (updated_at >= created_at),
            FOREIGN KEY (graph_node_id) REFERENCES graph_nodes(id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            UNIQUE (slug, version)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY NOT NULL,
            idempotency_key TEXT NOT NULL,
            user_id TEXT NOT NULL,
            event_type TEXT NOT NULL CHECK (length(trim(event_type)) > 0),
            payload_encrypted BLOB NOT NULL,
            occurred_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
                ON UPDATE CASCADE ON DELETE CASCADE,
            UNIQUE (user_id, idempotency_key)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS attempts (
            id TEXT PRIMARY KEY NOT NULL,
            idempotency_key TEXT NOT NULL,
            user_id TEXT NOT NULL,
            exercise_id TEXT NOT NULL,
            status TEXT NOT NULL
                CHECK (status IN ('draft', 'submitted', 'passed', 'failed', 'error')),
            source_code_encrypted BLOB NOT NULL,
            output_encrypted BLOB,
            score REAL CHECK (score IS NULL OR score BETWEEN 0.0 AND 1.0),
            duration_ms INTEGER CHECK (duration_ms IS NULL OR duration_ms >= 0),
            submitted_at TEXT,
            created_at TEXT NOT NULL,
            CHECK (
                status NOT IN ('passed', 'failed', 'error')
                OR submitted_at IS NOT NULL
            ),
            FOREIGN KEY (user_id) REFERENCES users(id)
                ON UPDATE CASCADE ON DELETE CASCADE,
            FOREIGN KEY (exercise_id) REFERENCES exercises(id)
                ON UPDATE CASCADE ON DELETE RESTRICT,
            UNIQUE (user_id, idempotency_key)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS graph_edges (
            source_node_id TEXT NOT NULL,
            target_node_id TEXT NOT NULL,
            weight REAL NOT NULL DEFAULT 0.0 CHECK (weight >= 0.0),
            co_occurrence_count INTEGER NOT NULL DEFAULT 0
                CHECK (co_occurrence_count >= 0),
            updated_at TEXT NOT NULL,
            PRIMARY KEY (source_node_id, target_node_id),
            CHECK (source_node_id <> target_node_id),
            FOREIGN KEY (source_node_id) REFERENCES graph_nodes(id)
                ON UPDATE CASCADE ON DELETE CASCADE,
            FOREIGN KEY (target_node_id) REFERENCES graph_nodes(id)
                ON UPDATE CASCADE ON DELETE CASCADE
        ) WITHOUT ROWID
        """,
        """
        CREATE TABLE IF NOT EXISTS profiles (
            user_id TEXT PRIMARY KEY NOT NULL,
            theta REAL NOT NULL DEFAULT 0.0 CHECK (theta BETWEEN -6.0 AND 6.0),
            xp INTEGER NOT NULL DEFAULT 0 CHECK (xp >= 0),
            streak_days INTEGER NOT NULL DEFAULT 0 CHECK (streak_days >= 0),
            preferences_encrypted BLOB NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL CHECK (updated_at >= created_at),
            FOREIGN KEY (user_id) REFERENCES users(id)
                ON UPDATE CASCADE ON DELETE CASCADE
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_events_user_occurred
        ON events(user_id, occurred_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_events_type_occurred
        ON events(event_type, occurred_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_attempts_user_created
        ON attempts(user_id, created_at DESC)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_attempts_exercise_status
        ON attempts(exercise_id, status)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_exercises_node
        ON exercises(graph_node_id)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_graph_edges_target
        ON graph_edges(target_node_id)
        """,
    ),
    2: (
        """
        ALTER TABLE events
        ADD COLUMN schema_version INTEGER NOT NULL DEFAULT 1
            CHECK (schema_version >= 1)
        """,
    ),
    3: (
        """
        CREATE TABLE user_node_stats (
            user_id TEXT NOT NULL,
            node_id TEXT NOT NULL,
            attempt_count INTEGER NOT NULL DEFAULT 0
                CHECK (attempt_count >= 0),
            success_count INTEGER NOT NULL DEFAULT 0
                CHECK (success_count >= 0),
            failure_count INTEGER NOT NULL DEFAULT 0
                CHECK (failure_count >= 0),
            thompson_alpha REAL NOT NULL DEFAULT 1.0
                CHECK (thompson_alpha > 0.0),
            thompson_beta REAL NOT NULL DEFAULT 1.0
                CHECK (thompson_beta > 0.0),
            last_seen_at TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, node_id),
            CHECK (success_count + failure_count <= attempt_count),
            FOREIGN KEY (user_id) REFERENCES users(id)
                ON UPDATE CASCADE ON DELETE CASCADE,
            FOREIGN KEY (node_id) REFERENCES graph_nodes(id)
                ON UPDATE CASCADE ON DELETE CASCADE
        ) WITHOUT ROWID
        """,
        """
        CREATE TABLE graph_processed_events (
            event_id TEXT PRIMARY KEY NOT NULL,
            user_id TEXT NOT NULL,
            node_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            processed_at TEXT NOT NULL,
            FOREIGN KEY (event_id) REFERENCES events(id)
                ON UPDATE CASCADE ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id)
                ON UPDATE CASCADE ON DELETE CASCADE,
            FOREIGN KEY (node_id) REFERENCES graph_nodes(id)
                ON UPDATE CASCADE ON DELETE CASCADE
        )
        """,
        """
        CREATE INDEX idx_graph_activity_user_time
        ON graph_processed_events(user_id, occurred_at DESC)
        """,
        """
        CREATE INDEX idx_user_node_stats_node
        ON user_node_stats(node_id)
        """,
    ),
    4: (
        """
        CREATE TABLE documents (
            id TEXT PRIMARY KEY NOT NULL,
            source_path TEXT NOT NULL UNIQUE,
            content_hash TEXT NOT NULL,
            title TEXT NOT NULL CHECK (length(trim(title)) > 0),
            author TEXT,
            content_type TEXT NOT NULL
                CHECK (content_type IN ('theory', 'exercise', 'paper')),
            complexity TEXT NOT NULL
                CHECK (complexity IN ('beginner', 'intermediate', 'advanced')),
            published_at TEXT,
            page_count INTEGER NOT NULL DEFAULT 0 CHECK (page_count >= 0),
            file_size INTEGER NOT NULL CHECK (file_size >= 0),
            modified_at TEXT NOT NULL,
            ingested_at TEXT NOT NULL
        )
        """,
        """
        CREATE UNIQUE INDEX idx_documents_content_hash
        ON documents(content_hash)
        """,
        """
        CREATE TABLE document_chunks (
            id TEXT PRIMARY KEY NOT NULL,
            document_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
            page_number INTEGER CHECK (page_number IS NULL OR page_number >= 1),
            section TEXT NOT NULL DEFAULT '',
            chunk_type TEXT NOT NULL
                CHECK (chunk_type IN ('theory', 'exercise', 'paper')),
            text_encrypted BLOB NOT NULL,
            token_count INTEGER NOT NULL CHECK (token_count > 0),
            graph_node_id TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (document_id) REFERENCES documents(id)
                ON UPDATE CASCADE ON DELETE CASCADE,
            FOREIGN KEY (graph_node_id) REFERENCES graph_nodes(id)
                ON UPDATE CASCADE ON DELETE SET NULL,
            UNIQUE (document_id, ordinal)
        )
        """,
        """
        CREATE INDEX idx_chunks_document_type
        ON document_chunks(document_id, chunk_type, ordinal)
        """,
        """
        CREATE TABLE chunk_embeddings (
            chunk_id TEXT PRIMARY KEY NOT NULL,
            model_id TEXT NOT NULL,
            dimensions INTEGER NOT NULL CHECK (dimensions > 0),
            vector_encrypted BLOB NOT NULL,
            norm REAL NOT NULL CHECK (norm > 0.0),
            created_at TEXT NOT NULL,
            FOREIGN KEY (chunk_id) REFERENCES document_chunks(id)
                ON UPDATE CASCADE ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE theory_cards (
            id TEXT PRIMARY KEY NOT NULL,
            chunk_id TEXT NOT NULL UNIQUE,
            graph_node_id TEXT,
            title TEXT NOT NULL CHECK (length(trim(title)) > 0),
            body_encrypted BLOB NOT NULL,
            code_example_encrypted BLOB,
            image_path TEXT,
            complexity TEXT NOT NULL
                CHECK (complexity IN ('beginner', 'intermediate', 'advanced')),
            created_at TEXT NOT NULL,
            FOREIGN KEY (chunk_id) REFERENCES document_chunks(id)
                ON UPDATE CASCADE ON DELETE CASCADE,
            FOREIGN KEY (graph_node_id) REFERENCES graph_nodes(id)
                ON UPDATE CASCADE ON DELETE SET NULL
        )
        """,
        """
        CREATE TABLE exercise_sources (
            exercise_id TEXT PRIMARY KEY NOT NULL,
            chunk_id TEXT NOT NULL UNIQUE,
            FOREIGN KEY (exercise_id) REFERENCES exercises(id)
                ON UPDATE CASCADE ON DELETE CASCADE,
            FOREIGN KEY (chunk_id) REFERENCES document_chunks(id)
                ON UPDATE CASCADE ON DELETE CASCADE
        ) WITHOUT ROWID
        """,
        """
        CREATE TABLE ingestion_runs (
            id TEXT PRIMARY KEY NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'partial', 'failed')),
            discovered_files INTEGER NOT NULL DEFAULT 0 CHECK (discovered_files >= 0),
            indexed_documents INTEGER NOT NULL DEFAULT 0 CHECK (indexed_documents >= 0),
            skipped_documents INTEGER NOT NULL DEFAULT 0 CHECK (skipped_documents >= 0),
            failed_documents INTEGER NOT NULL DEFAULT 0 CHECK (failed_documents >= 0),
            chunks INTEGER NOT NULL DEFAULT 0 CHECK (chunks >= 0),
            theory_cards INTEGER NOT NULL DEFAULT 0 CHECK (theory_cards >= 0),
            exercises INTEGER NOT NULL DEFAULT 0 CHECK (exercises >= 0),
            errors_encrypted BLOB
        )
        """,
    ),
    5: (
        """
        CREATE TABLE exercise_test_cases (
            id TEXT PRIMARY KEY NOT NULL,
            exercise_id TEXT NOT NULL,
            name TEXT NOT NULL CHECK (length(trim(name)) > 0),
            test_code_encrypted BLOB NOT NULL,
            ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
            FOREIGN KEY (exercise_id) REFERENCES exercises(id)
                ON UPDATE CASCADE ON DELETE CASCADE,
            UNIQUE (exercise_id, ordinal)
        )
        """,
        """
        CREATE TABLE grading_results (
            id TEXT PRIMARY KEY NOT NULL,
            attempt_id TEXT,
            score REAL NOT NULL CHECK (score BETWEEN 0.0 AND 1.0),
            status TEXT NOT NULL
                CHECK (status IN ('passed', 'failed', 'syntax_error', 'rejected', 'error')),
            report_encrypted BLOB NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (attempt_id) REFERENCES attempts(id)
                ON UPDATE CASCADE ON DELETE SET NULL
        )
        """,
        """
        CREATE INDEX idx_grading_results_attempt
        ON grading_results(attempt_id, created_at DESC)
        """,
    ),
    6: (
        """
        CREATE TABLE knowledge_taxonomy (
            chunk_id TEXT PRIMARY KEY NOT NULL,
            technologies_json TEXT NOT NULL DEFAULT '[]'
                CHECK (json_valid(technologies_json)),
            themes_json TEXT NOT NULL DEFAULT '[]'
                CHECK (json_valid(themes_json)),
            updated_at TEXT NOT NULL,
            FOREIGN KEY (chunk_id) REFERENCES document_chunks(id)
                ON UPDATE CASCADE ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE knowledge_clusters (
            id TEXT PRIMARY KEY NOT NULL,
            label TEXT NOT NULL CHECK (length(trim(label)) > 0),
            model_id TEXT NOT NULL,
            member_count INTEGER NOT NULL CHECK (member_count >= 0),
            centroid_encrypted BLOB,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL CHECK (updated_at >= created_at)
        )
        """,
        """
        CREATE TABLE knowledge_cluster_members (
            chunk_id TEXT PRIMARY KEY NOT NULL,
            cluster_id TEXT NOT NULL,
            probability REAL NOT NULL DEFAULT 1.0
                CHECK (probability BETWEEN 0.0 AND 1.0),
            FOREIGN KEY (chunk_id) REFERENCES document_chunks(id)
                ON UPDATE CASCADE ON DELETE CASCADE,
            FOREIGN KEY (cluster_id) REFERENCES knowledge_clusters(id)
                ON UPDATE CASCADE ON DELETE CASCADE
        )
        """,
        """
        CREATE INDEX idx_cluster_members_cluster
        ON knowledge_cluster_members(cluster_id, chunk_id)
        """,
    ),
    7: (
        """
        CREATE TABLE milestone_definitions (
            id TEXT PRIMARY KEY NOT NULL,
            technology TEXT NOT NULL,
            theme TEXT NOT NULL,
            rank_from TEXT NOT NULL,
            rank_to TEXT NOT NULL,
            required_distinct_passes INTEGER NOT NULL
                CHECK (required_distinct_passes > 0),
            position INTEGER NOT NULL CHECK (position >= 0),
            UNIQUE (technology, theme, rank_to)
        )
        """,
        """
        CREATE TABLE user_milestones (
            user_id TEXT NOT NULL,
            milestone_id TEXT NOT NULL,
            completed_exercises_json TEXT NOT NULL DEFAULT '[]'
                CHECK (json_valid(completed_exercises_json)),
            completed_at TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, milestone_id),
            FOREIGN KEY (user_id) REFERENCES users(id)
                ON UPDATE CASCADE ON DELETE CASCADE,
            FOREIGN KEY (milestone_id) REFERENCES milestone_definitions(id)
                ON UPDATE CASCADE ON DELETE CASCADE
        ) WITHOUT ROWID
        """,
        """
        CREATE TABLE local_projects (
            id TEXT PRIMARY KEY NOT NULL,
            user_id TEXT NOT NULL,
            name_encrypted BLOB NOT NULL,
            technology TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL CHECK (updated_at >= created_at),
            FOREIGN KEY (user_id) REFERENCES users(id)
                ON UPDATE CASCADE ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE project_files (
            id TEXT PRIMARY KEY NOT NULL,
            project_id TEXT NOT NULL,
            relative_path TEXT NOT NULL,
            content_encrypted BLOB NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES local_projects(id)
                ON UPDATE CASCADE ON DELETE CASCADE,
            UNIQUE (project_id, relative_path)
        )
        """,
        """
        CREATE TABLE generated_exercises (
            id TEXT PRIMARY KEY NOT NULL,
            user_id TEXT NOT NULL,
            base_exercise_id TEXT NOT NULL,
            variation INTEGER NOT NULL CHECK (variation >= 1),
            payload_encrypted BLOB NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
                ON UPDATE CASCADE ON DELETE CASCADE,
            FOREIGN KEY (base_exercise_id) REFERENCES exercises(id)
                ON UPDATE CASCADE ON DELETE CASCADE,
            UNIQUE (user_id, base_exercise_id, variation)
        )
        """,
    ),
    8: (
        """
        CREATE TABLE focus_sessions (
            id TEXT PRIMARY KEY NOT NULL,
            user_id TEXT NOT NULL,
            minutes INTEGER NOT NULL CHECK (minutes IN (25, 50, 90, 120)),
            elapsed_seconds INTEGER NOT NULL DEFAULT 0 CHECK (elapsed_seconds >= 0),
            status TEXT NOT NULL CHECK (status IN ('running', 'paused', 'completed', 'cancelled')),
            started_at TEXT NOT NULL,
            ended_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
                ON UPDATE CASCADE ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE attempt_justifications (
            attempt_id TEXT PRIMARY KEY NOT NULL,
            justification_encrypted BLOB NOT NULL,
            paste_ratio REAL NOT NULL CHECK (paste_ratio BETWEEN 0.0 AND 1.0),
            created_at TEXT NOT NULL,
            FOREIGN KEY (attempt_id) REFERENCES attempts(id)
                ON UPDATE CASCADE ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE editor_sessions (
            id TEXT PRIMARY KEY NOT NULL,
            user_id TEXT NOT NULL,
            exercise_id TEXT,
            typed_characters INTEGER NOT NULL DEFAULT 0 CHECK (typed_characters >= 0),
            pasted_characters INTEGER NOT NULL DEFAULT 0 CHECK (pasted_characters >= 0),
            deleted_characters INTEGER NOT NULL DEFAULT 0 CHECK (deleted_characters >= 0),
            started_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
                ON UPDATE CASCADE ON DELETE CASCADE,
            FOREIGN KEY (exercise_id) REFERENCES exercises(id)
                ON UPDATE CASCADE ON DELETE SET NULL
        )
        """,
    ),
    9: (
        """
        CREATE TABLE learning_tracks (
            id TEXT PRIMARY KEY NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            technology TEXT NOT NULL,
            position INTEGER NOT NULL CHECK(position >= 0)
        ) STRICT
        """,
        """
        CREATE TABLE learning_chapters (
            id TEXT PRIMARY KEY NOT NULL,
            track_id TEXT NOT NULL,
            graph_node_id TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            objective TEXT NOT NULL,
            position INTEGER NOT NULL CHECK(position >= 0),
            FOREIGN KEY(track_id) REFERENCES learning_tracks(id) ON DELETE CASCADE,
            FOREIGN KEY(graph_node_id) REFERENCES graph_nodes(id) ON DELETE RESTRICT
        ) STRICT
        """,
        """
        CREATE TABLE learning_units (
            id TEXT PRIMARY KEY NOT NULL,
            chapter_id TEXT NOT NULL,
            exercise_id TEXT,
            kind TEXT NOT NULL CHECK(kind IN ('practice','theory','quiz','hybrid','project','reference')),
            title TEXT NOT NULL,
            body_encrypted BLOB NOT NULL,
            example_encrypted BLOB,
            position INTEGER NOT NULL CHECK(position >= 0),
            practice_gate INTEGER NOT NULL DEFAULT 0 CHECK(practice_gate IN (0,1)),
            FOREIGN KEY(chapter_id) REFERENCES learning_chapters(id) ON DELETE CASCADE,
            FOREIGN KEY(exercise_id) REFERENCES exercises(id) ON DELETE SET NULL
        ) STRICT
        """,
        """
        CREATE TABLE learning_unit_dependencies (
            unit_id TEXT NOT NULL,
            prerequisite_unit_id TEXT NOT NULL,
            PRIMARY KEY(unit_id, prerequisite_unit_id),
            FOREIGN KEY(unit_id) REFERENCES learning_units(id) ON DELETE CASCADE,
            FOREIGN KEY(prerequisite_unit_id) REFERENCES learning_units(id) ON DELETE CASCADE,
            CHECK(unit_id <> prerequisite_unit_id)
        ) STRICT
        """,
        """
        CREATE TABLE IF NOT EXISTS learning_unit_progress (
            user_id TEXT NOT NULL,
            unit_id TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            PRIMARY KEY(user_id, unit_id),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(unit_id) REFERENCES learning_units(id) ON DELETE CASCADE
        ) STRICT
        """,
        """
        CREATE TABLE assessment_items (
            id TEXT PRIMARY KEY NOT NULL,
            unit_id TEXT NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('theory','practical','hybrid')),
            prompt_encrypted BLOB NOT NULL,
            answer_encrypted BLOB NOT NULL,
            explanation_encrypted BLOB NOT NULL,
            difficulty REAL NOT NULL CHECK(difficulty BETWEEN -3.0 AND 3.0),
            FOREIGN KEY(unit_id) REFERENCES learning_units(id) ON DELETE CASCADE
        ) STRICT
        """,
        """
        CREATE TABLE assessment_options (
            item_id TEXT NOT NULL,
            option_id TEXT NOT NULL,
            text_encrypted BLOB NOT NULL,
            position INTEGER NOT NULL CHECK(position >= 0),
            PRIMARY KEY(item_id, option_id),
            FOREIGN KEY(item_id) REFERENCES assessment_items(id) ON DELETE CASCADE
        ) STRICT
        """,
        """
        CREATE TABLE assessment_attempts (
            id TEXT PRIMARY KEY NOT NULL,
            user_id TEXT NOT NULL,
            item_id TEXT NOT NULL,
            answer_encrypted BLOB NOT NULL,
            passed INTEGER NOT NULL CHECK(passed IN (0,1)),
            score REAL NOT NULL CHECK(score BETWEEN 0.0 AND 1.0),
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(item_id) REFERENCES assessment_items(id) ON DELETE CASCADE
        ) STRICT
        """,
        """
        CREATE TABLE glossary_entries (
            id TEXT PRIMARY KEY NOT NULL,
            term TEXT NOT NULL,
            normalized_term TEXT NOT NULL UNIQUE,
            technology TEXT NOT NULL,
            definition_encrypted BLOB NOT NULL,
            signature_encrypted BLOB,
            example_encrypted BLOB,
            related_terms_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(related_terms_json))
        ) STRICT
        """,
        """
        CREATE TABLE bibliography_links (
            source_chunk_id TEXT NOT NULL,
            target_chunk_id TEXT NOT NULL,
            relation TEXT NOT NULL CHECK(relation IN ('same-cluster','same-concept','prerequisite','related')),
            weight REAL NOT NULL CHECK(weight BETWEEN 0.0 AND 1.0),
            PRIMARY KEY(source_chunk_id, target_chunk_id, relation),
            FOREIGN KEY(source_chunk_id) REFERENCES document_chunks(id) ON DELETE CASCADE,
            FOREIGN KEY(target_chunk_id) REFERENCES document_chunks(id) ON DELETE CASCADE,
            CHECK(source_chunk_id <> target_chunk_id)
        ) STRICT
        """,
        "CREATE INDEX learning_units_chapter_position ON learning_units(chapter_id, position)",
        "CREATE INDEX assessment_items_unit ON assessment_items(unit_id, kind)",
        "CREATE INDEX assessment_attempts_user_item ON assessment_attempts(user_id, item_id, created_at)",
        "CREATE INDEX glossary_entries_technology_term ON glossary_entries(technology, normalized_term)",
        "CREATE INDEX bibliography_links_target ON bibliography_links(target_chunk_id, relation)",
    ),
    10: (
        """
        CREATE TABLE IF NOT EXISTS learning_unit_progress (
            user_id TEXT NOT NULL,
            unit_id TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            PRIMARY KEY(user_id, unit_id),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(unit_id) REFERENCES learning_units(id) ON DELETE CASCADE
        ) STRICT
        """,
    ),
    11: (
        """
        CREATE TABLE study_days (
            user_id TEXT NOT NULL,
            study_date TEXT NOT NULL,
            PRIMARY KEY(user_id, study_date),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        ) STRICT
        """,
        """
        CREATE TABLE onboarding_state (
            user_id TEXT PRIMARY KEY NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('pending','completed')),
            assessed_level TEXT NOT NULL CHECK(assessed_level IN ('unassessed','initiate','adept','proficient')),
            attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
            completed_at TEXT,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        ) STRICT
        """,
        """
        CREATE TABLE local_achievements (
            user_id TEXT NOT NULL,
            code TEXT NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('badge','certificate')),
            title TEXT NOT NULL,
            evidence_json TEXT NOT NULL CHECK(json_valid(evidence_json)),
            earned_at TEXT NOT NULL,
            PRIMARY KEY(user_id, code),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        ) STRICT
        """,
        """
        CREATE TABLE card_review_state (
            user_id TEXT NOT NULL,
            card_id TEXT NOT NULL,
            mastery REAL NOT NULL DEFAULT 0 CHECK(mastery BETWEEN 0 AND 1),
            successful_reviews INTEGER NOT NULL DEFAULT 0 CHECK(successful_reviews >= 0),
            next_review_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(user_id, card_id),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(card_id) REFERENCES theory_cards(id) ON DELETE CASCADE
        ) STRICT
        """,
        "CREATE INDEX card_review_due ON card_review_state(user_id, next_review_at)",
    ),
    12: (
        """
        CREATE TABLE knowledge_areas (
            id TEXT PRIMARY KEY NOT NULL,
            parent_id TEXT,
            slug TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL CHECK(length(trim(title)) > 0),
            description TEXT NOT NULL,
            depth INTEGER NOT NULL CHECK(depth BETWEEN 0 AND 4),
            position INTEGER NOT NULL CHECK(position >= 0),
            icon TEXT NOT NULL DEFAULT '',
            recommended_order INTEGER NOT NULL CHECK(recommended_order >= 0),
            FOREIGN KEY(parent_id) REFERENCES knowledge_areas(id) ON DELETE CASCADE
        ) STRICT
        """,
        """
        CREATE TABLE knowledge_area_chunks (
            area_id TEXT NOT NULL,
            chunk_id TEXT NOT NULL,
            relevance REAL NOT NULL CHECK(relevance BETWEEN 0.0 AND 1.0),
            reason TEXT NOT NULL,
            PRIMARY KEY(area_id, chunk_id),
            FOREIGN KEY(area_id) REFERENCES knowledge_areas(id) ON DELETE CASCADE,
            FOREIGN KEY(chunk_id) REFERENCES document_chunks(id) ON DELETE CASCADE
        ) STRICT
        """,
        """
        CREATE TABLE curated_sources (
            id TEXT PRIMARY KEY NOT NULL,
            title TEXT NOT NULL,
            authors_json TEXT NOT NULL CHECK(json_valid(authors_json)),
            publication_year INTEGER CHECK(publication_year BETWEEN 1900 AND 2200),
            source_type TEXT NOT NULL CHECK(source_type IN ('book','paper','course','documentation','report')),
            canonical_url TEXT NOT NULL,
            doi TEXT,
            overview TEXT NOT NULL,
            why_it_matters TEXT NOT NULL,
            access_note TEXT NOT NULL,
            license_note TEXT NOT NULL,
            provenance TEXT NOT NULL
        ) STRICT
        """,
        """
        CREATE TABLE knowledge_area_sources (
            area_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            position INTEGER NOT NULL CHECK(position >= 0),
            PRIMARY KEY(area_id, source_id),
            FOREIGN KEY(area_id) REFERENCES knowledge_areas(id) ON DELETE CASCADE,
            FOREIGN KEY(source_id) REFERENCES curated_sources(id) ON DELETE CASCADE
        ) STRICT
        """,
        """
        CREATE TABLE search_shortcuts (
            id TEXT PRIMARY KEY NOT NULL,
            area_id TEXT NOT NULL,
            label TEXT NOT NULL,
            query TEXT NOT NULL,
            position INTEGER NOT NULL CHECK(position >= 0),
            FOREIGN KEY(area_id) REFERENCES knowledge_areas(id) ON DELETE CASCADE
        ) STRICT
        """,
        """
        CREATE TABLE reading_assistance (
            chunk_id TEXT PRIMARY KEY NOT NULL,
            algorithm_version TEXT NOT NULL,
            summary_encrypted BLOB NOT NULL,
            simplified_encrypted BLOB NOT NULL,
            key_points_encrypted BLOB NOT NULL,
            math_notes_encrypted BLOB NOT NULL,
            generated_at TEXT NOT NULL,
            FOREIGN KEY(chunk_id) REFERENCES document_chunks(id) ON DELETE CASCADE
        ) STRICT
        """,
        "CREATE INDEX knowledge_areas_parent_position ON knowledge_areas(parent_id, position)",
        "CREATE INDEX knowledge_area_chunks_chunk ON knowledge_area_chunks(chunk_id, relevance DESC)",
        "CREATE INDEX knowledge_area_sources_area ON knowledge_area_sources(area_id, position)",
        "CREATE INDEX search_shortcuts_area ON search_shortcuts(area_id, position)",
    ),
    13: (
        """
        CREATE TABLE content_quality_audits (
            document_id TEXT PRIMARY KEY NOT NULL,
            algorithm_version TEXT NOT NULL,
            accepted_chunks INTEGER NOT NULL CHECK(accepted_chunks >= 0),
            quarantined_chunks INTEGER NOT NULL CHECK(quarantined_chunks >= 0),
            boundary_page INTEGER CHECK(boundary_page IS NULL OR boundary_page >= 1),
            reason TEXT NOT NULL,
            audited_at TEXT NOT NULL,
            FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
        ) STRICT
        """,
        """
        CREATE TABLE chunk_quality (
            chunk_id TEXT PRIMARY KEY NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('accepted','quarantined')),
            score REAL NOT NULL CHECK(score BETWEEN 0.0 AND 1.0),
            reason TEXT NOT NULL,
            audited_at TEXT NOT NULL,
            FOREIGN KEY(chunk_id) REFERENCES document_chunks(id) ON DELETE CASCADE
        ) STRICT
        """,
        "CREATE INDEX chunk_quality_status ON chunk_quality(status, chunk_id)",
        """
        CREATE TABLE study_plans (
            user_id TEXT PRIMARY KEY NOT NULL,
            start_date TEXT NOT NULL,
            weekly_hours REAL NOT NULL CHECK(weekly_hours BETWEEN 0.5 AND 168.0),
            assessment_percent INTEGER NOT NULL CHECK(assessment_percent BETWEEN 0 AND 100),
            updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        ) STRICT
        """,
    ),
    14: (
        "ALTER TABLE assessment_attempts ADD COLUMN duration_seconds INTEGER CHECK(duration_seconds IS NULL OR duration_seconds >= 0)",
        "ALTER TABLE assessment_attempts ADD COLUMN mode TEXT NOT NULL DEFAULT 'training' CHECK(mode IN ('training','evaluation'))",
    ),
    15: (
        """
        CREATE TABLE feature_flags (
            name TEXT PRIMARY KEY NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
            source TEXT NOT NULL DEFAULT 'default'
                CHECK(source IN ('default','override','migration')),
            updated_at TEXT NOT NULL
        ) STRICT
        """,
        """
        CREATE TABLE diagnostic_events (
            id TEXT PRIMARY KEY NOT NULL,
            code TEXT NOT NULL CHECK(length(trim(code)) BETWEEN 1 AND 100),
            severity TEXT NOT NULL CHECK(severity IN ('info','warning','error')),
            subsystem TEXT NOT NULL CHECK(length(trim(subsystem)) BETWEEN 1 AND 60),
            message TEXT NOT NULL CHECK(length(trim(message)) BETWEEN 1 AND 240),
            context_encrypted BLOB NOT NULL,
            occurred_at TEXT NOT NULL
        ) STRICT
        """,
        """
        CREATE TABLE baseline_metrics (
            id TEXT PRIMARY KEY NOT NULL,
            name TEXT NOT NULL CHECK(length(trim(name)) BETWEEN 1 AND 100),
            value REAL NOT NULL,
            unit TEXT NOT NULL CHECK(length(trim(unit)) BETWEEN 1 AND 24),
            context_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(context_json)),
            measured_at TEXT NOT NULL
        ) STRICT
        """,
        "CREATE INDEX diagnostic_events_time ON diagnostic_events(occurred_at DESC)",
        "CREATE INDEX diagnostic_events_subsystem ON diagnostic_events(subsystem,severity,occurred_at DESC)",
        "CREATE INDEX baseline_metrics_name_time ON baseline_metrics(name,measured_at DESC)",
    ),
    16: (
        """
        CREATE TABLE learning_evidence (
            id TEXT PRIMARY KEY NOT NULL,
            user_id TEXT NOT NULL,
            node_id TEXT NOT NULL,
            source_key TEXT NOT NULL CHECK(length(trim(source_key)) BETWEEN 1 AND 180),
            evidence_type TEXT NOT NULL
                CHECK(evidence_type IN ('practice','theory','hybrid','review','project')),
            score REAL NOT NULL CHECK(score BETWEEN 0.0 AND 1.0),
            duration_seconds INTEGER CHECK(duration_seconds IS NULL OR duration_seconds BETWEEN 0 AND 86400),
            hint_count INTEGER NOT NULL DEFAULT 0 CHECK(hint_count BETWEEN 0 AND 100),
            paste_ratio REAL NOT NULL DEFAULT 0.0 CHECK(paste_ratio BETWEEN 0.0 AND 1.0),
            context_key TEXT NOT NULL DEFAULT '' CHECK(length(context_key) <= 80),
            occurred_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(node_id) REFERENCES graph_nodes(id) ON DELETE CASCADE,
            UNIQUE(user_id, source_key)
        ) STRICT
        """,
        """
        CREATE TABLE mastery_states (
            user_id TEXT NOT NULL,
            node_id TEXT NOT NULL,
            p_known REAL NOT NULL CHECK(p_known BETWEEN 0.0 AND 1.0),
            retention REAL NOT NULL CHECK(retention BETWEEN 0.0 AND 1.0),
            autonomy REAL NOT NULL CHECK(autonomy BETWEEN 0.0 AND 1.0),
            velocity REAL NOT NULL CHECK(velocity BETWEEN 0.0 AND 1.0),
            confidence REAL NOT NULL CHECK(confidence BETWEEN 0.0 AND 1.0),
            evidence_count INTEGER NOT NULL CHECK(evidence_count >= 0),
            successful_reviews INTEGER NOT NULL CHECK(successful_reviews >= 0),
            last_practiced_at TEXT,
            next_review_at TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(user_id,node_id),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(node_id) REFERENCES graph_nodes(id) ON DELETE CASCADE
        ) WITHOUT ROWID, STRICT
        """,
        """
        CREATE TABLE weekly_plan_items (
            id TEXT PRIMARY KEY NOT NULL,
            user_id TEXT NOT NULL,
            scheduled_for TEXT NOT NULL,
            node_id TEXT NOT NULL,
            title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 160),
            action TEXT NOT NULL CHECK(action IN ('learn','practice','review','assess','project')),
            duration_minutes INTEGER NOT NULL CHECK(duration_minutes BETWEEN 5 AND 180),
            reason_code TEXT NOT NULL CHECK(length(trim(reason_code)) BETWEEN 1 AND 60),
            completed INTEGER NOT NULL DEFAULT 0 CHECK(completed IN (0,1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(node_id) REFERENCES graph_nodes(id) ON DELETE CASCADE,
            UNIQUE(user_id,scheduled_for,node_id,action)
        ) STRICT
        """,
        "CREATE INDEX learning_evidence_user_time ON learning_evidence(user_id,occurred_at DESC)",
        "CREATE INDEX learning_evidence_node_time ON learning_evidence(user_id,node_id,occurred_at DESC)",
        "CREATE INDEX mastery_states_review ON mastery_states(user_id,next_review_at)",
        "CREATE INDEX weekly_plan_user_date ON weekly_plan_items(user_id,scheduled_for,completed)",
    ),
    17: (
        """
        CREATE TABLE learning_paths (
            id TEXT PRIMARY KEY NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 160),
            description TEXT NOT NULL,
            position INTEGER NOT NULL CHECK(position >= 0),
            active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1))
        ) STRICT
        """,
        """
        CREATE TABLE learning_path_courses (
            path_id TEXT NOT NULL,
            track_id TEXT NOT NULL,
            position INTEGER NOT NULL CHECK(position >= 0),
            required INTEGER NOT NULL DEFAULT 1 CHECK(required IN (0,1)),
            PRIMARY KEY(path_id,track_id),
            FOREIGN KEY(path_id) REFERENCES learning_paths(id) ON DELETE CASCADE,
            FOREIGN KEY(track_id) REFERENCES learning_tracks(id) ON DELETE CASCADE
        ) WITHOUT ROWID, STRICT
        """,
        """
        CREATE TABLE course_prerequisites (
            track_id TEXT NOT NULL,
            prerequisite_track_id TEXT NOT NULL,
            minimum_mastery REAL NOT NULL DEFAULT 0.7 CHECK(minimum_mastery BETWEEN 0 AND 1),
            PRIMARY KEY(track_id,prerequisite_track_id),
            CHECK(track_id <> prerequisite_track_id),
            FOREIGN KEY(track_id) REFERENCES learning_tracks(id) ON DELETE CASCADE,
            FOREIGN KEY(prerequisite_track_id) REFERENCES learning_tracks(id) ON DELETE CASCADE
        ) WITHOUT ROWID, STRICT
        """,
        """
        CREATE TABLE curriculum_objectives (
            id TEXT PRIMARY KEY NOT NULL,
            code TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL CHECK(length(trim(description)) BETWEEN 1 AND 500),
            cognitive_level TEXT NOT NULL
                CHECK(cognitive_level IN ('remember','understand','apply','analyze','evaluate','create'))
        ) STRICT
        """,
        """
        CREATE TABLE unit_objectives (
            unit_id TEXT NOT NULL,
            objective_id TEXT NOT NULL,
            required INTEGER NOT NULL DEFAULT 1 CHECK(required IN (0,1)),
            PRIMARY KEY(unit_id,objective_id),
            FOREIGN KEY(unit_id) REFERENCES learning_units(id) ON DELETE CASCADE,
            FOREIGN KEY(objective_id) REFERENCES curriculum_objectives(id) ON DELETE CASCADE
        ) WITHOUT ROWID, STRICT
        """,
        """
        CREATE TABLE curriculum_releases (
            version TEXT PRIMARY KEY NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('draft','validated','active','retired')),
            catalog_checksum TEXT NOT NULL CHECK(length(catalog_checksum)=64),
            track_count INTEGER NOT NULL CHECK(track_count >= 0),
            unit_count INTEGER NOT NULL CHECK(unit_count >= 0),
            activated_at TEXT NOT NULL
        ) STRICT
        """,
        "CREATE INDEX learning_path_courses_track ON learning_path_courses(track_id)",
        "CREATE INDEX course_prerequisites_parent ON course_prerequisites(prerequisite_track_id)",
        "CREATE INDEX unit_objectives_objective ON unit_objectives(objective_id)",
    ),
    18: (
        "ALTER TABLE documents ADD COLUMN lifecycle TEXT NOT NULL DEFAULT 'active' CHECK(lifecycle IN ('staging','active','retired','quarantined'))",
        """
        CREATE TABLE content_source_adapters (
            id TEXT PRIMARY KEY NOT NULL,
            domain TEXT NOT NULL UNIQUE,
            allowed_content_types_json TEXT NOT NULL CHECK(json_valid(allowed_content_types_json)),
            license_policy TEXT NOT NULL,
            robots_policy TEXT NOT NULL,
            parser_version TEXT NOT NULL,
            change_detection TEXT NOT NULL,
            authority_level TEXT NOT NULL CHECK(authority_level IN ('primary','reviewed','preprint','local-private')),
            enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
            updated_at TEXT NOT NULL
        ) STRICT
        """,
        """
        CREATE TABLE document_provenance (
            document_id TEXT PRIMARY KEY NOT NULL,
            source_adapter_id TEXT,
            logical_source TEXT NOT NULL,
            canonical_uri TEXT,
            license_id TEXT NOT NULL,
            rights_status TEXT NOT NULL CHECK(rights_status IN ('local-private','permitted','metadata-only','unknown')),
            content_version TEXT NOT NULL,
            trust_score REAL NOT NULL CHECK(trust_score BETWEEN 0.0 AND 1.0),
            reviewed_at TEXT,
            FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE,
            FOREIGN KEY(source_adapter_id) REFERENCES content_source_adapters(id) ON DELETE RESTRICT
        ) STRICT
        """,
        """
        CREATE TABLE content_revisions (
            id TEXT PRIMARY KEY NOT NULL,
            logical_source TEXT NOT NULL,
            document_id TEXT NOT NULL UNIQUE,
            content_hash TEXT NOT NULL,
            sequence INTEGER NOT NULL CHECK(sequence >= 1),
            status TEXT NOT NULL CHECK(status IN ('staging','active','retired','quarantined')),
            created_at TEXT NOT NULL,
            promoted_at TEXT,
            FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE,
            UNIQUE(logical_source,sequence)
        ) STRICT
        """,
        """
        CREATE TABLE content_validation_results (
            revision_id TEXT NOT NULL,
            check_code TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('passed','failed','warning')),
            detail TEXT NOT NULL CHECK(length(detail) <= 500),
            checked_at TEXT NOT NULL,
            PRIMARY KEY(revision_id,check_code),
            FOREIGN KEY(revision_id) REFERENCES content_revisions(id) ON DELETE CASCADE
        ) WITHOUT ROWID, STRICT
        """,
        """
        CREATE TABLE curriculum_coverage (
            objective_id TEXT PRIMARY KEY NOT NULL,
            theory_evidence_count INTEGER NOT NULL CHECK(theory_evidence_count >= 0),
            card_count INTEGER NOT NULL CHECK(card_count >= 0),
            exercise_count INTEGER NOT NULL CHECK(exercise_count >= 0),
            coverage_score REAL NOT NULL CHECK(coverage_score BETWEEN 0.0 AND 1.0),
            gap_code TEXT NOT NULL CHECK(gap_code IN ('none','needs-theory','needs-practice','needs-both')),
            measured_at TEXT NOT NULL,
            FOREIGN KEY(objective_id) REFERENCES curriculum_objectives(id) ON DELETE CASCADE
        ) STRICT
        """,
        "CREATE UNIQUE INDEX content_revisions_one_active ON content_revisions(logical_source) WHERE status='active'",
        "CREATE INDEX content_revisions_source_sequence ON content_revisions(logical_source,sequence DESC)",
        "CREATE INDEX document_provenance_adapter ON document_provenance(source_adapter_id,rights_status)",
        "CREATE INDEX curriculum_coverage_gap ON curriculum_coverage(gap_code,coverage_score)",
    ),
    19: (
        """
        CREATE TABLE curriculum_objective_evidence (
            objective_id TEXT NOT NULL,
            chunk_id TEXT NOT NULL,
            relevance REAL NOT NULL CHECK(relevance BETWEEN 0.0 AND 1.0),
            reason TEXT NOT NULL CHECK(length(trim(reason)) BETWEEN 1 AND 300),
            algorithm_version TEXT NOT NULL,
            linked_at TEXT NOT NULL,
            PRIMARY KEY(objective_id,chunk_id),
            FOREIGN KEY(objective_id) REFERENCES curriculum_objectives(id) ON DELETE CASCADE,
            FOREIGN KEY(chunk_id) REFERENCES document_chunks(id) ON DELETE CASCADE
        ) WITHOUT ROWID, STRICT
        """,
        """
        CREATE TABLE content_mapping_runs (
            algorithm_version TEXT PRIMARY KEY NOT NULL,
            document_signature TEXT NOT NULL,
            objective_signature TEXT NOT NULL,
            link_count INTEGER NOT NULL CHECK(link_count >= 0),
            completed_at TEXT NOT NULL
        ) STRICT
        """,
        "CREATE INDEX curriculum_evidence_chunk ON curriculum_objective_evidence(chunk_id,relevance DESC)",
    ),
    20: (
        """
        CREATE VIRTUAL TABLE search_fts_public USING fts5(
            chunk_id UNINDEXED,
            title,
            body,
            tokenize='unicode61 remove_diacritics 2 tokenchars ''_+#.-'''
        )
        """,
        """
        CREATE TABLE reading_bookmarks (
            user_id TEXT NOT NULL,
            evidence_id TEXT NOT NULL CHECK(length(trim(evidence_id)) BETWEEN 1 AND 500),
            title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 500),
            source TEXT NOT NULL CHECK(length(trim(source)) BETWEEN 1 AND 2000),
            created_at TEXT NOT NULL,
            PRIMARY KEY(user_id,evidence_id),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        ) WITHOUT ROWID, STRICT
        """,
        """
        CREATE TABLE reading_notes (
            id TEXT PRIMARY KEY NOT NULL,
            user_id TEXT NOT NULL,
            evidence_id TEXT NOT NULL CHECK(length(trim(evidence_id)) BETWEEN 1 AND 500),
            selection_start INTEGER CHECK(selection_start IS NULL OR selection_start >= 0),
            selection_end INTEGER CHECK(selection_end IS NULL OR selection_end >= selection_start),
            note_encrypted BLOB NOT NULL,
            quote_hash TEXT NOT NULL DEFAULT '' CHECK(length(quote_hash) IN (0,64)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL CHECK(updated_at >= created_at),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        ) STRICT
        """,
        """
        CREATE TABLE search_quality_runs (
            id TEXT PRIMARY KEY NOT NULL,
            algorithm_version TEXT NOT NULL,
            query_count INTEGER NOT NULL CHECK(query_count >= 0),
            recall_at_10 REAL NOT NULL CHECK(recall_at_10 BETWEEN 0 AND 1),
            mrr REAL NOT NULL CHECK(mrr BETWEEN 0 AND 1),
            ndcg_at_10 REAL NOT NULL CHECK(ndcg_at_10 BETWEEN 0 AND 1),
            p95_ms REAL NOT NULL CHECK(p95_ms >= 0),
            passed INTEGER NOT NULL CHECK(passed IN (0,1)),
            measured_at TEXT NOT NULL
        ) STRICT
        """,
        "CREATE INDEX reading_notes_user_evidence ON reading_notes(user_id,evidence_id,updated_at DESC)",
        "CREATE INDEX search_quality_runs_time ON search_quality_runs(measured_at DESC)",
    ),
    21: (
        """
        CREATE TABLE blind_search_terms (
            term_digest BLOB NOT NULL,
            chunk_id TEXT NOT NULL,
            body_frequency INTEGER NOT NULL CHECK(body_frequency BETWEEN 0 AND 65535),
            title_frequency INTEGER NOT NULL CHECK(title_frequency BETWEEN 0 AND 65535),
            PRIMARY KEY(term_digest,chunk_id),
            FOREIGN KEY(chunk_id) REFERENCES document_chunks(id) ON DELETE CASCADE
        ) WITHOUT ROWID, STRICT
        """,
        """
        CREATE TABLE embedding_lsh_buckets (
            bucket_digest BLOB NOT NULL,
            band INTEGER NOT NULL CHECK(band BETWEEN 0 AND 15),
            chunk_id TEXT NOT NULL,
            PRIMARY KEY(bucket_digest,band,chunk_id),
            FOREIGN KEY(chunk_id) REFERENCES document_chunks(id) ON DELETE CASCADE
        ) WITHOUT ROWID, STRICT
        """,
        """
        CREATE TABLE private_search_index_state (
            chunk_id TEXT PRIMARY KEY NOT NULL,
            algorithm_version TEXT NOT NULL,
            indexed_at TEXT NOT NULL,
            FOREIGN KEY(chunk_id) REFERENCES document_chunks(id) ON DELETE CASCADE
        ) WITHOUT ROWID, STRICT
        """,
        "CREATE INDEX blind_search_terms_chunk ON blind_search_terms(chunk_id)",
        "CREATE INDEX embedding_lsh_chunk ON embedding_lsh_buckets(chunk_id)",
    ),
    22: (
        """
        CREATE TABLE private_search_filters (
            chunk_id TEXT PRIMARY KEY NOT NULL,
            body_filter BLOB NOT NULL CHECK(length(body_filter)=256),
            title_filter BLOB NOT NULL CHECK(length(title_filter)=256),
            token_count INTEGER NOT NULL CHECK(token_count >= 0),
            algorithm_version TEXT NOT NULL,
            indexed_at TEXT NOT NULL,
            FOREIGN KEY(chunk_id) REFERENCES document_chunks(id) ON DELETE CASCADE
        ) WITHOUT ROWID, STRICT
        """,
        "CREATE INDEX private_search_filters_version ON private_search_filters(algorithm_version)",
    ),
    23: (
        """
        CREATE TABLE private_search_chunk_ordinals (
            ordinal INTEGER PRIMARY KEY NOT NULL CHECK(ordinal >= 0),
            chunk_id TEXT NOT NULL UNIQUE,
            FOREIGN KEY(chunk_id) REFERENCES document_chunks(id) ON DELETE CASCADE
        ) STRICT
        """,
        """
        CREATE TABLE private_search_bit_slices (
            field INTEGER NOT NULL CHECK(field IN (0,1)),
            position INTEGER NOT NULL CHECK(position BETWEEN 0 AND 2047),
            candidates BLOB NOT NULL,
            algorithm_version TEXT NOT NULL,
            PRIMARY KEY(field,position)
        ) WITHOUT ROWID, STRICT
        """,
    ),
    24: (
        """
        CREATE TABLE debug_sessions (
            id TEXT PRIMARY KEY NOT NULL,
            user_id TEXT NOT NULL,
            exercise_id TEXT,
            status TEXT NOT NULL CHECK(status IN (
                'completed','runtime_error','timeout','step_limit','rejected',
                'infrastructure_error','output_limit')),
            breakpoints_encrypted BLOB NOT NULL,
            watches_encrypted BLOB NOT NULL,
            last_step INTEGER NOT NULL DEFAULT 0 CHECK(last_step >= 0),
            coverage_percent REAL NOT NULL CHECK(coverage_percent BETWEEN 0 AND 100),
            duration_ms INTEGER NOT NULL CHECK(duration_ms >= 0),
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(exercise_id) REFERENCES exercises(id) ON DELETE SET NULL
        ) STRICT
        """,
        """
        CREATE TABLE editor_recovery_state (
            user_id TEXT NOT NULL,
            exercise_id TEXT NOT NULL,
            source_encrypted BLOB NOT NULL,
            cursor_index INTEGER NOT NULL DEFAULT 0 CHECK(cursor_index >= 0),
            breakpoints_encrypted BLOB NOT NULL,
            watches_encrypted BLOB NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(user_id,exercise_id),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(exercise_id) REFERENCES exercises(id) ON DELETE CASCADE
        ) WITHOUT ROWID, STRICT
        """,
        """
        CREATE TABLE project_file_versions (
            id TEXT PRIMARY KEY NOT NULL,
            project_id TEXT NOT NULL,
            file_id TEXT NOT NULL,
            version INTEGER NOT NULL CHECK(version >= 1),
            content_encrypted BLOB NOT NULL,
            reason TEXT NOT NULL CHECK(length(reason) BETWEEN 1 AND 80),
            created_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES local_projects(id) ON DELETE CASCADE,
            FOREIGN KEY(file_id) REFERENCES project_files(id) ON DELETE CASCADE,
            UNIQUE(file_id,version)
        ) STRICT
        """,
        """
        CREATE TABLE local_test_runs (
            id TEXT PRIMARY KEY NOT NULL,
            user_id TEXT NOT NULL,
            exercise_id TEXT,
            public_passed INTEGER NOT NULL CHECK(public_passed >= 0),
            public_total INTEGER NOT NULL CHECK(public_total >= public_passed),
            hidden_passed INTEGER NOT NULL CHECK(hidden_passed >= 0),
            hidden_total INTEGER NOT NULL CHECK(hidden_total >= hidden_passed),
            coverage_percent REAL NOT NULL CHECK(coverage_percent BETWEEN 0 AND 100),
            result_encrypted BLOB NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(exercise_id) REFERENCES exercises(id) ON DELETE SET NULL
        ) STRICT
        """,
        "CREATE INDEX debug_sessions_user_time ON debug_sessions(user_id,created_at DESC)",
        "CREATE INDEX project_file_versions_file ON project_file_versions(file_id,version DESC)",
        "CREATE INDEX local_test_runs_user_time ON local_test_runs(user_id,created_at DESC)",
    ),
    25: (
        """
        CREATE TABLE card_feedback_events (
            id TEXT PRIMARY KEY NOT NULL,
            user_id TEXT NOT NULL,
            card_id TEXT NOT NULL,
            feedback TEXT NOT NULL CHECK(feedback IN ('already_knew','useful','confusing','review')),
            mastery_before REAL NOT NULL CHECK(mastery_before BETWEEN 0 AND 1),
            mastery_after REAL NOT NULL CHECK(mastery_after BETWEEN 0 AND 1),
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(card_id) REFERENCES theory_cards(id) ON DELETE CASCADE
        ) STRICT
        """,
        "CREATE INDEX card_feedback_user_time ON card_feedback_events(user_id,created_at DESC)",
        "CREATE INDEX card_feedback_card_time ON card_feedback_events(card_id,created_at DESC)",
    ),
    26: (
        """
        CREATE TABLE tutor_messages (
            id TEXT PRIMARY KEY NOT NULL,
            user_id TEXT NOT NULL,
            strategy TEXT NOT NULL CHECK(strategy IN (
                'explain_differently','socratic','new_example','prerequisite',
                'simplify_math','analyze_error','mini_exercise')),
            question_encrypted BLOB NOT NULL,
            answer_encrypted BLOB NOT NULL,
            evidence_encrypted BLOB NOT NULL,
            confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1),
            declined INTEGER NOT NULL CHECK(declined IN (0,1)),
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        ) STRICT
        """,
        "CREATE INDEX tutor_messages_user_time ON tutor_messages(user_id,created_at DESC)",
    ),
    27: (
        """
        CREATE TABLE guided_project_templates (
            id TEXT PRIMARY KEY NOT NULL,
            track_slug TEXT NOT NULL,
            title TEXT NOT NULL,
            brief TEXT NOT NULL,
            requirements_json TEXT NOT NULL CHECK(json_valid(requirements_json)),
            milestones_json TEXT NOT NULL CHECK(json_valid(milestones_json)),
            rubric_json TEXT NOT NULL CHECK(json_valid(rubric_json)),
            level TEXT NOT NULL CHECK(level IN ('beginner','intermediate','advanced')),
            capstone INTEGER NOT NULL CHECK(capstone IN (0,1)),
            professional_briefing INTEGER NOT NULL CHECK(professional_briefing IN (0,1)),
            created_at TEXT NOT NULL,
            FOREIGN KEY(track_slug) REFERENCES learning_tracks(slug) ON DELETE CASCADE
        ) STRICT
        """,
        """
        CREATE TABLE portfolio_projects (
            project_id TEXT PRIMARY KEY NOT NULL,
            user_id TEXT NOT NULL,
            template_id TEXT NOT NULL,
            work_mode TEXT NOT NULL CHECK(work_mode IN ('guided','autonomous')),
            status TEXT NOT NULL CHECK(status IN ('active','submitted','passed','revision')),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES local_projects(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY(template_id) REFERENCES guided_project_templates(id) ON DELETE RESTRICT
        ) STRICT
        """,
        """
        CREATE TABLE project_evaluations (
            id TEXT PRIMARY KEY NOT NULL,
            project_id TEXT NOT NULL,
            score REAL NOT NULL CHECK(score BETWEEN 0 AND 1),
            passed INTEGER NOT NULL CHECK(passed IN (0,1)),
            result_encrypted BLOB NOT NULL,
            evaluated_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES portfolio_projects(project_id) ON DELETE CASCADE
        ) STRICT
        """,
        """
        CREATE TABLE project_milestone_state (
            project_id TEXT NOT NULL,
            ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
            completed INTEGER NOT NULL CHECK(completed IN (0,1)),
            completed_at TEXT,
            PRIMARY KEY(project_id,ordinal),
            FOREIGN KEY(project_id) REFERENCES portfolio_projects(project_id) ON DELETE CASCADE
        ) WITHOUT ROWID, STRICT
        """,
        "CREATE INDEX portfolio_user_status ON portfolio_projects(user_id,status,updated_at DESC)",
        "CREATE INDEX project_evaluations_project ON project_evaluations(project_id,evaluated_at DESC)",
    ),
    28: (
        """
        CREATE TABLE snippet_analyses (
            id TEXT PRIMARY KEY NOT NULL,
            user_id TEXT NOT NULL,
            action TEXT NOT NULL CHECK(action IN (
                'explain','complete','to_algorithm','to_python','find_problems',
                'create_tests','visualize','link_course')),
            original_encrypted BLOB NOT NULL,
            result_encrypted BLOB NOT NULL,
            confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1),
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        ) STRICT
        """,
        "CREATE INDEX snippet_analyses_user_time ON snippet_analyses(user_id,created_at DESC)",
    ),
    29: (
        """
        CREATE TABLE game_sessions (
            id TEXT PRIMARY KEY NOT NULL,
            user_id TEXT NOT NULL,
            game TEXT NOT NULL CHECK(game IN ('sudoku','minesweeper')),
            difficulty TEXT NOT NULL CHECK(difficulty IN ('Fácil','Médio','Difícil')),
            seed INTEGER NOT NULL,
            state_encrypted BLOB NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('active','won','lost','abandoned')),
            elapsed_seconds INTEGER NOT NULL CHECK(elapsed_seconds >= 0),
            daily_key TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(user_id,daily_key)
        ) STRICT
        """,
        """
        CREATE TABLE game_statistics (
            user_id TEXT NOT NULL,
            game TEXT NOT NULL CHECK(game IN ('sudoku','minesweeper')),
            difficulty TEXT NOT NULL CHECK(difficulty IN ('Fácil','Médio','Difícil')),
            plays INTEGER NOT NULL CHECK(plays >= 0),
            wins INTEGER NOT NULL CHECK(wins BETWEEN 0 AND plays),
            best_seconds INTEGER CHECK(best_seconds IS NULL OR best_seconds >= 0),
            updated_at TEXT NOT NULL,
            PRIMARY KEY(user_id,game,difficulty),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        ) WITHOUT ROWID, STRICT
        """,
        "CREATE INDEX game_sessions_user_status ON game_sessions(user_id,status,updated_at DESC)",
    ),
    30: (
        "ALTER TABLE learning_evidence ADD COLUMN active_seconds INTEGER CHECK(active_seconds IS NULL OR active_seconds BETWEEN 0 AND 86400)",
        "ALTER TABLE learning_evidence ADD COLUMN error_category TEXT NOT NULL DEFAULT 'none' CHECK(error_category IN ('none','conceptual','syntax','runtime','distraction'))",
        "ALTER TABLE learning_evidence ADD COLUMN transfer_score REAL CHECK(transfer_score IS NULL OR transfer_score BETWEEN 0.0 AND 1.0)",
        "ALTER TABLE learning_evidence ADD COLUMN project_quality REAL CHECK(project_quality IS NULL OR project_quality BETWEEN 0.0 AND 1.0)",
        "ALTER TABLE learning_evidence ADD COLUMN item_difficulty REAL NOT NULL DEFAULT 0.0 CHECK(item_difficulty BETWEEN -4.0 AND 4.0)",
        "ALTER TABLE learning_evidence ADD COLUMN item_discrimination REAL NOT NULL DEFAULT 1.0 CHECK(item_discrimination BETWEEN 0.25 AND 3.0)",
        "ALTER TABLE learning_evidence ADD COLUMN response_confidence REAL NOT NULL DEFAULT 0.5 CHECK(response_confidence BETWEEN 0.0 AND 1.0)",
        "ALTER TABLE mastery_states ADD COLUMN irt_ability REAL NOT NULL DEFAULT -1.0 CHECK(irt_ability BETWEEN -4.0 AND 4.0)",
        "ALTER TABLE mastery_states ADD COLUMN irt_information REAL NOT NULL DEFAULT 0.0 CHECK(irt_information >= 0.0)",
        "CREATE INDEX learning_evidence_error ON learning_evidence(user_id,error_category,occurred_at DESC)",
    ),
    31: (
        """
        CREATE TABLE glossary_aliases (
            entry_id TEXT NOT NULL,
            alias TEXT NOT NULL,
            normalized_alias TEXT NOT NULL,
            locale TEXT NOT NULL DEFAULT 'und',
            PRIMARY KEY(entry_id, normalized_alias),
            FOREIGN KEY(entry_id) REFERENCES glossary_entries(id) ON DELETE CASCADE
        ) WITHOUT ROWID, STRICT
        """,
        "CREATE INDEX glossary_aliases_lookup ON glossary_aliases(normalized_alias,entry_id)",
    ),
    32: (
        """
        CREATE TABLE exercise_source_links (
            exercise_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            rationale TEXT NOT NULL CHECK(length(trim(rationale)) BETWEEN 1 AND 500),
            PRIMARY KEY(exercise_id,source_id),
            FOREIGN KEY(exercise_id) REFERENCES exercises(id) ON DELETE CASCADE,
            FOREIGN KEY(source_id) REFERENCES curated_sources(id) ON DELETE CASCADE
        ) WITHOUT ROWID, STRICT
        """,
        "CREATE INDEX exercise_source_links_source ON exercise_source_links(source_id,exercise_id)",
    ),
    33: (
        """
        CREATE TABLE glossary_source_links (
            entry_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            position INTEGER NOT NULL CHECK(position >= 0),
            rationale TEXT NOT NULL CHECK(length(trim(rationale)) BETWEEN 1 AND 500),
            PRIMARY KEY(entry_id,source_id),
            FOREIGN KEY(entry_id) REFERENCES glossary_entries(id) ON DELETE CASCADE,
            FOREIGN KEY(source_id) REFERENCES curated_sources(id) ON DELETE CASCADE
        ) WITHOUT ROWID, STRICT
        """,
        "CREATE INDEX glossary_source_links_source ON glossary_source_links(source_id,entry_id)",
    ),
}
