"""Domain models and schemas for SQLite storage layer."""

from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO8601 format."""
    return datetime.now(timezone.utc).isoformat()


class DiscoveryRecord(BaseModel):
    """Storage model for a raw or processed research discovery."""

    id: str
    source_url: str
    title: str
    source_type: str = "web"  # github, firecrawl, agent_reach, web
    source_tier: int = 1  # 1 (original/repo/demo), 2 (technical analysis), 3 (aggregator/commentary)
    discovery_timestamp: str = Field(default_factory=utc_now_iso)
    raw_content: str
    summary: str = ""
    author: str = ""
    code_demo_indicators: list[str] = Field(default_factory=list)
    freshness_score: float = 1.0
    novelty_score: float = 0.0
    utility_score: float = 0.0
    evidence_score: float = 0.0
    content_potential: float = 0.0
    status: str = "RAW_INGESTED"  # RAW_INGESTED, DEDUPED, ANALYZED, SCORED, BRIEF_READY, SILENT_DISMISSED
    content_angle: str = ""
    verification_notes: str = ""
    linked_discoveries: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class ResearchCoreData(BaseModel):
    """Structured research core containing the factual foundation for all content generation."""

    hook: str
    core_insight: str
    evidence: list[str]
    practical_takeaway: str
    limitations: str
    content_angle: str  # workflow, unusual_tool_use, repo_watch, experiment, lesson, failure_analysis
    tags: list[str] = Field(default_factory=list)


class ContentDraftRecord(BaseModel):
    """Storage model for generated platform content."""

    id: str
    discovery_id: str
    research_core: dict[str, Any]
    generated_copy: str
    platform: str  # linkedin, x
    format: str  # post, carousel, cheat_sheet, thread
    visual_asset_path: str | None = None
    review_score: float = 0.0
    review_feedback: str = ""
    generation_version: int = 1
    status: str = "DRAFTED"  # DRAFTED, IN_REVIEW, REJECTED, APPROVED
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class PublishingQueueRecord(BaseModel):
    """Storage model for queued posts ready for scheduling and dispatch."""

    id: str
    content_id: str
    platform: str
    publish_state: str = "PENDING"  # PENDING, SCHEDULED, PUBLISHING, PUBLISHED, FAILED, RETRYING
    platform_post_id: str | None = None
    scheduled_time: str | None = None
    publish_timestamp: str | None = None
    retry_count: int = 0
    max_retries: int = 3
    error_message: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)


class AnalyticsRecord(BaseModel):
    """Storage model for tracking post performance and engagement metrics."""

    id: str
    content_id: str
    platform_post_id: str
    platform: str
    topic: str
    angle: str
    format: str
    impressions: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    clicks: int = 0
    collection_timestamp: str = Field(default_factory=utc_now_iso)
