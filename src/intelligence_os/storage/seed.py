"""Seed initial sample discoveries and drafts for visual demonstration."""

import json
from intelligence_os.config.settings import get_settings
from intelligence_os.storage.db import Database
from intelligence_os.storage.migrations import run_migrations
from intelligence_os.storage.models import DiscoveryRecord, ContentDraftRecord, PublishingQueueRecord, AnalyticsRecord
from intelligence_os.storage.repositories import (
    DiscoveryRepository,
    ContentDraftRepository,
    PublishingQueueRepository,
    AnalyticsRepository,
)


def seed_data():
    """Populate realistic high-signal AI discoveries and drafts."""
    settings = get_settings()
    db = Database(settings.database_path)
    run_migrations(db)

    disc_repo = DiscoveryRepository(db)
    draft_repo = ContentDraftRepository(db)
    queue_repo = PublishingQueueRepository(db)
    analytics_repo = AnalyticsRepository(db)

    samples = [
        DiscoveryRecord(
            id="disc-mcp-servers",
            source_url="https://github.com/modelcontextprotocol/servers",
            title="Model Context Protocol: Standardized Tool Integration Engine",
            source_type="github",
            source_tier=1,
            author="modelcontextprotocol",
            summary="Official reference implementations of MCP servers enabling instant tool discovery across local and cloud LLM coding agents.",
            raw_content="Standardized JSON-RPC protocol specification for LLM tool integration...",
            code_demo_indicators=["github_repo", "reproducible_code", "pip_package"],
            freshness_score=0.98,
            novelty_score=0.92,
            utility_score=0.96,
            evidence_score=0.98,
            content_potential=0.94,
            status="BRIEF_READY",
            content_angle="unusual_tool_use",
            verification_notes="Verified against official repository commit and architecture diagrams.",
        ),
        DiscoveryRecord(
            id="disc-browser-use",
            source_url="https://github.com/browser-use/browser-use",
            title="Browser-Use: Vision-Guided Autonomous Web Agent Loop",
            source_type="github",
            source_tier=1,
            author="gregpr07",
            summary="Open-source browser automation agent connecting Playwright with multimodal LLMs to navigate complex interactive SPAs.",
            raw_content="Browser-use enables agents to interact with any website using visual DOM element targeting...",
            code_demo_indicators=["github_repo", "video_demo", "reproducible_code"],
            freshness_score=0.95,
            novelty_score=0.90,
            utility_score=0.94,
            evidence_score=0.92,
            content_potential=0.91,
            status="BRIEF_READY",
            content_angle="experiment",
            verification_notes="Tested and reproduced across dynamic multi-page checkout flow.",
        ),
        DiscoveryRecord(
            id="disc-context-compression",
            source_url="https://simonwillison.net/2026/context-budgeting-agents/",
            title="Context Budgeting: Preventing Token Saturation in Long-Turn Coding Sessions",
            source_type="firecrawl",
            source_tier=1,
            author="simonw",
            summary="Empirical benchmarks demonstrating how selective token budgeting preserves tool accuracy over 500+ agent turns.",
            raw_content="Detailed breakdown of context compression techniques in autonomous loops...",
            code_demo_indicators=["blog_experiment", "reproducible_code"],
            freshness_score=0.90,
            novelty_score=0.86,
            utility_score=0.95,
            evidence_score=0.94,
            content_potential=0.89,
            status="BRIEF_READY",
            content_angle="workflow",
            verification_notes="Grounding verified against reproducible python test harness.",
        ),
        DiscoveryRecord(
            id="disc-eval-benchmark",
            source_url="https://github.com/swe-bench/experiments",
            title="SWE-bench Multi-Agent Coordination Breakdown",
            source_type="github",
            source_tier=2,
            author="swe-bench",
            summary="Failure analysis of multi-agent delegation patterns on real-world GitHub issues.",
            raw_content="Empirical analysis of 1,200 agent runs...",
            code_demo_indicators=["dataset", "benchmark_logs"],
            freshness_score=0.85,
            novelty_score=0.82,
            utility_score=0.88,
            evidence_score=0.90,
            content_potential=0.84,
            status="BRIEF_READY",
            content_angle="failure_analysis",
            verification_notes="Benchmark datasets verified.",
        ),
    ]

    for s in samples:
        if not disc_repo.get_by_id(s.id):
            disc_repo.insert(s)

    # Sample approved draft
    draft_id = "draft-li-mcp-01"
    if not draft_repo.get_by_id(draft_id):
        draft_repo.insert(
            ContentDraftRecord(
                id=draft_id,
                discovery_id="disc-mcp-servers",
                research_core={
                    "hook": "Stop writing handwritten tool parsers for every LLM agent.",
                    "core_insight": "Model Context Protocol creates a universal JSON-RPC tool bridge for AI workflows.",
                    "evidence": ["https://github.com/modelcontextprotocol/servers"],
                    "practical_takeaway": "Adopt the MCP stdio protocol for fast local agent tooling.",
                    "limitations": "Requires local runtime execution.",
                    "content_angle": "unusual_tool_use",
                },
                generated_copy="Stop writing brittle tool parsers for every AI agent.\n\nModel Context Protocol (MCP) solves tool fragmentation once and for all:\n• Standardized JSON-RPC protocol\n• Instant tool interoperability across Claude, Cursor, and custom agent loops\n• Eliminate 90% of boilerplate schema conversions\n\nVerified in production: https://github.com/modelcontextprotocol/servers\n\n#AIAgents #SoftwareEngineering #MCP #OpenSource",
                platform="linkedin",
                format="carousel",
                review_score=0.94,
                review_feedback="Grounding verified against primary repository release and architecture documentation.",
                status="APPROVED",
            )
        )

        queue_repo.enqueue(
            PublishingQueueRecord(
                id="queue-item-01",
                content_id=draft_id,
                platform="linkedin",
                publish_state="PENDING",
            )
        )

    print("Seed data loaded successfully!")


if __name__ == "__main__":
    seed_data()
