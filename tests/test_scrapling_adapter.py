"""Tests for ScraplingAdapter (Zero Docker web scraper)."""

import pytest
from unittest.mock import MagicMock, patch
from intelligence_os.research.adapters.scrapling import ScraplingAdapter


def test_scrapling_adapter_availability() -> None:
    """Verify ScraplingAdapter is natively available without Docker."""
    adapter = ScraplingAdapter()
    assert adapter.is_available() is True
    assert adapter.name == "scrapling"


def test_scrapling_adapter_harvest_mock() -> None:
    """Verify ScraplingAdapter extracts markdown and title from pages."""
    adapter = ScraplingAdapter()
    mock_page = MagicMock()
    mock_page.status = 200
    mock_page.css.return_value.get.return_value = "Test AI Agent Breakthrough"
    mock_page.markdown.return_value = "# Test AI Agent Breakthrough\n\nMCP standardizes tool discovery."

    with patch("scrapling.Fetcher.get", return_value=mock_page):
        items = adapter.harvest("https://example.com/ai-news")
        assert len(items) == 1
        assert items[0].title == "Test AI Agent Breakthrough"
        assert items[0].source_type == "scrapling"
        assert "MCP standardizes" in items[0].raw_content


def test_scrapling_adapter_markdown_fallback_to_html() -> None:
    """Verify adapter falls back to markdownify when scrapling .markdown() is unavailable."""
    adapter = ScraplingAdapter()
    mock_page = MagicMock()
    mock_page.status = 200
    mock_page.css.return_value.get.return_value = "Fallback Title"
    mock_page.markdown.side_effect = RuntimeError("no markdown method")
    mock_page.html_content = "<article><p>BeautifulSoup fallback content path.</p></article>"

    with patch("scrapling.Fetcher.get", return_value=mock_page), \
         patch("markdownify.markdownify", return_value="BeautifulSoup fallback content path."):
        items = adapter.harvest("https://example.com/fallback")
        assert len(items) == 1
        assert "fallback content" in items[0].raw_content
