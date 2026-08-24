"""GitHub intelligence adapter for repository, release, and commit tracking."""

from typing import Any
import httpx

from intelligence_os.core.logger import logger
from intelligence_os.research.adapters.base import BaseResearchAdapter, RawHarvestItem


class GitHubAdapter(BaseResearchAdapter):
    """Harvests repositories, release notes, and commit activity from GitHub API."""

    def __init__(
        self,
        token: str | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        super().__init__(name="github")
        self.token = token
        self.timeout_seconds = timeout_seconds
        self.api_base = "https://api.github.com"

    def _get_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "AI-Content-Intelligence-OS/0.1.0",
        }
        if self.token and self.token.strip():
            headers["Authorization"] = f"Bearer {self.token.strip()}"
        return headers

    def is_available(self) -> bool:
        """Check GitHub API reachability and rate limit status."""
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(f"{self.api_base}/zen", headers=self._get_headers())
                return resp.status_code == 200
        except Exception:
            return False

    def harvest(self, target: str, **kwargs: Any) -> list[RawHarvestItem]:
        """Harvest repositories based on explicit repo path ('owner/repo') or search query."""
        if "/" in target and not target.startswith(("topic:", "org:", "user:")) and " " not in target:
            # Direct repository path
            item = self._fetch_single_repo(target.strip())
            return [item] if item else []

        # Repository search query. GitHub search API does not support boolean OR,
        # so split compound queries ("topic:a OR topic:b") into separate searches.
        queries = [q.strip() for q in target.split(" OR ") if q.strip()]
        limit = kwargs.get("limit", 5)
        merged: dict[str, RawHarvestItem] = {}
        per_query_limit = max(limit // len(queries), 2) if queries else limit
        for query in queries:
            for item in self._search_repositories(query, limit=per_query_limit):
                merged.setdefault(item.source_url, item)
        return list(merged.values())[:limit]

    def _fetch_single_repo(self, repo_full_name: str) -> RawHarvestItem | None:
        """Fetch metadata, README, and latest release for a single repository."""
        headers = self._get_headers()
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                # 1. Repo Metadata
                repo_resp = client.get(f"{self.api_base}/repos/{repo_full_name}", headers=headers)
                if repo_resp.status_code == 404:
                    logger.warning(f"GitHub repository not found: {repo_full_name}")
                    return None
                repo_resp.raise_for_status()
                repo_data = repo_resp.json()

                # 2. Latest Release (if any)
                release_info = ""
                try:
                    rel_resp = client.get(f"{self.api_base}/repos/{repo_full_name}/releases/latest", headers=headers)
                    if rel_resp.status_code == 200:
                        rel_data = rel_resp.json()
                        release_info = f"\n\n### Latest Release: {rel_data.get('name') or rel_data.get('tag_name')}\n{rel_data.get('body', '')}"
                except Exception:
                    pass

                # 3. README
                readme_content = ""
                try:
                    readme_resp = client.get(
                        f"{self.api_base}/repos/{repo_full_name}/readme",
                        headers={**headers, "Accept": "application/vnd.github.raw+json"},
                    )
                    if readme_resp.status_code == 200:
                        readme_content = readme_resp.text[:8000]  # Cap at 8KB to avoid bloat
                except Exception:
                    pass

            title = f"{repo_data.get('full_name')}: {repo_data.get('description') or 'Open Source AI Project'}"
            full_markdown = f"# {title}\n\n**Stars:** {repo_data.get('stargazers_count')} | **Forks:** {repo_data.get('forks_count')} | **License:** {repo_data.get('license', {}).get('name') if repo_data.get('license') else 'None'}\n\n**Topics:** {', '.join(repo_data.get('topics', []))}\n\n## README Summary\n{readme_content}{release_info}"

            return RawHarvestItem(
                source_url=repo_data.get("html_url", f"https://github.com/{repo_full_name}"),
                title=title,
                raw_content=full_markdown,
                markdown_content=full_markdown,
                author=repo_data.get("owner", {}).get("login", ""),
                source_type="github",
                source_tier=1,
                metadata={
                    "stars": repo_data.get("stargazers_count", 0),
                    "forks": repo_data.get("forks_count", 0),
                    "open_issues": repo_data.get("open_issues_count", 0),
                    "language": repo_data.get("language"),
                    "topics": repo_data.get("topics", []),
                    "created_at": repo_data.get("created_at"),
                    "pushed_at": repo_data.get("pushed_at"),
                },
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                logger.warning("GitHub API rate limit exceeded. Set GITHUB_TOKEN in .env to increase limits.")
            else:
                logger.error(f"GitHub API error fetching {repo_full_name}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching GitHub repo {repo_full_name}: {e}")
            return None

    def _search_repositories(self, query: str, limit: int = 5) -> list[RawHarvestItem]:
        """Search GitHub for relevant repositories.

        Builds items directly from the search response (1 API call) instead of
        fetching each repo individually, preserving the unauthenticated rate limit.
        """
        headers = self._get_headers()
        # Extract a trailing "sort:<value>" qualifier into the dedicated sort param
        sort = "updated"
        query_parts = query.split()
        if "sort:" in query_parts:
            idx = query_parts.index("sort:")
            candidate = query_parts[idx + 1] if idx + 1 < len(query_parts) else ""
            if candidate in {"updated", "stars", "forks", "help-wanted-issues"}:
                sort = candidate
            query_parts = [p for i, p in enumerate(query_parts) if p != "sort:" and i != idx + 1]
        clean_query = " ".join(query_parts)

        params = {
            "q": clean_query,
            "sort": sort,
            "order": "desc",
            "per_page": min(limit, 10),
        }
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                resp = client.get(f"{self.api_base}/search/repositories", headers=headers, params=params)
                resp.raise_for_status()
                data = resp.json()

            results: list[RawHarvestItem] = []
            for item in data.get("items", [])[:limit]:
                full_name = item.get("full_name") or ""
                description = item.get("description") or "Open Source AI Project"
                title = f"{full_name}: {description}"
                markdown = (
                    f"# {title}\n\n"
                    f"**Stars:** {item.get('stargazers_count', 0)} | **Forks:** {item.get('forks_count', 0)} | "
                    f"**Language:** {item.get('language') or 'N/A'}\n\n"
                    f"**Topics:** {', '.join(item.get('topics', []))}\n\n"
                    f"{description}\n\n"
                    f"Last pushed: {item.get('pushed_at')}"
                )
                results.append(
                    RawHarvestItem(
                        source_url=item.get("html_url", f"https://github.com/{full_name}"),
                        title=title,
                        raw_content=markdown,
                        markdown_content=markdown,
                        author=item.get("owner", {}).get("login", ""),
                        source_type="github",
                        source_tier=1,
                        metadata={
                            "stars": item.get("stargazers_count", 0),
                            "forks": item.get("forks_count", 0),
                            "open_issues": item.get("open_issues_count", 0),
                            "language": item.get("language"),
                            "topics": item.get("topics", []),
                            "created_at": item.get("created_at"),
                            "pushed_at": item.get("pushed_at"),
                            "engine": "search_payload",
                        },
                    )
                )
            return results
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                logger.warning("GitHub API rate limit exceeded during search.")
            elif e.response.status_code == 422:
                logger.warning(f"GitHub rejected search query '{query}' (422). Skipping.")
            else:
                logger.error(f"GitHub search failed for '{query}': {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error in GitHub search '{query}': {e}")
            return []
