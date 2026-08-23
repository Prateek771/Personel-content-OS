"""Tests for Phase 3: Database and Storage Layer."""

import pytest
from intelligence_os.storage.db import Database
from intelligence_os.storage.migrations import run_migrations
from intelligence_os.storage.models import (
    DiscoveryRecord,
    ContentDraftRecord,
    PublishingQueueRecord,
    AnalyticsRecord,
)
from intelligence_os.storage.repositories import (
    DiscoveryRepository,
    ContentDraftRepository,
    PublishingQueueRepository,
    AnalyticsRepository,
)
from intelligence_os.config.settings import Settings


@pytest.fixture
def test_db(temp_workspace: Settings) -> Database:
    """Initialize test database with migrations applied."""
    db = Database(temp_workspace.database_path)
    run_migrations(db)
    return db


def test_migrations_idempotent(test_db: Database) -> None:
    """Verify applying migrations multiple times is safe and returns 0 applied."""
    reapplied = run_migrations(test_db)
    assert reapplied == 0


def test_discovery_crud(test_db: Database) -> None:
    """Verify Discovery repository insert, retrieve, list, and update."""
    repo = DiscoveryRepository(test_db)

    record = DiscoveryRecord(
        id="disc-123",
        source_url="https://github.com/example/ai-agent",
        title="Revolutionary Multi-Agent Orchestrator",
        source_type="github",
        source_tier=1,
        raw_content="README and code snippet demonstrating multi-agent workflows.",
        summary="Novel coordination mechanism for agents.",
        author="karpathy",
        code_demo_indicators=["github_repo", "reproducible_code"],
        freshness_score=1.0,
        novelty_score=0.85,
        utility_score=0.90,
        evidence_score=0.95,
        content_potential=0.89,
        status="ANALYZED",
        content_angle="workflow",
    )
    repo.insert(record)

    # By ID
    retrieved = repo.get_by_id("disc-123")
    assert retrieved is not None
    assert retrieved.title == "Revolutionary Multi-Agent Orchestrator"
    assert retrieved.code_demo_indicators == ["github_repo", "reproducible_code"]
    assert retrieved.novelty_score == 0.85

    # By URL
    by_url = repo.get_by_url("https://github.com/example/ai-agent")
    assert by_url is not None
    assert by_url.id == "disc-123"

    # Update scores & status
    repo.update_scores_and_status(
        discovery_id="disc-123",
        novelty=0.95,
        utility=0.92,
        evidence=0.98,
        potential=0.94,
        status="BRIEF_READY",
        content_angle="workflow",
        verification_notes="Verified against repo commit 8f3a1b.",
    )
    updated = repo.get_by_id("disc-123")
    assert updated.status == "BRIEF_READY"
    assert updated.content_potential == 0.94
    assert "commit 8f3a1b" in updated.verification_notes


def test_content_draft_and_review(test_db: Database) -> None:
    """Verify Content Draft insertion and review updates."""
    disc_repo = DiscoveryRepository(test_db)
    draft_repo = ContentDraftRepository(test_db)

    disc_repo.insert(
        DiscoveryRecord(
            id="disc-456",
            source_url="https://github.com/test/tool",
            title="MCP Tool Discovery",
            raw_content="MCP tool content",
        )
    )

    draft = ContentDraftRecord(
        id="draft-001",
        discovery_id="disc-456",
        research_core={
            "hook": "Stop writing brittle tool parsers.",
            "core_insight": "Standardized MCP schema enables instant agent interoperability.",
            "evidence": ["https://github.com/test/tool"],
            "practical_takeaway": "Use MCP stdio adapter.",
            "limitations": "Requires local runtime.",
            "content_angle": "unusual_tool_use",
        },
        generated_copy="Detailed breakdown of how MCP changes agent tooling...",
        platform="linkedin",
        format="post",
        status="DRAFTED",
    )
    draft_repo.insert(draft)

    retrieved = draft_repo.get_by_id("draft-001")
    assert retrieved is not None
    assert retrieved.research_core["hook"] == "Stop writing brittle tool parsers."

    # Update Review
    draft_repo.update_review(
        draft_id="draft-001",
        review_score=0.92,
        review_feedback="Grounding verified against primary repo.",
        status="APPROVED",
    )
    approved = draft_repo.get_by_id("draft-001")
    assert approved.status == "APPROVED"
    assert approved.review_score == 0.92


def test_publishing_queue_lifecycle(test_db: Database) -> None:
    """Verify publishing queue state transitions, retries, and dispatch."""
    disc_repo = DiscoveryRepository(test_db)
    draft_repo = ContentDraftRepository(test_db)
    queue_repo = PublishingQueueRepository(test_db)

    disc_repo.insert(
        DiscoveryRecord(
            id="disc-789",
            source_url="https://github.com/agent/eval",
            title="Agent Evaluation Benchmark",
            raw_content="Evaluation benchmark data",
        )
    )
    draft_repo.insert(
        ContentDraftRecord(
            id="draft-002",
            discovery_id="disc-789",
            research_core={"hook": "Benchmarking AI agents accurately."},
            generated_copy="Post content",
            platform="x",
            format="thread",
        )
    )

    queue_item = PublishingQueueRecord(
        id="queue-001",
        content_id="draft-002",
        platform="x",
        publish_state="PENDING",
    )
    queue_repo.enqueue(queue_item)

    pending = queue_repo.get_pending()
    assert len(pending) == 1
    assert pending[0].id == "queue-001"

    # Test failure retry
    queue_repo.record_failure("queue-001", "Rate limited by X API")
    pending = queue_repo.get_pending()
    assert len(pending) == 1
    assert pending[0].publish_state == "RETRYING"
    assert pending[0].retry_count == 1

    # Test publish success
    queue_repo.mark_published("queue-001", platform_post_id="x-post-98765")
    pending = queue_repo.get_pending()
    assert len(pending) == 0  # No longer pending


def test_analytics_recording(test_db: Database) -> None:
    """Verify analytics record insertion and query."""
    disc_repo = DiscoveryRepository(test_db)
    draft_repo = ContentDraftRepository(test_db)
    analytics_repo = AnalyticsRepository(test_db)

    disc_repo.insert(DiscoveryRecord(id="d1", source_url="https://a.com", title="A", raw_content="A"))
    draft_repo.insert(
        ContentDraftRecord(
            id="c1",
            discovery_id="d1",
            research_core={},
            generated_copy="Test post",
            platform="linkedin",
            format="carousel",
        )
    )

    analytics_repo.insert(
        AnalyticsRecord(
            id="a1",
            content_id="c1",
            platform_post_id="li-post-111",
            platform="linkedin",
            topic="agent_orchestration",
            angle="workflow",
            format="carousel",
            impressions=1250,
            likes=48,
            comments=12,
            shares=8,
            clicks=95,
        )
    )

    results = analytics_repo.list_by_platform("linkedin")
    assert len(results) == 1
    assert results[0].impressions == 1250
    assert results[0].likes == 48
