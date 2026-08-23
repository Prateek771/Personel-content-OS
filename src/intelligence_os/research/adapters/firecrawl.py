"""Firecrawl research adapter with local HTTP/BeautifulSoup fallback."""

from typing import Any
import httpx
from bs4 import BeautifulSoup
from markdownify import markdownify as md

from intelligence_os.core.logger import logger
from intelligence_os.research.adapters.base import BaseResearchAdapter, RawHarvestItem


class FirecrawlAdapter(BaseResearchAdapter):
    """Adapter for Firecrawl API with resilient local scraping fallback."""

    def __init__(
        self,
        base_url: str = "http://localhost:3002",
        api_key: str | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        super().__init__(name="firecrawl")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def is_available(self) -> bool:
        """Check if self-hosted Firecrawl instance is responsive."""
        try:
            with httpx.Client(timeout=3.0) as client:
                headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
                resp = client.get(f"{self.base_url}/health", headers=headers)
                return resp.status_code == 200
        except Exception:
            return False

    def harvest(self, target: str, **kwargs: Any) -> list[RawHarvestItem]:
        """Scrape webpage via Firecrawl API, or fall back cleanly to local HTTP/BS4 parser."""
        if not target.startswith(("http://", "https://")):
            logger.warning(f"FirecrawlAdapter target must be an HTTP(S) URL, got: {target}")
            return []

        # 1. Attempt Firecrawl API if reachable
        if self.is_available():
            try:
                item = self._scrape_firecrawl(target)
                if item:
                    return [item]
            except Exception as e:
                logger.warning(f"Firecrawl API scrape failed for {target}: {e}. Engaging local fallback.")

        # 2. Local Fallback Scraper
        try:
            return [self._scrape_local(target)]
        except Exception as e:
            logger.error(f"Local scraper fallback failed for {target}: {e}")
            return []

    def _scrape_firecrawl(self, url: str) -> RawHarvestItem | None:
        """Execute scrape via Firecrawl REST API."""
        endpoint = f"{self.base_url}/v1/scrape"
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "url": url,
            "formats": ["markdown", "html"],
            "onlyMainContent": True,
        }

        with httpx.Client(timeout=self.timeout_seconds) as client:
            resp = client.post(endpoint, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json().get("data", {})

            title = data.get("metadata", {}).get("title") or url
            markdown = data.get("markdown", "")
            raw_html = data.get("html", "")
            author = data.get("metadata", {}).get("author") or ""

            return RawHarvestItem(
                source_url=url,
                title=title.strip(),
                raw_content=raw_html or markdown,
                markdown_content=markdown,
                author=author,
                source_type="firecrawl",
                source_tier=kwargs_tier if (kwargs_tier := data.get("metadata", {}).get("tier")) else 1,
                metadata={"engine": "firecrawl_api", "status_code": resp.status_code},
            )

    def _scrape_local(self, url: str) -> RawHarvestItem:
        """Local HTTP + BeautifulSoup + Markdownify fallback parser."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            html_content = resp.text

        soup = BeautifulSoup(html_content, "html.parser")

        # Extract Title
        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        elif og_title := soup.find("meta", property="og:title"):
            title = og_title.get("content", "").strip()
        if not title:
            title = url

        # Extract Author
        author = ""
        if author_tag := soup.find("meta", attrs={"name": "author"}):
            author = author_tag.get("content", "").strip()
        elif og_author := soup.find("meta", property="article:author"):
            author = og_author.get("content", "").strip()

        # Remove non-content elements
        for element in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
            element.decompose()

        # Extract core content container if available
        article = soup.find("article") or soup.find("main") or soup.find("div", class_="content") or soup.body
        content_html = str(article) if article else html_content

        # Convert to clean markdown
        markdown_text = md(content_html, heading_style="ATX", strip=["img"]).strip()

        return RawHarvestItem(
            source_url=url,
            title=title,
            raw_content=content_html,
            markdown_content=markdown_text,
            author=author,
            source_type="firecrawl",
            source_tier=1,
            metadata={"engine": "local_fallback", "status_code": resp.status_code},
        )
