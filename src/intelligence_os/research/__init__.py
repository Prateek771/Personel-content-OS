"""Research harvesting and adapters package."""

from intelligence_os.research.adapters.base import BaseResearchAdapter, RawHarvestItem
from intelligence_os.research.adapters.firecrawl import FirecrawlAdapter
from intelligence_os.research.adapters.agent_reach import AgentReachAdapter
from intelligence_os.research.adapters.github import GitHubAdapter

__all__ = [
    "BaseResearchAdapter",
    "RawHarvestItem",
    "FirecrawlAdapter",
    "AgentReachAdapter",
    "GitHubAdapter",
]
