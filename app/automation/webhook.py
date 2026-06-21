"""GitHub Webhook Receiver + Incremental Commit Processor helpers."""

from __future__ import annotations

import hashlib
import hmac

from app.github.url_parser import GitHubRef, RefKind


def verify_signature(secret: str | None, body: bytes, signature_header: str | None) -> bool:
    """Verify a GitHub ``X-Hub-Signature-256`` header.

    If no secret is configured, verification is skipped (returns True) so the
    Space works in open/demo mode; when a secret is set, the signature must match.
    """
    if not secret:
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def extract_push_commits(payload: dict) -> list[GitHubRef]:
    """Turn a ``push`` webhook payload into commit references for processing."""
    repo = payload.get("repository", {}) or {}
    full_name = repo.get("full_name", "")
    if "/" not in full_name:
        return []
    owner, name = full_name.split("/", 1)
    commits = payload.get("commits", []) or []
    refs: list[GitHubRef] = []
    for c in commits:
        sha = c.get("id") or c.get("sha")
        if sha:
            refs.append(GitHubRef(kind=RefKind.COMMIT, owner=owner, repo=name, sha=sha))
    return refs
