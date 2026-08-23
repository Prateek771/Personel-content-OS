"""Custom exception hierarchy for AI Content Intelligence OS."""


class IntelligenceOSError(Exception):
    """Base exception for all domain errors within Intelligence OS."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message


class ConfigurationError(IntelligenceOSError):
    """Raised when application configuration is invalid or missing required values."""


class StorageError(IntelligenceOSError):
    """Raised when a database or persistence operation fails."""


class ResearchError(IntelligenceOSError):
    """Raised when research harvesting or adapter execution fails."""


class AdapterUnavailableError(ResearchError):
    """Raised when an external research adapter (Firecrawl, GitHub, Agent Reach) is down."""


class LLMGatewayError(IntelligenceOSError):
    """Raised when OpenRouter API calls fail or return malformed responses."""


class ReviewRejectionError(IntelligenceOSError):
    """Raised when content is rejected at the review gate due to unverified claims or hallucination."""


class PublishingError(IntelligenceOSError):
    """Raised when publishing to LinkedIn or X fails."""
