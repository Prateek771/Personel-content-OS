"""X (Twitter) publisher integration using OAuth 1.0a User Context and v2 API."""

import json
from typing import Any
import requests
from requests_oauthlib import OAuth1Session

from intelligence_os.config.settings import Settings, get_settings
from intelligence_os.core.exceptions import PublishingError
from intelligence_os.core.logger import logger
from intelligence_os.publishing.base import BasePublisher
from intelligence_os.storage.models import ContentDraftRecord


def extract_clean_tweets(raw_copy: str) -> list[str]:
    """Extract clean plain-text tweet strings from draft copy, stripping all JSON syntax."""
    text = raw_copy.strip()
    if text.startswith("{"):
        try:
            data = json.loads(text)
            if "posts" in data and isinstance(data["posts"], list):
                tweets = [p.get("text", "").strip() for p in data["posts"] if p.get("text")]
                if tweets:
                    return tweets
            if "full_text_rendered" in data and isinstance(data["full_text_rendered"], str):
                text = data["full_text_rendered"].strip()
            elif "post_copy" in data and isinstance(data["post_copy"], str):
                text = data["post_copy"].strip()
        except Exception:
            pass

    # Split by double newline if thread formatted
    parts = [p.strip() for p in text.split("\n\n") if p.strip() and not p.strip().startswith("{") and not p.strip().startswith("}")]
    if len(parts) > 1 and any("1/" in parts[0] or "1/5" in parts[0] for _ in [1]):
        return parts

    return [text]


class XPublisher(BasePublisher):
    """Publishes approved content drafts and threads to X using authenticated OAuth 1.0a."""

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__(platform_name="x")
        self.settings = settings or get_settings()
        self.consumer_key = self.settings.x_consumer_key or self.settings.x_api_key
        self.consumer_secret = self.settings.x_consumer_secret or self.settings.x_api_secret
        self.access_token = self.settings.x_access_token
        self.access_token_secret = self.settings.x_access_token_secret
        self.api_endpoint = "https://api.twitter.com/2/tweets"

    def is_configured(self) -> bool:
        """Check if X OAuth 1.0a credentials are fully configured."""
        return bool(
            self.consumer_key
            and self.consumer_secret
            and self.access_token
            and self.access_token_secret
        )

    def publish(self, draft: ContentDraftRecord) -> str:
        """Publish clean post or full connected thread to X via OAuth 1.0a User Context."""
        if not self.is_configured():
            raise PublishingError("X API credentials missing. Set X_CONSUMER_KEY, X_CONSUMER_SECRET, X_ACCESS_TOKEN, and X_ACCESS_TOKEN_SECRET in .env.")

        oauth = OAuth1Session(
            client_key=self.consumer_key.strip(),
            client_secret=self.consumer_secret.strip(),
            resource_owner_key=self.access_token.strip(),
            resource_owner_secret=self.access_token_secret.strip(),
        )

        tweets = extract_clean_tweets(draft.generated_copy)
        if not tweets:
            raise PublishingError("Draft has no readable text content to publish.")

        first_tweet_id = None
        previous_tweet_id = None

        logger.info(f"Publishing {len(tweets)} tweet(s) for draft {draft.id} to X...")

        for idx, tweet_text in enumerate(tweets):
            clean_text = tweet_text.strip()
            # Enforce 280 character limit
            if len(clean_text) > 280:
                clean_text = clean_text[:277] + "..."

            payload: dict[str, Any] = {"text": clean_text}
            if previous_tweet_id:
                payload["reply"] = {"in_reply_to_tweet_id": previous_tweet_id}

            try:
                resp = oauth.post(self.api_endpoint, json=payload, timeout=20.0)
                if resp.status_code in [200, 201]:
                    data = resp.json()
                    tweet_id = str(data.get("data", {}).get("id", f"x-{draft.id}-{idx}"))
                    if not first_tweet_id:
                        first_tweet_id = tweet_id
                    previous_tweet_id = tweet_id
                    logger.info(f"Published tweet #{idx+1}/{len(tweets)}: {tweet_id}")
                else:
                    logger.error(f"X API error on tweet #{idx+1} ({resp.status_code}): {resp.text}")
                    if not first_tweet_id:
                        raise PublishingError(f"X API returned {resp.status_code}: {resp.text}")
                    break

            except requests.RequestException as e:
                logger.error(f"X network connection failed on tweet #{idx+1}: {e}")
                if not first_tweet_id:
                    raise PublishingError(f"X request error: {e}") from e
                break

        return first_tweet_id or f"x-{draft.id}"
