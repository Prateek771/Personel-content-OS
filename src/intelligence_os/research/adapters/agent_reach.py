"""Agent Reach adapter for social and community technical intelligence."""

from typing import Any
import httpx
from intelligence_os.core.logger import logger
from intelligence_os.research.adapters.base import BaseResearchAdapter, RawHarvestItem


class AgentReachAdapter(BaseResearchAdapter):
    """Harvests builder posts, demos, and workflow discussions via Agent Reach service."""

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
        if not self.is_available():
            logger.debug(f"Agent Reach service at {self.base_url} is currently unavailable. Skipping.")
            return []

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
