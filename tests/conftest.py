"""Shared pytest fixtures: sample payloads and a mock-transport GitHub client."""

from __future__ import annotations

import httpx
import pytest

from app.config import Settings
from app.github.client import GitHubClient
from app.storage.stores import StorageBundle


def make_commit_payload(
    sha: str = "a" * 40,
    message: str = "feat(api): add endpoint",
    files: list[dict] | None = None,
    parents: int = 1,
) -> dict:
    if files is None:
        files = [
            {
                "filename": "app/api.py",
                "status": "added",
                "additions": 40,
                "deletions": 2,
                "changes": 42,
                "patch": "@@ -0,0 +1,40 @@\n+def handler():\n+    return True",
            }
        ]
    return {
        "sha": sha,
        "html_url": f"https://github.com/octocat/hello/commit/{sha}",
        "commit": {
            "author": {"name": "Octo Cat", "email": "octo@example.com", "date": "2026-01-01T10:00:00Z"},
            "committer": {"name": "Octo Cat", "email": "octo@example.com", "date": "2026-01-01T10:05:00Z"},
            "message": message,
        },
        "parents": [{"sha": f"{i}" * 40} for i in range(parents)],
        "stats": {
            "additions": sum(f.get("additions", 0) for f in files),
            "deletions": sum(f.get("deletions", 0) for f in files),
            "total": sum(f.get("changes", 0) for f in files),
        },
        "files": files,
    }


@pytest.fixture
def sample_commit() -> dict:
    return make_commit_payload()


@pytest.fixture
def commit_factory():
    return make_commit_payload


def build_mock_client(routes: dict[str, object], *, settings: Settings | None = None) -> GitHubClient:
    """Create a GitHubClient backed by an httpx.MockTransport.

    ``routes`` maps a path-substring to either a dict/list (200 JSON) or an
    ``httpx.Response``.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        for needle, value in routes.items():
            if needle in path:
                if isinstance(value, httpx.Response):
                    return value
                return httpx.Response(
                    200,
                    json=value,
                    headers={"X-RateLimit-Remaining": "4999", "X-RateLimit-Limit": "5000"},
                )
        return httpx.Response(404, json={"message": "Not Found"})

    transport = httpx.MockTransport(handler)
    return GitHubClient(
        settings or Settings(github_token="test-token"),
        cache=StorageBundle().cache,
        transport=transport,
    )


@pytest.fixture
def mock_client_factory():
    return build_mock_client
