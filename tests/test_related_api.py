import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.processing.schema_builder import build_metadata
from tests.conftest import make_commit_payload


@pytest.fixture
def client_with_data():
    with TestClient(main.app) as c:
        store = main.app.state.ctx.storage.metadata
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
            store.put(build_metadata(make_commit_payload(sha=i * 8, message=msg), repository="acme/app"))
        yield c


class TestRelatedEndpoint:
    def test_returns_seeds_related_and_suggested(self, client_with_data):
        r = client_with_data.get("/search/related", params={"q": "building pagination"})
        assert r.status_code == 200
        body = r.json()
        assert body["query"] == "building pagination"
        assert body["total_indexed"] == 7
        assert "pagination" in body["capabilities"]
        assert body["seeds"], "expected seed hits"
        assert body["related_features"], "expected related features"
        assert body["suggested_features"], "expected suggestions"

    def test_related_exclude_seeds(self, client_with_data):
        body = client_with_data.get("/search/related", params={"q": "pagination"}).json()
        seed_ids = {s["id"] for s in body["seeds"]}
        assert all(r["id"] not in seed_ids for r in body["related_features"])

    def test_related_have_reasons(self, client_with_data):
        body = client_with_data.get("/search/related", params={"q": "pagination"}).json()
        assert body["related_features"][0]["relation_reasons"]

    def test_suggestions_have_kind_and_reason(self, client_with_data):
        body = client_with_data.get("/search/related", params={"q": "pagination"}).json()
        for s in body["suggested_features"]:
            assert s["kind"] in ("capability", "feature")
            assert s["reason"]

    def test_limit_param(self, client_with_data):
        body = client_with_data.get("/search/related", params={"q": "pagination", "limit": 2}).json()
        assert len(body["related_features"]) <= 2

    def test_missing_query_422(self, client_with_data):
        assert client_with_data.get("/search/related").status_code == 422

    def test_root_lists_related(self, client_with_data):
        assert "/search/related" in client_with_data.get("/").json()["endpoints"]
