import pytest

from app.models import FileCategory
from app.processing.file_classifier import classify_file, detect_language


class TestClassifyFile:
    @pytest.mark.parametrize(
        "path,expected",
        [
            ("app/main.py", FileCategory.SOURCE),
            ("src/index.ts", FileCategory.SOURCE),
            ("tests/test_main.py", FileCategory.TEST),
            ("src/foo.test.js", FileCategory.TEST),
            ("README.md", FileCategory.DOCS),
            ("docs/guide.rst", FileCategory.DOCS),
            (".github/workflows/ci.yml", FileCategory.CI),
            ("Dockerfile", FileCategory.BUILD),
            ("pyproject.toml", FileCategory.BUILD),
            ("requirements.txt", FileCategory.BUILD),
            ("config/settings.ini", FileCategory.CONFIG),
            ("assets/logo.png", FileCategory.ASSET),
            ("data/records.csv", FileCategory.DATA),
            ("LICENSE", FileCategory.OTHER),
        ],
    )
    def test_classification(self, path, expected):
        assert classify_file(path) == expected

    def test_test_dir_beats_source_ext(self):
        assert classify_file("tests/helpers/widget.py") == FileCategory.TEST


class TestDetectLanguage:
    @pytest.mark.parametrize(
        "path,lang",
        [
            ("a.py", "Python"),
            ("a.ts", "TypeScript"),
            ("a.go", "Go"),
            ("a.unknownext", None),
        ],
    )
    def test_language(self, path, lang):
        assert detect_language(path) == lang
