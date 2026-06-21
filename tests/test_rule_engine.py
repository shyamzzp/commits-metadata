import pytest

from app.models import ChangedFile, ChangeType, FileCategory
from app.processing import rule_engine


def _file(name, category=FileCategory.SOURCE, lang="Python"):
    return ChangedFile(filename=name, status="modified", category=category, language=lang)


class TestChangeType:
    @pytest.mark.parametrize(
        "msg,expected",
        [
            ("feat: add login", ChangeType.FEATURE),
            ("feat(auth): add login", ChangeType.FEATURE),
            ("fix: null pointer", ChangeType.BUGFIX),
            ("fix(api)!: drop field", ChangeType.BUGFIX),
            ("docs: update readme", ChangeType.DOCS),
            ("test: add coverage", ChangeType.TEST),
            ("refactor: tidy module", ChangeType.REFACTOR),
            ("perf: speed up loop", ChangeType.PERF),
            ("ci: bump action", ChangeType.CI),
            ("revert: undo abc", ChangeType.REVERT),
        ],
    )
    def test_conventional_prefix(self, msg, expected):
        assert rule_engine.classify_change_type(msg) == expected

    def test_keyword_fallback_when_no_prefix(self):
        assert rule_engine.classify_change_type("Fixed a crash on startup") == ChangeType.BUGFIX
        assert rule_engine.classify_change_type("Add new dashboard page") == ChangeType.FEATURE

    def test_file_mix_fallback(self):
        files = [_file("docs/a.md", FileCategory.DOCS, "Markdown")]
        assert rule_engine.classify_change_type("misc updates", files) == ChangeType.DOCS

    def test_unknown_when_no_signal(self):
        assert rule_engine.classify_change_type("misc updates") == ChangeType.UNKNOWN


class TestIssueRefs:
    def test_hash_refs(self):
        assert rule_engine.extract_issue_references("fix #12 and #3") == ["#3", "#12"]

    def test_url_refs(self):
        msg = "see https://github.com/o/r/issues/99 closes #5"
        assert rule_engine.extract_issue_references(msg) == ["#5", "#99"]

    def test_no_refs(self):
        assert rule_engine.extract_issue_references("nothing here") == []


class TestBreaking:
    def test_breaking_change_footer(self):
        assert rule_engine.is_breaking_change("feat: x\n\nBREAKING CHANGE: drops api") is True

    def test_bang_marker(self):
        assert rule_engine.is_breaking_change("feat(api)!: remove field") is True

    def test_not_breaking(self):
        assert rule_engine.is_breaking_change("feat: safe change") is False


class TestSubjectAndTags:
    def test_subject_is_first_line(self):
        assert rule_engine.message_subject("hello\n\nbody") == "hello"
        assert rule_engine.message_subject("") == ""

    def test_tags_include_category_and_lang(self):
        tags = rule_engine.derive_tags("feat: x", [_file("a.py")])
        assert "cat:source" in tags
        assert "lang:python" in tags

    def test_tags_include_breaking(self):
        tags = rule_engine.derive_tags("feat!: x", [_file("a.py")])
        assert "breaking" in tags
