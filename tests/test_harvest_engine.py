"""Tests for Phase 8: Harvest Engine."""

import pytest
from unittest.mock import MagicMock

from intelligence_os.config.sources_manager import SourceManager
from intelligence_os.config.settings import Settings
from intelligence_os.research.adapters.base import RawHarvestItem
from intelligence_os.research.adapters.firecrawl import FirecrawlAdapter
from intelligence_os.research.adapters.github import GitHubAdapter
from intelligence_os.research.harvest_engine import HarvestEngine
from intelligence_os.storage.db import Database
from intelligence_os.storage.migrations import run_migrations
from intelligence_os.storage.repositories import DiscoveryRepository


@pytest.fixture
def populated_harvest_env(temp_workspace: Settings):
    db = Database(temp_workspace.database_path)
    run_migrations(db)

    source_mgr = SourceManager(sources_path="config/sources.yaml", topics_path="config/topics.yaml")
    return db, source_mgr


def test_harvest_engine_execution(populated_harvest_env) -> None:
    """Verify HarvestEngine polls adapters, creates discoveries, and skips duplicates."""
    db, source_mgr = populated_harvest_env
    repo = DiscoveryRepository(db)

    mock_firecrawl = MagicMock(spec=FirecrawlAdapter)
    mock_firecrawl.harvest.return_value = [
        RawHarvestItem(
            source_url="https://simonwillison.net/test-post",
            title="Simon Willison on Local Models",
            raw_content="Post about running LLMs locally.",
            markdown_content="Post about running LLMs locally.",
            author="Simon Willison",
            source_type="firecrawl",
            source_tier=1,
        )
    ]

    mock_github = MagicMock(spec=GitHubAdapter)
    mock_github.harvest.return_value = [
        RawHarvestItem(
            source_url="https://github.com/test-org/ai-tool",
            title="test-org/ai-tool: Autonomous Testing Agent",
            raw_content="README of testing agent.",
            markdown_content="README of testing agent.",
            author="test-org",
            source_type="github",
            source_tier=1,
        )
    ]

    engine = HarvestEngine(
        source_manager=source_mgr,
        db=db,
        firecrawl_adapter=mock_firecrawl,
        github_adapter=mock_github,
    )

    stats = engine.run_harvest_cycle()
    assert stats["new_inserted"] == 2
    assert stats["items_harvested"] >= 2

    # Verify discoveries in database
    recent = repo.list_recent()
    assert len(recent) == 2
    assert any(d.source_url == "https://simonwillison.net/test-post" for d in recent)

    # Second run should skip duplicates
    stats_second = engine.run_harvest_cycle()
    assert stats_second["new_inserted"] == 0
    assert stats_second["duplicates_skipped"] >= 2
