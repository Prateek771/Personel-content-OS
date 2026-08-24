"""Tests for XAdapter (official API v2 reads)."""

from unittest.mock import MagicMock, patch

from intelligence_os.research.adapters.x import XAdapter


def _mock_adapter():
    return XAdapter(
        consumer_key="k",
        consumer_secret="s",
        access_token="t",
        access_token_secret="ts",
    )


def test_x_adapter_not_configured_returns_empty() -> None:
    adapter = XAdapter()
    assert adapter.is_configured() is False
    assert adapter.harvest("from:simonw") == []


def test_x_adapter_harvest_filters_retweets() -> None:
    adapter = _mock_adapter()

    lookup_resp = MagicMock(status_code=200)
    lookup_resp.json.return_value = {"data": {"id": "123", "username": "simonw"}}
    timeline_resp = MagicMock(status_code=200)
    timeline_resp.json.return_value = {
        "data": [
            {
                "id": "999",
                "text": "RT @someone: look at this",
                "public_metrics": {"like_count": 5},
            },
            {
                "id": "1000",
                "text": "Original insight about local LLM tooling",
                "created_at": "2026-08-24T00:00:00Z",
                "public_metrics": {"like_count": 42, "retweet_count": 7, "reply_count": 3},
            },
        ]
    }

    mock_session = MagicMock()
    mock_session.get.side_effect = [lookup_resp, timeline_resp]

    with patch.object(adapter, "_session", return_value=mock_session):
        items = adapter.harvest("from:simonw", limit=2)

    assert len(items) == 1
    assert items[0].source_url == "https://x.com/simonw/status/1000"
    assert items[0].author == "simonw"
    assert items[0].metadata["platform"] == "x"


def test_x_adapter_lookup_failure_returns_empty() -> None:
    adapter = _mock_adapter()

    bad_resp = MagicMock(status_code=404)
    mock_session = MagicMock()
    mock_session.get.return_value = bad_resp

    with patch.object(adapter, "_session", return_value=mock_session):
        assert adapter.harvest("from:nonexistent_handle_xyz") == []
