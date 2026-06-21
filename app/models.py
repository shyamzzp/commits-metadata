"""Pydantic models: input layer requests and the fixed feature-metadata schema."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from app.config import ProcessingConfig


# --------------------------------------------------------------------------- #
# Input layer
# --------------------------------------------------------------------------- #
class CommitRequest(BaseModel):
    """Single Commit Processor input (Commit URL)."""

    commit_url: str = Field(..., description="Full GitHub commit URL.")
    config: ProcessingConfig = Field(default_factory=ProcessingConfig)


class RepoRequest(BaseModel):
    """Batch Processing Trigger input (Repository URL)."""

    repo_url: str = Field(..., description="GitHub repository URL.")
    config: ProcessingConfig = Field(default_factory=ProcessingConfig)


class OrgRequest(BaseModel):
    """Batch Processing Trigger input (Organization URL)."""

    org_url: str = Field(..., description="GitHub organization or user URL.")
    config: ProcessingConfig = Field(default_factory=ProcessingConfig)


# --------------------------------------------------------------------------- #
# Output layer — the fixed feature-metadata schema
# --------------------------------------------------------------------------- #
class ChangeType(str, Enum):
    FEATURE = "feature"
    BUGFIX = "bugfix"
    REFACTOR = "refactor"
    DOCS = "docs"
    TEST = "test"
    CHORE = "chore"
    STYLE = "style"
    PERF = "perf"
    BUILD = "build"
    CI = "ci"
    REVERT = "revert"
    UNKNOWN = "unknown"


class FileCategory(str, Enum):
    SOURCE = "source"
    TEST = "test"
    DOCS = "docs"
    CONFIG = "config"
    BUILD = "build"
    CI = "ci"
    ASSET = "asset"
    DATA = "data"
    OTHER = "other"


class ChangedFile(BaseModel):
    filename: str
    status: str  # added | modified | removed | renamed
    additions: int = 0
    deletions: int = 0
    changes: int = 0
    category: FileCategory = FileCategory.OTHER
    language: Optional[str] = None
    patch: Optional[str] = None


class FeatureMetadata(BaseModel):
    """The fixed JSON response shape emitted for every processed commit."""

    schema_version: str = "1.0"
    sha: str
    short_sha: str
    repository: str  # "owner/name"
    url: str
    author_name: Optional[str] = None
    author_email: Optional[str] = None
    authored_at: Optional[str] = None  # ISO-8601 UTC
    committed_at: Optional[str] = None  # ISO-8601 UTC
    message: str = ""
    message_subject: str = ""
    change_type: ChangeType = ChangeType.UNKNOWN
    is_merge: bool = False
    breaking_change: bool = False
    issue_references: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    stats: dict = Field(default_factory=dict)  # additions/deletions/total
    file_categories: dict = Field(default_factory=dict)  # category -> count
    languages: list[str] = Field(default_factory=list)
    files: list[ChangedFile] = Field(default_factory=list)
    llm_summary: Optional[str] = None


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class JobResult(BaseModel):
    job_id: str
    status: JobStatus
    repository: Optional[str] = None
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    commits: list[FeatureMetadata] = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Semantic feature search
# --------------------------------------------------------------------------- #
class Relevance(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FeatureSuggestion(BaseModel):
    """One ranked feature surfaced from the stored commit metadata."""

    id: str
    title: str
    repository: str
    sha: str
    short_sha: str
    url: str
    change_type: ChangeType
    score: float  # normalized 0..1 relative to the top hit
    relevance: Relevance
    matched_terms: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class FeatureSearchResponse(BaseModel):
    query: str
    method: str  # "lexical" | "hybrid"
    expanded_terms: list[str] = Field(default_factory=list)
    total_indexed: int = 0
    returned: int = 0
    results: list[FeatureSuggestion] = Field(default_factory=list)
