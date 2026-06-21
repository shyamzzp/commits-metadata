"""Changed File Classifier — maps filenames to categories and languages."""

from __future__ import annotations

import os

from app.models import FileCategory

# Extension → language
_LANG_BY_EXT = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".go": "Go",
    ".rb": "Ruby",
    ".rs": "Rust",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".cc": "C++",
    ".cs": "C#",
    ".php": "PHP",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".scala": "Scala",
    ".sh": "Shell",
    ".sql": "SQL",
    ".md": "Markdown",
    ".rst": "reStructuredText",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".json": "JSON",
    ".toml": "TOML",
}

_CONFIG_EXT = {".yml", ".yaml", ".toml", ".ini", ".cfg", ".env", ".json"}
_DOC_EXT = {".md", ".rst", ".txt", ".adoc"}
_ASSET_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2", ".ttf"}
_DATA_EXT = {".csv", ".tsv", ".parquet", ".xml"}

_BUILD_FILES = {
    "dockerfile",
    "makefile",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "poetry.lock",
    "requirements.txt",
    "go.mod",
    "go.sum",
    "cargo.toml",
    "cargo.lock",
    "build.gradle",
    "pom.xml",
}


def detect_language(filename: str) -> str | None:
    _, ext = os.path.splitext(filename.lower())
    return _LANG_BY_EXT.get(ext)


def _is_test_path(path: str) -> bool:
    base = os.path.basename(path)
    segments = path.split("/")
    if any(seg in ("test", "tests", "__tests__", "spec", "specs") for seg in segments):
        return True
    return (
        base.startswith("test_")
        or base.endswith("_test.py")
        or ".test." in base
        or ".spec." in base
    )


def classify_file(filename: str) -> FileCategory:
    """Classify a single changed file path into a :class:`FileCategory`."""
    path = filename.lower()
    base = os.path.basename(path)
    _, ext = os.path.splitext(base)

    if path.startswith(".github/workflows/") or "/.github/workflows/" in path:
        return FileCategory.CI
    if base in (".gitlab-ci.yml", ".travis.yml", "azure-pipelines.yml", "jenkinsfile"):
        return FileCategory.CI
    if _is_test_path(path):
        return FileCategory.TEST
    if base in _BUILD_FILES or base.startswith("dockerfile"):
        return FileCategory.BUILD
    if ext in _DOC_EXT or base == "readme":
        return FileCategory.DOCS
    if ext in _ASSET_EXT:
        return FileCategory.ASSET
    if ext in _DATA_EXT:
        return FileCategory.DATA
    if ext in _CONFIG_EXT:
        return FileCategory.CONFIG
    if ext in _LANG_BY_EXT and ext not in _DOC_EXT:
        return FileCategory.SOURCE
    return FileCategory.OTHER
