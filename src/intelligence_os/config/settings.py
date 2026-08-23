"""Configuration management using Pydantic Settings."""

from pathlib import Path
from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from intelligence_os.core.exceptions import ConfigurationError


class Settings(BaseSettings):
    """Application settings with validation and automatic environment loading."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General
    app_name: str = "AI Content Intelligence OS"
    app_version: str = "0.1.0"
    app_env: Literal["development", "production", "testing"] = "development"
    log_level: str = "INFO"

    # Paths (Base directories)
    base_dir: Path = Field(default_factory=lambda: Path.cwd())
    data_dir: Path = Field(default_factory=lambda: Path("data"))
    logs_dir: Path = Field(default_factory=lambda: Path("logs"))
    output_dir: Path = Field(default_factory=lambda: Path("output"))
    database_path: Path = Field(default_factory=lambda: Path("data/intelligence_os.db"))

    # AI Gateway (OpenRouter Models)
    openrouter_api_key: str | None = Field(default=None)
    openrouter_default_model: str = "anthropic/claude-3.5-sonnet-20241022"
    openrouter_fallback_model: str = "openai/gpt-4o-mini"
    openrouter_copywriting_model: str = "dots-studio/dots-3-note-preview:free"
    openrouter_image_model: str = "bytedance-seed/seedream-5-0-lite"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Research Sources
    firecrawl_base_url: str = "http://localhost:3002"
    firecrawl_api_key: str | None = None
    agent_reach_base_url: str = "http://localhost:8080"
    agent_reach_api_key: str | None = None
    github_token: str | None = None

    # Publishing: LinkedIn
    linkedin_client_id: str | None = None
    linkedin_client_secret: str | None = None
    linkedin_access_token: str | None = None
    linkedin_author_urn: str | None = None

    # Publishing: X (Twitter) OAuth 1.0a & v2
    x_consumer_key: str | None = None
    x_consumer_secret: str | None = None
    x_api_key: str | None = None
    x_api_secret: str | None = None
    x_access_token: str | None = None
    x_access_token_secret: str | None = None
    x_bearer_token: str | None = None

    # Scoring & Thresholds
    min_content_score: float = 0.65  # Minimum score to exit Silent Mode
    max_rewrite_attempts: int = 2

    def ensure_directories(self) -> None:
        """Ensure all required local directories exist."""
        for path in [self.data_dir, self.logs_dir, self.output_dir]:
            path.mkdir(parents=True, exist_ok=True)

    def validate_openrouter(self) -> None:
        """Validate that OpenRouter API key is available when executing LLM tasks."""
        if not self.openrouter_api_key or not self.openrouter_api_key.strip():
            raise ConfigurationError(
                "OPENROUTER_API_KEY is not configured. Please set it in your environment or .env file."
            )


def get_settings() -> Settings:
    """Instantiate and return settings singleton."""
    try:
        settings = Settings()
        settings.ensure_directories()
        return settings
    except Exception as e:
        raise ConfigurationError(f"Failed to load application settings: {e}") from e
