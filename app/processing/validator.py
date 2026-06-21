"""JSON Schema Validator — validates built metadata against the fixed schema."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

from app.models import FeatureMetadata

_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema" / "feature_metadata.schema.json"


class SchemaValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


@lru_cache(maxsize=1)
def load_schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    return Draft202012Validator(load_schema())


def validate_payload(payload: dict) -> None:
    """Raise :class:`SchemaValidationError` if ``payload`` violates the schema."""
    errors = sorted(_validator().iter_errors(payload), key=lambda e: list(e.path))
    if errors:
        raise SchemaValidationError([f"{list(e.path)}: {e.message}" for e in errors])


def validate_metadata(meta: FeatureMetadata) -> dict:
    """Validate a FeatureMetadata and return its JSON-ready dict."""
    payload = json.loads(meta.model_dump_json())
    validate_payload(payload)
    return payload
