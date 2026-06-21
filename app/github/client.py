"""GitHub API Client — thin async wrapper over the REST API with caching + auth."""

from __future__ import annotations

from typing import Any, Optional

import httpx

from app.config import Settings, get_settings
from app.github.rate_limiter import RateLimiter
from app.storage.stores import ResponseCache


class GitHubError(RuntimeError):
    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class GitHubClient:
    """Async GitHub REST client.

    A pluggable ``transport`` (httpx.MockTransport) makes this fully testable
    without network access.
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        *,
        cache: Optional[ResponseCache] = None,
        rate_limiter: Optional[RateLimiter] = None,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.cache = cache or ResponseCache()
        self.rate_limiter = rate_limiter or RateLimiter()
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "commits-metadata/0.1",
        }
        if self.settings.github_token:
            headers["Authorization"] = f"Bearer {self.settings.github_token}"
        self._client = httpx.AsyncClient(
            base_url=self.settings.github_api_base,
            headers=headers,
            transport=transport,
            timeout=httpx.Timeout(30.0),
        )

    async def __aenter__(self) -> "GitHubClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    async def get_json(self, path: str, *, params: Optional[dict] = None, use_cache: bool = True) -> Any:
        cache_key = path + ("?" + "&".join(f"{k}={v}" for k, v in sorted((params or {}).items())) if params else "")
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached

        resp = await self._client.get(path, params=params)
        self.rate_limiter.update_from_headers(resp.headers)

        if self.rate_limiter.is_rate_limited_response(resp.status_code, resp.headers):
            raise GitHubError("GitHub rate limit exceeded", status_code=resp.status_code)
        if resp.status_code == 404:
            raise GitHubError(f"Not found: {path}", status_code=404)
        if resp.status_code >= 400:
            raise GitHubError(
                f"GitHub API error {resp.status_code} for {path}: {resp.text[:200]}",
                status_code=resp.status_code,
            )

        data = resp.json()
        if use_cache:
            self.cache.set(cache_key, data)
        return data

    async def get_paginated(self, path: str, *, params: Optional[dict] = None, max_items: int = 1000) -> list:
        """Follow ``per_page`` pagination up to ``max_items``."""
        out: list = []
        page = 1
        params = dict(params or {})
        params.setdefault("per_page", 100)
        while len(out) < max_items:
            params["page"] = page
            batch = await self.get_json(path, params=params, use_cache=False)
            if not isinstance(batch, list) or not batch:
                break
            out.extend(batch)
            if len(batch) < params["per_page"]:
                break
            page += 1
        return out[:max_items]

    # --- Domain helpers ---------------------------------------------------- #
    async def get_commit(self, owner: str, repo: str, sha: str) -> dict:
        return await self.get_json(f"/repos/{owner}/{repo}/commits/{sha}")

    async def get_repo(self, owner: str, repo: str) -> dict:
        return await self.get_json(f"/repos/{owner}/{repo}")

    async def list_branches(self, owner: str, repo: str, *, max_items: int = 200) -> list:
        return await self.get_paginated(f"/repos/{owner}/{repo}/branches", max_items=max_items)

    async def list_commits(self, owner: str, repo: str, *, sha: Optional[str] = None, max_items: int = 100) -> list:
        params = {"sha": sha} if sha else None
        return await self.get_paginated(f"/repos/{owner}/{repo}/commits", params=params, max_items=max_items)

    async def list_org_repos(self, org: str, *, max_items: int = 200) -> list:
        # Works for both orgs and users via the /users endpoint fallback.
        try:
            return await self.get_paginated(f"/orgs/{org}/repos", max_items=max_items)
        except GitHubError as exc:
            if exc.status_code == 404:
                return await self.get_paginated(f"/users/{org}/repos", max_items=max_items)
            raise
