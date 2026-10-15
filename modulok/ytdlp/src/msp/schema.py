"""The staging schema: which fields exist, which are required, which are enums.

One definition, three consumers: the note renderer (templates.py), the manifest
writer (manifest.py) and the validator (validation.py). A field that is not
listed here is not written by the pipeline.

Naming note (spec sections 0 and 7): ``pipeline_status`` and ``source_note``
deliberately avoid the vault's own ``Status:`` (owner-only) and ``Source:``
(page-anchored) field names, so the two systems cannot be confused during
integration.
"""

from __future__ import annotations

from dataclasses import dataclass

SCHEMA_VERSION = 1

SOURCE_TYPE = "source"
TRANSCRIPT_TYPE = "transcript"

PIPELINE_STATUSES = ("downloaded", "metadata_only", "failed")
TRANSCRIPT_STATUSES = ("pending", "in_progress", "completed", "failed", "manual")
INTEGRATION_STATUSES = ("pending", "in_review", "integrated", "rejected")

MEDIA_STEM = "video"
SOURCE_NOTE_NAME = "source.md"
TRANSCRIPT_NOTE_NAME = "transcript.md"
METADATA_NAME = "metadata.json"
RAW_METADATA_NAME = "metadata.raw.json"
MANIFEST_NAME = "integration.json"

#: The anchor syntax a later integration step would use for a video claim,
#: mirroring the vault's ``[[FILE.pdf#page=NN]]`` convention.
ANCHOR_FORMAT = "[[{media}#t=HH:MM:SS]]"


@dataclass(frozen=True)
class FieldSpec:
    name: str
    required: bool = True
    nullable: bool = False
    kind: type | tuple[type, ...] = str
    enum: tuple[str, ...] | None = None
    description: str = ""


SOURCE_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("type", enum=(SOURCE_TYPE,), description="always 'source'"),
    FieldSpec("source_type", description="media kind, e.g. 'video'"),
    FieldSpec("source_id", description="stable <provider>-<id> identifier"),
    FieldSpec("title", description="human readable title"),
    FieldSpec("provider", description="platform display name"),
    FieldSpec("url", description="original page URL"),
    FieldSpec("language", nullable=True, description="content language if known"),
    FieldSpec("media_file", description="media file name inside this folder"),
    FieldSpec("transcript_file", description="transcript note file name"),
    FieldSpec("metadata_file", description="metadata JSON file name"),
    FieldSpec("downloaded_at", description="ISO 8601 timestamp"),
    FieldSpec("pipeline_status", enum=PIPELINE_STATUSES, description="staging pipeline state"),
    # optional, only written when the provider actually reported them
    FieldSpec("subject", required=False, nullable=True),
    FieldSpec("provider_video_id", required=False, nullable=True),
    FieldSpec("media_url", required=False, nullable=True,
              description="where the stream really came from, when the page only embeds it"),
    FieldSpec("duration_seconds", required=False, nullable=True, kind=(int, float)),
    FieldSpec("duration", required=False, nullable=True, description="HH:MM:SS"),
    FieldSpec("resolution", required=False, nullable=True),
    FieldSpec("uploader", required=False, nullable=True),
    FieldSpec("upload_date", required=False, nullable=True),
    FieldSpec("schema_version", required=False, kind=int),
)

TRANSCRIPT_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("type", enum=(TRANSCRIPT_TYPE,)),
    FieldSpec("source_id"),
    FieldSpec("source_note", description="wikilink to the source note"),
    FieldSpec("media", description="wikilink to the media file"),
    FieldSpec("language", nullable=True),
    FieldSpec("transcript_status", enum=TRANSCRIPT_STATUSES),
    FieldSpec("transcript_postprocessed", required=False, kind=bool,
              description="true if the text was altered after recognition (AI01 #14)"),
    FieldSpec("transcript_engine", required=False, nullable=True),
    FieldSpec("transcript_model", required=False, nullable=True),
    FieldSpec("transcript_confidence", required=False, nullable=True, kind=(int, float)),
    FieldSpec("transcript_generated_at", required=False, nullable=True),
    FieldSpec("schema_version", required=False, kind=int),
)

MANIFEST_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("schema_version", kind=int),
    FieldSpec("source_id"),
    FieldSpec("source_note"),
    FieldSpec("transcript"),
    FieldSpec("media"),
    FieldSpec("metadata"),
    FieldSpec("provider"),
    FieldSpec("url"),
    FieldSpec("title"),
    FieldSpec("language", nullable=True),
    FieldSpec("duration_seconds", nullable=True, kind=(int, float)),
    FieldSpec("suggested_subject", nullable=True),
    FieldSpec("subject_source", nullable=True),
    FieldSpec("suggested_topics", kind=list),
    FieldSpec("anchor_format"),
    FieldSpec("transcript_status", enum=TRANSCRIPT_STATUSES),
    FieldSpec("nn_anchorable", nullable=True, kind=bool,
              description="null = the vault owner has not decided yet (AI01 #9)"),
    FieldSpec("integration_status", enum=INTEGRATION_STATUSES),
)


def required_field_names(fields: tuple[FieldSpec, ...]) -> tuple[str, ...]:
    return tuple(spec.name for spec in fields if spec.required)


def field_map(fields: tuple[FieldSpec, ...]) -> dict[str, FieldSpec]:
    return {spec.name: spec for spec in fields}
