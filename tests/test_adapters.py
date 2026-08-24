"""Tests for Phase 6 & 7: Agent Reach and GitHub Intelligence Adapters."""

import httpx
import pytest
from unittest.mock import patch, MagicMock

from intelligence_os.research.adapters.agent_reach import AgentReachAdapter
from intelligence_os.research.adapters.github import GitHubAdapter


def test_agent_reach_hn_fallback_when_service_down() -> None:
    """Verify Agent Reach falls back to HN Algolia community search when service is unreachable."""
    adapter = AgentReachAdapter(base_url="http://localhost:8080")
    with patch.object(adapter, "is_available", return_value=False), \
         patch("httpx.Client.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "hits": [
                {
                    "objectID": "40000001",
                    "title": "Show HN: New coding agent framework",
                    "url": "https://example.com/agent-framework",
                    "author": "tester",
                    "points": 120,
                    "num_comments": 45,
                }
            ]
        }
        mock_get.return_value = mock_resp
        items = adapter.harvest("coding agent demo")

    assert len(items) == 1
    assert items[0].metadata["platform"] == "hacker_news"
    assert items[0].source_type == "agent_reach"


def test_agent_reach_x_handle_without_backend_returns_empty() -> None:
    """from:handle X queries yield nothing when no backend exists (no crash, no fabrication)."""
    adapter = AgentReachAdapter(base_url="http://localhost:8080")
    with patch.object(adapter, "is_available", return_value=False), \
         patch("httpx.Client.get") as mock_get:
        # Any accidental network call would still be empty; assert no fabrication
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"hits": []}
        mock_get.return_value = mock_resp
        items = adapter.harvest("query:('AI agent' OR 'coding agent')")

    # Query text survives stripping, HN returns no hits -> empty list is honest result
    assert items == []


def test_agent_reach_harvest_success() -> None:
    """Verify Agent Reach parses social demo post results."""
    adapter = AgentReachAdapter(base_url="http://localhost:8080")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "results": [
            {
                "url": "https://x.com/karpathy/status/123456789",
                "text": "Tested new multi-agent loop with persistent memory.",
                "author": "karpathy",
                "platform": "x",
                "source_tier": 1,
            }
        ]
    }

    with patch.object(adapter, "is_available", return_value=True), \
         patch.object(httpx.Client, "post", return_value=mock_resp):
        items = adapter.harvest("query:karpathy memory")

    assert len(items) == 1
    assert items[0].author == "karpathy"
    assert items[0].source_tier == 1
    assert "persistent memory" in items[0].raw_content


def test_github_single_repo_fetch() -> None:
    """Verify GitHub adapter fetches repository metadata, README, and release notes."""
    adapter = GitHubAdapter(token=None)

    mock_repo_resp = MagicMock()
    mock_repo_resp.status_code = 200
    mock_repo_resp.raise_for_status = MagicMock()
    mock_repo_resp.json.return_value = {
        "full_name": "modelcontextprotocol/servers",
        "description": "Model Context Protocol Server Implementations",
        "stargazers_count": 4500,
        "forks_count": 320,
        "html_url": "https://github.com/modelcontextprotocol/servers",
        "owner": {"login": "modelcontextprotocol"},
        "topics": ["mcp", "ai-agents", "tools"],
    }

    mock_readme_resp = MagicMock()
    mock_readme_resp.status_code = 200
    mock_readme_resp.text = "# MCP Servers\nOfficial reference implementations."

    mock_rel_resp = MagicMock()
    mock_rel_resp.status_code = 200
    mock_rel_resp.json.return_value = {"name": "v1.2.0", "body": "Added SQLite and Git MCP servers."}

    def mock_get(url, *args, **kwargs):
        if "/releases/latest" in url:
            return mock_rel_resp
        elif "/readme" in url:
            return mock_readme_resp
        return mock_repo_resp

    with patch.object(httpx.Client, "get", side_effect=mock_get):
        item = adapter._fetch_single_repo("modelcontextprotocol/servers")

    assert item is not None
    assert item.author == "modelcontextprotocol"
    assert item.metadata["stars"] == 4500
    assert "Added SQLite and Git MCP servers." in item.raw_content
    assert "v1.2.0" in item.raw_content


def test_github_rate_limit_graceful() -> None:
    """Verify GitHub adapter returns None/empty and handles 403 rate limits without crashing."""
    adapter = GitHubAdapter()

    mock_resp = MagicMock()
    mock_resp.status_code = 403
    request = httpx.Request("GET", "https://api.github.com/repos/test/repo")
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError("403 Forbidden", request=request, response=mock_resp)

    with patch.object(httpx.Client, "get", return_value=mock_resp):
        item = adapter._fetch_single_repo("test/repo")

    assert item is None
