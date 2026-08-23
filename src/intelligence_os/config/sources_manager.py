"""Manager and Pydantic schemas for sources.yaml and topics.yaml configuration."""

from pathlib import Path
from typing import Literal
import yaml
from pydantic import BaseModel, Field

from intelligence_os.core.exceptions import ConfigurationError
from intelligence_os.core.logger import logger


class PersonWatchlistEntry(BaseModel):
    """Builder or researcher to monitor for high-signal technical experiments."""

    id: str
    name: str
    role: str = ""
    source_tier: int = 1
    handles: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
    priority: Literal["high", "medium", "low"] = "medium"


class SourceConfigEntry(BaseModel):
    """Configured research harvesting source."""

    id: str
    name: str
    source_type: Literal["github", "firecrawl", "agent_reach", "rss", "web"]
    source_tier: int = 1
    target: str
    polling_frequency_minutes: int = 180
    enabled: bool = True
    priority: Literal["high", "medium", "low"] = "medium"
    extraction_hints: list[str] = Field(default_factory=list)


class SourcesConfig(BaseModel):
    """Root configuration model for sources.yaml."""

    version: float = 1.0
    people: list[PersonWatchlistEntry] = Field(default_factory=list)
    sources: list[SourceConfigEntry] = Field(default_factory=list)


class TopicConfigEntry(BaseModel):
    """Taxonomy category for research focus and scoring weights."""

    id: str
    name: str
    weight: float = 1.0
    keywords: list[str] = Field(default_factory=list)
    preferred_angles: list[str] = Field(default_factory=list)


class TopicsConfig(BaseModel):
    """Root configuration model for topics.yaml."""

    version: float = 1.0
    topics: list[TopicConfigEntry] = Field(default_factory=list)


class SourceManager:
    """Loads and queries declarative research sources and topic definitions."""

    def __init__(
        self,
        sources_path: str | Path = "config/sources.yaml",
        topics_path: str | Path = "config/topics.yaml",
    ) -> None:
        self.sources_path = Path(sources_path)
        self.topics_path = Path(topics_path)
        self.sources_config: SourcesConfig | None = None
        self.topics_config: TopicsConfig | None = None
        self.load()

    def load(self) -> None:
        """Load and validate sources and topics from YAML files."""
        if not self.sources_path.exists():
            raise ConfigurationError(f"Sources config file missing: {self.sources_path}")
        if not self.topics_path.exists():
            raise ConfigurationError(f"Topics config file missing: {self.topics_path}")

        try:
            with open(self.sources_path, "r", encoding="utf-8") as f:
                raw_sources = yaml.safe_load(f)
                self.sources_config = SourcesConfig(**raw_sources)
        except Exception as e:
            logger.error(f"Failed to parse {self.sources_path}: {e}")
            raise ConfigurationError(f"Invalid sources configuration: {e}") from e

        try:
            with open(self.topics_path, "r", encoding="utf-8") as f:
                raw_topics = yaml.safe_load(f)
                self.topics_config = TopicsConfig(**raw_topics)
        except Exception as e:
            logger.error(f"Failed to parse {self.topics_path}: {e}")
            raise ConfigurationError(f"Invalid topics configuration: {e}") from e

    def get_enabled_sources(
        self, source_type: str | None = None, priority: str | None = None
    ) -> list[SourceConfigEntry]:
        """Return enabled sources filtered by type and priority."""
        if not self.sources_config:
            return []
        results = [s for s in self.sources_config.sources if s.enabled]
        if source_type:
            results = [s for s in results if s.source_type == source_type]
        if priority:
            results = [s for s in results if s.priority == priority]
        return results

    def get_enabled_people(self) -> list[PersonWatchlistEntry]:
        """Return enabled monitored builders and researchers."""
        if not self.sources_config:
            return []
        return [p for p in self.sources_config.people if p.enabled]

    def get_topics(self) -> list[TopicConfigEntry]:
        """Return all configured topic categories."""
        if not self.topics_config:
            return []
        return self.topics_config.topics
