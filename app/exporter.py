"""JSON Exporter — serialises results to the fixed JSON response / download file."""

from __future__ import annotations

import json
from typing import Iterable

from app.models import FeatureMetadata, JobResult


def export_metadata(meta: FeatureMetadata) -> dict:
    return json.loads(meta.model_dump_json())


def export_job(result: JobResult) -> dict:
    return json.loads(result.model_dump_json())


def export_collection(items: Iterable[FeatureMetadata]) -> dict:
    """Bundle many commits into a single downloadable JSON document."""
    commits = [export_metadata(m) for m in items]
    return {
        "schema_version": "1.0",
        "count": len(commits),
        "commits": commits,
    }


def to_json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
