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
        if "/" in target and not target.startswith("topic:") and not target.startswith("org:") and " " not in target:
            # Direct repository path
            item = self._fetch_single_repo(target.strip())
            return [item] if item else []

        # Repository search query
        return self._search_repositories(target, limit=kwargs.get("limit", 5))

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
        """Search GitHub for relevant repositories."""
        headers = self._get_headers()
        params = {
            "q": query,
            "sort": "updated",
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
                full_name = item.get("full_name")
                if full_name:
                    repo_item = self._fetch_single_repo(full_name)
                    if repo_item:
                        results.append(repo_item)
            return results
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                logger.warning("GitHub API rate limit exceeded during search.")
            else:
                logger.error(f"GitHub search failed for '{query}': {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error in GitHub search '{query}': {e}")
            return []
