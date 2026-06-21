from app.models import FileCategory
from app.processing import diff_extractor
from tests.conftest import make_commit_payload


class TestExtractChangedFiles:
    def test_extracts_files_with_classification(self):
        payload = make_commit_payload(
            files=[
                {"filename": "app/main.py", "status": "modified", "additions": 5, "deletions": 1, "changes": 6, "patch": "x"},
                {"filename": "README.md", "status": "added", "additions": 3, "deletions": 0, "changes": 3},
            ]
        )
        files = diff_extractor.extract_changed_files(payload)
        assert len(files) == 2
        assert files[0].category == FileCategory.SOURCE
        assert files[0].language == "Python"
        assert files[1].category == FileCategory.DOCS

    def test_include_patch_false_strips_patch(self):
        payload = make_commit_payload()
        files = diff_extractor.extract_changed_files(payload, include_patch=False)
        assert all(f.patch is None for f in files)

    def test_empty_files(self):
        assert diff_extractor.extract_changed_files({"files": []}) == []
        assert diff_extractor.extract_changed_files({}) == []


class TestAggregations:
    def test_uses_github_stats_when_present(self):
        payload = make_commit_payload(
            files=[{"filename": "a.py", "status": "modified", "additions": 10, "deletions": 4, "changes": 14}]
        )
        files = diff_extractor.extract_changed_files(payload)
        stats = diff_extractor.aggregate_stats(files, payload)
        assert stats["additions"] == 10
        assert stats["deletions"] == 4
        assert stats["files_changed"] == 1

    def test_falls_back_to_summing_files(self):
        files = diff_extractor.extract_changed_files(
            {"files": [{"filename": "a.py", "status": "modified", "additions": 2, "deletions": 1, "changes": 3}]}
        )
        stats = diff_extractor.aggregate_stats(files, None)
        assert stats["total"] == 3

    def test_category_counts_and_languages(self):
        files = diff_extractor.extract_changed_files(
            make_commit_payload(
                files=[
                    {"filename": "a.py", "status": "modified", "additions": 1, "deletions": 0, "changes": 1},
                    {"filename": "b.ts", "status": "modified", "additions": 1, "deletions": 0, "changes": 1},
                ]
            )
        )
        counts = diff_extractor.category_counts(files)
        assert counts["source"] == 2
        assert diff_extractor.distinct_languages(files) == ["Python", "TypeScript"]
