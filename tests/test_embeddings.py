import math

from app.search.embeddings import (
    Embedder,
    cosine,
    default_embed,
    hybrid_score,
    l2_normalize,
)


class TestVectorMath:
    def test_l2_normalize_unit_length(self):
        v = l2_normalize([3.0, 4.0])
        assert math.isclose(math.sqrt(sum(x * x for x in v)), 1.0, rel_tol=1e-9)

    def test_l2_normalize_zero_vector(self):
        assert l2_normalize([0.0, 0.0]) == [0.0, 0.0]

    def test_cosine_identical_is_one(self):
        v = default_embed("add pagination support")
        assert math.isclose(cosine(v, v), 1.0, rel_tol=1e-9)

    def test_cosine_mismatched_dims_zero(self):
        assert cosine([1.0], [1.0, 2.0]) == 0.0


class TestEmbedder:
    def test_deterministic(self):
        e = Embedder()
        assert e.embed("pagination") == e.embed("pagination")

    def test_related_text_more_similar_than_unrelated(self):
        e = Embedder()
        base = "add pagination with per page limit"
        related = e.similarity(base, "pagination per page offset")
        unrelated = e.similarity(base, "fix readme typo")
        assert related > unrelated


class TestHybrid:
    def test_blend_weights(self):
        # alpha=1 -> pure lexical
        assert hybrid_score(0.8, 0.2, alpha=1.0) == 0.8
        # alpha=0 -> pure cosine
        assert hybrid_score(0.8, 0.2, alpha=0.0) == 0.2
        # in-between is between the two
        mid = hybrid_score(1.0, 0.0, alpha=0.6)
        assert math.isclose(mid, 0.6, rel_tol=1e-9)

    def test_negative_cosine_clamped(self):
        assert hybrid_score(0.5, -0.9, alpha=0.5) == 0.25
