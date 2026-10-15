"""integration.json - the machine-readable hand-off to the integration step.

The manifest is what a later, vault-aware Claude instance reads first. Two
fields encode the open questions of CLAUDE.md instead of hiding them:

``nn_anchorable``
    ``null`` until the vault owner decides whether video-derived content may
    become an NN-anchorable source at all (AI01 #9). No integration step may
    treat ``null`` as "yes".

``anchor_format``
    The timestamp anchor shape a video claim would use, mirroring the vault's
    page-anchored ``Source:`` convention.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import schema
from .fsio import read_json, write_json_atomic


def build_manifest(
    *,
    source_id: str,
    title: str,
    provider: str,
    url: str,
    media_file: str,
    language: str | None = None,
    duration_seconds: float | int | None = None,
    suggested_subject: str | None = None,
    subject_source: str | None = None,
    suggested_topics: list[str] | None = None,
    transcript_status: str = "pending",
    integration_status: str = "pending",
    nn_anchorable: bool | None = None,
) -> dict[str, Any]:
    """Build the integration.json payload."""
    if transcript_status not in schema.TRANSCRIPT_STATUSES:
        raise ValueError(f"unknown transcript_status: {transcript_status}")
    if integration_status not in schema.INTEGRATION_STATUSES:
        raise ValueError(f"unknown integration_status: {integration_status}")

    return {
        "schema_version": schema.SCHEMA_VERSION,
        "source_id": source_id,
        "source_note": schema.SOURCE_NOTE_NAME,
        "transcript": schema.TRANSCRIPT_NOTE_NAME,
        "media": media_file,
        "metadata": schema.METADATA_NAME,
        "provider": provider,
        "url": url,
        "title": title,
        "language": language,
        "duration_seconds": int(duration_seconds) if isinstance(duration_seconds, (int, float)) else None,
        # Should match the vault's own subject spelling character for character
        # (open decision #3 in CLAUDE.md).
        "suggested_subject": suggested_subject,
        "subject_source": subject_source,
        # Never guessed by the pipeline: topics are a knowledge judgement.
        "suggested_topics": list(suggested_topics or []),
        "anchor_format": schema.ANCHOR_FORMAT.format(media=media_file),
        "transcript_status": transcript_status,
        "nn_anchorable": nn_anchorable,
        "integration_status": integration_status,
    }


def write_manifest(path: str | Path, data: dict[str, Any]) -> Path:
    return write_json_atomic(path, data)


def read_manifest(path: str | Path) -> dict[str, Any]:
    data = read_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: integration.json must contain a JSON object")
    return data


def update_manifest(path: str | Path, updates: dict[str, Any]) -> dict[str, Any]:
    """Merge fields into an existing manifest, keeping unknown keys intact."""
    data = read_manifest(path)
    data.update(updates)
    write_manifest(path, data)
    return data
