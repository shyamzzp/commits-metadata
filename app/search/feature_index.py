"""Feature index: turn stored FeatureMetadata into searchable docs + BM25 scoring."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

from app.models import FeatureMetadata
from app.search.tokenizer import tokenize

# BM25 hyper-parameters.
_K1 = 1.5
_B = 0.75


@dataclass
class FeatureDocument:
    id: str
    repository: str
    sha: str
    title: str
    url: str
    change_type: str
    tags: list[str] = field(default_factory=list)
    text: str = ""
    tokens: list[str] = field(default_factory=list)
    tf: Counter = field(default_factory=Counter)

    @property
    def length(self) -> int:
        return len(self.tokens)


def document_text(meta: FeatureMetadata) -> str:
    """Compose the searchable text for a commit's feature."""
    parts: list[str] = [meta.message_subject or "", meta.change_type.value]
    parts.extend(meta.tags)
    parts.extend(meta.languages)
    parts.extend(cat for cat in meta.file_categories)
    parts.extend(f.filename for f in meta.files[:20])
    # Include the body lines beyond the subject for richer matching.
    body = (meta.message or "").splitlines()
    parts.extend(body[1:6])
    return " ".join(p for p in parts if p)


def build_document(meta: FeatureMetadata) -> FeatureDocument:
    text = document_text(meta)
    tokens = tokenize(text)
    return FeatureDocument(
        id=f"{meta.repository}@{meta.sha}",
        repository=meta.repository,
        sha=meta.sha,
        title=meta.message_subject or meta.short_sha,
        url=meta.url,
        change_type=meta.change_type.value,
        tags=list(meta.tags),
        text=text,
        tokens=tokens,
        tf=Counter(tokens),
    )


class FeatureIndex:
    """An in-memory BM25 index over feature documents."""

    def __init__(self) -> None:
        self.docs: list[FeatureDocument] = []
        self.df: Counter = Counter()
        self.idf: dict[str, float] = {}
        self.avgdl: float = 0.0

    @property
    def size(self) -> int:
        return len(self.docs)

    def build(self, metas: list[FeatureMetadata]) -> "FeatureIndex":
        self.docs = [build_document(m) for m in metas]
        self.df = Counter()
        for doc in self.docs:
            self.df.update(set(doc.tokens))
        n = max(1, len(self.docs))
        # BM25 idf (with the +1 floor so common terms stay non-negative).
        self.idf = {
            term: math.log(1 + (n - df + 0.5) / (df + 0.5))
            for term, df in self.df.items()
        }
        total_len = sum(doc.length for doc in self.docs)
        self.avgdl = (total_len / n) if self.docs else 0.0
        return self

    def score_doc(self, doc: FeatureDocument, query_weights: dict[str, float]) -> float:
        if not doc.tokens or self.avgdl == 0:
            return 0.0
        score = 0.0
        denom_len = _K1 * (1 - _B + _B * doc.length / self.avgdl)
        for term, weight in query_weights.items():
            f = doc.tf.get(term, 0)
            if not f:
                continue
            idf = self.idf.get(term, 0.0)
            score += weight * idf * (f * (_K1 + 1)) / (f + denom_len)
        return score

    def score_all(self, query_weights: dict[str, float]) -> list[tuple[FeatureDocument, float]]:
        scored = [(doc, self.score_doc(doc, query_weights)) for doc in self.docs]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored

    def matched_terms(self, doc: FeatureDocument, query_weights: dict[str, float]) -> list[str]:
        return sorted(t for t in query_weights if doc.tf.get(t, 0) > 0)
