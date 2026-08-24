"""LinkedIn content generator specialized 100% in multi-slide visual carousels and natural English descriptions."""

import json
from typing import Any, Literal
from pydantic import BaseModel, Field

from intelligence_os.core.logger import logger
from intelligence_os.intelligence.openrouter import OpenRouterClient, clean_json_response
from intelligence_os.storage.models import ResearchCoreData


class LinkedInCarouselSlide(BaseModel):
    """Structure for a single LinkedIn carousel slide."""

    slide_number: int
    title: str
    subtitle: str = ""
    bullet_points: list[str] = Field(default_factory=list)
    code_snippet: str = ""
    takeaway: str = ""


class LinkedInCarouselData(BaseModel):
    """Structured data payload for generating multi-slide visual carousels."""

    topic_title: str
    total_slides: int
    slides: list[LinkedInCarouselSlide]


class LinkedInContentResult(BaseModel):
    """Result of LinkedIn generation containing carousel structure and natural English companion post."""

    format: Literal["carousel"] = "carousel"
    post_copy: str
    carousel_data: LinkedInCarouselData
    tags: list[str] = Field(default_factory=list)


LINKEDIN_CAROUSEL_SYSTEM_PROMPT = """You are an elite AI systems architect and technical writer crafting multi-slide visual carousels for LinkedIn.
Your audience: AI developers, tech leads, and founders who want clear, visual, high-signal explanations with bullet points.

MANDATORY RULES:
1. Focus 100% on a 4-Slide Technical Carousel breakdown about the supplied topic (a 5th call-to-action slide is appended automatically).
2. Slide 1 (Hook): Punchy title & why this topic matters right now.
3. Slide 2 (Evidence / Problem): The strongest evidence, data point, or problem the topic solves.
4. Slide 3 (Mechanism / Implication): How it works or what it means for practitioners.
5. Slide 4 (Takeaway): The concrete, actionable takeaway.
6. Every slide title, subtitle, bullet point and takeaway MUST be derived from THIS research core and the typed topic — never reuse generic protocol/architecture examples. No invented facts, no hashtags in slide copy.
7. Write companion `post_copy` in 100% natural, human English with emojis and bullet points. Zero JSON, zero code blocks in post text. The post must reference the actual subject by name.

Output strictly in JSON matching the schema."""


class LinkedInGenerator:
    """Generates 5-slide visual carousels and companion natural English posts for LinkedIn."""

    def __init__(self, openrouter_client: OpenRouterClient) -> None:
        self.client = openrouter_client

    def generate(
        self,
        core: ResearchCoreData,
        preferred_format: Literal["carousel"] = "carousel",
    ) -> LinkedInContentResult:
        """Generate structured LinkedIn carousel using configured copywriting model."""
        logger.info(f"Generating LinkedIn 5-Slide Carousel with model {self.client.copywriting_model} for angle: {core.content_angle}")

        user_prompt = f"""RESEARCH CORE BLUEPRINT:
Hook: {core.hook}
Core Insight: {core.core_insight}
Evidence Sources: {', '.join(core.evidence)}
Practical Takeaway: {core.practical_takeaway}
Limitations: {core.limitations}
Content Angle: {core.content_angle}
Tags: {', '.join(core.tags)}

INSTRUCTIONS:
Create a 4-slide CONTENT carousel breakdown (the 5th CTA slide is added automatically) with companion post copy.
Every slide title, subtitle, bullet point and takeaway MUST be derived from THIS research core and the typed topic above — never reuse generic protocol/architecture examples.
The companion post_copy must reference the actual subject by name.

Return ONLY JSON with exactly this shape (values below are placeholders to be replaced):
{{
  "format": "carousel",
  "post_copy": "<3-6 sentence natural English post about THIS topic, emojis allowed, ends with hashtags>",
  "carousel_data": {{
    "topic_title": "<short punchy title>",
    "total_slides": 4,
    "slides": [
      {{"slide_number": 1, "title": "<hook>", "subtitle": "<why it matters>", "bullet_points": ["<point>", "<point>"], "takeaway": "<transition>"}},
      {{"slide_number": 2, "title": "<evidence/problem>", "subtitle": "...", "bullet_points": ["..."], "takeaway": "..."}},
      {{"slide_number": 3, "title": "<mechanism/implication>", "subtitle": "...", "bullet_points": ["..."], "takeaway": "..."}},
      {{"slide_number": 4, "title": "<takeaway>", "subtitle": "...", "bullet_points": ["..."], "takeaway": "..."}}
    ]
  }},
  "tags": {json.dumps(core.tags)}
}}"""

        messages = [
            {"role": "system", "content": LINKEDIN_CAROUSEL_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        response_text = self.client.generate_chat_completion(
            messages,
            model_override=self.client.copywriting_model,
            temperature=0.3,
        )
        cleaned = clean_json_response(response_text)
        try:
            raw_json = json.loads(cleaned)
            return LinkedInContentResult(**raw_json)
        except Exception as e:
            logger.warning(f"Fallback parsing for LinkedIn carousel: {e}")
            fallback_slides = [
                LinkedInCarouselSlide(slide_number=1, title="Why it matters", subtitle=core.hook[:60], bullet_points=[core.core_insight[:80]]),
                LinkedInCarouselSlide(slide_number=2, title="The evidence", subtitle="What the research shows", bullet_points=[core.core_insight[:100]]),
                LinkedInCarouselSlide(slide_number=3, title="How it works", subtitle="Mechanism", bullet_points=[core.practical_takeaway[:100]]),
                LinkedInCarouselSlide(slide_number=4, title="Key takeaway", subtitle="What to do", bullet_points=[core.limitations[:100]]),
            ]
            return LinkedInContentResult(
                format="carousel",
                post_copy=f"🚀 {core.hook}\n\nSwipe through the carousel below for the complete architecture breakdown 👇\n\n{' '.join(core.tags)}",
                carousel_data=LinkedInCarouselData(topic_title=core.hook[:50], total_slides=5, slides=fallback_slides),
                tags=core.tags,
            )
