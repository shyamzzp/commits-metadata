"""Rule-Based Metadata Extractor — derives change type, tags, refs from a commit.

Heuristics combine Conventional Commits parsing, keyword scanning, and the
file-category mix so the engine works even on repos that don't follow a
convention.
"""

from __future__ import annotations

import re

from app.models import ChangedFile, ChangeType, FileCategory

_CONVENTIONAL_RE = re.compile(
    r"^(?P<type>feat|feature|fix|bugfix|docs|test|tests|chore|refactor|style|perf|build|ci|revert)"
    r"(?P<scope>\([^)]*\))?(?P<bang>!)?:",
    re.IGNORECASE,
)

_TYPE_ALIASES = {
    "feat": ChangeType.FEATURE,
    "feature": ChangeType.FEATURE,
    "fix": ChangeType.BUGFIX,
    "bugfix": ChangeType.BUGFIX,
    "docs": ChangeType.DOCS,
    "test": ChangeType.TEST,
    "tests": ChangeType.TEST,
    "chore": ChangeType.CHORE,
    "refactor": ChangeType.REFACTOR,
    "style": ChangeType.STYLE,
    "perf": ChangeType.PERF,
    "build": ChangeType.BUILD,
    "ci": ChangeType.CI,
    "revert": ChangeType.REVERT,
}

_KEYWORD_RULES = [
    (ChangeType.BUGFIX, re.compile(r"\b(fix(e[ds])?|bug|patch|hotfix|resolve[sd]?)\b", re.I)),
    (ChangeType.FEATURE, re.compile(r"\b(add(ed|s)?|implement(ed|s)?|introduce[sd]?|feature|support)\b", re.I)),
    (ChangeType.REFACTOR, re.compile(r"\b(refactor(ed|ing)?|cleanup|clean up|simplif(y|ied)|rename[ds]?)\b", re.I)),
    (ChangeType.PERF, re.compile(r"\b(perf(ormance)?|optimi[sz]e[ds]?|speed ?up|faster)\b", re.I)),
    (ChangeType.REVERT, re.compile(r"^revert\b", re.I)),
]

_ISSUE_RE = re.compile(r"#(\d+)")
_GH_ISSUE_URL_RE = re.compile(r"github\.com/[^/\s]+/[^/\s]+/(?:issues|pull)/(\d+)", re.I)
_BREAKING_RE = re.compile(r"BREAKING[ -]CHANGE", re.I)


def extract_issue_references(message: str) -> list[str]:
    refs = {f"#{m}" for m in _ISSUE_RE.findall(message)}
    refs.update(f"#{m}" for m in _GH_ISSUE_URL_RE.findall(message))
    return sorted(refs, key=lambda r: int(r[1:]))


def message_subject(message: str) -> str:
    return (message or "").strip().splitlines()[0] if message else ""


def is_breaking_change(message: str) -> bool:
    if _BREAKING_RE.search(message or ""):
        return True
    m = _CONVENTIONAL_RE.match((message or "").strip())
    return bool(m and m.group("bang"))


def classify_change_type(message: str, files: list[ChangedFile] | None = None) -> ChangeType:
    """Determine the dominant change type for a commit."""
    subject = message_subject(message)

    # 1. Conventional Commits prefix wins if present.
    m = _CONVENTIONAL_RE.match(subject.strip())
    if m:
        return _TYPE_ALIASES.get(m.group("type").lower(), ChangeType.UNKNOWN)

    # 2. Keyword heuristics on the subject line.
    for change_type, pattern in _KEYWORD_RULES:
        if pattern.search(subject):
            return change_type

    # 3. Fall back to the file-category mix.
    if files:
        counts: dict[FileCategory, int] = {}
        for f in files:
            counts[f.category] = counts.get(f.category, 0) + 1
        if counts:
            dominant = max(counts, key=counts.get)
            mapping = {
                FileCategory.TEST: ChangeType.TEST,
                FileCategory.DOCS: ChangeType.DOCS,
                FileCategory.CI: ChangeType.CI,
                FileCategory.BUILD: ChangeType.BUILD,
                FileCategory.SOURCE: ChangeType.FEATURE,
            }
            return mapping.get(dominant, ChangeType.UNKNOWN)

    return ChangeType.UNKNOWN


def derive_tags(message: str, files: list[ChangedFile]) -> list[str]:
    tags: set[str] = set()
    for f in files:
        tags.add(f"cat:{f.category.value}")
        if f.language:
            tags.add(f"lang:{f.language.lower()}")
    if is_breaking_change(message):
        tags.add("breaking")
    return sorted(tags)
