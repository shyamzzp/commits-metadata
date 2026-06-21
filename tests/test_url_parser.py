import pytest

from app.github.url_parser import GitHubURLError, RefKind, parse_github_url


class TestCommitUrls:
    def test_full_commit_url(self):
        ref = parse_github_url("https://github.com/octocat/Hello-World/commit/abc1234def5678")
        assert ref.kind is RefKind.COMMIT
        assert ref.owner == "octocat"
        assert ref.repo == "Hello-World"
        assert ref.sha == "abc1234def5678"
        assert ref.full_name == "octocat/Hello-World"

    def test_commit_sha_is_lowercased(self):
        ref = parse_github_url("https://github.com/o/r/commit/ABCDEF1")
        assert ref.sha == "abcdef1"

    def test_commits_plural_segment(self):
        ref = parse_github_url("https://github.com/o/r/commits/1234567")
        assert ref.kind is RefKind.COMMIT

    def test_invalid_sha_rejected(self):
        with pytest.raises(GitHubURLError):
            parse_github_url("https://github.com/o/r/commit/zz")


class TestRepoUrls:
    def test_repo_url(self):
        ref = parse_github_url("https://github.com/octocat/Hello-World")
        assert ref.kind is RefKind.REPO
        assert ref.full_name == "octocat/Hello-World"

    def test_repo_url_with_git_suffix(self):
        ref = parse_github_url("https://github.com/octocat/Hello-World.git")
        assert ref.repo == "Hello-World"

    def test_repo_url_without_scheme(self):
        ref = parse_github_url("github.com/octocat/Hello-World")
        assert ref.kind is RefKind.REPO


class TestOrgUrls:
    def test_org_url(self):
        ref = parse_github_url("https://github.com/octocat")
        assert ref.kind is RefKind.ORG
        assert ref.owner == "octocat"
        assert ref.repo is None


class TestErrors:
    @pytest.mark.parametrize("bad", ["", "   ", "https://gitlab.com/a/b", "not a url at all "])
    def test_rejects_non_github_or_empty(self, bad):
        with pytest.raises(GitHubURLError):
            parse_github_url(bad)

    def test_rejects_none(self):
        with pytest.raises(GitHubURLError):
            parse_github_url(None)  # type: ignore[arg-type]
