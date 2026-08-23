"""Intelligence Brief compilation and Silent Mode enforcement."""

from typing import Any
from pydantic import BaseModel, Field

from intelligence_os.core.logger import logger
from intelligence_os.intelligence.analyzer import GroundedAnalysisResult, IntelligenceAnalyzer
from intelligence_os.intelligence.research_core import build_research_core
from intelligence_os.intelligence.scorer import DiscoveryScorer
from intelligence_os.storage.db import Database
from intelligence_os.storage.models import DiscoveryRecord, ResearchCoreData, utc_now_iso
from intelligence_os.storage.repositories import DiscoveryRepository


class TopicOpportunity(BaseModel):
    """A scored, ranked technical topic selected for content publishing."""

    discovery_id: str
    title: str
    source_url: str
    content_potential: float
    content_angle: str
    research_core: ResearchCoreData
    rationale: str


class IntelligenceBrief(BaseModel):
    """Internal intelligence brief synthesized at the end of an intelligence cycle."""

    generated_at: str = Field(default_factory=utc_now_iso)
    is_silent_mode: bool
    silent_mode_reason: str = ""
    total_evaluated: int
    selected_opportunities: list[TopicOpportunity] = Field(default_factory=list)
    top_themes: list[str] = Field(default_factory=list)


class IntelligenceOrchestrator:
    """Coordinates analysis, scoring, Silent Mode detection, and brief generation."""

    def __init__(
        self,
        db: Database,
        analyzer: IntelligenceAnalyzer,
        scorer: DiscoveryScorer | None = None,
        min_content_score: float = 0.65,
    ) -> None:
        self.db = db
        self.discovery_repo = DiscoveryRepository(db)
        self.analyzer = analyzer
        self.scorer = scorer or DiscoveryScorer()
        self.min_content_score = min_content_score

    def run_intelligence_cycle(self, limit: int = 20) -> IntelligenceBrief:
        """Process 'DEDUPED' discoveries through 14-point analysis, scoring, and brief generation."""
        logger.info("Starting intelligence analysis and scoring cycle...")
        pending_items = self.discovery_repo.list_by_status("DEDUPED", limit=limit)

        opportunities: list[TopicOpportunity] = []

        for item in pending_items:
            try:
                # 1. Run 14-point Grounded Analysis
                analysis = self.analyzer.analyze_discovery(item)

                # 2. Score Discovery
                freshness, potential = self.scorer.calculate_score(analysis, item)

                # 3. Update Database Record
                new_status = "BRIEF_READY" if potential >= self.min_content_score else "SILENT_DISMISSED"
                self.discovery_repo.update_scores_and_status(
                    discovery_id=item.id,
                    novelty=analysis.novelty_score,
                    utility=analysis.utility_score,
                    evidence=analysis.evidence_score,
                    potential=potential,
                    status=new_status,
                    content_angle=analysis.strongest_content_angle,
                    verification_notes=f"Evidence: {analysis.evidence_found} | Reproducible: {analysis.can_be_reproduced}",
                )

                # 4. If passed score threshold, construct Research Core and queue opportunity
                if potential >= self.min_content_score:
                    core = build_research_core(item, analysis)
                    opportunities.append(
                        TopicOpportunity(
                            discovery_id=item.id,
                            title=item.title,
                            source_url=item.source_url,
                            content_potential=potential,
                            content_angle=analysis.strongest_content_angle,
                            research_core=core,
                            rationale=f"High score ({potential:.2f}): {analysis.why_useful[:150]}",
                        )
                    )
            except Exception as e:
                logger.error(f"Error analyzing discovery {item.id} ({item.source_url}): {e}")

        # Rank opportunities by content potential
        opportunities.sort(key=lambda o: o.content_potential, reverse=True)

        # Evaluate Silent Mode
        if not opportunities:
            logger.info("SILENT MODE ACTIVATED: NO PUBLISHABLE INTELLIGENCE meets the quality/evidence threshold.")
            return IntelligenceBrief(
                is_silent_mode=True,
                silent_mode_reason="NO PUBLISHABLE INTELLIGENCE — No discovered item passed the 0.65 evidence/utility threshold.",
                total_evaluated=len(pending_items),
                selected_opportunities=[],
            )

        logger.info(f"Intelligence cycle produced {len(opportunities)} qualified topic opportunities.")
        return IntelligenceBrief(
            is_silent_mode=False,
            total_evaluated=len(pending_items),
            selected_opportunities=opportunities[:3],  # Top 3 highest signal
            top_themes=list({o.content_angle for o in opportunities}),
        )
