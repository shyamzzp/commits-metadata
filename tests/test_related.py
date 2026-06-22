from app.processing.schema_builder import build_metadata
from app.search.recommender import FeatureRecommender
from app.search.related import RelatedEngine
from app.storage.stores import MetadataStore
from tests.conftest import make_commit_payload


def _store():
    s = MetadataStore()
    corpus = [
        ("11", "feat: add pagination with per-page limit and offset cursor"),
        ("22", "feat: infinite scroll load-more pagination for the feed"),
        ("33", "feat: autocomplete search box with a search button"),
        ("44", "feat: rate limiting and throttling on the list api"),
        ("55", "feat: action buttons edit delete on each list row"),
        ("66", "feat: sortable columns and ordering controls on tables"),
        ("77", "fix: correct a typo in the readme"),
    ]
    for i, msg in corpus:
        s.put(build_metadata(make_commit_payload(sha=i * 8, message=msg), repository="acme/app"))
    return s


def _engine(store=None):
    return RelatedEngine(FeatureRecommender(store if store is not None else _store()))


class TestRelatedFeatures:
    def test_returns_related_excluding_seeds(self):
        eng = _engine()
        resp = eng.related("building pagination")
        seed_ids = {s.id for s in resp.seeds}
        assert resp.seeds, "expected seed hits"
        # related must not contain any seed
        assert all(r.id not in seed_ids for r in resp.related_features)

    def test_related_have_reasons_and_scores(self):
        eng = _engine()
        resp = eng.related("pagination")
        assert resp.related_features, "expected related features"
        top = resp.related_features[0]
        assert 0.0 < top.relatedness <= 1.0
        assert top.relation_reasons
        assert top.support >= 1

    def test_capabilities_detected(self):
        eng = _engine()
        resp = eng.related("building pagination")
        assert "pagination" in resp.capabilities

    def test_ranked_descending(self):
        eng = _engine()
        resp = eng.related("pagination")
        scores = [r.relatedness for r in resp.related_features]
        assert scores == sorted(scores, reverse=True)


class TestSuggestedFeatures:
    def test_suggests_adjacent_capabilities(self):
        eng = _engine()
        resp = eng.related("building pagination")
        caps = {s.text for s in resp.suggested_features if s.kind == "capability"}
        # pagination commonly ships with limits / ui-actions / sorting in the corpus
        assert any("features" in c for c in caps)
        # the query's own capability is not re-suggested
        assert "pagination features" not in caps

    def test_suggestions_are_grounded(self):
        eng = _engine()
        resp = eng.related("pagination")
        for s in resp.suggested_features:
            assert s.text
            assert s.kind in ("capability", "feature")
            if s.kind == "feature":
                assert s.examples  # backed by a real feature id

    def test_suggestion_limit(self):
        eng = _engine()
        resp = eng.related("pagination", suggest_limit=3)
        assert len(resp.suggested_features) <= 3

    def test_dedupe_suggestion_text(self):
        eng = _engine()
        resp = eng.related("pagination")
        texts = [s.text for s in resp.suggested_features]
        assert len(texts) == len(set(texts))


class TestEdgeCases:
    def test_empty_store(self):
        eng = _engine(MetadataStore())
        resp = eng.related("pagination")
        assert resp.total_indexed == 0
        assert resp.related_features == []
        assert resp.suggested_features == []

    def test_query_with_no_match(self):
        eng = _engine()
        resp = eng.related("zzzxqq nonexistent")
        # no seeds -> no related/suggested, but call still succeeds
        assert resp.related_features == []
