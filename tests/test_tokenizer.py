from app.search.tokenizer import capability_labels, expand_query, stem, tokenize


class TestTokenize:
    def test_basic_lowercasing_and_split(self):
        assert tokenize("Add Pagination Support", do_stem=False, keep_stopwords=True) == [
            "add", "pagination", "support",
        ]

    def test_drops_stopwords(self):
        toks = tokenize("building the pagination for users")
        assert "the" not in toks and "for" not in toks and "building" not in toks
        assert "pagination" in " ".join(toks) or "paginat" in " ".join(toks)

    def test_stemming(self):
        assert stem("pages") == "page"
        assert stem("paginated") == "paginat"
        assert stem("limits") == "limit"
        assert stem("caching") == "cach"

    def test_empty(self):
        assert tokenize("") == []
        assert tokenize(None) == []

    def test_punctuation_stripped(self):
        assert tokenize("rate-limit, per_page!", do_stem=False) == ["rate", "limit", "per", "page"]


class TestExpandQuery:
    def test_original_terms_weight_one(self):
        toks = tokenize("pagination")
        weights = expand_query(toks)
        assert weights[toks[0]] == 1.0

    def test_synonyms_added_with_lower_weight(self):
        weights = expand_query(tokenize("pagination"))
        # "page"/"offset"/"limit" stems should appear as expansion at 0.5
        expanded = {k: v for k, v in weights.items() if v == 0.5}
        assert len(expanded) > 0
        assert all(0.0 < v <= 0.5 for v in expanded.values())

    def test_unknown_term_has_no_expansion(self):
        weights = expand_query(tokenize("zzzxqq"))
        assert all(v == 1.0 for v in weights.values())


class TestCapabilityLabels:
    def test_detects_pagination(self):
        assert "pagination" in capability_labels(tokenize("add pagination offset"))

    def test_detects_multiple_areas(self):
        labels = capability_labels(tokenize("rate limiting on the search autocomplete"))
        assert "rate-limiting" in labels
        assert "search" in labels

    def test_no_label_for_unrelated(self):
        assert capability_labels(tokenize("zzzxqq blorp")) == []

    def test_each_label_once(self):
        labels = capability_labels(tokenize("page page paginate offset cursor"))
        assert labels.count("pagination") == 1
