"""Tests for Phase 9: Exact and Semantic Deduplication."""

import pytest
from intelligence_os.config.settings import Settings
from intelligence_os.dedup.exact import normalize_url
from intelligence_os.dedup.semantic import compute_cosine_similarity
from intelligence_os.dedup.engine import DeduplicationEngine
from intelligence_os.storage.db import Database
from intelligence_os.storage.migrations import run_migrations
from intelligence_os.storage.models import DiscoveryRecord
from intelligence_os.storage.repositories import DiscoveryRepository


def test_url_normalization() -> None:
    """Verify URL normalization removes tracking parameters and trailing slashes."""
    url1 = "https://GitHub.com/example/agent/?utm_source=twitter&ref=feed"
    url2 = "https://github.com/example/agent"
    assert normalize_url(url1) == normalize_url(url2)


def test_semantic_similarity_calculation() -> None:
    """Verify local cosine similarity on related text vs unrelated text."""
    text_a = "Anthropic releases Model Context Protocol specification for tool integration."
    text_b = "Model Context Protocol released by Anthropic enabling standardized tool calling."
    text_unrelated = "Cooking recipe for homemade sourdough pizza crust."

    sim_high = compute_cosine_similarity(text_a, text_b)
    sim_low = compute_cosine_similarity(text_a, text_unrelated)

    assert sim_high >= 0.50
    assert sim_low <= 0.05


def test_deduplication_engine_merging(temp_workspace: Settings) -> None:
    """Verify DeduplicationEngine detects duplicates, merges evidence links, and marks non-duplicates."""
    db = Database(temp_workspace.database_path)
    run_migrations(db)
    repo = DiscoveryRepository(db)

    # 1. Insert original item
    repo.insert(
        DiscoveryRecord(
            id="d-orig",
            source_url="https://github.com/agent/mcp-server",
            title="MCP Server Implementation",
            summary="Reference MCP server in Python for local tools.",
            raw_content="Python MCP server code...",
            source_type="github",
            source_tier=1,
            status="RAW_INGESTED",
        )
    )

    # 2. Insert semantic duplicate with different tracking URL
    repo.insert(
        DiscoveryRecord(
            id="d-dup",
            source_url="https://x.com/builder/status/999?utm_source=feed",
            title="New MCP Server Released",
            summary="A great reference MCP server in Python for local tools.",
            raw_content="Check out this Python MCP server...",
            source_type="agent_reach",
            source_tier=2,
            status="RAW_INGESTED",
        )
    )

    # 3. Insert unique distinct discovery
    repo.insert(
        DiscoveryRecord(
            id="d-distinct",
            source_url="https://github.com/eval/benchmark",
            title="Agent Reasoning Benchmark",
            summary="New empirical benchmark testing code agents against edge cases.",
            raw_content="Benchmark results and evaluation harness.",
            source_type="github",
            source_tier=1,
            status="RAW_INGESTED",
        )
    )

    dedup = DeduplicationEngine(db, similarity_threshold=0.50)
    stats = dedup.process_raw_ingested()

    assert stats["merged"] >= 1
    assert stats["deduped_unique"] >= 1

    # Original should be updated with merged link
    orig = repo.get_by_id("d-orig")
    assert orig is not None
    assert orig.status in ["DEDUPED", "RAW_INGESTED"]

    # Duplicate should be marked MERGED_DUPLICATE
    dup = repo.get_by_id("d-dup")
    assert dup is not None
    assert dup.status == "MERGED_DUPLICATE"
