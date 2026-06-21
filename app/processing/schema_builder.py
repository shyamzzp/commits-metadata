"""Feature Metadata Builder — assembles a FeatureMetadata from a raw commit."""

from __future__ import annotations

from app.models import FeatureMetadata
from app.processing import diff_extractor, rule_engine
from app.processing.llm_analyzer import LLMAnalyzer


def build_metadata(
    commit_payload: dict,
    *,
    repository: str,
    include_patch: bool = True,
    llm: LLMAnalyzer | None = None,
) -> FeatureMetadata:
    """Build the fixed feature-metadata object from a GitHub commit payload."""
    sha = commit_payload.get("sha", "")
    commit = commit_payload.get("commit", {}) or {}
    author = commit.get("author", {}) or {}
    committer = commit.get("committer", {}) or {}
    message = commit.get("message", "") or ""
    parents = commit_payload.get("parents", []) or []

    files = diff_extractor.extract_changed_files(commit_payload, include_patch=include_patch)
    stats = diff_extractor.aggregate_stats(files, commit_payload)

    change_type = rule_engine.classify_change_type(message, files)
    summary = llm.analyze(message, files) if llm else None

    return FeatureMetadata(
        sha=sha,
        short_sha=sha[:7],
        repository=repository,
        url=commit_payload.get("html_url", ""),
        author_name=author.get("name"),
        author_email=author.get("email"),
        authored_at=author.get("date"),
        committed_at=committer.get("date"),
        message=message,
        message_subject=rule_engine.message_subject(message),
        change_type=change_type,
        is_merge=len(parents) > 1,
        breaking_change=rule_engine.is_breaking_change(message),
        issue_references=rule_engine.extract_issue_references(message),
        tags=rule_engine.derive_tags(message, files),
        stats=stats,
        file_categories=diff_extractor.category_counts(files),
        languages=diff_extractor.distinct_languages(files),
        files=files,
        llm_summary=summary,
    )
