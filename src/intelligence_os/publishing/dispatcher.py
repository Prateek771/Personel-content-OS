"""Publishing Dispatcher managing transactional queue processing."""

from intelligence_os.core.exceptions import PublishingError
from intelligence_os.core.logger import logger
from intelligence_os.publishing.base import BasePublisher
from intelligence_os.publishing.linkedin import LinkedInPublisher
from intelligence_os.publishing.x import XPublisher
from intelligence_os.storage.db import Database
from intelligence_os.storage.repositories import ContentDraftRepository, PublishingQueueRepository


class PublishingDispatcher:
    """Consumes pending items from the publishing queue and dispatches to configured publishers."""

    def __init__(
        self,
        db: Database,
        linkedin_publisher: LinkedInPublisher | None = None,
        x_publisher: XPublisher | None = None,
    ) -> None:
        self.db = db
        self.draft_repo = ContentDraftRepository(db)
        self.queue_repo = PublishingQueueRepository(db)
        self.publishers: dict[str, BasePublisher] = {}

        if linkedin_publisher:
            self.publishers["linkedin"] = linkedin_publisher
        if x_publisher:
            self.publishers["x"] = x_publisher

    def dispatch_pending(self, limit: int = 5) -> dict[str, int]:
        """Dispatch pending queue items to appropriate platforms."""
        pending_items = self.queue_repo.get_pending(limit=limit)
        stats = {
            "pending_found": len(pending_items),
            "published": 0,
            "failed_retrying": 0,
            "skipped_unconfigured": 0,
        }

        for item in pending_items:
            publisher = self.publishers.get(item.platform)
            if not publisher or not publisher.is_configured():
                logger.debug(f"Publisher for platform '{item.platform}' not configured. Retaining in queue.")
                stats["skipped_unconfigured"] += 1
                continue

            draft = self.draft_repo.get_by_id(item.content_id)
            if not draft:
                logger.error(f"Draft {item.content_id} not found for queue item {item.id}. Marking failed.")
                self.queue_repo.record_failure(item.id, "Draft record missing")
                stats["failed_retrying"] += 1
                continue

            try:
                platform_post_id = publisher.publish(draft)
                self.queue_repo.mark_published(item.id, platform_post_id=platform_post_id)
                stats["published"] += 1
            except PublishingError as e:
                logger.warning(f"Publishing failed for queue item {item.id}: {e}")
                self.queue_repo.record_failure(item.id, str(e))
                stats["failed_retrying"] += 1

        return stats
