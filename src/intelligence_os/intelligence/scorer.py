"""Multi-factor scoring engine with temporal freshness decay and source tier calibration."""

import math
from datetime import datetime, timezone
from intelligence_os.intelligence.analyzer import GroundedAnalysisResult
from intelligence_os.storage.models import DiscoveryRecord


class ScoringWeights:
    """Configurable weights for calculating overall content potential."""

    def __init__(
        self,
        novelty_weight: float = 0.35,
        utility_weight: float = 0.35,
        evidence_weight: float = 0.15,
        freshness_weight: float = 0.15,
        half_life_days: float = 7.0,
    ) -> None:
        self.novelty_weight = novelty_weight
        self.utility_weight = utility_weight
        self.evidence_weight = evidence_weight
        self.freshness_weight = freshness_weight
        self.decay_constant = math.log(2) / half_life_days  # lambda = ln(2) / t_half


class DiscoveryScorer:
    """Calculates grounded multi-factor score and freshness decay."""

    def __init__(self, weights: ScoringWeights | None = None) -> None:
        self.weights = weights or ScoringWeights()

    def compute_freshness(self, timestamp_iso: str) -> float:
        """Calculate exponential time-decay freshness score between 0.0 and 1.0."""
        try:
            discovery_time = datetime.fromisoformat(timestamp_iso)
            if discovery_time.tzinfo is None:
                discovery_time = discovery_time.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            delta_days = max(0.0, (now - discovery_time).total_seconds() / 86400.0)
            return float(math.exp(-self.weights.decay_constant * delta_days))
        except Exception:
            return 1.0

    def calculate_score(
        self,
        analysis: GroundedAnalysisResult,
        discovery: DiscoveryRecord,
    ) -> tuple[float, float]:
        """Compute (freshness_score, content_potential)."""
        freshness = self.compute_freshness(discovery.discovery_timestamp)

        # Base composite score
        base_score = (
            (analysis.novelty_score * self.weights.novelty_weight)
            + (analysis.utility_score * self.weights.utility_weight)
            + (analysis.evidence_score * self.weights.evidence_weight)
            + (freshness * self.weights.freshness_weight)
        )

        # Source Tier Multiplier: Tier 1 (1.0), Tier 2 (0.85), Tier 3 (0.60)
        tier_multipliers = {1: 1.0, 2: 0.85, 3: 0.60}
        tier_mult = tier_multipliers.get(discovery.source_tier, 0.70)

        # Reproducibility bonus / penalty
        repro_mult = 1.05 if analysis.can_be_reproduced else 0.90

        # Publication worthiness check
        if not analysis.is_worth_publishing:
            base_score *= 0.50

        final_potential = round(min(1.0, max(0.0, base_score * tier_mult * repro_mult)), 4)
        return freshness, final_potential
