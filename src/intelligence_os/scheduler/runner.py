"""Autonomous execution runner and pipeline coordinator."""

import time
from typing import Any
from intelligence_os.config.settings import Settings, get_settings
from intelligence_os.config.sources_manager import SourceManager
from intelligence_os.content.generator import ContentOrchestrator
from intelligence_os.core.logger import logger
from intelligence_os.dedup.engine import DeduplicationEngine
from intelligence_os.intelligence.analyzer import IntelligenceAnalyzer
from intelligence_os.intelligence.brief import IntelligenceOrchestrator
from intelligence_os.intelligence.openrouter import OpenRouterClient
from intelligence_os.publishing.dispatcher import PublishingDispatcher
from intelligence_os.publishing.linkedin import LinkedInPublisher
from intelligence_os.publishing.x import XPublisher
from intelligence_os.research.adapters.firecrawl import FirecrawlAdapter
from intelligence_os.research.adapters.github import GitHubAdapter
from intelligence_os.research.adapters.agent_reach import AgentReachAdapter
from intelligence_os.research.harvest_engine import HarvestEngine
from intelligence_os.review.gate import ReviewGate
from intelligence_os.review.verifier import ReviewVerifier
from intelligence_os.storage.db import Database
from intelligence_os.storage.migrations import run_migrations
from intelligence_os.storage.repositories import DiscoveryRepository


class PipelineRunner:
    """Coordinates end-to-end execution of the Content Intelligence OS."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.db = Database(self.settings.database_path)
        run_migrations(self.db)

        # Config & Sources
        self.source_manager = SourceManager()

        # Research Adapters
        self.firecrawl = FirecrawlAdapter(
            base_url=self.settings.firecrawl_base_url,
            api_key=self.settings.firecrawl_api_key,
        )
        self.agent_reach = AgentReachAdapter(
            base_url=self.settings.agent_reach_base_url,
            api_key=self.settings.agent_reach_api_key,
        )
        self.github = GitHubAdapter(token=self.settings.github_token)

        # Harvest Engine
        self.harvest_engine = HarvestEngine(
            source_manager=self.source_manager,
            db=self.db,
            firecrawl_adapter=self.firecrawl,
            agent_reach_adapter=self.agent_reach,
            github_adapter=self.github,
        )

        # Deduplication
        self.dedup_engine = DeduplicationEngine(self.db)

        # Intelligence
        self.openrouter = OpenRouterClient(self.settings)
        self.analyzer = IntelligenceAnalyzer(self.openrouter)
        self.intel_orchestrator = IntelligenceOrchestrator(
            db=self.db,
            analyzer=self.analyzer,
            min_content_score=self.settings.min_content_score,
        )

        # Content
        self.content_orchestrator = ContentOrchestrator(self.db, self.openrouter)

        # Review Gate
        self.verifier = ReviewVerifier(self.openrouter)
        self.review_gate = ReviewGate(self.db, self.verifier)

        # Publishing
        self.linkedin_pub = LinkedInPublisher(self.settings)
        self.x_pub = XPublisher(self.settings)
        self.dispatcher = PublishingDispatcher(
            self.db,
            linkedin_publisher=self.linkedin_pub,
            x_publisher=self.x_pub,
        )

    def run_full_pipeline_cycle(self) -> dict[str, Any]:
        """Execute a single end-to-end pipeline run."""
        logger.info("=== Starting AI Content Intelligence Pipeline Cycle ===")
        results: dict[str, Any] = {}

        # 1. Harvest
        results["harvest"] = self.harvest_engine.run_harvest_cycle()

        # 2. Dedup
        results["dedup"] = self.dedup_engine.process_raw_ingested()

        # 3. Intelligence & Brief
        brief = self.intel_orchestrator.run_intelligence_cycle()
        results["brief"] = brief.model_dump()

        if brief.is_silent_mode:
            logger.info("=== Pipeline Cycle Finished in SILENT MODE ===")
            return results

        # 4. Content Generation for top opportunities
        discovery_repo = DiscoveryRepository(self.db)
        generated_draft_count = 0
        for opp in brief.selected_opportunities:
            discovery = discovery_repo.get_by_id(opp.discovery_id)
            if discovery:
                drafts = self.content_orchestrator.generate_drafts_for_discovery(
                    discovery=discovery,
                    research_core=opp.research_core,
                )
                generated_draft_count += len(drafts)
        results["content_drafts_generated"] = generated_draft_count

        # 5. Review Gate
        results["review_gate"] = self.review_gate.process_pending_drafts()

        # 6. Publishing Dispatch
        results["publishing"] = self.dispatcher.dispatch_pending()

        logger.info("=== AI Content Intelligence Pipeline Cycle Completed Successfully ===")
        return results
