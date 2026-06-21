"""GitHub URL Parser — turns user-supplied URLs into structured references."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from urllib.parse import urlparse


class RefKind(str, Enum):
    COMMIT = "commit"
    REPO = "repo"
    ORG = "org"


class GitHubURLError(ValueError):
    """Raised when a URL cannot be parsed as a recognised GitHub reference."""


@dataclass(frozen=True)
class GitHubRef:
    kind: RefKind
    owner: str
    repo: Optional[str] = None
    sha: Optional[str] = None

    @property
    def full_name(self) -> Optional[str]:
        return f"{self.owner}/{self.repo}" if self.repo else None


_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")
_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _clean_segments(path: str) -> list[str]:
    return [seg for seg in path.strip("/").split("/") if seg]


def parse_github_url(url: str) -> GitHubRef:
    """Parse a GitHub URL into a :class:`GitHubRef`.

    Supports:
      * commit:  https://github.com/owner/repo/commit/<sha>
      * repo:    https://github.com/owner/repo  (optionally .git)
      * org/user: https://github.com/owner
    """
    if not url or not isinstance(url, str):
        raise GitHubURLError("URL must be a non-empty string")

    candidate = url.strip()
    if "://" not in candidate:
        candidate = "https://" + candidate

    parsed = urlparse(candidate)
    host = (parsed.netloc or "").lower()
    if "github" not in host:
        raise GitHubURLError(f"Not a GitHub host: {parsed.netloc!r}")

    segments = _clean_segments(parsed.path)
    if not segments:
        raise GitHubURLError("No owner found in URL")

    owner = segments[0]
    if not _NAME_RE.match(owner):
        raise GitHubURLError(f"Invalid owner segment: {owner!r}")

    # org / user only
    if len(segments) == 1:
        return GitHubRef(kind=RefKind.ORG, owner=owner)

    repo = segments[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    if not _NAME_RE.match(repo):
        raise GitHubURLError(f"Invalid repo segment: {repo!r}")

    # commit reference: .../commit/<sha>  or  .../commits/<sha>
    if len(segments) >= 4 and segments[2] in ("commit", "commits"):
        sha = segments[3]
        if not _SHA_RE.match(sha):
            raise GitHubURLError(f"Invalid commit SHA: {sha!r}")
        return GitHubRef(kind=RefKind.COMMIT, owner=owner, repo=repo, sha=sha.lower())

    # plain repo reference
    return GitHubRef(kind=RefKind.REPO, owner=owner, repo=repo)
