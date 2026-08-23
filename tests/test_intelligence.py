"""Tests for Phases 10, 11 & 12: Grounded Analysis, Multi-Factor Scoring, Research Core, and Silent Mode Brief."""

import pytest
from unittest.mock import MagicMock

from intelligence_os.config.settings import Settings
from intelligence_os.intelligence.analyzer import GroundedAnalysisResult, IntelligenceAnalyzer
from intelligence_os.intelligence.brief import IntelligenceOrchestrator
from intelligence_os.intelligence.openrouter import OpenRouterClient
from intelligence_os.intelligence.research_core import build_research_core
from intelligence_os.intelligence.scorer import DiscoveryScorer, ScoringWeights
from intelligence_os.storage.db import Database
from intelligence_os.storage.migrations import run_migrations
from intelligence_os.storage.models import DiscoveryRecord
from intelligence_os.storage.repositories import DiscoveryRepository


def test_scorer_calculation_and_decay() -> None:
    """Verify multi-factor score calculation and temporal decay."""
    scorer = DiscoveryScorer(ScoringWeights(novelty_weight=0.4, utility_weight=0.4, evidence_weight=0.1, freshness_weight=0.1))

    analysis = GroundedAnalysisResult(
        what_happened="Built a multi-agent loop with persistent memory",
        what_is_actually_new="Zero-shot context compression mechanism",
        demonstrator_name="Simon Willison",
        demonstrator_role="builder",
        tool_model_agent_used="Claude 3.5 Sonnet",
        action_taken="Tested 500 multi-turn iterations",
        result_obtained="Reduced context usage by 45%",
        evidence_found="Benchmark logs and open source repository",
        can_be_reproduced=True,
        why_useful="Solves token context saturation in long coding sessions",
        limitations="Requires local SQLite storage",
        what_is_overhyped="Not fully generalized to every domain",
        is_worth_publishing=True,
        strongest_content_angle="workflow",
        novelty_score=0.90,
        utility_score=0.95,
        evidence_score=0.90,
        summary_insight="Context compression enables scalable long-running coding agents.",
    )

    discovery = DiscoveryRecord(
        id="d-test-1",
        source_url="https://github.com/test/agent-context",
        title="Agent Context Compression",
        raw_content="Raw research text",
        source_type="github",
        source_tier=1,
    )

    freshness, potential = scorer.calculate_score(analysis, discovery)
    assert freshness > 0.95
    assert potential >= 0.85


def test_research_core_synthesis() -> None:
    """Verify Research Core is synthesized with hook, insight, evidence, takeaways."""
    analysis = GroundedAnalysisResult(
        what_happened="Released browser-use library",
        what_is_actually_new="Playwright automated vision agent",
        demonstrator_name="Gregor",
        demonstrator_role="builder",
        tool_model_agent_used="browser-use",
        action_taken="Automated web actions using vision",
        result_obtained="Completed complex checkout workflow autonomously",
        evidence_found="GitHub repository and demo video",
        can_be_reproduced=True,
        why_useful="Automates tasks behind dynamic web apps",
        limitations="DOM structure changes can cause retries",
        what_is_overhyped="Does not replace human validation for transactions",
        is_worth_publishing=True,
        strongest_content_angle="repo_watch",
        novelty_score=0.88,
        utility_score=0.92,
        evidence_score=0.90,
        summary_insight="Vision-based browser automation handles dynamic web apps reliably.",
    )

    discovery = DiscoveryRecord(
        id="d-browser",
        source_url="https://github.com/browser-use/browser-use",
        title="browser-use: Web Automation Agent",
        raw_content="README",
        source_tier=1,
    )

    core = build_research_core(discovery, analysis)
    assert "browser-use" in core.hook
    assert "https://github.com/browser-use/browser-use" in core.evidence
    assert core.content_angle == "repo_watch"
    assert "DOM structure" in core.limitations


def test_silent_mode_enforcement(temp_workspace: Settings) -> None:
    """Verify Silent Mode is triggered when discoveries fail score threshold."""
    db = Database(temp_workspace.database_path)
    run_migrations(db)
    repo = DiscoveryRepository(db)

    # Insert weak / low-quality news discovery
    repo.insert(
        DiscoveryRecord(
            id="d-weak",
            source_url="https://news.example.com/hype-article",
            title="AI Might Change Everything In 10 Years",
            raw_content="Generic opinion piece without code or data.",
            source_tier=3,
            status="DEDUPED",
        )
    )

    mock_client = MagicMock(spec=OpenRouterClient)
    analyzer = IntelligenceAnalyzer(mock_client)

    # Mock weak analysis response
    weak_analysis = GroundedAnalysisResult(
        what_happened="Opinion editorial about AI future",
        what_is_actually_new="Nothing new",
        demonstrator_name="Unknown",
        demonstrator_role="commentator",
        tool_model_agent_used="None",
        action_taken="Speculation",
        result_obtained="None",
        evidence_found="Insufficient evidence in source",
        can_be_reproduced=False,
        why_useful="General reading",
        limitations="No proof",
        what_is_overhyped="Everything",
        is_worth_publishing=False,
        strongest_content_angle="lesson",
        novelty_score=0.10,
        utility_score=0.15,
        evidence_score=0.10,
        summary_insight="Low signal commentary.",
    )
    analyzer.analyze_discovery = MagicMock(return_value=weak_analysis)

    orchestrator = IntelligenceOrchestrator(db, analyzer, min_content_score=0.65)
    brief = orchestrator.run_intelligence_cycle()

    assert brief.is_silent_mode is True
    assert "NO PUBLISHABLE INTELLIGENCE" in brief.silent_mode_reason
    assert len(brief.selected_opportunities) == 0

    # Discovery should be marked SILENT_DISMISSED
    updated_rec = repo.get_by_id("d-weak")
    assert updated_rec is not None
    assert updated_rec.status == "SILENT_DISMISSED"
