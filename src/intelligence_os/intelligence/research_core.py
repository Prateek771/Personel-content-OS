"""Research Core generator synthesizing the factual blueprint for content generation."""

from intelligence_os.intelligence.analyzer import GroundedAnalysisResult
from intelligence_os.storage.models import DiscoveryRecord, ResearchCoreData


def build_research_core(
    discovery: DiscoveryRecord,
    analysis: GroundedAnalysisResult,
) -> ResearchCoreData:
    """Construct a clean, reusable Research Core strictly grounded in verified facts."""
    hook = (
        f"How {analysis.demonstrator_name or 'engineers'} achieved {analysis.result_obtained[:100]} "
        f"using {analysis.tool_model_agent_used}."
    )
    if analysis.strongest_content_angle == "repo_watch":
        hook = f"New AI repository breakdown: {discovery.title.split(':')[0]} — {analysis.what_is_actually_new[:120]}"
    elif analysis.strongest_content_angle == "workflow":
        hook = f"A new agentic workflow pattern: {analysis.action_taken[:120]}"
    elif analysis.strongest_content_angle == "failure_analysis":
        hook = f"Why {analysis.tool_model_agent_used} hits limits: {analysis.limitations[:120]}"

    evidence_list = [discovery.source_url]
    if discovery.linked_discoveries:
        evidence_list.extend(discovery.linked_discoveries)

    return ResearchCoreData(
        hook=hook,
        core_insight=analysis.summary_insight or analysis.what_is_actually_new,
        evidence=evidence_list,
        practical_takeaway=analysis.why_useful,
        limitations=analysis.limitations or "No critical blockers stated; requires environment validation.",
        content_angle=analysis.strongest_content_angle,
        tags=[analysis.tool_model_agent_used, analysis.strongest_content_angle, discovery.source_type],
    )
