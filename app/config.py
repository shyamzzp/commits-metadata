"""Processing configuration (the ``Config`` node in the architecture)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel, Field


@dataclass
class Settings:
    """Runtime/environment settings, loaded once at startup."""

    github_token: Optional[str] = field(
        default_factory=lambda: os.getenv("GITHUB_TOKEN") or None
    )
    github_api_base: str = field(
        default_factory=lambda: os.getenv("GITHUB_API_BASE", "https://api.github.com")
    )
    webhook_secret: Optional[str] = field(
        default_factory=lambda: os.getenv("GITHUB_WEBHOOK_SECRET") or None
    )
    enable_llm_analyzer: bool = field(
        default_factory=lambda: os.getenv("ENABLE_LLM_ANALYZER", "false").lower()
        in ("1", "true", "yes")
    )


def get_settings() -> Settings:
    """Return a fresh ``Settings`` instance (re-reads env each call for testability)."""
    return Settings()


class ProcessingConfig(BaseModel):
    """Per-request processing configuration submitted by the user/UI."""

    max_commits: int = Field(
        default=100, ge=1, le=5000, description="Hard cap on commits processed per job."
    )
    branches: Optional[list[str]] = Field(
        default=None,
        description="Restrict scanning to these branches; default = repo default branch.",
    )
    include_diff: bool = Field(
        default=True, description="Fetch and attach diff/patch text for changed files."
    )
    enable_llm: bool = Field(
        default=False, description="Run the optional LLM analyzer in addition to rules."
    )
    max_retries: int = Field(
        default=3, ge=0, le=10, description="Retry attempts per failed commit."
    )
    dedupe: bool = Field(
        default=True, description="Deduplicate commit SHAs across branches."
    )
