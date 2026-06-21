import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.processing.schema_builder import build_metadata
from tests.conftest import make_commit_payload


@pytest.fixture
def client_with_data():
    """TestClient with the metadata store pre-seeded with a feature corpus."""
    with TestClient(main.app) as c:
        store = main.app.state.ctx.storage.metadata
        corpus = [
            ("1", "feat: add pagination with per page limits and offset cursor"),
            ("2", "feat: autocomplete search box with a search button"),
            ("3", "feat: add rate limiting and throttling to the api"),
            ("4", "feat: action buttons on paginated list rows"),
            ("5", "fix: correct a typo in the readme"),
        ]
        for i, msg in corpus:
            store.put(build_metadata(make_commit_payload(sha=i * 40, message=msg), repository="acme/app"))
        yield c


class TestSearchFeatures:
    def test_pagination_query_returns_ranked_features(self, client_with_data):
        r = client_with_data.get("/search/features", params={"q": "building pagination"})
        assert r.status_code == 200
        body = r.json()
        assert body["query"] == "building pagination"
        assert body["method"] == "lexical"
        assert body["total_indexed"] == 5
        assert body["results"], "expected ranked results"
        assert "pagination" in body["results"][0]["title"].lower()
        assert body["results"][0]["score"] == 1.0
        assert body["results"][0]["relevance"] == "high"

    def test_results_carry_matched_terms_and_metadata(self, client_with_data):
        r = client_with_data.get("/search/features", params={"q": "pagination"})
        top = r.json()["results"][0]
        assert top["matched_terms"]
        assert top["repository"] == "acme/app"
        assert top["change_type"] == "feature"

    def test_irrelevant_excluded(self, client_with_data):
        r = client_with_data.get("/search/features", params={"q": "pagination"})
        titles = [x["title"].lower() for x in r.json()["results"]]
        assert not any("typo" in t for t in titles)

    def test_pagination_of_results(self, client_with_data):
        r = client_with_data.get("/search/features", params={"q": "search", "limit": 1})
        assert len(r.json()["results"]) <= 1

    def test_ai_hybrid_mode(self, client_with_data):
        r = client_with_data.get("/search/features", params={"q": "pagination", "ai": "true"})
        assert r.json()["method"] == "hybrid"

    def test_missing_query_422(self, client_with_data):
        assert client_with_data.get("/search/features").status_code == 422


class TestSuggest:
    def test_autocomplete(self, client_with_data):
        r = client_with_data.get("/search/suggest", params={"prefix": "pag"})
        assert r.status_code == 200
        assert any("pag" in s.lower() for s in r.json()["suggestions"])

    def test_missing_prefix_422(self, client_with_data):
        assert client_with_data.get("/search/suggest").status_code == 422


class TestRootListsSearch:
    def test_root_endpoints_include_search(self, client_with_data):
        assert "/search/features" in client_with_data.get("/").json()["endpoints"]
