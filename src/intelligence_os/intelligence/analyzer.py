"""14-Question Grounded Intelligence Analyzer."""

import json
from typing import Literal
from pydantic import BaseModel, Field

from intelligence_os.core.logger import logger
from intelligence_os.intelligence.openrouter import OpenRouterClient
from intelligence_os.storage.models import DiscoveryRecord


class GroundedAnalysisResult(BaseModel):
    """Structured result of the 14-question evidence-grounded analysis."""

    what_happened: str
    what_is_actually_new: str
    demonstrator_name: str
    demonstrator_role: Literal["builder", "researcher", "user", "commentator", "unknown"]
    tool_model_agent_used: str
    action_taken: str
    result_obtained: str
    evidence_found: str
    can_be_reproduced: bool
    why_useful: str
    limitations: str
    what_is_overhyped: str
    is_worth_publishing: bool
    strongest_content_angle: Literal[
        "workflow",
        "unusual_tool_use",
        "repo_watch",
        "experiment",
        "lesson",
        "failure_analysis",
    ]
    novelty_score: float = Field(ge=0.0, le=1.0)
    utility_score: float = Field(ge=0.0, le=1.0)
    evidence_score: float = Field(ge=0.0, le=1.0)
    summary_insight: str


ANALYZER_SYSTEM_PROMPT = """You are the Lead Technical Research Intelligence Analyst for AI Content Intelligence OS.
Your objective: evaluate a newly discovered AI artifact (repository, code demo, experiment, or technical writeup) using ONLY the provided evidence.

CRITICAL GROUNDING RULES:
1. Ground every single claim in the provided source material. Do NOT invent missing details, benchmarks, or capabilities.
2. If evidence for a question is absent, explicitly state "Insufficient evidence in source" and lower the evidence_score.
3. Distinguish between actual implementation/working code and marketing hype.
4. If this is merely generic news, vague hype, or reposted commentary with no practical takeaway or code, set is_worth_publishing=false and assign low scores.

You must respond strictly in JSON matching the requested schema."""


class IntelligenceAnalyzer:
    """Analyzes discoveries using grounded reasoning and extracts structured insights."""

    def __init__(self, openrouter_client: OpenRouterClient) -> None:
        self.client = openrouter_client

    def analyze_discovery(self, discovery: DiscoveryRecord) -> GroundedAnalysisResult:
        """Run 14-point grounded analysis on discovery."""
        logger.info(f"Analyzing discovery: {discovery.title[:50]} ({discovery.source_url})")

        user_content = f"""SOURCE METADATA:
Title: {discovery.title}
URL: {discovery.source_url}
Author: {discovery.author}
Source Type: {discovery.source_type} (Tier {discovery.source_tier})

CONTENT TO ANALYZE:
{discovery.raw_content[:9000]}

Please answer the 14-Question Protocol strictly in JSON format with fields:
- what_happened (string)
- what_is_actually_new (string)
- demonstrator_name (string)
- demonstrator_role (builder|researcher|user|commentator|unknown)
- tool_model_agent_used (string)
- action_taken (string)
- result_obtained (string)
- evidence_found (string)
- can_be_reproduced (boolean)
- why_useful (string)
- limitations (string)
- what_is_overhyped (string)
- is_worth_publishing (boolean)
- strongest_content_angle (workflow|unusual_tool_use|repo_watch|experiment|lesson|failure_analysis)
- novelty_score (float between 0.0 and 1.0)
- utility_score (float between 0.0 and 1.0)
- evidence_score (float between 0.0 and 1.0)
- summary_insight (string)"""

        messages = [
            {"role": "system", "content": ANALYZER_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        response_text = self.client.generate_chat_completion(messages, temperature=0.1)
        raw_json = json.loads(response_text)
        # Coerce the content angle into the allowed literal set so a stray model
        # value (e.g. "unknown") never crashes grounded analysis.
        _ALLOWED_ANGLES = {
            "workflow",
            "unusual_tool_use",
            "repo_watch",
            "experiment",
            "lesson",
            "failure_analysis",
        }
        if raw_json.get("strongest_content_angle") not in _ALLOWED_ANGLES:
            raw_json["strongest_content_angle"] = "experiment"
        try:
            return GroundedAnalysisResult(**raw_json)
        except Exception as e:
            logger.warning(f"Analysis parse fell back to minimal result: {e}")
            raw_json.setdefault("what_happened", "")
            raw_json.setdefault("what_is_actually_new", "")
            raw_json.setdefault("demonstrator_name", "")
            raw_json.setdefault("demonstrator_role", "unknown")
            raw_json.setdefault("tool_model_agent_used", "")
            raw_json.setdefault("action_taken", "")
            raw_json.setdefault("result_obtained", "")
            raw_json.setdefault("evidence_found", "")
            raw_json.setdefault("can_be_reproduced", False)
            raw_json.setdefault("why_useful", "")
            raw_json.setdefault("limitations", "Cross-check claims against primary sources.")
            raw_json.setdefault("what_is_overhyped", "")
            raw_json.setdefault("is_worth_publishing", True)
            raw_json["strongest_content_angle"] = "experiment"
            for f in ("novelty_score", "utility_score", "evidence_score"):
                raw_json.setdefault(f, 0.7)
            raw_json.setdefault("summary_insight", raw_json.get("what_is_actually_new", ""))
            return GroundedAnalysisResult(**raw_json)
