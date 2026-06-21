"""Commit Processing Engine — orchestrates fetch → extract → build → validate → store."""

from __future__ import annotations

import uuid

from app.github.client import GitHubClient, GitHubError
from app.jobqueue.job_queue import CommitJob, CommitQueue
from app.models import FeatureMetadata, JobResult, JobStatus
from app.observability.telemetry import Telemetry
from app.processing import schema_builder, validator
from app.processing.llm_analyzer import LLMAnalyzer
from app.storage.stores import StorageBundle


class ProcessingEngine:
    """Drives a single commit and batches of commits through the pipeline."""

    def __init__(
        self,
        client: GitHubClient,
        storage: StorageBundle,
        telemetry: Telemetry | None = None,
        *,
        enable_llm: bool = False,
    ) -> None:
        self.client = client
        self.storage = storage
        self.telemetry = telemetry or Telemetry()
        self.llm = LLMAnalyzer(enabled=enable_llm)

    async def process_commit(
        self, owner: str, repo: str, sha: str, *, include_patch: bool = True
    ) -> FeatureMetadata:
        """Fetch one commit and run the full pipeline. Persists to all stores."""
        repository = f"{owner}/{repo}"
        raw = await self.client.get_commit(owner, repo, sha)
        self.storage.commits.put(repository, raw.get("sha", sha), raw)
        self.telemetry.metrics.inc("commits_fetched")

        meta = schema_builder.build_metadata(
            raw, repository=repository, include_patch=include_patch, llm=self.llm
        )
        validator.validate_metadata(meta)  # raises on schema violation
        self.telemetry.metrics.inc("commits_validated")

        self.storage.metadata.put(meta)
        self.storage.repo_state.set_last_sha(repository, meta.sha)
        self.telemetry.log.info("processed %s@%s -> %s", repository, meta.short_sha, meta.change_type.value)
        return meta

    async def process_batch(
        self,
        owner: str,
        repo: str,
        shas: list[str],
        *,
        include_patch: bool = True,
        max_retries: int = 3,
    ) -> JobResult:
        """Run a list of SHAs through a retrying queue and collect results."""
        job_id = uuid.uuid4().hex[:12]
        repository = f"{owner}/{repo}"
        queue = CommitQueue(max_retries=max_retries)
        queue.enqueue_many([CommitJob(owner, repo, sha) for sha in shas])

        result = JobResult(job_id=job_id, status=JobStatus.RUNNING, repository=repository, total=len(shas))

        while not queue.is_empty():
            job = queue.next_job()
            if job is None:
                break
            try:
                meta = await self.process_commit(
                    job.owner, job.repo, job.sha, include_patch=include_patch
                )
                result.commits.append(meta)
                result.succeeded += 1
                self.telemetry.metrics.inc("jobs_succeeded")
            except (GitHubError, validator.SchemaValidationError) as exc:
                dest = queue.mark_failed(job, str(exc))
                self.telemetry.metrics.inc(f"jobs_{dest}")
                if dest == "dead_letter":
                    result.failed += 1
                    result.errors.append({"sha": job.sha, "error": str(exc)})
                    self.telemetry.errors.record(
                        repository=repository, sha=job.sha, error=str(exc), fatal=True
                    )

        self.storage.repo_state.mark_processed(repository, result.succeeded)
        if result.failed == 0:
            result.status = JobStatus.COMPLETED
        elif result.succeeded == 0:
            result.status = JobStatus.FAILED
        else:
            result.status = JobStatus.PARTIAL
        return result
