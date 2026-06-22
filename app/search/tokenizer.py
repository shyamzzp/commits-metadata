"""Tokenizer + domain query-expansion lexicon for feature search.

Deterministic, dependency-free. The expansion lexicon lets a short natural
query ("building pagination") reach commits that use related vocabulary
(page / offset / limit / infinite scroll) even without an AI model.
"""

from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[a-z0-9]+")

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "to", "of", "in", "on",
    "for", "with", "without", "by", "at", "from", "into", "as", "is", "are",
    "be", "being", "been", "this", "that", "these", "those", "it", "its",
    "build", "building", "built", "add", "added", "adding", "make", "making",
    "use", "using", "want", "need", "should", "can", "feature", "features",
    "support", "implement", "implementing", "create", "creating", "new",
}

# Labeled domain capability groups. Members of a group are mutually expandable,
# and the label names the capability area (used for "people also asked").
CAPABILITY_GROUPS: dict[str, set[str]] = {
    "pagination": {"pagination", "paginate", "paginated", "page", "pages",
                   "paging", "offset", "cursor", "perpage", "infinite",
                   "scroll", "loadmore"},
    "search": {"search", "query", "autocomplete", "typeahead", "suggest",
               "suggestion", "filter", "fulltext", "lookup"},
    "rate-limiting": {"ratelimit", "ratelimiting", "rate", "throttle",
                      "throttling", "quota", "backoff", "debounce"},
    "authentication": {"auth", "authentication", "authorization", "login",
                       "signin", "oauth", "token", "session", "credential"},
    "caching": {"cache", "caching", "memoize", "ttl", "invalidate"},
    "file-transfer": {"upload", "download", "file", "attachment", "multipart",
                      "stream"},
    "webhooks": {"webhook", "callback", "event", "subscribe", "notification"},
    "validation": {"validation", "validate", "schema", "sanitize", "verify"},
    "retry-queue": {"retry", "retries", "deadletter", "queue", "backoff"},
    "ui-actions": {"button", "action", "click", "control", "ui", "component"},
    "sorting": {"sort", "sorting", "order", "ordering", "rank", "ranking"},
    "limits": {"limit", "limits", "max", "maximum", "bound", "cap"},
}

# Each group's members are mutually expandable.
_SYNONYM_GROUPS: list[set[str]] = [set(members) for members in CAPABILITY_GROUPS.values()]

# Build a fast lookup: token -> set of synonyms (excluding itself).
_EXPANSION: dict[str, set[str]] = {}
for _group in _SYNONYM_GROUPS:
    for _term in _group:
        _EXPANSION.setdefault(_term, set()).update(_group - {_term})


def stem(token: str) -> str:
    """Very small suffix stemmer (good enough for code/commit vocab)."""
    for suffix in ("ization", "isation", "ingly", "edly", "ing", "ers", "er",
                   "ed", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    return token


def tokenize(text: str, *, keep_stopwords: bool = False, do_stem: bool = True) -> list[str]:
    """Split text into normalized tokens."""
    if not text:
        return []
    raw = _TOKEN_RE.findall(text.lower())
    out: list[str] = []
    for tok in raw:
        if not keep_stopwords and tok in STOPWORDS:
            continue
        out.append(stem(tok) if do_stem else tok)
    return out


def expand_query(tokens: list[str]) -> dict[str, float]:
    """Return a weighted bag of terms: original terms weight 1.0, synonyms 0.5.

    Synonyms are matched on the *raw* (unstemmed) lexicon then stemmed so the
    weights line up with document tokens.
    """
    weights: dict[str, float] = {}
    for tok in tokens:
        weights[tok] = max(weights.get(tok, 0.0), 1.0)
    # Expansion uses the unstemmed lexicon; tokens here are already stemmed,
    # so match against stemmed lexicon keys.
    stemmed_expansion = _stemmed_expansion()
    for tok in tokens:
        for syn in stemmed_expansion.get(tok, ()):  # type: ignore[arg-type]
            weights[syn] = max(weights.get(syn, 0.0), 0.5)
    return weights


_STEMMED_EXPANSION_CACHE: dict[str, set[str]] | None = None


def _stemmed_expansion() -> dict[str, set[str]]:
    global _STEMMED_EXPANSION_CACHE
    if _STEMMED_EXPANSION_CACHE is None:
        cache: dict[str, set[str]] = {}
        for term, syns in _EXPANSION.items():
            key = stem(term)
            cache.setdefault(key, set()).update(stem(s) for s in syns)
            cache[key].discard(key)
        _STEMMED_EXPANSION_CACHE = cache
    return _STEMMED_EXPANSION_CACHE


_STEMMED_CAPABILITIES_CACHE: dict[str, set[str]] | None = None


def _stemmed_capabilities() -> dict[str, set[str]]:
    global _STEMMED_CAPABILITIES_CACHE
    if _STEMMED_CAPABILITIES_CACHE is None:
        _STEMMED_CAPABILITIES_CACHE = {
            label: {stem(m) for m in members}
            for label, members in CAPABILITY_GROUPS.items()
        }
    return _STEMMED_CAPABILITIES_CACHE


def capability_labels(tokens: list[str]) -> list[str]:
    """Map (already-stemmed) tokens to the capability areas they touch.

    Order follows the lexicon definition; each label appears at most once.
    """
    token_set = set(tokens)
    return [
        label
        for label, members in _stemmed_capabilities().items()
        if token_set & members
    ]
