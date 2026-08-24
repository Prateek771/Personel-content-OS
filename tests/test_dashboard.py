"""Tests for Dashboard with Scrapling Engine and Interactive Approval."""

import pytest
from starlette.testclient import TestClient
from intelligence_os.dashboard.app import app


client = TestClient(app)


def test_dashboard_index_route() -> None:
    """Verify dashboard index serves HTML response with Scrapling N8N canvas."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "AI Content Intelligence OS" in response.text
    assert "topic-input" in response.text
    assert "LinkedIn Carousel Studio" in response.text
    # N8N-style node canvas
    assert "node-scrapling" in response.text


def test_dashboard_telemetry_endpoint() -> None:
    """Verify telemetry API returns structured metrics, discoveries, and health."""
    response = client.get("/api/telemetry")
    assert response.status_code == 200
    data = response.json()
    assert "stats" in data
    assert "total_discoveries" in data["stats"]
    assert "discoveries" in data
    assert "health" in data
