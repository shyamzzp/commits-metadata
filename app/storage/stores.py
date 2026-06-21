"""Storage layer: raw commit store, metadata store, repo state, response cache.

All stores are in-memory and thread-safe enough for a single-process Space.
They share one interface so they can later be swapped for Redis/SQLite without
touching callers.
"""

from __future__ import annotations

import threading
from typing import Any, Optional

from app.models import FeatureMetadata


class ResponseCache:
    """API Response Cache — simple key/value cache for GitHub responses."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            return self._data.get(key)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        return len(self._data)


class CommitStore:
    """Raw Commit Store — keyed by ``owner/repo@sha``."""

    def __init__(self) -> None:
        self._data: dict[str, dict] = {}
        self._lock = threading.RLock()

    @staticmethod
    def key(repo: str, sha: str) -> str:
        return f"{repo}@{sha}"

    def put(self, repo: str, sha: str, raw: dict) -> None:
        with self._lock:
            self._data[self.key(repo, sha)] = raw

    def get(self, repo: str, sha: str) -> Optional[dict]:
        with self._lock:
            return self._data.get(self.key(repo, sha))

    def __len__(self) -> int:
        return len(self._data)


class MetadataStore:
    """Feature Metadata Store — feeds Search/Browse and the Dashboard."""

    def __init__(self) -> None:
        self._data: dict[str, FeatureMetadata] = {}
        self._lock = threading.RLock()

    def put(self, meta: FeatureMetadata) -> None:
        with self._lock:
            self._data[f"{meta.repository}@{meta.sha}"] = meta

    def get(self, repo: str, sha: str) -> Optional[FeatureMetadata]:
        with self._lock:
            return self._data.get(f"{repo}@{sha}")

    def all(self) -> list[FeatureMetadata]:
        with self._lock:
            return list(self._data.values())

    def search(
        self,
        *,
        repository: Optional[str] = None,
        change_type: Optional[str] = None,
        text: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[FeatureMetadata]:
        with self._lock:
            items = list(self._data.values())
        if repository:
            items = [m for m in items if m.repository == repository]
        if change_type:
            items = [m for m in items if m.change_type.value == change_type]
        if text:
            needle = text.lower()
            items = [m for m in items if needle in m.message.lower()]
        return items[offset : offset + limit]

    def dashboard(self) -> dict:
        with self._lock:
            items = list(self._data.values())
        by_type: dict[str, int] = {}
        by_repo: dict[str, int] = {}
        for m in items:
            by_type[m.change_type.value] = by_type.get(m.change_type.value, 0) + 1
            by_repo[m.repository] = by_repo.get(m.repository, 0) + 1
        return {
            "total_commits": len(items),
            "by_change_type": by_type,
            "by_repository": by_repo,
        }

    def __len__(self) -> int:
        return len(self._data)


class RepoStateStore:
    """Repo Processing State — tracks last processed SHA per repo for backfill."""

    def __init__(self) -> None:
        self._data: dict[str, dict] = {}
        self._lock = threading.RLock()

    def set_last_sha(self, repo: str, sha: str) -> None:
        with self._lock:
            self._data.setdefault(repo, {})["last_sha"] = sha

    def get_last_sha(self, repo: str) -> Optional[str]:
        with self._lock:
            return self._data.get(repo, {}).get("last_sha")

    def mark_processed(self, repo: str, count: int) -> None:
        with self._lock:
            state = self._data.setdefault(repo, {})
            state["processed"] = state.get("processed", 0) + count

    def get_state(self, repo: str) -> dict:
        with self._lock:
            return dict(self._data.get(repo, {}))


class StorageBundle:
    """Convenience container wiring all stores together for the app."""

    def __init__(self) -> None:
        self.cache = ResponseCache()
        self.commits = CommitStore()
        self.metadata = MetadataStore()
        self.repo_state = RepoStateStore()
