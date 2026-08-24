"""Research harvesting and adapters package."""

from intelligence_os.research.adapters.base import BaseResearchAdapter, RawHarvestItem
from intelligence_os.research.adapters.scrapling import ScraplingAdapter
from intelligence_os.research.adapters.rss import RSSAdapter
from intelligence_os.research.adapters.agent_reach import AgentReachAdapter
from intelligence_os.research.adapters.github import GitHubAdapter
from intelligence_os.research.adapters.x import XAdapter

__all__ = [
    "BaseResearchAdapter",
    "RawHarvestItem",
    "ScraplingAdapter",
    "RSSAdapter",
    "AgentReachAdapter",
    "GitHubAdapter",
    "XAdapter",
]
