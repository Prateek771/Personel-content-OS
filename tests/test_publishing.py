"""Tests for Phase 18 & 19: Publishing Integrations (LinkedIn & X) and Dispatcher."""

import pytest
from unittest.mock import MagicMock

from intelligence_os.config.settings import Settings
from intelligence_os.core.exceptions import PublishingError
from intelligence_os.publishing.dispatcher import PublishingDispatcher
from intelligence_os.publishing.linkedin import LinkedInPublisher
from intelligence_os.publishing.x import XPublisher
from intelligence_os.storage.db import Database
from intelligence_os.storage.migrations import run_migrations
from intelligence_os.storage.models import ContentDraftRecord, DiscoveryRecord, PublishingQueueRecord
from intelligence_os.storage.repositories import ContentDraftRepository, DiscoveryRepository, PublishingQueueRepository


def test_publishing_dispatcher_flow(temp_workspace: Settings) -> None:
    """Verify PublishingDispatcher fetches pending item, dispatches to publisher, and updates queue state."""
    db = Database(temp_workspace.database_path)
    run_migrations(db)

    disc_repo = DiscoveryRepository(db)
    draft_repo = ContentDraftRepository(db)
    queue_repo = PublishingQueueRepository(db)

    disc_repo.insert(DiscoveryRecord(id="d-pub", source_url="https://github.com/agent/pub", title="Pub", raw_content="..."))
    draft_repo.insert(
        ContentDraftRecord(
            id="draft-li",
            discovery_id="d-pub",
            research_core={},
            generated_copy="LinkedIn approved copy",
            platform="linkedin",
            format="post",
            status="APPROVED",
        )
    )
    queue_repo.enqueue(
        PublishingQueueRecord(
            id="q-li",
            content_id="draft-li",
            platform="linkedin",
            publish_state="PENDING",
        )
    )

    mock_li_pub = MagicMock(spec=LinkedInPublisher)
    mock_li_pub.is_configured.return_value = True
    mock_li_pub.publish.return_value = "urn:li:share:123456789"

    dispatcher = PublishingDispatcher(db, linkedin_publisher=mock_li_pub)
    stats = dispatcher.dispatch_pending()

    assert stats["published"] == 1
    assert stats["failed_retrying"] == 0

    # Queue item should no longer be pending
    pending = queue_repo.get_pending()
    assert len(pending) == 0


def test_publishing_dispatcher_retry_on_failure(temp_workspace: Settings) -> None:
    """Verify PublishingDispatcher records error and increments retry count on API failure."""
    db = Database(temp_workspace.database_path)
    run_migrations(db)

    disc_repo = DiscoveryRepository(db)
    draft_repo = ContentDraftRepository(db)
    queue_repo = PublishingQueueRepository(db)

    disc_repo.insert(DiscoveryRecord(id="d-fail", source_url="https://github.com/agent/fail", title="Fail", raw_content="..."))
    draft_repo.insert(
        ContentDraftRecord(
            id="draft-x-fail",
            discovery_id="d-fail",
            research_core={},
            generated_copy="X post copy",
            platform="x",
            format="post",
            status="APPROVED",
        )
    )
    queue_repo.enqueue(
        PublishingQueueRecord(
            id="q-x-fail",
            content_id="draft-x-fail",
            platform="x",
            publish_state="PENDING",
            retry_count=0,
            max_retries=3,
        )
    )

    mock_x_pub = MagicMock(spec=XPublisher)
    mock_x_pub.is_configured.return_value = True
    mock_x_pub.publish.side_effect = PublishingError("Rate limit exceeded (429)")

    dispatcher = PublishingDispatcher(db, x_publisher=mock_x_pub)
    stats = dispatcher.dispatch_pending()

    assert stats["published"] == 0
    assert stats["failed_retrying"] == 1

    # Should remain in queue with RETRYING status and retry_count=1
    pending = queue_repo.get_pending()
    assert len(pending) == 1
    assert pending[0].publish_state == "RETRYING"
    assert pending[0].retry_count == 1
