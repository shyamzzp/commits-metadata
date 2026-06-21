import hashlib
import hmac
import json

import httpx
import pytest

from app.automation import scheduler, webhook
from app.config import Settings
from app.discovery.scanner import CommitDiscovery
from app.github.client import GitHubClient
from app.github.url_parser import RefKind
from app.observability.telemetry import Telemetry
from app.processing.engine import ProcessingEngine
from app.storage.stores import StorageBundle
from tests.conftest import make_commit_payload


class TestWebhookSignature:
    def test_no_secret_skips_verification(self):
        assert webhook.verify_signature(None, b"body", None) is True

    def test_valid_signature(self):
        secret = "s3cr3t"
        body = b'{"a":1}'
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert webhook.verify_signature(secret, body, sig) is True

    def test_invalid_signature(self):
        assert webhook.verify_signature("s3cr3t", b"body", "sha256=deadbeef") is False

    def test_missing_signature_with_secret(self):
        assert webhook.verify_signature("s3cr3t", b"body", None) is False


class TestExtractPushCommits:
    def test_extracts_refs(self):
        payload = {
            "repository": {"full_name": "octocat/hello"},
            "commits": [{"id": "a" * 40}, {"id": "b" * 40}],
        }
        refs = webhook.extract_push_commits(payload)
        assert len(refs) == 2
        assert refs[0].kind is RefKind.COMMIT
        assert refs[0].owner == "octocat" and refs[0].repo == "hello"

    def test_no_repo(self):
        assert webhook.extract_push_commits({"commits": [{"id": "a"}]}) == []


def _engine_and_discovery(handler):
    storage = StorageBundle()
    client = GitHubClient(Settings(github_token="t"), cache=storage.cache, transport=httpx.MockTransport(handler))
    engine = ProcessingEngine(client, storage, Telemetry())
    return engine, CommitDiscovery(client), client


@pytest.mark.asyncio
class TestScheduler:
    async def test_new_shas_since_last(self):
        def handler(request):
            path = request.url.path
            if path.endswith("/commits"):
                return httpx.Response(
                    200,
                    json=[{"sha": "c" * 40}, {"sha": "b" * 40}, {"sha": "a" * 40}],
                    headers={"X-RateLimit-Remaining": "10"},
                )
            return httpx.Response(200, json={"default_branch": "main", "full_name": "o/r"}, headers={"X-RateLimit-Remaining": "10"})

        engine, discovery, client = _engine_and_discovery(handler)
        engine.storage.repo_state.set_last_sha("o/r", "b" * 40)
        new = await scheduler.new_shas_since_last(discovery, engine.storage.repo_state, "o", "r")
        assert new == ["c" * 40]  # stops at last-seen "b"
        await client.close()

    async def test_run_backfill_processes_new(self):
        def handler(request):
            path = request.url.path
            if "/commits/" in path:  # single commit detail
                sha = path.rsplit("/", 1)[-1]
                return httpx.Response(200, json=make_commit_payload(sha=sha), headers={"X-RateLimit-Remaining": "10"})
            if path.endswith("/commits"):
                return httpx.Response(200, json=[{"sha": "a" * 40}], headers={"X-RateLimit-Remaining": "10"})
            return httpx.Response(200, json={"default_branch": "main", "full_name": "o/r"}, headers={"X-RateLimit-Remaining": "10"})

        engine, discovery, client = _engine_and_discovery(handler)
        result = await scheduler.run_backfill(engine, discovery, "o", "r")
        assert result.succeeded == 1
        await client.close()
