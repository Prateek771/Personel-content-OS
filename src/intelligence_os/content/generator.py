"""Unified Content Orchestrator coordinating multi-platform content generation."""

import uuid
from intelligence_os.content.linkedin import LinkedInGenerator, LinkedInContentResult
from intelligence_os.content.x import XGenerator, XContentResult
from intelligence_os.core.logger import logger
from intelligence_os.intelligence.openrouter import OpenRouterClient
from intelligence_os.storage.db import Database
from intelligence_os.storage.models import ContentDraftRecord, DiscoveryRecord, ResearchCoreData
from intelligence_os.storage.repositories import ContentDraftRepository


class ContentOrchestrator:
    """Coordinates generation of multi-platform drafts from verified Research Cores."""

    def __init__(self, db: Database, openrouter_client: OpenRouterClient) -> None:
        self.db = db
        self.draft_repo = ContentDraftRepository(db)
        self.linkedin_gen = LinkedInGenerator(openrouter_client)
        self.x_gen = XGenerator(openrouter_client)

    def generate_drafts_for_discovery(
        self,
        discovery: DiscoveryRecord,
        research_core: ResearchCoreData,
    ) -> list[ContentDraftRecord]:
        """Generate LinkedIn and X drafts and save to database."""
        logger.info(f"Generating multi-platform content drafts for discovery: {discovery.id}")
        drafts: list[ContentDraftRecord] = []

        # 1. LinkedIn Draft (Post or Carousel based on angle)
        li_format = "carousel" if research_core.content_angle in ["workflow", "unusual_tool_use"] else "post"
        try:
            li_result: LinkedInContentResult = self.linkedin_gen.generate(
                research_core, preferred_format=li_format
            )
            li_draft = ContentDraftRecord(
                id=f"draft-li-{uuid.uuid4().hex[:10]}",
                discovery_id=discovery.id,
                research_core=research_core.model_dump(),
                generated_copy=li_result.post_copy,
                platform="linkedin",
                format=li_result.format,
                visual_asset_path=None,  # Populated during Phase 16
                status="DRAFTED",
            )
            self.draft_repo.insert(li_draft)
            drafts.append(li_draft)
        except Exception as e:
            logger.error(f"Failed to generate LinkedIn draft for {discovery.id}: {e}")

        # 2. X Draft (Thread or Post)
        x_format = "thread" if research_core.content_angle in ["workflow", "repo_watch", "experiment"] else "post"
        try:
            x_result: XContentResult = self.x_gen.generate(research_core, preferred_format=x_format)
            x_draft = ContentDraftRecord(
                id=f"draft-x-{uuid.uuid4().hex[:10]}",
                discovery_id=discovery.id,
                research_core=research_core.model_dump(),
                generated_copy=x_result.full_text_rendered,
                platform="x",
                format=x_result.format,
                status="DRAFTED",
            )
            self.draft_repo.insert(x_draft)
            drafts.append(x_draft)
        except Exception as e:
            logger.error(f"Failed to generate X draft for {discovery.id}: {e}")

        return drafts
