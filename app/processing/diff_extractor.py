"""Diff / Patch Extractor — normalises GitHub commit ``files`` into ChangedFile."""

from __future__ import annotations

from app.models import ChangedFile
from app.processing.file_classifier import classify_file, detect_language


def extract_changed_files(commit_payload: dict, *, include_patch: bool = True) -> list[ChangedFile]:
    """Turn a GitHub commit payload's ``files`` array into ChangedFile objects."""
    files = commit_payload.get("files") or []
    out: list[ChangedFile] = []
    for f in files:
        filename = f.get("filename", "")
        if not filename:
            continue
        out.append(
            ChangedFile(
                filename=filename,
                status=f.get("status", "modified"),
                additions=int(f.get("additions", 0) or 0),
                deletions=int(f.get("deletions", 0) or 0),
                changes=int(f.get("changes", 0) or 0),
                category=classify_file(filename),
                language=detect_language(filename),
                patch=f.get("patch") if include_patch else None,
            )
        )
    return out


def aggregate_stats(files: list[ChangedFile], commit_payload: dict | None = None) -> dict:
    """Aggregate additions/deletions. Prefer GitHub's authoritative ``stats``."""
    if commit_payload and isinstance(commit_payload.get("stats"), dict):
        stats = commit_payload["stats"]
        additions = int(stats.get("additions", 0) or 0)
        deletions = int(stats.get("deletions", 0) or 0)
        return {
            "additions": additions,
            "deletions": deletions,
            "total": int(stats.get("total", additions + deletions) or 0),
            "files_changed": len(files),
        }
    additions = sum(f.additions for f in files)
    deletions = sum(f.deletions for f in files)
    return {
        "additions": additions,
        "deletions": deletions,
        "total": additions + deletions,
        "files_changed": len(files),
    }


def category_counts(files: list[ChangedFile]) -> dict:
    counts: dict[str, int] = {}
    for f in files:
        counts[f.category.value] = counts.get(f.category.value, 0) + 1
    return counts


def distinct_languages(files: list[ChangedFile]) -> list[str]:
    langs = {f.language for f in files if f.language}
    return sorted(langs)
