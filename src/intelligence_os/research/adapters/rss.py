"""RSS/Atom feed adapter using feedparser for blogs, substacks, and changelogs."""

from typing import Any
import feedparser

from intelligence_os.core.logger import logger
from intelligence_os.research.adapters.base import BaseResearchAdapter, RawHarvestItem


class RSSAdapter(BaseResearchAdapter):
    """Harvests entries from any RSS/Atom feed with zero external services."""

    def __init__(self, timeout_seconds: float = 15.0) -> None:
        super().__init__(name="rss")
        self.timeout_seconds = timeout_seconds

    def is_available(self) -> bool:
        """feedparser is a pure Python library and is always available."""
        return True

    def harvest(self, target: str, **kwargs: Any) -> list[RawHarvestItem]:
        """Fetch and normalize the latest entries of an RSS/Atom feed."""
        logger.info(f"RSS harvesting feed: {target}...")
        try:
            feed = feedparser.parse(target, agent="AI-Content-Intelligence-OS/0.1.0")
            if feed.bozo and not feed.entries:
                logger.warning(f"RSS parse failed for {target}: {feed.bozo_exception}")
                return []

            items: list[RawHarvestItem] = []
            for entry in feed.entries[: kwargs.get("limit", 10)]:
                link = entry.get("link", "").strip()
                if not link:
                    continue
                title = entry.get("title", "Untitled Entry").strip()
                summary_html = entry.get("summary", "") or entry.get("description", "")

                content = summary_html
                if entry.get("content"):
                    content = entry["content"][0].get("value", summary_html)

                items.append(
                    RawHarvestItem(
                        source_url=link,
                        title=title,
                        raw_content=content[:10000],
                        markdown_content=content[:10000],
                        author=entry.get("author", feed.feed.get("title", "")),
                        source_type="rss",
                        source_tier=kwargs.get("tier", 1),
                        metadata={
                            "engine": "feedparser",
                            "published": entry.get("published", ""),
                            "feed_title": feed.feed.get("title", ""),
                        },
                    )
                )
            return items
        except Exception as e:
            logger.warning(f"RSS harvest error for {target}: {e}")
            return []
