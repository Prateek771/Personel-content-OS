"""Unified Harvest Engine coordinating multi-source research ingestion."""

import hashlib
from typing import Any
from intelligence_os.config.sources_manager import SourceManager, SourceConfigEntry, PersonWatchlistEntry
from intelligence_os.core.logger import logger
from intelligence_os.research.adapters.base import BaseResearchAdapter, RawHarvestItem
from intelligence_os.research.adapters.firecrawl import FirecrawlAdapter
from intelligence_os.research.adapters.agent_reach import AgentReachAdapter
from intelligence_os.research.adapters.github import GitHubAdapter
from intelligence_os.storage.db import Database
from intelligence_os.storage.models import DiscoveryRecord
from intelligence_os.storage.repositories import DiscoveryRepository


def generate_discovery_id(url: str) -> str:
    """Generate a deterministic SHA-256 hash ID for a URL."""
    return f"disc-{hashlib.sha256(url.strip().encode('utf-8')).hexdigest()[:16]}"


class HarvestEngine:
    """Autonomous coordinator for polling research sources and persisting raw findings."""

    def __init__(
        self,
        source_manager: SourceManager,
        db: Database,
        firecrawl_adapter: FirecrawlAdapter | None = None,
        agent_reach_adapter: AgentReachAdapter | None = None,
        github_adapter: GitHubAdapter | None = None,
    ) -> None:
        self.source_manager = source_manager
        self.db = db
        self.discovery_repo = DiscoveryRepository(db)
        self.adapters: dict[str, BaseResearchAdapter] = {}

        if firecrawl_adapter:
            self.adapters["firecrawl"] = firecrawl_adapter
            self.adapters["web"] = firecrawl_adapter
        if agent_reach_adapter:
            self.adapters["agent_reach"] = agent_reach_adapter
        if github_adapter:
            self.adapters["github"] = github_adapter

    def run_harvest_cycle(self) -> dict[str, Any]:
        """Execute a complete harvest cycle across all enabled sources and people watchlist."""
        logger.info("Starting research harvest cycle...")
        stats = {
            "sources_processed": 0,
            "items_harvested": 0,
            "new_inserted": 0,
            "duplicates_skipped": 0,
            "errors": [],
        }

        # 1. Harvest Configured Sources
        for source in self.source_manager.get_enabled_sources():
            stats["sources_processed"] += 1
            adapter = self.adapters.get(source.source_type)
            if not adapter:
                logger.debug(f"No adapter registered for source type '{source.source_type}' ({source.id}). Skipping.")
                continue

            try:
                logger.info(f"Harvesting source '{source.name}' via {source.source_type}...")
                items = adapter.harvest(source.target)
                self._process_harvested_items(items, source.source_tier, stats)
            except Exception as e:
                err_msg = f"Harvest error for source '{source.id}': {e}"
                logger.error(err_msg)
                stats["errors"].append({"source_id": source.id, "error": str(e)})

        # 2. Harvest Monitored People Watchlist
        for person in self.source_manager.get_enabled_people():
            self._harvest_person(person, stats)

        logger.info(
            f"Harvest cycle finished: {stats['items_harvested']} items retrieved, "
            f"{stats['new_inserted']} new discoveries stored, {stats['duplicates_skipped']} duplicates skipped."
        )
        return stats

    def _harvest_person(self, person: PersonWatchlistEntry, stats: dict[str, Any]) -> None:
        """Poll activity handles for a monitored builder/researcher."""
        # GitHub Handle
        if "github" in person.handles and "github" in self.adapters:
            gh_user = person.handles["github"]
            try:
                items = self.adapters["github"].harvest(f"user:{gh_user} sort:updated")
                self._process_harvested_items(items, person.source_tier, stats)
            except Exception as e:
                logger.warning(f"Error harvesting GitHub activity for person {person.name}: {e}")
                stats["errors"].append({"person": person.id, "handle": "github", "error": str(e)})

        # Blog / Web Handle
        if "blog" in person.handles and "firecrawl" in self.adapters:
            blog_url = person.handles["blog"]
            try:
                items = self.adapters["firecrawl"].harvest(blog_url)
                self._process_harvested_items(items, person.source_tier, stats)
            except Exception as e:
                logger.warning(f"Error harvesting blog for person {person.name}: {e}")
                stats["errors"].append({"person": person.id, "handle": "blog", "error": str(e)})

        # Social / X via Agent Reach
        if "x" in person.handles and "agent_reach" in self.adapters:
            x_handle = person.handles["x"]
            try:
                items = self.adapters["agent_reach"].harvest(f"from:{x_handle}")
                self._process_harvested_items(items, person.source_tier, stats)
            except Exception as e:
                logger.warning(f"Error harvesting social for person {person.name}: {e}")
                stats["errors"].append({"person": person.id, "handle": "x", "error": str(e)})

    def _process_harvested_items(
        self, items: list[RawHarvestItem], source_tier: int, stats: dict[str, Any]
    ) -> None:
        """Normalize and insert new raw items into SQLite."""
        for item in items:
            stats["items_harvested"] += 1
            url = item.source_url.strip()
            if not url:
                continue

            existing = self.discovery_repo.get_by_url(url)
            if existing:
                stats["duplicates_skipped"] += 1
                continue

            disc_id = generate_discovery_id(url)
            record = DiscoveryRecord(
                id=disc_id,
                source_url=url,
                title=item.title,
                source_type=item.source_type,
                source_tier=source_tier,
                raw_content=item.raw_content,
                summary=item.markdown_content[:500] if item.markdown_content else item.raw_content[:500],
                author=item.author,
                status="RAW_INGESTED",
            )

            try:
                self.discovery_repo.insert(record)
                stats["new_inserted"] += 1
            except Exception as e:
                logger.error(f"Failed to persist discovery record {disc_id}: {e}")
                stats["errors"].append({"url": url, "error": str(e)})
