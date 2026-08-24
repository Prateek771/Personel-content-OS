"""Local Pillow renderer for high-end LinkedIn technical carousels."""

import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from intelligence_os.content.linkedin import LinkedInCarouselData, LinkedInCarouselSlide
from intelligence_os.core.logger import logger
from intelligence_os.visuals.theme import THEME


class CarouselRenderer:
    """Renders 1080x1080 high-contrast, technical LinkedIn carousel slides locally."""

    def __init__(self, output_base_dir: str | Path = "output/carousels") -> None:
        self.output_base_dir = Path(output_base_dir)
        self.output_base_dir.mkdir(parents=True, exist_ok=True)
        self.width = 1080
        self.height = 1080

    def render_carousel(self, carousel_data: LinkedInCarouselData, topic_slug: str, bg_image_path: str | None = None, on_slide_rendered=None) -> list[str]:
        """Render each slide in carousel data to PNG and return absolute file paths.

        The generated background image is applied to EVERY slide so the copy text
        overlays the contextual visual (per product spec). ``on_slide_rendered`` is
        invoked after each slide so the UI can show step-by-step progress.
        """
        topic_dir = self.output_base_dir / topic_slug
        topic_dir.mkdir(parents=True, exist_ok=True)

        generated_paths: list[str] = []
        total_slides = len(carousel_data.slides)

        bg_image = None
        if bg_image_path and Path(bg_image_path).exists():
            try:
                bg_image = Image.open(bg_image_path).convert("RGBA")
                bg_image = bg_image.resize((self.width, self.height), Image.Resampling.LANCZOS)
            except Exception as e:
                logger.warning(f"Failed to load background image {bg_image_path}: {e}")

        for i, slide in enumerate(carousel_data.slides, start=1):
            slide_path = topic_dir / f"slide_{i:02d}.png"
            self._render_single_slide(
                slide=slide,
                current_slide=i,
                total_slides=total_slides,
                topic_title=carousel_data.topic_title,
                output_path=slide_path,
                bg_image=bg_image,  # overlay generated context image on every slide
            )
            generated_paths.append(str(slide_path.resolve()))
            if on_slide_rendered:
                try:
                    on_slide_rendered(i, str(slide_path.resolve()))
                except Exception:
                    pass

        logger.info(f"Rendered {len(generated_paths)} carousel slides for '{topic_slug}' in {topic_dir}")
        return generated_paths

    def _render_single_slide(
        self,
        slide: LinkedInCarouselSlide,
        current_slide: int,
        total_slides: int,
        topic_title: str,
        output_path: Path,
        bg_image: Image.Image | None = None,
    ) -> None:
        """Render a single 1080x1080 slide image."""
        img = Image.new("RGBA", (self.width, self.height), color=THEME.bg_primary)
        
        if bg_image:
            # Blend the Seedream image with a dark overlay for readability
            img.alpha_composite(bg_image)
            overlay = Image.new("RGBA", (self.width, self.height), color=(15, 23, 42, 200)) # Slate-900 with 80% opacity
            img.alpha_composite(overlay)
            
        draw = ImageDraw.Draw(img)

        # 1. Subtle top glowing gradient bar
        for y in range(8):
            draw.line([(0, y), (self.width, y)], fill=THEME.accent_cyan)

        # 2. Main content card
        card_margin = 60
        card_rect = [card_margin, 80, self.width - card_margin, self.height - 80]
        draw.rounded_rectangle(card_rect, radius=24, fill=THEME.bg_card, outline=THEME.border_card, width=2)

        # 3. Slide Badge & Category Header
        badge_y = 120
        draw.text((100, badge_y), f"AI CONTENT INTELLIGENCE OS", fill=THEME.text_secondary)
        slide_counter_text = f"SLIDE {current_slide:02d} / {total_slides:02d}"
        draw.text((self.width - 240, badge_y), slide_counter_text, fill=THEME.accent_cyan)

        # 4. Slide Title
        title_y = 180
        draw.text((100, title_y), slide.title[:65], fill=THEME.text_primary)
        if slide.subtitle:
            draw.text((100, title_y + 45), slide.subtitle[:80], fill=THEME.text_secondary)

        # 5. Bullet Points
        bullet_start_y = 280
        for idx, bullet in enumerate(slide.bullet_points[:4]):
            y_pos = bullet_start_y + (idx * 80)
            # Glowing indicator dot
            draw.ellipse([100, y_pos + 4, 114, y_pos + 18], fill=THEME.accent_cyan)
            # Bullet text
            draw.text((130, y_pos), bullet[:75], fill=THEME.text_primary)

        # 6. Code snippet box if present
        if slide.code_snippet and slide.code_snippet.strip():
            code_rect = [100, 620, self.width - 100, 780]
            draw.rounded_rectangle(code_rect, radius=12, fill=THEME.bg_code, outline=THEME.border_card, width=1)
            draw.text((120, 640), "// IMPLEMENTATION PATTERN", fill=THEME.text_secondary)
            code_lines = slide.code_snippet.strip().split("\n")[:4]
            for line_idx, line in enumerate(code_lines):
                draw.text((120, 675 + (line_idx * 24)), line[:60], fill=THEME.accent_cyan)

        # 7. Bottom Practical Takeaway Bar
        if slide.takeaway:
            takeaway_rect = [100, 820, self.width - 100, 940]
            draw.rounded_rectangle(takeaway_rect, radius=16, fill=THEME.bg_code, outline=THEME.accent_emerald, width=2)
            draw.text((130, 840), "KEY TAKEAWAY", fill=THEME.accent_emerald)
            draw.text((130, 875), slide.takeaway[:85], fill=THEME.text_primary)

        # Save image
        img.save(output_path, format="PNG", optimize=True)
