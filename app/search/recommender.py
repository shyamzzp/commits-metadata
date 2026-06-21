"""Feature recommender: rank stored features by relevance to a free-text query.

Pipeline:  query -> tokenize -> expand (synonyms) -> BM25 over the feature index
-> optional AI cosine re-rank (hybrid) -> normalize 0..1 -> ranked suggestions.

The index is cached and rebuilt only when the metadata store changes size, so
repeated queries are cheap.
"""

from __future__ import annotations

from app.models import (
    ChangeType,
    FeatureSearchResponse,
    FeatureSuggestion,
    Relevance,
)
from app.search.embeddings import Embedder, hybrid_score
from app.search.feature_index import FeatureIndex
from app.search.tokenizer import expand_query, tokenize
from app.storage.stores import MetadataStore


def _relevance(score: float) -> Relevance:
    if score >= 0.66:
        return Relevance.HIGH
    if score >= 0.33:
        return Relevance.MEDIUM
    return Relevance.LOW


class FeatureRecommender:
    def __init__(
        self,
        store: MetadataStore,
        *,
        embedder: Embedder | None = None,
        alpha: float = 0.6,
    ) -> None:
        self.store = store
        self.embedder = embedder or Embedder(enabled=False)
        self.alpha = alpha
        self._index = FeatureIndex()
        self._indexed_size = -1

    # --- indexing ---------------------------------------------------------- #
    def _ensure_index(self) -> FeatureIndex:
        current = len(self.store)
        if current != self._indexed_size:
            self._index.build(self.store.all())
            self._indexed_size = current
        return self._index

    def reindex(self) -> int:
        self._indexed_size = -1
        return self._ensure_index().size

    # --- search ------------------------------------------------------------ #
    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        offset: int = 0,
        min_score: float = 0.0,
        use_ai: bool = False,
    ) -> FeatureSearchResponse:
        index = self._ensure_index()
        tokens = tokenize(query)
        weights = expand_query(tokens)

        scored = index.score_all(weights)  # [(doc, bm25)], desc
        max_bm25 = scored[0][1] if scored else 0.0

        ai = use_ai or self.embedder.enabled
        method = "hybrid" if ai else "lexical"
        query_vec = self.embedder.embed(query) if ai else None

        rows: list[tuple[object, float]] = []
        for doc, bm25 in scored:
            bm25_norm = (bm25 / max_bm25) if max_bm25 > 0 else 0.0
            if ai and query_vec is not None:
                from app.search.embeddings import cosine

                sim = cosine(query_vec, self.embedder.embed(doc.text))
                final = hybrid_score(bm25_norm, sim, alpha=self.alpha)
            else:
                final = bm25_norm
            rows.append((doc, final))

        rows.sort(key=lambda r: r[1], reverse=True)

        suggestions: list[FeatureSuggestion] = []
        for doc, score in rows:
            if score <= 0.0 or score < min_score:
                continue
            suggestions.append(
                FeatureSuggestion(
                    id=doc.id,
                    title=doc.title,
                    repository=doc.repository,
                    sha=doc.sha,
                    short_sha=doc.sha[:7],
                    url=doc.url,
                    change_type=ChangeType(doc.change_type) if doc.change_type in ChangeType._value2member_map_ else ChangeType.UNKNOWN,
                    score=round(score, 4),
                    relevance=_relevance(score),
                    matched_terms=index.matched_terms(doc, weights),
                    tags=doc.tags,
                )
            )

        page = suggestions[offset : offset + limit]
        return FeatureSearchResponse(
            query=query,
            method=method,
            expanded_terms=sorted(weights.keys()),
            total_indexed=index.size,
            returned=len(page),
            results=page,
        )

    # --- autocomplete ------------------------------------------------------ #
    def suggest(self, prefix: str, *, limit: int = 8) -> list[str]:
        """Autocomplete: titles + tags + indexed terms starting with prefix."""
        index = self._ensure_index()
        pref = prefix.strip().lower()
        if not pref:
            return []
        candidates: dict[str, int] = {}
        for doc in index.docs:
            title = doc.title.strip()
            if title.lower().startswith(pref):
                candidates[title] = candidates.get(title, 0) + 3
            for tag in doc.tags:
                if tag.lower().startswith(pref):
                    candidates[tag] = candidates.get(tag, 0) + 2
        for term, df in index.df.items():
            if term.startswith(pref):
                candidates[term] = candidates.get(term, 0) + df
        ranked = sorted(candidates.items(), key=lambda kv: (-kv[1], kv[0]))
        return [c for c, _ in ranked[:limit]]
