"""Tests for Phase 4: Declarative Source Configuration."""

import pytest
from pathlib import Path
from intelligence_os.config.sources_manager import SourceManager
from intelligence_os.core.exceptions import ConfigurationError


def test_load_default_sources_and_topics() -> None:
    """Verify loading default sources.yaml and topics.yaml."""
    mgr = SourceManager(sources_path="config/sources.yaml", topics_path="config/topics.yaml")

    people = mgr.get_enabled_people()
    assert len(people) >= 5
    karpathy = next((p for p in people if p.id == "person-karpathy"), None)
    assert karpathy is not None
    assert karpathy.handles.get("github") == "karpathy"
    assert karpathy.source_tier == 1

    sources = mgr.get_enabled_sources()
    assert len(sources) >= 3

    gh_sources = mgr.get_enabled_sources(source_type="github")
    assert len(gh_sources) >= 1
    assert any("ai-agent" in s.target for s in gh_sources)

    topics = mgr.get_topics()
    assert len(topics) >= 5
    agent_topic = next((t for t in topics if t.id == "ai_agents"), None)
    assert agent_topic is not None
    assert agent_topic.weight == 1.0
    assert "workflow" in agent_topic.preferred_angles


def test_missing_config_files_raises() -> None:
    """Verify ConfigurationError when YAML file paths do not exist."""
    with pytest.raises(ConfigurationError):
        SourceManager(sources_path="nonexistent_sources.yaml", topics_path="config/topics.yaml")


def test_filtering_sources_by_priority() -> None:
    """Verify filtering sources by high/medium priority."""
    mgr = SourceManager(sources_path="config/sources.yaml", topics_path="config/topics.yaml")
    high_priority = mgr.get_enabled_sources(priority="high")
    assert len(high_priority) > 0
    assert all(s.priority == "high" for s in high_priority)
