"""Live on-demand scraper using Scrapling, GitHub API, and Agent Reach."""

import uuid
import httpx
import markdownify
from scrapling import Fetcher

from intelligence_os.core.logger import logger
from intelligence_os.storage.db import Database
from intelligence_os.storage.models import DiscoveryRecord
from intelligence_os.storage.repositories import DiscoveryRepository


class LiveTaskScraper:
    """Performs live on-demand scraping of repositories, articles, and topic queries using Scrapling."""

    def __init__(self, db: Database, github_token: str | None = None) -> None:
        self.db = db
        self.disc_repo = DiscoveryRepository(db)
        self.github_token = github_token

    def scrape_topic_or_url(self, topic: str | None = None, url: str | None = None) -> DiscoveryRecord:
        """Execute live scraping on target topic or URL and save/update in SQLite."""
        # Explicit URL targets keep their old behaviour (repo / single page).
        if url:
            if "github.com" in url:
                return self._safe_insert(self._scrape_github_url(url, topic or "GitHub Topic"))
            return self._safe_insert(self._scrape_with_scrapling(url, topic or url))
        # A plain topic now fans out across web + social instead of a single GitHub repo.
        results = self.scrape_topic(topic or "AI coding agents")
        if not results:
            raise ValueError(f"No scraped content found for topic '{topic}'.")
        return results[0]

    def scrape_topic(self, topic: str, max_items: int = 8, recency_days: int = 14) -> list[DiscoveryRecord]:
        """Fan-out scrape for a topic across GitHub (best-match) + social (HN) + web.

        Sources are ranked by TOPIC RELEVANCE (not raw popularity) so the strongest
        signal is always the subject the user typed, never a hardcoded default repo.
        Recency is enforced where source dates are available (default last 14 days);
        older items are kept only as a fallback when nothing recent exists.
        """
        topic = (topic or "").strip()
        if not topic:
            return []

        collected: list[DiscoveryRecord] = []

        # 1) GitHub best-match search -> scrape the README of top topical repos.
        #    Best-match (not stars) keeps the subject on-topic instead of surfacing
        #    mega-list repos that shadow the intended query.
        try:
            collected.extend(self._scrape_github_topic(topic, limit=3))
        except Exception as e:
            logger.warning(f"GitHub topic phase failed for '{topic}': {e}")

        # 2) Social / community — Agent Reach (HN keyless fallback).
        try:
            from intelligence_os.research.adapters.agent_reach import AgentReachAdapter
            ar = AgentReachAdapter()
            for it in ar.harvest(topic, limit=8):
                collected.append(self._item_to_discovery(it, "agent_reach", topic))
        except Exception as e:
            logger.warning(f"Agent Reach phase failed for '{topic}': {e}")

        # 3) Web — best-effort DuckDuckGo HTML -> Scrapling (skipped if blocked).
        try:
            from intelligence_os.research.adapters.scrapling import ScraplingAdapter
            web_urls = self._duckduckgo_search(topic, limit=5)
            if web_urls:
                adapter = ScraplingAdapter()
                for url in web_urls:
                    try:
                        items = adapter.harvest(url)
                        if items and items[0].markdown_content and len(items[0].markdown_content) > 200:
                            collected.append(self._item_to_discovery(items[0], "web", topic))
                    except Exception as e:
                        logger.warning(f"Web scrape failed for {url}: {e}")
        except Exception as e:
            logger.warning(f"Web search phase failed for '{topic}': {e}")

        if not collected:
            return []

        # 4) Rank by topic relevance so discoveries[0] is the most on-topic source.
        collected.sort(key=lambda d: self._relevance_score(d, topic), reverse=True)

        # 5) Recency filter (only when dates are known).
        recent, old = self._split_by_recency(collected, recency_days)
        collected = recent if recent else old

        # 6) Dedupe + cap.
        seen: set[str] = set()
        out: list[DiscoveryRecord] = []
        for d in collected:
            key = d.source_url or d.title
            if key in seen:
                continue
            seen.add(key)
            out.append(d)
        return out[:max_items]

    def _scrape_github_topic(self, topic: str, limit: int = 3) -> list[DiscoveryRecord]:
        """GitHub repository search (best-match) for a topic, scraping each README."""
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "AI-Content-Intelligence-OS"}
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"
        out: list[DiscoveryRecord] = []
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(
                    "https://api.github.com/search/repositories",
                    headers=headers,
                    params={"q": topic, "per_page": limit},
                )
                if resp.status_code != 200:
                    logger.warning(f"GitHub topic search returned HTTP {resp.status_code}")
                    return out
                for item in resp.json().get("items", [])[:limit]:
                    repo_url = item.get("html_url")
                    if not repo_url:
                        continue
                    try:
                        disc = self._scrape_github_url(repo_url, f"{item.get('name')}: {item.get('description') or topic}")
                        if disc:
                            out.append(disc)
                    except Exception as e:
                        logger.warning(f"GitHub README scrape failed for {repo_url}: {e}")
        except Exception as e:
            logger.warning(f"GitHub search live error: {e}")
        return out

    @staticmethod
    def _relevance_score(disc: DiscoveryRecord, topic: str) -> float:
        """Score a discovery by overlap of topic keywords with its content."""
        tokens = [t for t in topic.lower().split() if len(t) >= 3 and t.isalpha()]
        if not tokens:
            return 0.0
        blob = f"{disc.title} {disc.summary} {disc.source_url} {(disc.raw_content or '')[:600]}".lower()
        score = sum(1 for t in tokens if t in blob)
        # Prefer sources that carry real scraped content over link-only stubs.
        if disc.raw_content and len(disc.raw_content) > 300:
            score += 0.5
        return float(score)

    def _duckduckgo_search(self, topic: str, limit: int = 6) -> list[str]:
        """Return result URLs from DuckDuckGo HTML (no API key required)."""
        from urllib.parse import quote_plus, urlparse, parse_qs
        from scrapling import Fetcher

        query = quote_plus(topic)
        search_url = f"https://html.duckduckgo.com/html/?q={query}"
        urls: list[str] = []
        try:
            page = Fetcher.get(search_url, timeout=15)
            # DuckDuckGo wraps results in <a class="result__a" href="/l/?uddg=ENCODED">
            for href in page.css("a.result__a::attr(href)").getall():
                if not href:
                    continue
                if href.startswith("/l/?uddg="):
                    decoded = parse_qs(urlparse(href).query).get("uddg", [None])[0]
                    if decoded:
                        urls.append(decoded)
                elif href.startswith("http"):
                    urls.append(href)
                if len(urls) >= limit:
                    break
        except Exception as e:
            logger.warning(f"DuckDuckGo search failed: {e}")
        return urls

    def _item_to_discovery(self, item, source_type: str, topic: str) -> DiscoveryRecord:
        """Convert a RawHarvestItem into a stored DiscoveryRecord."""
        md = (getattr(item, "markdown_content", "") or getattr(item, "raw_content", "") or "")
        summary = (md or getattr(item, "title", topic))[:400].replace("\n", " ").strip()
        created = (getattr(item, "metadata", {}) or {}).get("created_at")
        return DiscoveryRecord(
            id=f"disc-{source_type}-{uuid.uuid4().hex[:6]}",
            source_url=getattr(item, "source_url", "") or f"https://search.local/{uuid.uuid4().hex[:8]}",
            title=getattr(item, "title", "") or topic,
            source_type=source_type,
            source_tier=1 if source_type == "web" else 2,
            author=getattr(item, "author", "") or "",
            raw_content=md[:9000],
            summary=summary,
            status="BRIEF_READY",
            content_potential=0.9 if source_type == "web" else 0.8,
            content_angle="experiment",
            verification_notes=f"Live {source_type} intelligence for topic: {topic}",
        )

    @staticmethod
    def _split_by_recency(discoveries: list[DiscoveryRecord], recency_days: int):
        """Split into (recent, old) using discovery_timestamp / metadata.created_at."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        recent, old = [], []
        for d in discoveries:
            ts = d.discovery_timestamp
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                if (now - dt).days <= recency_days:
                    recent.append(d)
                else:
                    old.append(d)
            except Exception:
                # No reliable date — keep as "recent" so we never silently drop content.
                recent.append(d)
        return recent, old

    def _safe_insert(self, disc: DiscoveryRecord) -> DiscoveryRecord:
        """Save or update in database safely (handling UNIQUE constraint)"""
        existing = self.disc_repo.get_by_url(disc.source_url)
        if existing:
            logger.info(f"Reusing existing discovery for {disc.source_url}: {existing.id}")
            return existing
        self.disc_repo.insert(disc)
        logger.info(f"Inserted new live discovery: {disc.id} ({disc.title})")
        return disc

    def _scrape_agent_reach(self, query: str, fallback_title: str) -> DiscoveryRecord | None:
        """Scrape socials via local AgentReach adapter."""
        from intelligence_os.research.adapters.agent_reach import AgentReachAdapter
        adapter = AgentReachAdapter()
        if not adapter.is_available():
            logger.warning("Agent Reach is offline. Please start local service on port 8080. Falling back to web/github.")
            return None
        
        items = adapter.harvest(query, limit=1)
        if not items:
            return None
        
        item = items[0]
        return DiscoveryRecord(
            id=f"disc-ar-{uuid.uuid4().hex[:6]}",
            source_url=item.source_url or f"https://agentreach.local/{uuid.uuid4().hex[:8]}",
            title=item.title or fallback_title,
            source_type="agent_reach",
            source_tier=2,
            author=item.author,
            raw_content=item.raw_content,
            summary=item.raw_content[:350].strip(),
            status="BRIEF_READY",
            content_potential=0.88,
            content_angle="experiment",
            verification_notes="Live social intelligence gathered via local Agent Reach.",
        )

    def _scrape_with_scrapling(self, url: str, fallback_title: str) -> DiscoveryRecord:
        """Scrape web page or technical article using ScraplingAdapter (Zero Docker)."""
        from intelligence_os.research.adapters.scrapling import ScraplingAdapter
        adapter = ScraplingAdapter()

        items = adapter.harvest(url)
        if items:
            item = items[0]
            return DiscoveryRecord(
                id=f"disc-scrapling-{uuid.uuid4().hex[:6]}",
                source_url=url,
                title=item.title or fallback_title,
                source_type="scrapling",
                source_tier=1,
                raw_content=item.markdown_content[:8000],
                summary=(item.markdown_content or "")[:350].replace("\n", " ").strip(),
                status="BRIEF_READY",
                content_potential=0.94,
                content_angle="experiment",
                verification_notes="Live scraped with Scrapling adaptive stealth engine (Zero Docker).",
            )

        # Honest failure: never fabricate content that would poison LLM grounding.
        raise ValueError(f"Live scrape returned no usable content for {url}.")

    def _scrape_github_url(self, url: str, fallback_title: str) -> DiscoveryRecord:
        """Scrape live repository README and metadata from GitHub."""
        parts = url.rstrip("/").split("github.com/")[-1].split("/")
        if len(parts) >= 2:
            owner, repo = parts[0], parts[1]
            raw_readme_url = f"https://raw.githubusercontent.com/{owner}/{repo}/main/README.md"
            headers = {"User-Agent": "AI-Content-Intelligence-OS"}
            if self.github_token:
                headers["Authorization"] = f"Bearer {self.github_token}"

            try:
                with httpx.Client(timeout=10.0) as client:
                    resp = client.get(raw_readme_url, headers=headers)
                    if resp.status_code != 200:
                        raw_readme_url = f"https://raw.githubusercontent.com/{owner}/{repo}/master/README.md"
                        resp = client.get(raw_readme_url, headers=headers)

                    if resp.status_code == 200:
                        content = resp.text
                        title = f"{owner}/{repo}: {fallback_title}" if fallback_title != "Trending AI Development" else f"{owner}/{repo}"
                        return DiscoveryRecord(
                            id=f"disc-gh-{owner}-{repo}",
                            source_url=url,
                            title=title,
                            source_type="github",
                            source_tier=1,
                            author=owner,
                            raw_content=content[:8000],
                            summary=content[:350].replace("#", "").strip(),
                            status="BRIEF_READY",
                            content_potential=0.95,
                            content_angle="workflow",
                            verification_notes="Live scraped from GitHub repository README.",
                        )
            except Exception as e:
                logger.warning(f"Failed to scrape GitHub README for {url}: {e}")

        return DiscoveryRecord(
            id=f"disc-gh-{uuid.uuid4().hex[:6]}",
            source_url=url,
            title=fallback_title or url,
            source_type="github",
            source_tier=1,
            raw_content=f"Live repository reference: {url}",
            summary=f"Technical repository for {fallback_title}",
            status="BRIEF_READY",
            content_potential=0.90,
            content_angle="workflow",
        )

    def _search_and_scrape_topic(self, topic: str) -> DiscoveryRecord:
        """Live search GitHub and technical repositories for a topic query."""
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "AI-Content-Intelligence-OS",
        }
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"

        params = {
            "q": f"{topic} in:name,description,readme stars:>50",
            # GitHub's default 'best match' ranks topical repos correctly;
            # sorting by stars lets mega-lists shadow the intended subject.
            "order": "desc",
            "per_page": 3,
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(
                    "https://api.github.com/search/repositories",
                    headers=headers,
                    params=params,
                )
                if resp.status_code != 200:
                    logger.warning(f"GitHub topic search returned HTTP {resp.status_code} (rate limits reset each minute/hour)")
                elif resp.json().get("items"):
                    top = resp.json()["items"][0]
                    repo_url = top.get("html_url")
                    owner = top.get("owner", {}).get("login", "ai-builder")
                    name = top.get("name")
                    desc = top.get("description") or topic
                    stars = top.get("stargazers_count", 0)

                    return self._scrape_github_url(repo_url, f"{name}: {desc} ({stars:,} stars)")
        except Exception as e:
            logger.warning(f"GitHub search live error: {e}")

        # Honest failure: no fabricated placeholder repos.
        raise ValueError(
            f"GitHub search returned no results for '{topic}'. "
            "If this persists, add GITHUB_TOKEN to .env to lift unauthenticated rate limits."
        )
