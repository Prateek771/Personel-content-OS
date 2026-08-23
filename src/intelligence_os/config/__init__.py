"""Configuration package for AI Content Intelligence OS."""

from intelligence_os.config.settings import Settings, get_settings
from intelligence_os.config.sources_manager import (
    SourceManager,
    SourcesConfig,
    TopicsConfig,
    PersonWatchlistEntry,
    SourceConfigEntry,
    TopicConfigEntry,
)

__all__ = [
    "Settings",
    "get_settings",
    "SourceManager",
    "SourcesConfig",
    "TopicsConfig",
    "PersonWatchlistEntry",
    "SourceConfigEntry",
    "TopicConfigEntry",
]
