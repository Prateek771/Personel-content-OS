"""OpenRouter Image Generator using bytedance-seed/seedream-5-0-lite."""

import json
import base64
from pathlib import Path
from typing import Any
import httpx

from intelligence_os.config.settings import Settings, get_settings
from intelligence_os.core.logger import logger
from intelligence_os.storage.models import ResearchCoreData


class OpenRouterImageGenerator:
    """Generates visual concept graphics and diagrams using bytedance-seed/seedream-5-0-lite."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.base_url = self.settings.openrouter_base_url.rstrip("/")
        self.image_model = self.settings.openrouter_image_model
        self.api_key = self.settings.openrouter_api_key
        self.output_dir = Path("output") / "generated_images"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_concept_prompt(self, core: ResearchCoreData) -> str:
        """Create high-signal visual prompt based on technical research core."""
        return (
            f"Minimalist, high-contrast dark tech architecture schematic illustration of {core.content_angle}: "
            f"{core.core_insight[:120]}. Clean vector isometric nodes, neon cyan and emerald glowing circuits, "
            f"obsidian background, technical HUD data overlays, sharp typography, 8k resolution, modern developer aesthetic."
        )

    def generate_image_asset(self, core: ResearchCoreData, topic_slug: str) -> str | None:
        """Generate concept graphic using configured OpenRouter image model."""
        if not self.api_key or not self.api_key.strip():
            logger.warning("OPENROUTER_API_KEY missing. Skipping OpenRouter image generation.")
            return None

        prompt = self.generate_concept_prompt(core)
        logger.info(f"Requesting image generation via '{self.image_model}' for topic: {topic_slug}")

        headers = {
            "Authorization": f"Bearer {self.api_key.strip()}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/intelligence-os",
            "X-Title": "AI Content Intelligence OS",
        }

        payload = {
            "model": self.image_model,
            "prompt": prompt,
            "n": 1,
            "size": "1024x1024",
        }

        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(f"{self.base_url}/images/generations", headers=headers, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    item = data.get("data", [{}])[0]
                    file_path = self.output_dir / f"{topic_slug}.jpg"
                    
                    if "b64_json" in item:
                        # Handle Base64 encoded images (Seedream default)
                        image_bytes = base64.b64decode(item["b64_json"])
                        file_path.write_bytes(image_bytes)
                        logger.info(f"Saved generated base64 image to {file_path}")
                        return str(file_path.resolve())
                    elif "url" in item:
                        # Handle URL images (DALL-E etc)
                        image_url = item["url"]
                        img_resp = client.get(image_url)
                        file_path.write_bytes(img_resp.content)
                        logger.info(f"Saved downloaded image to {file_path}")
                        return str(file_path.resolve())
                    else:
                        logger.warning("OpenRouter image response contained neither url nor b64_json.")
                        return None
                else:
                    logger.warning(f"OpenRouter image generation returned {resp.status_code}: {resp.text}")
                    return None
        except Exception as e:
            logger.warning(f"Failed to generate image via OpenRouter {self.image_model}: {e}")
            return None
