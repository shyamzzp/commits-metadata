from app.processing.schema_builder import build_metadata
from app.search.feature_index import FeatureIndex, build_document, document_text
from app.search.tokenizer import expand_query, tokenize
from tests.conftest import make_commit_payload


def _meta(sha, message, repo="o/r", files=None):
    return build_metadata(make_commit_payload(sha=sha, message=message, files=files), repository=repo)


class TestDocument:
    def test_document_text_includes_subject_and_tags(self):
        m = _meta("a" * 40, "feat: add pagination to list view")
        text = document_text(m).lower()
        assert "pagination" in text
        assert "feature" in text  # change_type

    def test_build_document_fields(self):
        m = _meta("a" * 40, "feat: add pagination")
        doc = build_document(m)
        assert doc.id == "o/r@" + "a" * 40
        assert doc.title == "feat: add pagination"
        assert doc.length > 0


class TestBM25:
    def _index(self):
        metas = [
            _meta("1" * 40, "feat: add pagination with per page limits and offset"),
            _meta("2" * 40, "feat: autocomplete search box with suggestions"),
            _meta("3" * 40, "fix: correct typo in readme"),
            _meta("4" * 40, "feat: add rate limiting and throttling to api"),
        ]
        return FeatureIndex().build(metas)

    def test_pagination_query_ranks_pagination_doc_first(self):
        idx = self._index()
        weights = expand_query(tokenize("building pagination"))
        ranked = idx.score_all(weights)
        top = ranked[0][0]
        assert "pagination" in top.title.lower()
        assert ranked[0][1] > 0

    def test_irrelevant_doc_scores_zero(self):
        idx = self._index()
        weights = expand_query(tokenize("pagination"))
        scores = {doc.title: s for doc, s in idx.score_all(weights)}
        # the readme typo fix shares no pagination vocabulary
        assert scores["fix: correct typo in readme"] == 0.0

    def test_idf_and_avgdl_computed(self):
        idx = self._index()
        assert idx.size == 4
        assert idx.avgdl > 0
        assert all(v >= 0 for v in idx.idf.values())

    def test_empty_corpus(self):
        idx = FeatureIndex().build([])
        assert idx.size == 0
        assert idx.score_all(expand_query(tokenize("anything"))) == []

    def test_matched_terms(self):
        idx = self._index()
        weights = expand_query(tokenize("pagination"))
        doc = idx.score_all(weights)[0][0]
        assert len(idx.matched_terms(doc, weights)) > 0
