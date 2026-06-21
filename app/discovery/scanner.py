"""Commit Discovery Layer: repo scanner, branch scanner, commit lister, deduper."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.github.client import GitHubClient


def deduplicate_shas(shas: list[str]) -> list[str]:
    """Commit SHA Deduplicator — preserves first-seen order, case-insensitive."""
    seen: set[str] = set()
    out: list[str] = []
    for sha in shas:
        norm = sha.lower()
        if norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out


@dataclass
class DiscoveredCommits:
    repository: str
    default_branch: str
    branches: list[str] = field(default_factory=list)
    shas: list[str] = field(default_factory=list)


class CommitDiscovery:
    """Walks a repo (optionally across branches) and returns a deduped SHA list."""

    def __init__(self, client: GitHubClient) -> None:
        self.client = client

    async def discover_repo(
        self,
        owner: str,
        repo: str,
        *,
        branches: list[str] | None = None,
        max_commits: int = 100,
        dedupe: bool = True,
    ) -> DiscoveredCommits:
        repo_info = await self.client.get_repo(owner, repo)
        default_branch = repo_info.get("default_branch", "main")
        full_name = repo_info.get("full_name", f"{owner}/{repo}")

        target_branches = branches or [default_branch]
        all_shas: list[str] = []
        # Spread the commit budget across the requested branches.
        per_branch = max(1, max_commits // max(1, len(target_branches)))
        for branch in target_branches:
            commits = await self.client.list_commits(
                owner, repo, sha=branch, max_items=per_branch
            )
            all_shas.extend(c["sha"] for c in commits if "sha" in c)

        shas = deduplicate_shas(all_shas) if dedupe else all_shas
        return DiscoveredCommits(
            repository=full_name,
            default_branch=default_branch,
            branches=target_branches,
            shas=shas[:max_commits],
        )

    async def discover_org(
        self, org: str, *, max_repos: int = 50
    ) -> list[str]:
        """Return ``owner/repo`` full names for an org/user."""
        repos = await self.client.list_org_repos(org, max_items=max_repos)
        return [r["full_name"] for r in repos if "full_name" in r]
