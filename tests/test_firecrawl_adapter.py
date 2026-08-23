"""Tests for Phase 5: Firecrawl and Web Research Adapter."""

import httpx
import pytest
from unittest.mock import patch, MagicMock

from intelligence_os.research.adapters.firecrawl import FirecrawlAdapter
from intelligence_os.research.adapters.base import RawHarvestItem


SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Building Multi-Agent Workflows in Python</title>
    <meta name="author" content="Simon Willison">
    <meta property="og:title" content="Building Multi-Agent Workflows in Python">
</head>
<body>
    <header><nav>Home | About</nav></header>
    <article>
        <h1>Building Multi-Agent Workflows in Python</h1>
        <p>In this experiment, we explore how MCP enables tool calling across independent agent processes.</p>
        <pre><code>def run_agent(): return "done"</code></pre>
    </article>
    <footer>Copyright 2026</footer>
</body>
</html>
"""


def test_firecrawl_local_fallback_parsing() -> None:
    """Verify local scraper parses HTML, extracts title/author, and converts to markdown."""
    adapter = FirecrawlAdapter(base_url="http://localhost:3002")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = SAMPLE_HTML
    mock_resp.raise_for_status = MagicMock()

    with patch.object(adapter, "is_available", return_value=False), \
         patch.object(httpx.Client, "get", return_value=mock_resp):
        items = adapter.harvest("https://simonwillison.net/2026/multi-agent-experiment/")

    assert len(items) == 1
    item = items[0]
    assert item.title == "Building Multi-Agent Workflows in Python"
    assert item.author == "Simon Willison"
    assert "MCP enables tool calling" in item.markdown_content
    assert "run_agent()" in item.markdown_content
    assert item.metadata["engine"] == "local_fallback"


def test_firecrawl_api_success() -> None:
    """Verify Firecrawl API ingestion when container/service is available."""
    adapter = FirecrawlAdapter(base_url="http://localhost:3002", api_key="fc-test")

    mock_scrape = MagicMock()
    mock_scrape.status_code = 200
    mock_scrape.raise_for_status = MagicMock()
    mock_scrape.json.return_value = {
        "data": {
            "metadata": {"title": "Firecrawl Scraped Article", "author": "Andrej Karpathy"},
            "markdown": "# Direct Firecrawl Markdown\nHigh signal AI finding.",
            "html": "<p>High signal AI finding.</p>",
        }
    }

    with patch.object(adapter, "is_available", return_value=True), \
         patch.object(httpx.Client, "post", return_value=mock_scrape):
        items = adapter.harvest("https://karpathy.ai/blog/agent-insights")

    assert len(items) == 1
    assert items[0].title == "Firecrawl Scraped Article"
    assert items[0].author == "Andrej Karpathy"
    assert items[0].metadata["engine"] == "firecrawl_api"


def test_firecrawl_error_handling_graceful() -> None:
    """Verify 404 or connection failure does not crash harvest and returns empty list."""
    adapter = FirecrawlAdapter(base_url="http://localhost:3002")

    with patch.object(adapter, "is_available", return_value=False), \
         patch.object(httpx.Client, "get", side_effect=httpx.ConnectError("Connection refused")):
        items = adapter.harvest("https://invalid-non-existent-site-12345.org")

    assert items == []
