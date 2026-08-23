"""Typed CRUD repositories for database access."""

import json
from datetime import datetime, timezone
from typing import Any
from intelligence_os.storage.db import Database
from intelligence_os.storage.models import (
    DiscoveryRecord,
    ContentDraftRecord,
    PublishingQueueRecord,
    AnalyticsRecord,
    utc_now_iso,
)


class DiscoveryRepository:
    """Repository for managing discoveries in SQLite."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def insert(self, record: DiscoveryRecord) -> None:
        """Insert a new discovery record."""
        with self.db.session() as conn:
            conn.execute(
                """
                INSERT INTO discoveries (
                    id, source_url, title, source_type, source_tier, discovery_timestamp,
                    raw_content, summary, author, code_demo_indicators,
                    freshness_score, novelty_score, utility_score, evidence_score, content_potential,
                    status, content_angle, verification_notes, linked_discoveries,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    record.id,
                    record.source_url,
                    record.title,
                    record.source_type,
                    record.source_tier,
                    record.discovery_timestamp,
                    record.raw_content,
                    record.summary,
                    record.author,
                    json.dumps(record.code_demo_indicators),
                    record.freshness_score,
                    record.novelty_score,
                    record.utility_score,
                    record.evidence_score,
                    record.content_potential,
                    record.status,
                    record.content_angle,
                    record.verification_notes,
                    json.dumps(record.linked_discoveries),
                    record.created_at,
                    record.updated_at,
                ),
            )

    def get_by_id(self, discovery_id: str) -> DiscoveryRecord | None:
        """Retrieve discovery by unique ID."""
        with self.db.session() as conn:
            cursor = conn.execute("SELECT * FROM discoveries WHERE id = ?;", (discovery_id,))
            row = cursor.fetchone()
            return self._row_to_model(row) if row else None

    def get_by_url(self, source_url: str) -> DiscoveryRecord | None:
        """Retrieve discovery by unique source URL."""
        with self.db.session() as conn:
            cursor = conn.execute("SELECT * FROM discoveries WHERE source_url = ?;", (source_url,))
            row = cursor.fetchone()
            return self._row_to_model(row) if row else None

    def list_by_status(self, status: str, limit: int = 50) -> list[DiscoveryRecord]:
        """List discoveries matching a status code."""
        with self.db.session() as conn:
            cursor = conn.execute(
                "SELECT * FROM discoveries WHERE status = ? ORDER BY content_potential DESC, created_at DESC LIMIT ?;",
                (status, limit),
            )
            return [self._row_to_model(row) for row in cursor.fetchall()]

    def list_recent(self, limit: int = 50) -> list[DiscoveryRecord]:
        """List most recent discoveries."""
        with self.db.session() as conn:
            cursor = conn.execute(
                "SELECT * FROM discoveries ORDER BY created_at DESC LIMIT ?;",
                (limit,),
            )
            return [self._row_to_model(row) for row in cursor.fetchall()]

    def update_scores_and_status(
        self,
        discovery_id: str,
        novelty: float,
        utility: float,
        evidence: float,
        potential: float,
        status: str,
        content_angle: str = "",
        verification_notes: str = "",
    ) -> None:
        """Update scoring metrics and pipeline status."""
        with self.db.session() as conn:
            conn.execute(
                """
                UPDATE discoveries
                SET novelty_score = ?, utility_score = ?, evidence_score = ?,
                    content_potential = ?, status = ?, content_angle = ?,
                    verification_notes = ?, updated_at = ?
                WHERE id = ?;
                """,
                (
                    novelty,
                    utility,
                    evidence,
                    potential,
                    status,
                    content_angle,
                    verification_notes,
                    utc_now_iso(),
                    discovery_id,
                ),
            )

    @staticmethod
    def _row_to_model(row: Any) -> DiscoveryRecord:
        d = dict(row)
        d["code_demo_indicators"] = json.loads(d["code_demo_indicators"]) if isinstance(d["code_demo_indicators"], str) else []
        d["linked_discoveries"] = json.loads(d["linked_discoveries"]) if isinstance(d["linked_discoveries"], str) else []
        return DiscoveryRecord(**d)


class ContentDraftRepository:
    """Repository for managing content drafts."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def insert(self, record: ContentDraftRecord) -> None:
        """Insert a new content draft."""
        with self.db.session() as conn:
            conn.execute(
                """
                INSERT INTO content_drafts (
                    id, discovery_id, research_core, generated_copy, platform,
                    format, visual_asset_path, review_score, review_feedback,
                    generation_version, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    record.id,
                    record.discovery_id,
                    json.dumps(record.research_core),
                    record.generated_copy,
                    record.platform,
                    record.format,
                    record.visual_asset_path,
                    record.review_score,
                    record.review_feedback,
                    record.generation_version,
                    record.status,
                    record.created_at,
                    record.updated_at,
                ),
            )

    def get_by_id(self, draft_id: str) -> ContentDraftRecord | None:
        """Retrieve draft by ID."""
        with self.db.session() as conn:
            cursor = conn.execute("SELECT * FROM content_drafts WHERE id = ?;", (draft_id,))
            row = cursor.fetchone()
            return self._row_to_model(row) if row else None

    def list_by_status(self, status: str, limit: int = 50) -> list[ContentDraftRecord]:
        """List drafts by status."""
        with self.db.session() as conn:
            cursor = conn.execute(
                "SELECT * FROM content_drafts WHERE status = ? ORDER BY created_at DESC LIMIT ?;",
                (status, limit),
            )
            return [self._row_to_model(row) for row in cursor.fetchall()]

    def update_review(
        self,
        draft_id: str,
        review_score: float,
        review_feedback: str,
        status: str,
    ) -> None:
        """Update review score, feedback, and draft status."""
        with self.db.session() as conn:
            conn.execute(
                """
                UPDATE content_drafts
                SET review_score = ?, review_feedback = ?, status = ?, updated_at = ?
                WHERE id = ?;
                """,
                (review_score, review_feedback, status, utc_now_iso(), draft_id),
            )

    @staticmethod
    def _row_to_model(row: Any) -> ContentDraftRecord:
        d = dict(row)
        d["research_core"] = json.loads(d["research_core"]) if isinstance(d["research_core"], str) else {}
        return ContentDraftRecord(**d)


class PublishingQueueRepository:
    """Repository for managing the persistent publishing dispatch queue."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def enqueue(self, record: PublishingQueueRecord) -> None:
        """Enqueue an item for publishing."""
        with self.db.session() as conn:
            conn.execute(
                """
                INSERT INTO publishing_queue (
                    id, content_id, platform, publish_state, platform_post_id,
                    scheduled_time, publish_timestamp, retry_count, max_retries,
                    error_message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    record.id,
                    record.content_id,
                    record.platform,
                    record.publish_state,
                    record.platform_post_id,
                    record.scheduled_time,
                    record.publish_timestamp,
                    record.retry_count,
                    record.max_retries,
                    record.error_message,
                    record.created_at,
                ),
            )

    def get_pending(self, limit: int = 10) -> list[PublishingQueueRecord]:
        """Fetch pending queue items ready for dispatch."""
        with self.db.session() as conn:
            cursor = conn.execute(
                "SELECT * FROM publishing_queue WHERE publish_state IN ('PENDING', 'RETRYING') ORDER BY created_at ASC LIMIT ?;",
                (limit,),
            )
            return [PublishingQueueRecord(**dict(row)) for row in cursor.fetchall()]

    def mark_published(self, queue_id: str, platform_post_id: str) -> None:
        """Mark item as successfully published."""
        with self.db.session() as conn:
            conn.execute(
                """
                UPDATE publishing_queue
                SET publish_state = 'PUBLISHED', platform_post_id = ?, publish_timestamp = ?
                WHERE id = ?;
                """,
                (platform_post_id, utc_now_iso(), queue_id),
            )

    def record_failure(self, queue_id: str, error_message: str) -> None:
        """Record dispatch failure with retry tracking."""
        with self.db.session() as conn:
            cursor = conn.execute("SELECT retry_count, max_retries FROM publishing_queue WHERE id = ?;", (queue_id,))
            row = cursor.fetchone()
            if row:
                retries = row["retry_count"] + 1
                max_retries = row["max_retries"]
                new_state = "FAILED" if retries >= max_retries else "RETRYING"
                conn.execute(
                    """
                    UPDATE publishing_queue
                    SET retry_count = ?, publish_state = ?, error_message = ?
                    WHERE id = ?;
                    """,
                    (retries, new_state, error_message, queue_id),
                )


class AnalyticsRepository:
    """Repository for post performance metrics."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def insert(self, record: AnalyticsRecord) -> None:
        """Record performance metrics."""
        with self.db.session() as conn:
            conn.execute(
                """
                INSERT INTO analytics (
                    id, content_id, platform_post_id, platform, topic,
                    angle, format, impressions, likes, comments, shares,
                    clicks, collection_timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    record.id,
                    record.content_id,
                    record.platform_post_id,
                    record.platform,
                    record.topic,
                    record.angle,
                    record.format,
                    record.impressions,
                    record.likes,
                    record.comments,
                    record.shares,
                    record.clicks,
                    record.collection_timestamp,
                ),
            )

    def list_by_platform(self, platform: str, limit: int = 50) -> list[AnalyticsRecord]:
        """Fetch analytics records for platform."""
        with self.db.session() as conn:
            cursor = conn.execute(
                "SELECT * FROM analytics WHERE platform = ? ORDER BY collection_timestamp DESC LIMIT ?;",
                (platform, limit),
            )
            return [AnalyticsRecord(**dict(row)) for row in cursor.fetchall()]
