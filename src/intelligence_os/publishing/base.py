"""Base publisher interface and dispatch models."""

from abc import ABC, abstractmethod
from typing import Any
from intelligence_os.storage.models import ContentDraftRecord


class BasePublisher(ABC):
    """Abstract interface for platform publishing adapters."""

    def __init__(self, platform_name: str) -> None:
        self.platform_name = platform_name

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if platform credentials and tokens are present."""
        pass

    @abstractmethod
    def publish(self, draft: ContentDraftRecord) -> str:
        """Publish draft content to platform and return the external platform_post_id."""
        pass
