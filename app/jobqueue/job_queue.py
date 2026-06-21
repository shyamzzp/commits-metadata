"""Processing Queue: Job Queue, Retry Queue, and Failed Commit (dead-letter) Queue."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CommitJob:
    owner: str
    repo: str
    sha: str
    attempts: int = 0
    last_error: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    @property
    def repository(self) -> str:
        return f"{self.owner}/{self.repo}"


class CommitQueue:
    """A three-tier queue: main → retry (bounded by max_retries) → dead-letter."""

    def __init__(self, max_retries: int = 3) -> None:
        self.max_retries = max_retries
        self._main: deque[CommitJob] = deque()
        self._retry: deque[CommitJob] = deque()
        self._dead: list[CommitJob] = []

    # --- enqueue ----------------------------------------------------------- #
    def enqueue(self, job: CommitJob) -> None:
        self._main.append(job)

    def enqueue_many(self, jobs: list[CommitJob]) -> None:
        self._main.extend(jobs)

    # --- dequeue ----------------------------------------------------------- #
    def next_job(self) -> Optional[CommitJob]:
        """Drain retry queue first (fairness), then the main queue."""
        if self._retry:
            return self._retry.popleft()
        if self._main:
            return self._main.popleft()
        return None

    # --- outcome handling -------------------------------------------------- #
    def mark_failed(self, job: CommitJob, error: str) -> str:
        """Route a failed job to retry or dead-letter. Returns the destination."""
        job.attempts += 1
        job.last_error = error
        if job.attempts <= self.max_retries:
            self._retry.append(job)
            return "retry"
        self._dead.append(job)
        return "dead_letter"

    # --- introspection ----------------------------------------------------- #
    @property
    def pending(self) -> int:
        return len(self._main) + len(self._retry)

    @property
    def dead_letters(self) -> list[CommitJob]:
        return list(self._dead)

    def is_empty(self) -> bool:
        return self.pending == 0

    def stats(self) -> dict:
        return {
            "main": len(self._main),
            "retry": len(self._retry),
            "dead_letter": len(self._dead),
        }
