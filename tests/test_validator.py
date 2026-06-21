import pytest

from app.processing.schema_builder import build_metadata
from app.processing.validator import (
    SchemaValidationError,
    validate_metadata,
    validate_payload,
)
from tests.conftest import make_commit_payload


class TestValidator:
    def test_valid_metadata_passes(self):
        meta = build_metadata(make_commit_payload(), repository="octocat/hello")
        payload = validate_metadata(meta)
        assert payload["sha"] == meta.sha
        assert payload["change_type"] in {"feature", "bugfix", "unknown", "docs"}

    def test_missing_required_field_fails(self):
        with pytest.raises(SchemaValidationError):
            validate_payload({"sha": "abc1234"})  # missing many required fields

    def test_bad_sha_pattern_fails(self):
        meta = build_metadata(make_commit_payload(), repository="octocat/hello").model_dump()
        meta["sha"] = "not-a-sha!!"
        import json
        # round-trip through json to mimic real payloads
        with pytest.raises(SchemaValidationError):
            validate_payload(json.loads(json.dumps(meta)))

    def test_bad_change_type_enum_fails(self):
        import json
        meta = build_metadata(make_commit_payload(), repository="octocat/hello").model_dump()
        meta["change_type"] = "totally-invalid"
        with pytest.raises(SchemaValidationError):
            validate_payload(json.loads(json.dumps(meta)))

    def test_repository_must_be_owner_slash_name(self):
        import json
        meta = build_metadata(make_commit_payload(), repository="octocat/hello").model_dump()
        meta["repository"] = "no-slash"
        with pytest.raises(SchemaValidationError):
            validate_payload(json.loads(json.dumps(meta)))
