"""Building, writing and surgically updating the two Markdown notes.

``source.md`` is the entry point of a staged source; ``transcript.md`` is the
machine-readable text layer of the same source. Neither is a knowledge note.

Frontmatter updates (e.g. flipping ``transcript_status`` after transcription)
are done line by line rather than by re-serialising the whole mapping, so any
manual edit - added fields, comments, field order - survives untouched.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

from . import schema, templates
from .errors import ConfigError, FilesystemError
from .fsio import read_text, write_text_atomic
from .timestamps import format_timestamp
from .yamlio import parse_frontmatter, to_yaml_scalar


def _wikilink(target: str) -> str:
    """``transcript.md`` -> ``[[transcript]]`` (spec section 15).

    Unqualified wikilinks are what the spec asks for. They are ambiguous across
    hundreds of source folders in one vault, which is exactly why integration
    regenerates them; the body of each note additionally carries unambiguous
    relative Markdown links.
    """
    stem = target[:-3] if target.endswith(".md") else target
    return f"[[{stem}]]"


def build_source_values(
    *,
    source_id: str,
    title: str,
    provider: str,
    url: str,
    media_file: str,
    downloaded_at: str,
    subject: str | None = None,
    language: str | None = None,
    duration_seconds: float | int | None = None,
    resolution: str | None = None,
    uploader: str | None = None,
    upload_date: str | None = None,
    provider_video_id: str | None = None,
    media_url: str | None = None,
    pipeline_status: str = "downloaded",
    source_type: str = "video",
) -> dict[str, Any]:
    """Assemble the value map for ``source.md``.

    Optional keys are simply left out when unknown - the template then drops
    the corresponding line instead of inventing a value (spec section 7).
    """
    if pipeline_status not in schema.PIPELINE_STATUSES:
        raise ValueError(f"unknown pipeline_status: {pipeline_status}")

    values: dict[str, Any] = {
        "type": schema.SOURCE_TYPE,
        "source_type": source_type,
        "source_id": source_id,
        "title": title,
        "provider": provider,
        "url": url,
        "language": language,  # required but nullable: null means "not reported"
        "media_file": media_file,
        "media_file_href": media_file,
        "transcript_file": schema.TRANSCRIPT_NOTE_NAME,
        "transcript_file_href": schema.TRANSCRIPT_NOTE_NAME,
        "metadata_file": schema.METADATA_NAME,
        "downloaded_at": downloaded_at,
        "pipeline_status": pipeline_status,
        "schema_version": schema.SCHEMA_VERSION,
    }
    if subject:
        values["subject"] = subject
    if provider_video_id:
        values["provider_video_id"] = provider_video_id
    if media_url and media_url != url:
        values["media_url"] = media_url
    if isinstance(duration_seconds, (int, float)):
        values["duration_seconds"] = int(duration_seconds)
        values["duration"] = format_timestamp(duration_seconds)
    if resolution:
        values["resolution"] = resolution
    if uploader:
        values["uploader"] = uploader
    if upload_date:
        values["upload_date"] = upload_date
    return values


def build_transcript_values(
    *,
    source_id: str,
    title: str,
    media_file: str,
    language: str | None = None,
    transcript_status: str = "pending",
    body: str | None = None,
    postprocessed: bool = False,
    engine: str | None = None,
    model: str | None = None,
    confidence: float | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Assemble the value map for ``transcript.md``."""
    if transcript_status not in schema.TRANSCRIPT_STATUSES:
        raise ValueError(f"unknown transcript_status: {transcript_status}")

    values: dict[str, Any] = {
        "type": schema.TRANSCRIPT_TYPE,
        "source_id": source_id,
        # `source_note` / `media`, not `source:` - the vault's own Source: field
        # means a page-anchored quote and must not be shadowed (spec section 9).
        "source_note": _wikilink(schema.SOURCE_NOTE_NAME),
        "media": _wikilink(media_file),
        "language": language,
        "transcript_status": transcript_status,
        "transcript_postprocessed": bool(postprocessed),
        "schema_version": schema.SCHEMA_VERSION,
        "title": title,
        "body": body if body is not None else templates.PENDING_TRANSCRIPT_BODY,
    }
    if engine:
        values["transcript_engine"] = engine
    if model:
        values["transcript_model"] = model
    if confidence is not None:
        values["transcript_confidence"] = round(float(confidence), 4)
    if generated_at:
        values["transcript_generated_at"] = generated_at
    return values


def render_source_note(values: Mapping[str, Any], templates_dir: Path | None = None) -> str:
    return templates.render(
        templates.load_template(templates.SOURCE_TEMPLATE_NAME, templates_dir), values
    )


def render_transcript_note(values: Mapping[str, Any], templates_dir: Path | None = None) -> str:
    return templates.render(
        templates.load_template(templates.TRANSCRIPT_TEMPLATE_NAME, templates_dir), values
    )


def write_source_note(path: str | Path, values: Mapping[str, Any], templates_dir: Path | None = None) -> Path:
    return write_text_atomic(path, render_source_note(values, templates_dir))


def write_transcript_note(path: str | Path, values: Mapping[str, Any], templates_dir: Path | None = None) -> Path:
    return write_text_atomic(path, render_transcript_note(values, templates_dir))


def read_note(path: str | Path) -> tuple[dict[str, Any], str]:
    """Parse a generated note into (frontmatter mapping, body)."""
    target = Path(path)
    return parse_frontmatter(read_text(target), origin=str(target))


def update_frontmatter(path: str | Path, updates: Mapping[str, Any]) -> Path:
    """Set frontmatter fields in place, keeping everything else byte-identical.

    Existing keys are replaced where they stand; new keys are appended just
    before the closing ``---``.
    """
    target = Path(path)
    text = read_text(target)
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ConfigError(f"{target}: cannot update frontmatter, the file does not start with '---'")

    closing = None
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            closing = index
            break
    if closing is None:
        raise ConfigError(f"{target}: unterminated YAML frontmatter")

    remaining = dict(updates)
    for index in range(1, closing):
        match = re.match(r"\A(\s*)(\"[^\"]+\"|'[^']+'|[A-Za-z_][A-Za-z0-9_-]*)(\s*):", lines[index])
        if not match:
            continue
        key = match.group(2).strip("\"'")
        if key in remaining:
            newline = "\r\n" if lines[index].endswith("\r\n") else "\n"
            lines[index] = f"{match.group(1)}{key}: {to_yaml_scalar(remaining.pop(key))}{newline}"

    if remaining:
        addition = [f"{key}: {to_yaml_scalar(value)}\n" for key, value in remaining.items()]
        lines[closing:closing] = addition

    try:
        return write_text_atomic(target, "".join(lines))
    except OSError as exc:  # pragma: no cover - surfaced as FilesystemError
        raise FilesystemError(f"Cannot update {target}: {exc}") from exc


def replace_body(path: str | Path, body: str) -> Path:
    """Replace everything after the frontmatter (used by the transcript writer)."""
    target = Path(path)
    text = read_text(target)
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ConfigError(f"{target}: cannot replace body, the file has no frontmatter")
    closing = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if closing is None:
        raise ConfigError(f"{target}: unterminated YAML frontmatter")
    head = "".join(lines[: closing + 1])
    if not body.endswith("\n"):
        body += "\n"
    return write_text_atomic(target, f"{head}\n{body}")
