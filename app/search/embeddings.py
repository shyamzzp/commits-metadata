"""Provider-agnostic embeddings + hybrid scoring.

The default embedder is deterministic (hashed bag-of-tokens projected into a
fixed-dim, L2-normalized vector) so the search works offline with no API keys.
Inject a real model via ``embed_fn`` (e.g. an OpenAI/Cohere/local embedder) to
get true semantic similarity; the rest of the pipeline is unchanged.
"""

from __future__ import annotations

import hashlib
import math
from typing import Callable, Optional, Sequence

from app.search.tokenizer import tokenize

EmbedFn = Callable[[str], Sequence[float]]

_DIM = 256


def _hash_token(token: str) -> int:
    digest = hashlib.md5(token.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % _DIM


def default_embed(text: str, *, dim: int = _DIM) -> list[float]:
    """Deterministic hashing embedding. Lexical, but stable and key-free."""
    vec = [0.0] * dim
    for tok in tokenize(text):
        vec[_hash_token(tok) % dim] += 1.0
    return l2_normalize(vec)


def l2_normalize(vec: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return list(vec)
    return [v / norm for v in vec]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    # Inputs are expected normalized; clamp for float safety.
    return max(-1.0, min(1.0, dot))


class Embedder:
    def __init__(self, *, enabled: bool = False, embed_fn: Optional[EmbedFn] = None) -> None:
        self.enabled = enabled
        self._embed_fn = embed_fn or default_embed

    def embed(self, text: str) -> list[float]:
        return list(self._embed_fn(text))

    def similarity(self, query: str, text: str) -> float:
        return cosine(self.embed(query), self.embed(text))


def hybrid_score(bm25_norm: float, cosine_sim: float, *, alpha: float = 0.6) -> float:
    """Blend a normalized BM25 score with cosine similarity.

    ``alpha`` weights the lexical signal; ``1 - alpha`` weights the AI signal.
    """
    alpha = max(0.0, min(1.0, alpha))
    return alpha * bm25_norm + (1 - alpha) * max(0.0, cosine_sim)
