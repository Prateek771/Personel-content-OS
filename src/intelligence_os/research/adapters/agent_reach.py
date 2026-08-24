"""Agent Reach adapter for social and community technical intelligence.

Layered backends, best-first:
1. Self-hosted Agent Reach HTTP service (if running at base_url)
2. Hacker News Algolia API (keyless community discussion search) — always works
"""

from typing import Any
import httpx
from intelligence_os.core.logger import logger
from intelligence_os.research.adapters.base import BaseResearchAdapter, RawHarvestItem


class AgentReachAdapter(BaseResearchAdapter):
    """Harvests builder posts, demos, and workflow discussions via Agent Reach."""

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        api_key: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        super().__init__(name="agent_reach")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def is_available(self) -> bool:
        """Check if self-hosted Agent Reach instance is reachable."""
        try:
            with httpx.Client(timeout=2.0) as client:
                headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
                resp = client.get(f"{self.base_url}/health", headers=headers)
                return resp.status_code == 200
        except Exception:
            return False

    def harvest(self, target: str, **kwargs: Any) -> list[RawHarvestItem]:
        """Harvest discussions and demos matching query or handle."""
        # Backend 1: real Agent Reach HTTP service when present
        if self.is_available():
            items = self._harvest_http_service(target, **kwargs)
            if items:
                return items

        # Backend 2: keyless HN Algolia community search
        return self._harvest_hn_algolia(target, **kwargs)

    def _harvest_http_service(self, target: str, **kwargs: Any) -> list[RawHarvestItem]:
        endpoint = f"{self.base_url}/api/v1/search"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "query": target,
            "limit": kwargs.get("limit", 10),
            "include_media": True,
        }

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                resp = client.post(endpoint, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            items: list[RawHarvestItem] = []
            for entry in data.get("results", []):
                items.append(
                    RawHarvestItem(
                        source_url=entry.get("url", ""),
                        title=entry.get("title") or entry.get("text", "")[:80],
                        raw_content=entry.get("text", ""),
                        markdown_content=entry.get("text", ""),
                        author=entry.get("author", ""),
                        source_type="agent_reach",
                        source_tier=entry.get("source_tier", 2),
                        metadata={
                            "platform": entry.get("platform", "social"),
                            "engagement": entry.get("engagement", {}),
                            "media_urls": entry.get("media_urls", []),
                        },
                    )
                )
            return items
        except Exception as e:
            logger.warning(f"Agent Reach query failed for '{target}': {e}")
            return []

    def _harvest_hn_algolia(self, target: str, **kwargs: Any) -> list[RawHarvestItem]:
        """Fallback community intelligence via Hacker News Algolia search API."""
        query = target.strip()
        # "from:handle" style X queries cannot run on HN; strip to keywords instead
        if query.lower().startswith(("from:", "query:", "@")):
            query = query.split(":", 1)[-1].strip().strip("'\"")
        if not query:
            logger.debug(
                "Agent Reach social handle harvesting requires a backend. "
                "Install one with: pipx install twitter-cli (then agent-reach doctor)."
            )
            return []

        limit = min(kwargs.get("limit", 10), 20)
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                resp = client.get(
                    "https://hn.algolia.com/api/v1/search",
                    params={"query": query, "tags": "story", "hitsPerPage": limit},
                )
                resp.raise_for_status()
                data = resp.json()

            items: list[RawHarvestItem] = []
            for hit in data.get("hits", []):
                title = hit.get("title") or hit.get("story_title") or ""
                url = hit.get("url") or (
                    f"https://news.ycombinator.com/item?id={hit.get('objectID')}" if hit.get("objectID") else ""
                )
                if not url or not title:
                    continue
                discussion = f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
                content = (
                    f"{title}\n\nPoints: {hit.get('points', 0)} | Comments: {hit.get('num_comments', 0)}\n"
                    f"Discussion: {discussion}\nArticle: {url}"
                )
                items.append(
                    RawHarvestItem(
                        source_url=url,
                        title=title,
                        raw_content=content,
                        markdown_content=content,
                        author=hit.get("author", ""),
                        source_type="agent_reach",
                        source_tier=2,
                        metadata={
                            "platform": "hacker_news",
                            "points": hit.get("points", 0),
                            "num_comments": hit.get("num_comments", 0),
                            "discussion_url": discussion,
                            "engine": "hn_algolia",
                            "created_at": hit.get("created_at"),
                        },
                    )
                )
            logger.info(f"HN Algolia fallback returned {len(items)} items for '{target}'")
            return items
        except Exception as e:
            logger.warning(f"HN Algolia fallback failed for '{target}': {e}")
            return []
