"""Tests for Phase 17: Review Gate and Fact Checking."""

import pytest
from unittest.mock import MagicMock

from intelligence_os.config.settings import Settings
from intelligence_os.intelligence.openrouter import OpenRouterClient
from intelligence_os.review.gate import ReviewGate
from intelligence_os.review.verifier import ReviewResult, ReviewVerifier
from intelligence_os.storage.db import Database
from intelligence_os.storage.migrations import run_migrations
from intelligence_os.storage.models import ContentDraftRecord, DiscoveryRecord, ResearchCoreData
from intelligence_os.storage.repositories import ContentDraftRepository, DiscoveryRepository, PublishingQueueRepository


@pytest.fixture
def sample_core() -> ResearchCoreData:
    return ResearchCoreData(
        hook="How to evaluate coding agents.",
        core_insight="Standard benchmarks fail on multi-file dependencies.",
        evidence=["https://github.com/agent/benchmark"],
        practical_takeaway="Use repo-level integration tests.",
        limitations="Long execution time.",
        content_angle="experiment",
    )


def test_review_verifier_pass(sample_core: ResearchCoreData) -> None:
    """Verify ReviewVerifier marks valid draft as approved."""
    mock_client = MagicMock(spec=OpenRouterClient)
    verifier = ReviewVerifier(mock_client, passing_threshold=0.80)

    mock_resp = ReviewResult(
        is_approved=True,
        overall_score=0.92,
        factual_accuracy_score=0.95,
        hook_strength_score=0.90,
        practical_usefulness_score=0.90,
        hallucination_detected=False,
        unsupported_claims=[],
        feedback="Accurate breakdown directly backed by evidence.",
    )
    verifier.verify_draft = MagicMock(return_value=mock_resp)

    res = verifier.verify_draft("Verified post copy", sample_core, "linkedin")
    assert res.is_approved is True
    assert res.overall_score == 0.92
    assert not res.hallucination_detected


def test_review_verifier_rejects_hallucination(sample_core: ResearchCoreData) -> None:
    """Verify ReviewVerifier rejects draft with hallucinated claims."""
    mock_client = MagicMock(spec=OpenRouterClient)
    verifier = ReviewVerifier(mock_client, passing_threshold=0.80)

    mock_resp = ReviewResult(
        is_approved=False,
        overall_score=0.45,
        factual_accuracy_score=0.30,
        hook_strength_score=0.80,
        practical_usefulness_score=0.50,
        hallucination_detected=True,
        unsupported_claims=["Claims 100x speedup not mentioned in source"],
        rejection_reasons=["Fabricated speedup metric"],
        feedback="Hallucination detected in benchmark claims.",
    )
    verifier.verify_draft = MagicMock(return_value=mock_resp)

    res = verifier.verify_draft("Copy with hallucination", sample_core, "linkedin")
    assert res.is_approved is False
    assert res.hallucination_detected is True
    assert len(res.unsupported_claims) == 1


def test_review_gate_enqueues_approved_draft(temp_workspace: Settings, sample_core: ResearchCoreData) -> None:
    """Verify ReviewGate transitions draft to APPROVED and enqueues to PublishingQueue."""
    db = Database(temp_workspace.database_path)
    run_migrations(db)

    disc_repo = DiscoveryRepository(db)
    draft_repo = ContentDraftRepository(db)
    queue_repo = PublishingQueueRepository(db)

    disc_repo.insert(
        DiscoveryRecord(id="d-eval", source_url="https://github.com/agent/benchmark", title="Benchmark", raw_content="...")
    )
    draft_repo.insert(
        ContentDraftRecord(
            id="draft-approved",
            discovery_id="d-eval",
            research_core=sample_core.model_dump(),
            generated_copy="Verified post content",
            platform="linkedin",
            format="post",
            status="DRAFTED",
        )
    )

    mock_client = MagicMock(spec=OpenRouterClient)
    verifier = ReviewVerifier(mock_client)
    verifier.verify_draft = MagicMock(
        return_value=ReviewResult(
            is_approved=True,
            overall_score=0.90,
            factual_accuracy_score=0.95,
            hook_strength_score=0.85,
            practical_usefulness_score=0.90,
            hallucination_detected=False,
            feedback="Great factual grounding.",
        )
    )

    gate = ReviewGate(db, verifier)
    stats = gate.process_pending_drafts()

    assert stats["approved"] == 1
    assert stats["rejected"] == 0

    # Draft should be APPROVED
    approved_draft = draft_repo.get_by_id("draft-approved")
    assert approved_draft.status == "APPROVED"

    # Queue should have pending item
    pending = queue_repo.get_pending()
    assert len(pending) == 1
    assert pending[0].content_id == "draft-approved"
    assert pending[0].publish_state == "PENDING"
