"""Database schema creation and migration management."""

import sqlite3
from intelligence_os.storage.db import Database
from intelligence_os.core.logger import logger


MIGRATIONS = [
    (
        1,
        "initial_schema",
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
        );

        CREATE TABLE IF NOT EXISTS discoveries (
            id TEXT PRIMARY KEY,
            source_url TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_tier INTEGER NOT NULL DEFAULT 1,
            discovery_timestamp TEXT NOT NULL,
            raw_content TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            author TEXT NOT NULL DEFAULT '',
            code_demo_indicators TEXT NOT NULL DEFAULT '[]',
            freshness_score REAL NOT NULL DEFAULT 1.0,
            novelty_score REAL NOT NULL DEFAULT 0.0,
            utility_score REAL NOT NULL DEFAULT 0.0,
            evidence_score REAL NOT NULL DEFAULT 0.0,
            content_potential REAL NOT NULL DEFAULT 0.0,
            status TEXT NOT NULL DEFAULT 'RAW_INGESTED',
            content_angle TEXT NOT NULL DEFAULT '',
            verification_notes TEXT NOT NULL DEFAULT '',
            linked_discoveries TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
        );

        CREATE INDEX IF NOT EXISTS idx_discoveries_status ON discoveries(status);
        CREATE INDEX IF NOT EXISTS idx_discoveries_potential ON discoveries(content_potential);
        CREATE INDEX IF NOT EXISTS idx_discoveries_created_at ON discoveries(created_at);

        CREATE TABLE IF NOT EXISTS content_drafts (
            id TEXT PRIMARY KEY,
            discovery_id TEXT NOT NULL REFERENCES discoveries(id) ON DELETE CASCADE,
            research_core TEXT NOT NULL,
            generated_copy TEXT NOT NULL,
            platform TEXT NOT NULL,
            format TEXT NOT NULL,
            visual_asset_path TEXT,
            review_score REAL NOT NULL DEFAULT 0.0,
            review_feedback TEXT NOT NULL DEFAULT '',
            generation_version INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'DRAFTED',
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
        );

        CREATE INDEX IF NOT EXISTS idx_content_drafts_discovery ON content_drafts(discovery_id);
        CREATE INDEX IF NOT EXISTS idx_content_drafts_status ON content_drafts(status);

        CREATE TABLE IF NOT EXISTS publishing_queue (
            id TEXT PRIMARY KEY,
            content_id TEXT NOT NULL REFERENCES content_drafts(id) ON DELETE CASCADE,
            platform TEXT NOT NULL,
            publish_state TEXT NOT NULL DEFAULT 'PENDING',
            platform_post_id TEXT,
            scheduled_time TEXT,
            publish_timestamp TEXT,
            retry_count INTEGER NOT NULL DEFAULT 0,
            max_retries INTEGER NOT NULL DEFAULT 3,
            error_message TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
        );

        CREATE INDEX IF NOT EXISTS idx_publishing_queue_state ON publishing_queue(publish_state);

        CREATE TABLE IF NOT EXISTS analytics (
            id TEXT PRIMARY KEY,
            content_id TEXT NOT NULL REFERENCES content_drafts(id) ON DELETE CASCADE,
            platform_post_id TEXT NOT NULL,
            platform TEXT NOT NULL,
            topic TEXT NOT NULL DEFAULT '',
            angle TEXT NOT NULL DEFAULT '',
            format TEXT NOT NULL DEFAULT '',
            impressions INTEGER NOT NULL DEFAULT 0,
            likes INTEGER NOT NULL DEFAULT 0,
            comments INTEGER NOT NULL DEFAULT 0,
            shares INTEGER NOT NULL DEFAULT 0,
            clicks INTEGER NOT NULL DEFAULT 0,
            collection_timestamp TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
        );

        CREATE INDEX IF NOT EXISTS idx_analytics_platform ON analytics(platform);
        """
    )
]


def run_migrations(db: Database) -> int:
    """Apply all pending migrations to the SQLite database. Returns count of applied migrations."""
    applied_count = 0
    with db.session() as conn:
        # Ensure schema_migrations table exists
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
            );
            """
        )
        cursor = conn.execute("SELECT version FROM schema_migrations ORDER BY version ASC;")
        applied_versions = {row[0] for row in cursor.fetchall()}

        for version, name, sql in MIGRATIONS:
            if version not in applied_versions:
                logger.info(f"Applying database migration v{version}: {name}")
                conn.executescript(sql)
                conn.execute(
                    "INSERT INTO schema_migrations (version, name) VALUES (?, ?);",
                    (version, name),
                )
                applied_count += 1

    return applied_count
