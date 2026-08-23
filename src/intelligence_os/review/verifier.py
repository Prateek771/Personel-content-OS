"""Automated Fact-Checker and Review Gate Verifier."""

import json
from pydantic import BaseModel, Field

from intelligence_os.core.logger import logger
from intelligence_os.intelligence.openrouter import OpenRouterClient
from intelligence_os.storage.models import ResearchCoreData


class ReviewResult(BaseModel):
    """Detailed evaluation from the automated quality and hallucination gate."""

    is_approved: bool
    overall_score: float = Field(ge=0.0, le=1.0)
    factual_accuracy_score: float = Field(ge=0.0, le=1.0)
    hook_strength_score: float = Field(ge=0.0, le=1.0)
    practical_usefulness_score: float = Field(ge=0.0, le=1.0)
    hallucination_detected: bool
    unsupported_claims: list[str] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)
    feedback: str = ""


REVIEW_SYSTEM_PROMPT = """You are the Senior Fact-Checking Gatekeeper and Editorial Auditor for AI Content Intelligence OS.
Your ONLY mission: enforce absolute factual accuracy and ruthless quality standards.

REVIEW CRITERIA:
1. FACTUAL GROUNDING: Every claim in the generated copy MUST be directly supported by the provided Research Core and Evidence. Any fabricated benchmark, hallucinated capability, or unsupported claim is an IMMEDIATE REJECTION.
2. HOOK QUALITY: Does the hook open directly with a specific, high-signal technical fact? (Reject vague buzzwords or cliches).
3. PRACTICAL UTILITY: Is there an actionable takeaway for a senior AI practitioner?
4. OVERCLAIMING: Does the copy claim more than the evidence proves?

PASSING THRESHOLD:
- overall_score >= 0.80
- hallucination_detected MUST be false
- unsupported_claims MUST be empty

You must respond strictly in JSON matching the requested schema."""


class ReviewVerifier:
    """Evaluates drafts against the underlying factual Research Core."""

    def __init__(self, openrouter_client: OpenRouterClient, passing_threshold: float = 0.80) -> None:
        self.client = openrouter_client
        self.passing_threshold = passing_threshold

    def verify_draft(self, generated_copy: str, research_core: ResearchCoreData, platform: str) -> ReviewResult:
        """Verify draft against research core."""
        logger.info(f"Running automated review gate on {platform} draft...")

        user_prompt = f"""EVIDENCE & RESEARCH CORE:
Hook: {research_core.hook}
Core Insight: {research_core.core_insight}
Evidence Sources: {', '.join(research_core.evidence)}
Practical Takeaway: {research_core.practical_takeaway}
Limitations: {research_core.limitations}
Content Angle: {research_core.content_angle}

GENERATED {platform.upper()} DRAFT TO AUDIT:
{generated_copy}

Please evaluate strictly and return JSON matching:
{{
  "is_approved": true,
  "overall_score": 0.88,
  "factual_accuracy_score": 0.95,
  "hook_strength_score": 0.85,
  "practical_usefulness_score": 0.90,
  "hallucination_detected": false,
  "unsupported_claims": [],
  "rejection_reasons": [],
  "feedback": "Concise editorial feedback summary"
}}"""

        messages = [
            {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        response_text = self.client.generate_chat_completion(messages, temperature=0.1)
        raw_json = json.loads(response_text)
        result = ReviewResult(**raw_json)

        # Enforce strict programmatic threshold
        if result.overall_score < self.passing_threshold or result.hallucination_detected or result.unsupported_claims:
            result.is_approved = False

        return result
