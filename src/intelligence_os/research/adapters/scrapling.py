"""Scrapling adapter for high-performance, stealthy, and zero-Docker web scraping."""

from typing import Any
from scrapling import Fetcher

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

            # Extract title
            title = page.css("title::text").get() or page.css("h1::text").get() or target
            title = title.strip()

            # Prefer scrapling's built-in markdown conversion; fall back to raw HTML text
            clean_md = ""
            try:
                md_result = page.markdown()
                clean_md = md_result if isinstance(md_result, str) else str(md_result)
            except Exception as e:
                logger.debug(f"scrapling .markdown() unavailable ({e}); falling back to html_content")
            if not clean_md.strip():
                html = page.html_content or ""
                if html:
                    from markdownify import markdownify
                    clean_md = markdownify(html, heading_style="ATX")
            clean_md = clean_md.strip()

            return [
                RawHarvestItem(
                    source_url=target,
                    source_type="scrapling",
                    source_tier=kwargs.get("tier", 1),
                    title=title,
                    raw_content=clean_md[:10000],
                    markdown_content=clean_md[:10000],
                    author=page.css("meta[name='author']::attr(content)").get() or "",
                    metadata={
                        "http_status": page.status,
                        "engine": "scrapling",
                    },
                )
            ]
        except Exception as e:
            logger.warning(f"Scrapling harvest error for {target}: {e}")
            return []
