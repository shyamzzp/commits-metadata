"""People-Also-Asked for features.

Given a query, find the directly-relevant features (seeds) via the recommender,
then surface:

* ``related_features`` — other features in the data that *co-occur* with the
  seeds (shared tags / similar terms / same repo / shared capability area), and
* ``suggested_features`` — short "you might also want" suggestions synthesized
  from the related set and the capability lexicon.

Everything is grounded in stored data; nothing is invented.
"""

from __future__ import annotations

from app.models import (
    ChangeType,
    RelatedFeature,
    RelatedSearchResponse,
    SuggestedFeature,
)
from app.search.feature_index import FeatureDocument
from app.search.recommender import FeatureRecommender
from app.search.tokenizer import capability_labels, expand_query, tokenize

# Relatedness component weights (sum to 1.0).
_W_TAGS = 0.4
_W_TERMS = 0.4
_W_REPO = 0.1
_W_CAP = 0.1

# Generic tags that shouldn't, on their own, make two features "related".
_GENERIC_TAGS = {"cat:source", "cat:other"}


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _to_change_type(value: str) -> ChangeType:
    return ChangeType(value) if value in ChangeType._value2member_map_ else ChangeType.UNKNOWN


class RelatedEngine:
    def __init__(self, recommender: FeatureRecommender) -> None:
        self.recommender = recommender

    def related(
        self,
        query: str,
        *,
        seed_k: int = 5,
        limit: int = 10,
        suggest_limit: int = 8,
        use_ai: bool = False,
    ) -> RelatedSearchResponse:
        index = self.recommender.current_index()
        docs_by_id: dict[str, FeatureDocument] = {d.id: d for d in index.docs}

        seed_resp = self.recommender.search(query, limit=seed_k, use_ai=use_ai)
        seeds = seed_resp.results
        seed_ids = {s.id for s in seeds}
        seed_docs = [docs_by_id[s.id] for s in seeds if s.id in docs_by_id]

        query_terms = set(expand_query(tokenize(query)).keys())
        query_caps = capability_labels(tokenize(query))

        # --- related features (co-occurrence with the seeds) --------------- #
        related: list[RelatedFeature] = []
        for cand in index.docs:
            if cand.id in seed_ids or not seed_docs:
                continue
            best = 0.0
            reasons: list[str] = []
            support = 0
            for seed_doc in seed_docs:
                score, why = self._relatedness(seed_doc, cand, query_terms)
                if score > 0:
                    support += 1
                    for r in why:
                        if r not in reasons:
                            reasons.append(r)
                    best = max(best, score)
            if best <= 0:
                continue
            related.append(
                RelatedFeature(
                    id=cand.id,
                    title=cand.title,
                    repository=cand.repository,
                    sha=cand.sha,
                    short_sha=cand.sha[:7],
                    url=cand.url,
                    change_type=_to_change_type(cand.change_type),
                    relatedness=round(best, 4),
                    support=support,
                    relation_reasons=reasons[:4],
                    tags=cand.tags,
                )
            )
        related.sort(key=lambda r: (r.relatedness, r.support), reverse=True)
        related = related[:limit]

        # --- suggested features (people also asked) ------------------------ #
        suggestions = self._suggest(
            seed_docs, related, docs_by_id, query_caps, suggest_limit
        )

        return RelatedSearchResponse(
            query=query,
            total_indexed=index.size,
            capabilities=query_caps,
            seeds=seeds,
            related_features=related,
            suggested_features=suggestions,
        )

    # --- internals --------------------------------------------------------- #
    def _relatedness(
        self, seed: FeatureDocument, cand: FeatureDocument, query_terms: set
    ) -> tuple[float, list[str]]:
        score = 0.0
        reasons: list[str] = []

        s_tags = set(seed.tags) - _GENERIC_TAGS
        c_tags = set(cand.tags) - _GENERIC_TAGS
        tag_j = _jaccard(s_tags, c_tags)
        if tag_j > 0:
            score += _W_TAGS * tag_j
            shared = sorted(s_tags & c_tags)[:3]
            if shared:
                reasons.append("shared tags: " + ", ".join(shared))

        s_tok = set(seed.tokens) - query_terms
        c_tok = set(cand.tokens) - query_terms
        tok_j = _jaccard(s_tok, c_tok)
        if tok_j > 0:
            score += _W_TERMS * tok_j
            shared_tok = sorted(s_tok & c_tok)[:3]
            if shared_tok:
                reasons.append("similar terms: " + ", ".join(shared_tok))

        if seed.repository == cand.repository:
            score += _W_REPO
            reasons.append("same repository")

        s_caps = set(capability_labels(seed.tokens))
        c_caps = set(capability_labels(cand.tokens))
        cap_overlap = s_caps & c_caps
        if cap_overlap:
            score += _W_CAP
            reasons.append("shared capability: " + ", ".join(sorted(cap_overlap)))

        return score, reasons

    def _suggest(
        self,
        seed_docs: list[FeatureDocument],
        related: list[RelatedFeature],
        docs_by_id: dict[str, FeatureDocument],
        query_caps: list[str],
        limit: int,
    ) -> list[SuggestedFeature]:
        query_cap_set = set(query_caps)

        # Capability areas that co-occur with the query (but aren't the query's).
        cap_support: dict[str, int] = {}
        cap_examples: dict[str, list[str]] = {}
        pool = list(seed_docs) + [docs_by_id[r.id] for r in related if r.id in docs_by_id]
        for doc in pool:
            for cap in capability_labels(doc.tokens):
                if cap in query_cap_set:
                    continue
                cap_support[cap] = cap_support.get(cap, 0) + 1
                cap_examples.setdefault(cap, [])
                if doc.id not in cap_examples[cap] and len(cap_examples[cap]) < 3:
                    cap_examples[cap].append(doc.id)

        suggestions: list[SuggestedFeature] = []
        seen_text: set[str] = set()

        anchor = ", ".join(query_caps) if query_caps else "this feature"
        for cap, support in sorted(cap_support.items(), key=lambda kv: (-kv[1], kv[0])):
            text = f"{cap} features"
            if text in seen_text:
                continue
            seen_text.add(text)
            suggestions.append(
                SuggestedFeature(
                    text=text,
                    kind="capability",
                    reason=f"commonly ships alongside {anchor}",
                    support=support,
                    examples=cap_examples.get(cap, []),
                )
            )

        # Concrete related features as "people also built" suggestions.
        for r in related:
            if len(suggestions) >= limit:
                break
            if r.title in seen_text:
                continue
            seen_text.add(r.title)
            suggestions.append(
                SuggestedFeature(
                    text=r.title,
                    kind="feature",
                    reason="related feature already in your codebase",
                    support=r.support,
                    examples=[r.id],
                )
            )

        return suggestions[:limit]
