import httpx
import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.config import Settings
from app.github.client import GitHubClient
from tests.conftest import make_commit_payload


@pytest.fixture
def client(monkeypatch):
    """TestClient with make_client patched to a mock-transport GitHub client.

    The mock client reuses the app's per-process storage cache so that data
    persisted during /process is visible to /commits, /dashboard, /export.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        hdr = {"X-RateLimit-Remaining": "10"}
        if "/commits/" in path:
            sha = path.rsplit("/", 1)[-1]
            return httpx.Response(200, json=make_commit_payload(sha=sha, message="feat: add x #1"), headers=hdr)
        if path.endswith("/commits"):
            return httpx.Response(200, json=[{"sha": "a" * 40}, {"sha": "b" * 40}], headers=hdr)
        if "/repos/" in path and path.count("/") == 3:  # /repos/o/r
            return httpx.Response(200, json={"default_branch": "main", "full_name": path.split("/repos/")[1]}, headers=hdr)
        if "/repos" in path:  # org repos
            return httpx.Response(200, json=[{"full_name": "octocat/hello"}], headers=hdr)
        return httpx.Response(404, json={"message": "nf"}, headers=hdr)

    def fake_make_client(settings, state):
        return GitHubClient(Settings(github_token="t"), cache=state.storage.cache, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(main, "make_client", fake_make_client)
    with TestClient(main.app) as c:
        yield c


class TestMeta:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_root_lists_endpoints(self, client):
        r = client.get("/")
        assert "/process/commit" in r.json()["endpoints"]


class TestProcessCommit:
    def test_process_single_commit(self, client):
        r = client.post(
            "/process/commit",
            json={"commit_url": f"https://github.com/octocat/hello/commit/{'a' * 40}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["change_type"] == "feature"
        assert body["issue_references"] == ["#1"]

    def test_rejects_non_commit_url(self, client):
        r = client.post("/process/commit", json={"commit_url": "https://github.com/octocat/hello"})
        assert r.status_code == 422

    def test_rejects_bad_url(self, client):
        r = client.post("/process/commit", json={"commit_url": "https://gitlab.com/x/y"})
        assert r.status_code == 422


class TestProcessRepo:
    def test_process_repo_batch(self, client):
        r = client.post(
            "/process/repo",
            json={"repo_url": "https://github.com/octocat/hello", "config": {"max_commits": 5}},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] in ("completed", "partial")
        assert body["total"] == 2


class TestOutputLayer:
    def test_search_and_get_and_dashboard_and_export(self, client):
        # populate
        client.post("/process/commit", json={"commit_url": f"https://github.com/octocat/hello/commit/{'a' * 40}"})

        r = client.get("/commits", params={"repository": "octocat/hello"})
        assert r.status_code == 200 and len(r.json()) >= 1

        r = client.get(f"/commits/octocat/hello/{'a' * 40}")
        assert r.status_code == 200

        r = client.get("/dashboard")
        assert r.json()["total_commits"] >= 1

        r = client.get("/export", params={"repository": "octocat/hello"})
        assert r.status_code == 200
        assert "attachment" in r.headers["content-disposition"]
        assert r.json()["count"] >= 1

    def test_get_missing_commit_404(self, client):
        r = client.get("/commits/no/repo/deadbeef")
        assert r.status_code == 404

    def test_metrics(self, client):
        client.post("/process/commit", json={"commit_url": f"https://github.com/octocat/hello/commit/{'a' * 40}"})
        r = client.get("/metrics")
        assert r.json()["counters"]["commits_validated"] >= 1


class TestWebhook:
    def test_push_event_processed(self, client):
        payload = {"repository": {"full_name": "octocat/hello"}, "commits": [{"id": "a" * 40}]}
        r = client.post("/webhook/github", json=payload, headers={"X-GitHub-Event": "push"})
        assert r.status_code == 200
        assert r.json()["processed"] == 1

    def test_non_push_ignored(self, client):
        r = client.post("/webhook/github", json={}, headers={"X-GitHub-Event": "ping"})
        assert r.json()["status"] == "ignored"
