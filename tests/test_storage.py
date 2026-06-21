from app.processing.schema_builder import build_metadata
from app.storage.stores import (
    CommitStore,
    MetadataStore,
    RepoStateStore,
    ResponseCache,
    StorageBundle,
)
from tests.conftest import make_commit_payload


class TestResponseCache:
    def test_get_set(self):
        c = ResponseCache()
        assert c.get("k") is None
        c.set("k", {"v": 1})
        assert c.get("k") == {"v": 1}
        assert len(c) == 1
        c.clear()
        assert len(c) == 0


class TestCommitStore:
    def test_put_get(self):
        s = CommitStore()
        s.put("o/r", "abc", {"sha": "abc"})
        assert s.get("o/r", "abc") == {"sha": "abc"}
        assert s.get("o/r", "missing") is None


class TestMetadataStore:
    def _meta(self, sha, msg="feat: x", repo="octocat/hello"):
        return build_metadata(make_commit_payload(sha=sha, message=msg), repository=repo)

    def test_put_and_search(self):
        s = MetadataStore()
        s.put(self._meta("a" * 40, "feat: add"))
        s.put(self._meta("b" * 40, "fix: bug"))
        assert len(s) == 2
        assert len(s.search(change_type="feature")) == 1
        assert len(s.search(text="bug")) == 1
        assert len(s.search(repository="octocat/hello")) == 2
        assert len(s.search(repository="nobody/none")) == 0

    def test_pagination(self):
        s = MetadataStore()
        for i in range(5):
            s.put(self._meta(f"{i}" * 40, f"feat: c{i}"))
        assert len(s.search(limit=2)) == 2
        assert len(s.search(limit=2, offset=4)) == 1

    def test_dashboard(self):
        s = MetadataStore()
        s.put(self._meta("a" * 40, "feat: add"))
        s.put(self._meta("b" * 40, "fix: bug"))
        d = s.dashboard()
        assert d["total_commits"] == 2
        assert d["by_change_type"]["feature"] == 1
        assert d["by_change_type"]["bugfix"] == 1


class TestRepoStateStore:
    def test_last_sha_and_processed(self):
        s = RepoStateStore()
        assert s.get_last_sha("o/r") is None
        s.set_last_sha("o/r", "abc")
        assert s.get_last_sha("o/r") == "abc"
        s.mark_processed("o/r", 3)
        s.mark_processed("o/r", 2)
        assert s.get_state("o/r")["processed"] == 5


class TestBundle:
    def test_bundle_has_all_stores(self):
        b = StorageBundle()
        assert b.cache is not None
        assert b.commits is not None
        assert b.metadata is not None
        assert b.repo_state is not None
