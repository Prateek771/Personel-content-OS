"""Scrapling adapter for high-performance, stealthy, and zero-Docker web scraping."""

from typing import Any
import markdownify
from scrapling import Fetcher, Selector

from intelligence_os.core.logger import logger
from intelligence_os.research.adapters.base import BaseResearchAdapter, RawHarvestItem


class ScraplingAdapter(BaseResearchAdapter):
    """High-performance, adaptive web scraper utilizing Scrapling (Zero Docker required)."""

    def __init__(self, timeout_seconds: float = 15.0) -> None:
        super().__init__(name="scrapling")
        self.timeout_seconds = timeout_seconds

    def is_available(self) -> bool:
        """Scrapling is a pure Python native engine and is always available."""
        return True

    def harvest(self, target: str, **kwargs: Any) -> list[RawHarvestItem]:
        """Scrape web page or technical documentation directly into clean markdown and raw items."""
        logger.info(f"Scrapling harvesting URL: {target}...")
        try:
            page = Fetcher.get(target, timeout=int(self.timeout_seconds))
            if page.status != 200:
                logger.warning(f"Scrapling received HTTP status {page.status} for {target}")

            # Extract title using adaptive css selectors
            title = page.css("title::text").get() or page.css("h1::text").get() or target
            title = title.strip()

            # Clean body content to markdown
            html_content = page.body if hasattr(page, "body") and isinstance(page.body, str) else str(page.root)
            clean_md = markdownify.markdownify(html_content, heading_style="ATX").strip()

            # Extract top text snippet for summary
            summary = clean_md[:350].replace("\n", " ").replace("#", "").strip()

            return [
                RawHarvestItem(
                    source_url=target,
                    source_type="scrapling",
                    source_tier=kwargs.get("tier", 1),
                    title=title,
                    raw_content=clean_md[:10000],
                    summary=summary,
                    author=kwargs.get("author", "web-author"),
                    metadata={
                        "http_status": page.status,
                        "engine": "scrapling",
                        "scraped_at": str(kwargs.get("scraped_at", "")),
                    },
                )
            ]
        except Exception as e:
            logger.warning(f"Scrapling harvest error for {target}: {e}")
            return []
