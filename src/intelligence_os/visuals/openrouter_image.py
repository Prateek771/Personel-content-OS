"""OpenRouter image generator that renders each carousel slide as a complete artwork.

Mirrors the reference pipeline: one shared art-direction system is locked across all
slides, slide 1 establishes the visual style, and every slide is generated as a
finished 1024x1024 PNG with its headline/body/watermark rendered directly in the image
(no second text layer). Falls back to the local Pillow renderer per-slide if the image
model fails, so a run always yields a full 5-slide set.
"""

import json
import base64
from pathlib import Path
from typing import Any, Callable
import httpx

from intelligence_os.config.settings import Settings, get_settings
from intelligence_os.core.logger import logger
from intelligence_os.storage.models import ResearchCoreData

# Shared visual system locked across every slide (generic — no third-party branding).
CAROUSEL_ART_DIRECTION = """
FORMAT: Premium square LinkedIn carousel slide, 1024 x 1024.
VISUAL SYSTEM: Modern editorial technology magazine; deep charcoal background (#0B0D12), warm ivory typography (#F3F0E8), one electric cobalt accent (#5570FF), subtle paper grain, crisp geometric composition, sophisticated and restrained.
LAYOUT: Fixed 12-column grid, generous margins, slide number at top-left, short headline in the middle-left, supporting sentence below it, small watermark at bottom-left. One conceptual editorial visual occupies the right half without reducing text readability.
TYPOGRAPHY: Clean bold neo-grotesk sans-serif headline, regular sans-serif body, high contrast, immaculate spacing, no decorative fonts.
INVARIANTS: Keep the exact palette, grid, type hierarchy, margins, watermark position and overall art direction on every slide. No logos, no UI screenshots, no fake interface, no extra captions, no extra words.
"""


class OpenRouterImageGenerator:
    """Generates one finished image per carousel slide via OpenRouter image models."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.base_url = self.settings.openrouter_base_url.rstrip("/")
        self.image_model = self.settings.openrouter_image_model
        self.api_key = self.settings.openrouter_api_key
        self.output_dir = Path("output") / "generated_images"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def generate_carousel_images(
        self,
        slides: list[Any],
        art_direction: str,
        draft_id: str,
        on_slide_rendered: Callable[[int, str], None] | None = None,
    ) -> list[str]:
        """Render every slide as a complete PNG and return absolute file paths.

        The same ``art_direction`` is used for each slide so the visual system stays
        linked across the set (slide 1 anchors the style). Each slide is generated, in
        order, by the image model; if the model fails for a slide, that slide falls back
        to the local Pillow renderer so the carousel is always complete. The function
        walks all slides before returning, so the caller receives a full set.
        """
        if not self.api_key or not self.api_key.strip():
            logger.warning("OPENROUTER_API_KEY missing. Using local Pillow renderer for all slides.")
            return self._pillow_fallback(slides, draft_id, on_slide_rendered)

        out_dir = Path("output") / "carousels" / draft_id
        out_dir.mkdir(parents=True, exist_ok=True)
        total = len(slides)
        paths: list[str] = []

        for i, slide in enumerate(slides, start=1):
            title = getattr(slide, "title", "") or ""
            body = (
                getattr(slide, "subtitle", "")
                or (slide.bullet_points[0] if getattr(slide, "bullet_points", []) else "")
                or (getattr(slide, "takeaway", "") or "")
            )
            watermark = getattr(slide, "watermark", None) or "AI Content OS"
            prompt = self._slide_prompt(art_direction, i, total, title, body, watermark)
            path = out_dir / f"slide_{i:02d}.png"

            if not self._generate_to_file(prompt, path):
                logger.warning(f"Image model failed for slide {i}; using Pillow fallback.")
                self._render_single_with_pillow(slide, i, total, path)

            if path.exists():
                paths.append(str(path.resolve()))
                if on_slide_rendered:
                    try:
                        on_slide_rendered(i, str(path.resolve()))
                    except Exception:
                        pass
            else:
                logger.error(f"Slide {i} could not be rendered.")

        logger.info(f"Rendered {len(paths)} carousel slide images for {draft_id}")
        return paths

    # ------------------------------------------------------------------ #
    # Prompt + request helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _slide_prompt(art_direction: str, index: int, total: int, title: str, body: str, watermark: str) -> str:
        return f"""{art_direction}
SLIDE: {index} of {total}.
HEADLINE — render exactly: "{title}"
BODY — render exactly: "{body}"
WATERMARK — render exactly: "{watermark}" (spell it out, no abbreviations).
FINAL CHECK: Produce a complete, finished carousel slide. All quoted text must be legible, spelled exactly, and high contrast. Do not add any other text."""

    def _generate_to_file(self, prompt: str, path: Path) -> bool:
        """Call the image model once and write the result to ``path``. Returns success."""
        if not self.api_key:
            return False
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
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(f"{self.base_url}/images/generations", headers=headers, json=payload)
                if resp.status_code != 200:
                    logger.warning(f"Image model returned {resp.status_code}: {resp.text[:200]}")
                    return False
                item = resp.json().get("data", [{}])[0]
                if "b64_json" in item:
                    path.write_bytes(base64.b64decode(item["b64_json"]))
                    return True
                if "url" in item:
                    img_resp = client.get(item["url"])
                    path.write_bytes(img_resp.content)
                    return True
                logger.warning("Image response contained neither url nor b64_json.")
                return False
        except Exception as e:
            logger.warning(f"Image generation failed: {e}")
            return False

    # ------------------------------------------------------------------ #
    # Fallback (local Pillow renderer)
    # ------------------------------------------------------------------ #
    def _pillow_fallback(self, slides, draft_id, on_slide_rendered) -> list[str]:
        out_dir = Path("output") / "carousels" / draft_id
        out_dir.mkdir(parents=True, exist_ok=True)
        paths: list[str] = []
        for i, slide in enumerate(slides, start=1):
            path = out_dir / f"slide_{i:02d}.png"
            self._render_single_with_pillow(slide, i, len(slides), path)
            if path.exists():
                paths.append(str(path.resolve()))
                if on_slide_rendered:
                    try:
                        on_slide_rendered(i, str(path.resolve()))
                    except Exception:
                        pass
        return paths

    @staticmethod
    def _render_single_with_pillow(slide, index: int, total: int, path: Path) -> None:
        from intelligence_os.visuals.carousel_renderer import CarouselRenderer

        renderer = CarouselRenderer(Path("output") / "carousels")
        renderer._render_single_slide(
            slide=slide,
            current_slide=index,
            total_slides=total,
            topic_title="",
            output_path=path,
            bg_image=None,
        )
