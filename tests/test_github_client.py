import httpx
import pytest

from app.github.client import GitHubClient, GitHubError
from app.config import Settings
from app.storage.stores import StorageBundle
from tests.conftest import make_commit_payload


@pytest.mark.asyncio
class TestGitHubClient:
    async def test_get_commit(self, mock_client_factory):
        client = mock_client_factory({"/commits/": make_commit_payload(sha="c" * 40)})
        data = await client.get_commit("octocat", "hello", "c" * 40)
        assert data["sha"] == "c" * 40
        await client.close()

    async def test_404_raises(self, mock_client_factory):
        client = mock_client_factory({})  # nothing matches -> 404
        with pytest.raises(GitHubError) as ei:
            await client.get_commit("o", "r", "deadbeef")
        assert ei.value.status_code == 404
        await client.close()

    async def test_rate_limit_raises(self):
        def handler(request):
            return httpx.Response(403, json={"message": "limit"}, headers={"X-RateLimit-Remaining": "0"})

        client = GitHubClient(
            Settings(github_token="t"),
            cache=StorageBundle().cache,
            transport=httpx.MockTransport(handler),
        )
        with pytest.raises(GitHubError) as ei:
            await client.get_commit("o", "r", "abc1234")
        assert ei.value.status_code == 403
        await client.close()

    async def test_cache_avoids_second_call(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(200, json={"sha": "x" * 40}, headers={"X-RateLimit-Remaining": "10"})

        client = GitHubClient(
            Settings(github_token="t"),
            cache=StorageBundle().cache,
            transport=httpx.MockTransport(handler),
        )
        await client.get_commit("o", "r", "x" * 40)
        await client.get_commit("o", "r", "x" * 40)
        assert calls["n"] == 1  # second served from cache
        await client.close()

    async def test_pagination_stops_on_short_page(self):
        pages = {1: [{"sha": f"{i}" * 40} for i in range(100)], 2: [{"sha": "z" * 40}]}

        def handler(request):
            page = int(request.url.params.get("page", "1"))
            return httpx.Response(200, json=pages.get(page, []), headers={"X-RateLimit-Remaining": "10"})

        client = GitHubClient(
            Settings(github_token="t"),
            cache=StorageBundle().cache,
            transport=httpx.MockTransport(handler),
        )
        commits = await client.list_commits("o", "r", max_items=500)
        assert len(commits) == 101
        await client.close()

    async def test_authorization_header_set(self):
        captured = {}

        def handler(request):
            captured["auth"] = request.headers.get("Authorization")
            return httpx.Response(200, json={"sha": "a" * 40}, headers={"X-RateLimit-Remaining": "10"})

        client = GitHubClient(
            Settings(github_token="secret"),
            cache=StorageBundle().cache,
            transport=httpx.MockTransport(handler),
        )
        await client.get_commit("o", "r", "a" * 40)
        assert captured["auth"] == "Bearer secret"
        await client.close()
