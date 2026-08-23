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
1. Focus 100% on a 5-Slide Technical Carousel breakdown.
2. Slide 1 (Hook): Punchy title & why this architecture matters.
3. Slide 2 (The Problem): Why traditional methods break down.
4. Slide 3 (The Mechanism): The core architecture broken into 3 clean bullet points.
5. Slide 4 (Implementation): Practical step-by-step developer implementation.
6. Slide 5 (Summary & Takeaway): Production trade-offs and key takeaway.
7. Write companion `post_copy` in 100% natural, human English with emojis and bullet points. Zero JSON, zero code blocks in post text.

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
Create a 5-slide carousel breakdown with companion post copy.
Return JSON matching:
{{
  "format": "carousel",
  "post_copy": "🚀 Stop writing brittle tool parsers for every AI agent.\\n\\nHere is a 5-slide visual breakdown on how standardized protocols work:\\n\\n📌 1. Standardized JSON-RPC\\n📌 2. Dynamic Tool Discovery\\n📌 3. Local stdio Performance\\n\\nSwipe through the carousel below for the complete architecture breakdown 👇\\n\\n#AIAgents #OpenSource #SoftwareEngineering",
  "carousel_data": {{
    "topic_title": "{core.hook[:50]}",
    "total_slides": 5,
    "slides": [
      {{
        "slide_number": 1,
        "title": "Architecture Blueprint",
        "subtitle": "{core.hook[:60]}",
        "bullet_points": ["Why traditional agents break", "The standardized protocol shift"],
        "takeaway": "Swipe to explore ->"
      }},
      {{
        "slide_number": 2,
        "title": "The Core Shift",
        "subtitle": "Decoupling Tools from Models",
        "bullet_points": ["No hardcoded API calls", "Universal JSON-RPC standard", "Pluggable capabilities"],
        "takeaway": "Dynamic capability discovery"
      }},
      {{
        "slide_number": 3,
        "title": "How It Works",
        "subtitle": "Step-by-Step Flow",
        "bullet_points": ["Agent spawns stdio process", "Server registers tools & schemas", "Agent invokes typed functions"],
        "takeaway": "Zero boilerplate glue code"
      }},
      {{
        "slide_number": 4,
        "title": "Key Trade-offs",
        "subtitle": "Production Realities",
        "bullet_points": ["Requires local runtime environment", "Process startup overhead", "OS dependency management"],
        "takeaway": "Best for local dev loops"
      }},
      {{
        "slide_number": 5,
        "title": "Actionable Takeaway",
        "subtitle": "Get Started Today",
        "bullet_points": ["Adopt lightweight stdio servers", "Separate tool logic from prompts", "Reference: {core.evidence[0] if core.evidence else 'GitHub'}"],
        "takeaway": "Build modular agent tools"
      }}
    ]
  }},
  "tags": ["#AIAgents", "#OpenSource", "#SoftwareEngineering"]
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
                LinkedInCarouselSlide(slide_number=1, title="AI Architecture", subtitle=core.hook[:50], bullet_points=[core.core_insight[:60]]),
                LinkedInCarouselSlide(slide_number=2, title="Core Insight", subtitle="Key Mechanism", bullet_points=[core.core_insight[:80]]),
                LinkedInCarouselSlide(slide_number=3, title="Implementation", subtitle="Workflow", bullet_points=[core.practical_takeaway[:80]]),
                LinkedInCarouselSlide(slide_number=4, title="Limitations", subtitle="Trade-offs", bullet_points=[core.limitations[:80]]),
                LinkedInCarouselSlide(slide_number=5, title="Key Takeaway", subtitle="Summary", bullet_points=["Adopt modular protocols."]),
            ]
            return LinkedInContentResult(
                format="carousel",
                post_copy=f"🚀 {core.hook}\n\nSwipe through the carousel below for the complete architecture breakdown 👇\n\n{' '.join(core.tags)}",
                carousel_data=LinkedInCarouselData(topic_title=core.hook[:50], total_slides=5, slides=fallback_slides),
                tags=core.tags,
            )
