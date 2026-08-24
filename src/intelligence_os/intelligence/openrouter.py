"""OpenRouter API client with fallback model routing, markdown stripping, and retries."""

import json
import re
from typing import Any
import httpx

from intelligence_os.config.settings import Settings, get_settings
from intelligence_os.core.exceptions import LLMGatewayError
from intelligence_os.core.logger import logger


def clean_json_response(raw_text: str | None) -> str:
    """Extract pure JSON from LLM output, removing markdown fences or leading/trailing commentary."""
    if not raw_text:
        return "{}"
    text = str(raw_text).strip()
    if text.startswith("```"):
        # Match ```json ... ``` or ``` ... ```
        pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
        match = re.search(pattern, text)
        if match:
            text = match.group(1).strip()
    return text


class OpenRouterClient:
    """Robust client for OpenRouter AI gateway with model fallback and structured JSON output."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.base_url = self.settings.openrouter_base_url.rstrip("/")
        self.primary_model = self.settings.openrouter_default_model
        self.copywriting_model = self.settings.openrouter_copywriting_model
        self.fallback_model = self.settings.openrouter_fallback_model
        self.api_key = self.settings.openrouter_api_key
        # Reasoning models can take well over 60s; free tiers rate-limit bursts.
        self.request_timeout_seconds = 180.0
        self.max_attempts_per_model = 3

    def generate_chat_completion(
        self,
        messages: list[dict[str, str]],
        model_override: str | None = None,
        temperature: float = 0.2,
        response_format_json: bool = True,
        max_tokens: int = 16000,
    ) -> str:
        """Call OpenRouter Chat Completion API with automatic fallback model."""
        if not self.api_key or not self.api_key.strip():
            raise LLMGatewayError("OpenRouter API key is missing. Set OPENROUTER_API_KEY in .env.")

        headers = {
            "Authorization": f"Bearer {self.api_key.strip()}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/intelligence-os",
            "X-Title": "AI Content Intelligence OS",
        }

        # Model priority list
        candidate_models = []
        if model_override:
            candidate_models.append(model_override)
        candidate_models.extend([self.primary_model, self.fallback_model])
        # Deduplicate while preserving order
        unique_models = list(dict.fromkeys(candidate_models))

        last_error: Exception | None = None
        for model in unique_models:
            payload: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if response_format_json:
                payload["response_format"] = {"type": "json_object"}

            # Reasoning models vary in how many tokens they burn thinking;
            # retry the same model before moving to the next candidate.
            for attempt in range(1, self.max_attempts_per_model + 1):
                try:
                    logger.info(f"Calling OpenRouter with model '{model}' (attempt {attempt})...")
                    with httpx.Client(timeout=self.request_timeout_seconds) as client:
                        resp = client.post(
                            f"{self.base_url}/chat/completions",
                            headers=headers,
                            json=payload,
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        choices = data.get("choices", [])
                        if choices:
                            message = choices[0].get("message", {})
                            content = message.get("content")
                            finish_reason = choices[0].get("finish_reason")
                            if content and isinstance(content, str) and content.strip():
                                return clean_json_response(content)
                            if finish_reason == "length":
                                logger.warning(
                                    f"Model '{model}' exhausted its token budget on reasoning "
                                    f"({data.get('usage', {}).get('completion_tokens')} tokens); "
                                    "retrying (reasoning length varies per run)."
                                )
                            else:
                                logger.warning(f"Model '{model}' returned empty or null message content.")
                        else:
                            logger.warning(f"Model '{model}' returned empty choices array.")

                except httpx.HTTPStatusError as e:
                    last_error = e
                    logger.warning(f"OpenRouter call failed on model '{model}': {e.response.status_code}")
                    break  # HTTP errors (rate limit / 404) won't fix themselves on retry
                except Exception as e:
                    last_error = e
                    logger.warning(f"OpenRouter connection failed on model '{model}': {e}")

        raise LLMGatewayError(f"All candidate OpenRouter models failed to respond. Last error: {last_error}")
