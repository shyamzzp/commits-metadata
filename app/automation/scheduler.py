"""Scheduled Backfill Job + Incremental Commit Processor.

The scheduler is intentionally framework-light: it computes *what* to backfill
(new SHAs since the last processed one) and delegates execution to the engine.
A real deployment can drive ``run_backfill`` from APScheduler / a cron route.
"""

from __future__ import annotations

from app.discovery.scanner import CommitDiscovery
from app.models import JobResult
from app.processing.engine import ProcessingEngine
from app.storage.stores import RepoStateStore


async def new_shas_since_last(
    discovery: CommitDiscovery,
    repo_state: RepoStateStore,
    owner: str,
    repo: str,
    *,
    max_commits: int = 100,
) -> list[str]:
    """Return SHAs newer than the last processed SHA (incremental processing)."""
    repository = f"{owner}/{repo}"
    discovered = await discovery.discover_repo(owner, repo, max_commits=max_commits)
    last = repo_state.get_last_sha(repository)
    if not last:
        return discovered.shas
    out: list[str] = []
    for sha in discovered.shas:
        if sha == last:
            break
        out.append(sha)
    return out


async def run_backfill(
    engine: ProcessingEngine,
    discovery: CommitDiscovery,
    owner: str,
    repo: str,
    *,
    max_commits: int = 100,
) -> JobResult:
    """Discover new commits and process them incrementally."""
    shas = await new_shas_since_last(
        discovery, engine.storage.repo_state, owner, repo, max_commits=max_commits
    )
    return await engine.process_batch(owner, repo, shas)
