"""Base interface and data models for all research adapters."""

from abc import ABC, abstractmethod
from typing import Any
from pydantic import BaseModel, Field
from intelligence_os.storage.models import utc_now_iso


class RawHarvestItem(BaseModel):
    """Normalized raw harvested payload from any research adapter."""

    source_url: str
    title: str
    raw_content: str
    markdown_content: str = ""
    author: str = ""
    source_type: str  # firecrawl, github, agent_reach, web
    source_tier: int = 1
    metadata: dict[str, Any] = Field(default_factory=dict)
    harvested_at: str = Field(default_factory=utc_now_iso)


class BaseResearchAdapter(ABC):
    """Abstract base class for research adapters."""

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def harvest(self, target: str, **kwargs: Any) -> list[RawHarvestItem]:
        """Harvest raw content from the specified target (URL, query, or repo)."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check whether the adapter service / endpoint is reachable and ready."""
        pass
