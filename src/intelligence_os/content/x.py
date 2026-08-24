"""X (Twitter) content generator for standalone posts and technical threads in natural English."""

import json
import re
from typing import Literal
from pydantic import BaseModel, Field

from intelligence_os.core.logger import logger
from intelligence_os.intelligence.openrouter import OpenRouterClient, clean_json_response
from intelligence_os.storage.models import ResearchCoreData


class XPostItem(BaseModel):
    """Single post within an X thread."""

    post_number: int
    text: str = Field(description="Clean plain-text English tweet with bullet points and emojis. Max 280 characters. Zero JSON formatting.")


class XContentResult(BaseModel):
    """Result of X content generation (standalone post or multi-post thread)."""

    format: Literal["post", "thread"]
    posts: list[XPostItem] = Field(default_factory=list)
    full_text_rendered: str


X_SYSTEM_PROMPT = """You are a senior AI systems engineer writing high-signal, engaging posts and threads for X (formerly Twitter).
Your tone: sharp, insightful, natural English, written by an experienced developer.

MANDATORY RULES:
1. Write in 100% natural, human English. Use bullet points (•, ⚡, 📌), numbered takeaways, and emojis.
2. NEVER output programming code blocks (like Python/JSON) inside the tweet copy unless it is an inline 3-word command.
3. NEVER output raw JSON syntax in the text itself.
4. Each post MUST be under 270 characters to fit Twitter's limit.
5. If format is 'thread':
   - Post 1: High-impact hook stating the breakthrough and why it matters (1/5)
   - Post 2: The exact technical mechanism / architecture in bullet points (2/5)
   - Post 3: Step-by-step developer implementation (3/5)
   - Post 4: Honest trade-offs, edge cases, or limitations (4/5)
   - Post 5: Key takeaway and link to source evidence (5/5)

Output strictly in JSON matching the schema so our parser can extract the clean text."""


class XGenerator:
    """Generates clean, natural English posts and threads for X."""

    def __init__(self, openrouter_client: OpenRouterClient) -> None:
        self.client = openrouter_client

    def generate(
        self,
        core: ResearchCoreData,
        preferred_format: Literal["post", "thread"] = "thread",
    ) -> XContentResult:
        """Generate structured X content using configured copywriting model."""
        logger.info(f"Generating X {preferred_format} with model {self.client.copywriting_model} for angle: {core.content_angle}")

        user_prompt = f"""TOPIC & RESEARCH CORE:
Topic: {core.hook}
Core Insight: {core.core_insight}
Evidence Sources: {', '.join(core.evidence)}
Practical Takeaway: {core.practical_takeaway}
Limitations: {core.limitations}
Content Angle: {core.content_angle}

Preferred Format: {preferred_format}

INSTRUCTIONS:
Write a high-signal 5-post thread in natural English with bullet points.
Every post MUST be derived from THIS research core above and name the actual project/tool.
Return JSON matching:
{{
  "format": "{preferred_format}",
  "posts": [
    {{"post_number": 1, "text": "1/5 <hook about this exact topic>"}},
    {{"post_number": 2, "text": "2/5 <architecture/mechanism bullets>"}},
    {{"post_number": 3, "text": "3/5 <implementation steps>"}},
    {{"post_number": 4, "text": "4/5 <limitations & edge cases>"}},
    {{"post_number": 5, "text": "5/5 <takeaway + link: {core.evidence[0] if core.evidence else ''}>"}}
  ],
  "full_text_rendered": "<all posts joined with double newlines>"
}}"""

        messages = [
            {"role": "system", "content": X_SYSTEM_PROMPT},
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
            posts = [XPostItem(**p) for p in raw_json.get("posts", [])]
            if posts:
                rendered = "\n\n".join(p.text for p in posts)
                return XContentResult(format=preferred_format, posts=posts, full_text_rendered=rendered)
            return XContentResult(**raw_json)
        except Exception as e:
            logger.warning(f"Fallback parsing for X generator: {e}")
            # Salvage post texts even when the surrounding JSON is malformed
            salvaged = re.findall(r'"text"\s*:\s*"((?:[^"\\]|\\.)*)"', cleaned)
            if salvaged:
                texts = [t.encode().decode("unicode_escape", errors="ignore").strip() for t in salvaged]
                posts = [XPostItem(post_number=i + 1, text=t) for i, t in enumerate(texts) if t]
                if posts:
                    return XContentResult(
                        format=preferred_format,
                        posts=posts,
                        full_text_rendered="\n\n".join(p.text for p in posts),
                    )
            clean_lines = [line.strip() for line in cleaned.split("\n") if line.strip() and not line.startswith("{") and not line.startswith("}")]
            combined = "\n\n".join(clean_lines) if clean_lines else cleaned
            return XContentResult(
                format=preferred_format,
                posts=[XPostItem(post_number=1, text=combined[:270])],
                full_text_rendered=combined,
            )
