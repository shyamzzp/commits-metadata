from app.models import ChangeType
from app.processing.llm_analyzer import LLMAnalyzer
from app.processing.schema_builder import build_metadata
from tests.conftest import make_commit_payload


class TestBuildMetadata:
    def test_builds_full_metadata(self):
        payload = make_commit_payload(message="feat(api): add endpoint #7")
        meta = build_metadata(payload, repository="octocat/hello")
        assert meta.repository == "octocat/hello"
        assert meta.short_sha == meta.sha[:7]
        assert meta.change_type == ChangeType.FEATURE
        assert meta.issue_references == ["#7"]
        assert meta.author_name == "Octo Cat"
        assert meta.stats["additions"] >= 1
        assert "Python" in meta.languages

    def test_merge_detection(self):
        payload = make_commit_payload(parents=2, message="Merge pull request #4")
        meta = build_metadata(payload, repository="o/r")
        assert meta.is_merge is True

    def test_breaking_change(self):
        payload = make_commit_payload(message="feat(api)!: drop v1")
        meta = build_metadata(payload, repository="o/r")
        assert meta.breaking_change is True

    def test_llm_summary_added_when_enabled(self):
        payload = make_commit_payload()
        meta = build_metadata(payload, repository="o/r", llm=LLMAnalyzer(enabled=True))
        assert meta.llm_summary is not None

    def test_llm_summary_none_when_disabled(self):
        payload = make_commit_payload()
        meta = build_metadata(payload, repository="o/r", llm=LLMAnalyzer(enabled=False))
        assert meta.llm_summary is None
