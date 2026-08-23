"""Intelligence analysis, reasoning, and scoring package."""

from intelligence_os.intelligence.openrouter import OpenRouterClient
from intelligence_os.intelligence.analyzer import GroundedAnalysisResult, IntelligenceAnalyzer
from intelligence_os.intelligence.scorer import ScoringWeights, DiscoveryScorer
from intelligence_os.intelligence.research_core import build_research_core
from intelligence_os.intelligence.brief import (
    TopicOpportunity,
    IntelligenceBrief,
    IntelligenceOrchestrator,
)

__all__ = [
    "OpenRouterClient",
    "GroundedAnalysisResult",
    "IntelligenceAnalyzer",
    "ScoringWeights",
    "DiscoveryScorer",
    "build_research_core",
    "TopicOpportunity",
    "IntelligenceBrief",
    "IntelligenceOrchestrator",
]
