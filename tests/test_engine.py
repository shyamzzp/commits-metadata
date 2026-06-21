import httpx
import pytest

from app.config import Settings
from app.github.client import GitHubClient
from app.models import JobStatus
from app.observability.telemetry import Telemetry
from app.processing.engine import ProcessingEngine
from app.storage.stores import StorageBundle
from tests.conftest import make_commit_payload


def _engine_with(handler, *, enable_llm=False):
    storage = StorageBundle()
    client = GitHubClient(
        Settings(github_token="t"), cache=storage.cache, transport=httpx.MockTransport(handler)
    )
    return ProcessingEngine(client, storage, Telemetry(), enable_llm=enable_llm), client, storage


@pytest.mark.asyncio
class TestProcessCommit:
    async def test_single_commit_pipeline_persists(self):
        def handler(request):
            return httpx.Response(
                200,
                json=make_commit_payload(sha="a" * 40, message="feat: x"),
                headers={"X-RateLimit-Remaining": "10"},
            )

        engine, client, storage = _engine_with(handler)
        meta = await engine.process_commit("octocat", "hello", "a" * 40)
        assert meta.change_type.value == "feature"
        assert storage.metadata.get("octocat/hello", "a" * 40) is not None
        assert storage.commits.get("octocat/hello", "a" * 40) is not None
        assert storage.repo_state.get_last_sha("octocat/hello") == "a" * 40
        await client.close()

    async def test_llm_summary_present_when_enabled(self):
        def handler(request):
            return httpx.Response(200, json=make_commit_payload(), headers={"X-RateLimit-Remaining": "10"})

        engine, client, _ = _engine_with(handler, enable_llm=True)
        meta = await engine.process_commit("o", "r", "a" * 40)
        assert meta.llm_summary is not None
        await client.close()


@pytest.mark.asyncio
class TestProcessBatch:
    async def test_all_succeed(self):
        def handler(request):
            sha = request.url.path.rsplit("/", 1)[-1]
            return httpx.Response(200, json=make_commit_payload(sha=sha), headers={"X-RateLimit-Remaining": "10"})

        engine, client, _ = _engine_with(handler)
        shas = ["a" * 40, "b" * 40, "c" * 40]
        result = await engine.process_batch("o", "r", shas)
        assert result.status == JobStatus.COMPLETED
        assert result.succeeded == 3
        assert result.failed == 0
        await client.close()

    async def test_partial_when_some_fail(self):
        def handler(request):
            sha = request.url.path.rsplit("/", 1)[-1]
            if sha.startswith("b"):
                return httpx.Response(404, json={"message": "no"}, headers={"X-RateLimit-Remaining": "10"})
            return httpx.Response(200, json=make_commit_payload(sha=sha), headers={"X-RateLimit-Remaining": "10"})

        engine, client, _ = _engine_with(handler)
        result = await engine.process_batch("o", "r", ["a" * 40, "b" * 40], max_retries=1)
        assert result.status == JobStatus.PARTIAL
        assert result.succeeded == 1
        assert result.failed == 1
        assert len(result.errors) == 1
        await client.close()

    async def test_all_fail(self):
        def handler(request):
            return httpx.Response(404, json={"message": "no"}, headers={"X-RateLimit-Remaining": "10"})

        engine, client, _ = _engine_with(handler)
        result = await engine.process_batch("o", "r", ["a" * 40], max_retries=0)
        assert result.status == JobStatus.FAILED
        assert result.failed == 1
        await client.close()
