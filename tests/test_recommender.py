import pytest

from app.models import Relevance
from app.processing.schema_builder import build_metadata
from app.search.embeddings import Embedder
from app.search.recommender import FeatureRecommender
from app.storage.stores import MetadataStore
from tests.conftest import make_commit_payload


def _store():
    s = MetadataStore()
    corpus = [
        ("1", "feat: add pagination with per page limits and offset cursor"),
        ("2", "feat: autocomplete search box with suggestions and search button"),
        ("3", "feat: add rate limiting and throttling to the api"),
        ("4", "feat: action buttons on list rows"),
        ("5", "fix: correct a typo in the readme"),
        ("6", "docs: update contributing guide"),
    ]
    for i, msg in corpus:
        s.put(build_metadata(make_commit_payload(sha=i * 40, message=msg), repository="acme/app"))
    return s


class TestSearch:
    def test_pagination_query_ranks_pagination_first(self):
        rec = FeatureRecommender(_store())
        resp = rec.search("building pagination")
        assert resp.total_indexed == 6
        assert resp.results, "expected at least one result"
        assert "pagination" in resp.results[0].title.lower()
        assert resp.results[0].relevance == Relevance.HIGH
        assert resp.results[0].score == 1.0  # normalized top hit

    def test_expansion_surfaces_related_features(self):
        rec = FeatureRecommender(_store())
        resp = rec.search("pagination")
        titles = " | ".join(r.title.lower() for r in resp.results)
        # per-page/offset doc is top; related limit/page vocab pulls others in
        assert "pagination" in titles

    def test_irrelevant_docs_excluded(self):
        rec = FeatureRecommender(_store())
        resp = rec.search("pagination")
        returned_titles = [r.title.lower() for r in resp.results]
        assert not any("typo" in t for t in returned_titles)

    def test_limit_and_offset(self):
        rec = FeatureRecommender(_store())
        full = rec.search("search", limit=10)
        first = rec.search("search", limit=1, offset=0)
        second = rec.search("search", limit=1, offset=1)
        assert len(first.results) == 1
        if len(full.results) > 1:
            assert first.results[0].id != second.results[0].id

    def test_min_score_filter(self):
        rec = FeatureRecommender(_store())
        resp = rec.search("pagination", min_score=0.99)
        assert all(r.score >= 0.99 for r in resp.results)

    def test_method_label(self):
        rec = FeatureRecommender(_store())
        assert rec.search("pagination").method == "lexical"
        assert rec.search("pagination", use_ai=True).method == "hybrid"

    def test_hybrid_runs_with_embedder(self):
        rec = FeatureRecommender(_store(), embedder=Embedder(enabled=True))
        resp = rec.search("pagination")
        assert resp.method == "hybrid"
        assert resp.results

    def test_empty_store(self):
        rec = FeatureRecommender(MetadataStore())
        resp = rec.search("pagination")
        assert resp.total_indexed == 0
        assert resp.results == []


class TestReindex:
    def test_index_rebuilds_on_store_change(self):
        store = _store()
        rec = FeatureRecommender(store)
        assert rec.search("pagination").total_indexed == 6
        store.put(build_metadata(make_commit_payload(sha="9" * 40, message="feat: add infinite scroll pagination"), repository="acme/app"))
        assert rec.search("pagination").total_indexed == 7


class TestSuggest:
    def test_autocomplete_prefix(self):
        rec = FeatureRecommender(_store())
        out = rec.suggest("pag")
        assert any("pag" in s.lower() for s in out)

    def test_empty_prefix(self):
        rec = FeatureRecommender(_store())
        assert rec.suggest("") == []

    def test_limit(self):
        rec = FeatureRecommender(_store())
        assert len(rec.suggest("a", limit=2)) <= 2
