"""Tests for Content Generators (LinkedIn & X) and ContentOrchestrator."""

import pytest
from unittest.mock import MagicMock
from intelligence_os.content.linkedin import (
    LinkedInGenerator,
    LinkedInContentResult,
    LinkedInCarouselData,
    LinkedInCarouselSlide,
)
from intelligence_os.content.x import XGenerator, XContentResult, XPostItem
from intelligence_os.content.generator import ContentOrchestrator
from intelligence_os.config.settings import Settings
from intelligence_os.intelligence.openrouter import OpenRouterClient
from intelligence_os.storage.db import Database
from intelligence_os.storage.migrations import run_migrations
from intelligence_os.storage.models import ResearchCoreData, DiscoveryRecord
from intelligence_os.storage.repositories import DiscoveryRepository


@pytest.fixture
def sample_core() -> ResearchCoreData:
    return ResearchCoreData(
        hook="How to build robust local coding agents without context bloat.",
        core_insight="Selective context truncation and SQLite caching reduces token consumption by 70%.",
        evidence=["https://github.com/agent/context-compression"],
        practical_takeaway="Implement LRU sliding windows over AST parse trees.",
        limitations="Requires structured memory store.",
        content_angle="workflow",
        tags=["#AIAgents", "#CodingAgents", "#MCP"],
    )


def test_linkedin_generator_mock(sample_core: ResearchCoreData) -> None:
    """Verify LinkedInGenerator produces structured carousel outputs."""
    mock_client = MagicMock(spec=OpenRouterClient)
    mock_client.copywriting_model = "dots-studio/dots-3-note-preview:free"
    mock_client.generate_chat_completion.return_value = """{
        "format": "carousel",
        "post_copy": "Here is how to optimize local agent contexts...",
        "carousel_data": {
            "topic_title": "Context Optimization",
            "total_slides": 2,
            "slides": [
                {
                    "slide_number": 1,
                    "title": "Introduction",
                    "subtitle": "The Problem",
                    "bullet_points": ["Context bloat causes high latency"],
                    "takeaway": "Swipe to learn more"
                }
            ]
        },
        "tags": ["#AI"]
    }"""

    generator = LinkedInGenerator(mock_client)
    res = generator.generate(sample_core, preferred_format="carousel")

    assert res.format == "carousel"
    assert "optimize" in res.post_copy
    assert res.carousel_data is not None
    assert len(res.carousel_data.slides) == 1


def test_x_generator_mock(sample_core: ResearchCoreData) -> None:
    """Verify XGenerator outputs clean thread structures."""
    mock_client = MagicMock(spec=OpenRouterClient)
    mock_client.copywriting_model = "dots-studio/dots-3-note-preview:free"
    mock_client.generate_chat_completion.return_value = """{
        "format": "thread",
        "posts": [
            {"post_number": 1, "text": "1/3 Here is how we reduced agent token bloat by 70%:"},
            {"post_number": 2, "text": "2/3 Instead of sending raw code, parse AST diffs directly."},
            {"post_number": 3, "text": "3/3 Summary and takeaways here."}
        ],
        "full_text_rendered": "1/3 Post 1\\n\\n2/3 Post 2\\n\\n3/3 Post 3"
    }"""

    generator = XGenerator(mock_client)
    res = generator.generate(sample_core, preferred_format="thread")

    assert res.format == "thread"
    assert len(res.posts) == 3
    assert res.posts[0].post_number == 1


def test_content_orchestrator(temp_workspace: Settings, sample_core: ResearchCoreData) -> None:
    """Verify ContentOrchestrator generates and saves drafts for both LinkedIn and X."""
    db = Database(temp_workspace.database_path)
    run_migrations(db)

    # Insert parent discovery into database to satisfy foreign key constraint
    discovery_repo = DiscoveryRepository(db)
    discovery = DiscoveryRecord(
        id="d-orch",
        source_url="https://github.com/agent/context-compression",
        title="Agent Context Compression",
        raw_content="Raw text",
    )
    discovery_repo.insert(discovery)

    mock_client = MagicMock(spec=OpenRouterClient)
    orchestrator = ContentOrchestrator(db, mock_client)

    carousel_data = LinkedInCarouselData(
        topic_title="Context Optimization",
        total_slides=1,
        slides=[
            LinkedInCarouselSlide(
                slide_number=1,
                title="Intro",
                subtitle="Sub",
                bullet_points=["Point 1"],
                takeaway="Takeaway",
            )
        ],
    )

    # Mock internal generators
    orchestrator.linkedin_gen.generate = MagicMock(
        return_value=LinkedInContentResult(format="carousel", post_copy="LI post content", carousel_data=carousel_data, tags=["#AI"])
    )
    orchestrator.x_gen.generate = MagicMock(
        return_value=XContentResult(
            format="thread",
            posts=[XPostItem(post_number=1, text="X post 1")],
            full_text_rendered="X post 1",
        )
    )

    drafts = orchestrator.generate_drafts_for_discovery(discovery, sample_core)
    assert len(drafts) == 2
    platforms = [d.platform for d in drafts]
    assert "linkedin" in platforms
    assert "x" in platforms
