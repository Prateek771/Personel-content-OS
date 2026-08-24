"""X (Twitter) intelligence adapter using official API v2 with OAuth 1.0a user context."""

from typing import Any
from requests_oauthlib import OAuth1Session

from intelligence_os.core.logger import logger
from intelligence_os.research.adapters.base import BaseResearchAdapter, RawHarvestItem


class XAdapter(BaseResearchAdapter):
    """Harvests recent original tweets from monitored builders via X API v2."""

    def __init__(
        self,
        consumer_key: str | None = None,
        consumer_secret: str | None = None,
        access_token: str | None = None,
        access_token_secret: str | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        super().__init__(name="x")
        self.consumer_key = (consumer_key or "").strip()
        self.consumer_secret = (consumer_secret or "").strip()
        self.access_token = (access_token or "").strip()
        self.access_token_secret = (access_token_secret or "").strip()
        self.timeout_seconds = timeout_seconds
        self.api_base = "https://api.twitter.com/2"
        # Cache handle -> user id to avoid repeated lookups within a cycle
        self._user_id_cache: dict[str, str] = {}

    def _session(self) -> OAuth1Session:
        return OAuth1Session(
            client_key=self.consumer_key,
            client_secret=self.consumer_secret,
            resource_owner_key=self.access_token,
            resource_owner_secret=self.access_token_secret,
        )

    def is_configured(self) -> bool:
        """Check if all four OAuth 1.0a credentials are present."""
        return bool(self.consumer_key and self.consumer_secret and self.access_token and self.access_token_secret)

    def is_available(self) -> bool:
        """Verify credentials by resolving the authenticated user."""
        if not self.is_configured():
            return False
        try:
            resp = self._session().get(f"{self.api_base}/users/me", timeout=self.timeout_seconds)
            return resp.status_code == 200
        except Exception:
            return False

    def harvest(self, target: str, **kwargs: Any) -> list[RawHarvestItem]:
        """Harvest recent original tweets for an 'x' target like 'from:karpathy' or plain handle."""
        if not self.is_configured():
            logger.debug("X adapter not configured; skipping.")
            return []

        handle = target.strip().removeprefix("from:").removeprefix("@").strip("/")
        if not handle:
            return []
        try:
            session = self._session()

            # Resolve handle -> numeric ID (cached)
            if handle not in self._user_id_cache:
                lookup = session.get(
                    f"{self.api_base}/users/by/username/{handle}",
                    timeout=self.timeout_seconds,
                )
                if lookup.status_code != 200:
                    logger.warning(f"X user lookup failed for '{handle}': {lookup.status_code}")
                    return []
                uid = lookup.json().get("data", {}).get("id")
                if not uid:
                    return []
                self._user_id_cache[handle] = uid

            limit = min(kwargs.get("limit", 5), 10)
            timeline = session.get(
                f"{self.api_base}/users/{self._user_id_cache[handle]}/tweets",
                params={"max_results": max(limit, 5), "exclude": "replies", "tweet.fields": "created_at,public_metrics"},
                timeout=self.timeout_seconds,
            )
            if timeline.status_code != 200:
                logger.warning(f"X timeline fetch failed for '{handle}': {timeline.status_code} {timeline.text[:150]}")
                return []

            items: list[RawHarvestItem] = []
            for tweet in timeline.json().get("data", []):
                text = tweet.get("text", "").strip()
                # Retweets are amplification noise, not original builder signal
                if text.startswith("RT @"):
                    continue
                tweet_id = tweet.get("id", "")
                metrics = tweet.get("public_metrics", {})
                content = (
                    f"{text}\n\n"
                    f"Likes: {metrics.get('like_count', 0)} | Retweets: {metrics.get('retweet_count', 0)} | "
                    f"Replies: {metrics.get('reply_count', 0)}\n"
                    f"Posted: {tweet.get('created_at', '')}"
                )
                items.append(
                    RawHarvestItem(
                        source_url=f"https://x.com/{handle}/status/{tweet_id}",
                        title=text[:100] or f"Tweet by @{handle}",
                        raw_content=content,
                        markdown_content=content,
                        author=handle,
                        source_type="x",
                        source_tier=kwargs.get("tier", 1),
                        metadata={
                            "platform": "x",
                            "tweet_id": tweet_id,
                            "likes": metrics.get("like_count", 0),
                            "retweets": metrics.get("retweet_count", 0),
                            "engine": "x_api_v2_oauth1",
                        },
                    )
                )
            logger.info(f"X harvested {len(items)} tweets from @{handle}")
            return items
        except Exception as e:
            logger.warning(f"X harvest error for '{target}': {e}")
            return []
