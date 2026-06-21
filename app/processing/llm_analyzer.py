"""Optional LLM Analyzer — additive natural-language summary of a commit.

This is intentionally provider-agnostic and defaults to a deterministic
heuristic summariser so the pipeline (and its tests) never require network
access or API keys. A real LLM can be wired in by passing a ``summarizer``
callable.
"""

from __future__ import annotations

from typing import Callable, Optional

from app.models import ChangedFile

Summarizer = Callable[[str, list[ChangedFile]], str]


def heuristic_summary(message: str, files: list[ChangedFile]) -> str:
    subject = (message or "").strip().splitlines()[0] if message else "(no message)"
    n = len(files)
    cats = sorted({f.category.value for f in files})
    langs = sorted({f.language for f in files if f.language})
    parts = [f"{subject}"]
    if n:
        parts.append(f"Touches {n} file(s)")
        if cats:
            parts.append("across " + ", ".join(cats))
        if langs:
            parts.append("in " + ", ".join(langs))
    return " — ".join(parts)


class LLMAnalyzer:
    def __init__(self, enabled: bool = False, summarizer: Optional[Summarizer] = None) -> None:
        self.enabled = enabled
        self._summarizer = summarizer or heuristic_summary

    def analyze(self, message: str, files: list[ChangedFile]) -> Optional[str]:
        if not self.enabled:
            return None
        return self._summarizer(message, files)
