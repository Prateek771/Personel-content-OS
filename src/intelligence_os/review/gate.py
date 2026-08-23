"""Review Gate workflow orchestrating draft verification and queue dispatch."""

import uuid
from intelligence_os.core.logger import logger
from intelligence_os.review.verifier import ReviewVerifier, ReviewResult
from intelligence_os.storage.db import Database
from intelligence_os.storage.models import ContentDraftRecord, PublishingQueueRecord, ResearchCoreData
from intelligence_os.storage.repositories import ContentDraftRepository, PublishingQueueRepository


class ReviewGate:
    """Orchestrates draft reviews and automatically routes approved content to the publishing queue."""

    def __init__(
        self,
        db: Database,
        verifier: ReviewVerifier,
        max_rewrite_attempts: int = 2,
    ) -> None:
        self.db = db
        self.draft_repo = ContentDraftRepository(db)
        self.queue_repo = PublishingQueueRepository(db)
        self.verifier = verifier
        self.max_rewrite_attempts = max_rewrite_attempts

    def process_pending_drafts(self) -> dict[str, int]:
        """Review all drafts in 'DRAFTED' or 'IN_REVIEW' state."""
        pending_drafts = self.draft_repo.list_by_status("DRAFTED", limit=20)
        stats = {
            "evaluated": len(pending_drafts),
            "approved": 0,
            "rejected": 0,
        }

        for draft in pending_drafts:
            try:
                core = ResearchCoreData(**draft.research_core)
                review: ReviewResult = self.verifier.verify_draft(
                    generated_copy=draft.generated_copy,
                    research_core=core,
                    platform=draft.platform,
                )

                if review.is_approved:
                    logger.info(f"Draft {draft.id} ({draft.platform}) PASSED review gate with score {review.overall_score:.2f}.")
                    self.draft_repo.update_review(
                        draft_id=draft.id,
                        review_score=review.overall_score,
                        review_feedback=review.feedback,
                        status="APPROVED",
                    )
                    # Enqueue to persistent publishing queue
                    queue_item = PublishingQueueRecord(
                        id=f"queue-{uuid.uuid4().hex[:10]}",
                        content_id=draft.id,
                        platform=draft.platform,
                        publish_state="PENDING",
                    )
                    self.queue_repo.enqueue(queue_item)
                    stats["approved"] += 1
                else:
                    logger.warning(
                        f"Draft {draft.id} REJECTED by review gate (Score: {review.overall_score:.2f}). "
                        f"Reasons: {', '.join(review.rejection_reasons or review.unsupported_claims)}"
                    )
                    self.draft_repo.update_review(
                        draft_id=draft.id,
                        review_score=review.overall_score,
                        review_feedback=f"REJECTED: {review.feedback} | Claims: {review.unsupported_claims}",
                        status="REJECTED",
                    )
                    stats["rejected"] += 1

            except Exception as e:
                logger.error(f"Error processing review for draft {draft.id}: {e}")

        return stats
