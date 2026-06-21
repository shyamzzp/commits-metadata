import pytest

from app.discovery.scanner import CommitDiscovery, deduplicate_shas


class TestDeduplicate:
    def test_preserves_order_case_insensitive(self):
        assert deduplicate_shas(["A", "b", "a", "B", "c"]) == ["a", "b", "c"]

    def test_empty(self):
        assert deduplicate_shas([]) == []


@pytest.mark.asyncio
class TestCommitDiscovery:
    async def test_discover_repo_default_branch(self, mock_client_factory):
        client = mock_client_factory(
            {
                "/repos/octocat/hello/commits": [{"sha": "a" * 40}, {"sha": "b" * 40}],
                "/repos/octocat/hello": {"default_branch": "main", "full_name": "octocat/hello"},
            }
        )
        disc = CommitDiscovery(client)
        result = await disc.discover_repo("octocat", "hello", max_commits=10)
        assert result.repository == "octocat/hello"
        assert result.default_branch == "main"
        assert result.shas == ["a" * 40, "b" * 40]
        await client.close()

    async def test_dedup_across_branches(self, mock_client_factory):
        client = mock_client_factory(
            {
                "/repos/o/r/commits": [{"sha": "a" * 40}, {"sha": "b" * 40}],
                "/repos/o/r": {"default_branch": "main", "full_name": "o/r"},
            }
        )
        disc = CommitDiscovery(client)
        result = await disc.discover_repo("o", "r", branches=["main", "dev"], max_commits=10)
        # same mock returns same shas for both branches -> deduped
        assert result.shas == ["a" * 40, "b" * 40]
        await client.close()

    async def test_discover_org(self, mock_client_factory):
        client = mock_client_factory(
            {"/orgs/octocat/repos": [{"full_name": "octocat/a"}, {"full_name": "octocat/b"}]}
        )
        disc = CommitDiscovery(client)
        assert await disc.discover_org("octocat") == ["octocat/a", "octocat/b"]
        await client.close()
