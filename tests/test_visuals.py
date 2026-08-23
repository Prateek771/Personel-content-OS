"""Tests for Phase 16: Local Visual Generation (Pillow Carousel)."""

import os
from pathlib import Path
from PIL import Image

from intelligence_os.config.settings import Settings
from intelligence_os.content.linkedin import LinkedInCarouselData, LinkedInCarouselSlide
from intelligence_os.visuals.carousel_renderer import CarouselRenderer


def test_carousel_rendering(temp_workspace: Settings) -> None:
    """Verify local Pillow carousel renderer generates valid 1080x1080 PNG images."""
    renderer = CarouselRenderer(output_base_dir=temp_workspace.output_dir / "carousels")

    carousel = LinkedInCarouselData(
        topic_title="MCP Protocol Guide",
        total_slides=2,
        slides=[
            LinkedInCarouselSlide(
                slide_number=1,
                title="Building Reliable Agent Tooling",
                subtitle="Why standard JSON-RPC is replacing ad-hoc tool parsers",
                bullet_points=[
                    "Universal protocol across local and cloud models",
                    "Eliminates handwritten schema adapters",
                    "Instant tool reuse across Claude, Cursor, and custom loops",
                ],
                takeaway="Adopt MCP stdio protocol for fast local development.",
            ),
            LinkedInCarouselSlide(
                slide_number=2,
                title="Implementation Architecture",
                subtitle="Server configuration pattern",
                bullet_points=[
                    "Run lightweight stdio subprocess",
                    "Expose typed tools with strict Pydantic validation",
                ],
                code_snippet="from mcp.server import Server\nserver = Server('my-agent')",
                takeaway="Keep servers single-purpose and stateless.",
            ),
        ],
    )

    rendered_paths = renderer.render_carousel(carousel, topic_slug="mcp_guide_test")
    assert len(rendered_paths) == 2

    for p in rendered_paths:
        file_path = Path(p)
        assert file_path.exists()
        assert file_path.stat().st_size > 5000  # Non-trivial image file size

        # Verify image dimensions
        with Image.open(file_path) as img:
            assert img.size == (1080, 1080)
            assert img.format == "PNG"
