"""LinkedIn publisher integration using REST API."""

from typing import Any
import httpx

from intelligence_os.config.settings import Settings, get_settings
from intelligence_os.core.exceptions import PublishingError
from intelligence_os.core.logger import logger
from intelligence_os.publishing.base import BasePublisher
from intelligence_os.storage.models import ContentDraftRecord


class LinkedInPublisher(BasePublisher):
    """Publishes approved content drafts to LinkedIn using the Official REST API."""

    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__(platform_name="linkedin")
        self.settings = settings or get_settings()
        self.access_token = self.settings.linkedin_access_token
        self.author_urn = self.settings.linkedin_author_urn or "urn:li:person:UNKNOWN"
        self.api_endpoint = "https://api.linkedin.com/v2/ugcPosts"

    def is_configured(self) -> bool:
        """Check if LinkedIn API token is configured."""
        return bool(self.access_token and self.access_token.strip())

    def publish(self, draft: ContentDraftRecord) -> str:
        """Publish post to LinkedIn."""
        if not self.is_configured():
            raise PublishingError("LinkedIn access token is missing. Configure LINKEDIN_ACCESS_TOKEN in .env.")

        headers = {
            "Authorization": f"Bearer {self.access_token.strip()}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }

        payload: dict[str, Any] = {
            "author": self.author_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": draft.generated_copy},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        }

        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.post(self.api_endpoint, json=payload, headers=headers)
                resp.raise_for_status()
                post_id = resp.headers.get("x-restli-id") or resp.json().get("id", f"urn:li:share:{draft.id}")
                logger.info(f"Successfully published draft {draft.id} to LinkedIn with ID: {post_id}")
                return str(post_id)
        except Exception as e:
            logger.error(f"LinkedIn publishing failed for draft {draft.id}: {e}")
            raise PublishingError(f"LinkedIn API error: {e}") from e
