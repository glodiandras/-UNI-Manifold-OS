"""Rendering a TranscriptResult into transcript.md.

Body layout (spec section 9) - a zero-padded marker on its own line, then the
text, so a later step can turn any marker into ``[[video.mp4#t=HH:MM:SS]]``::

    [00:00:00]

    ...

    [00:01:32]

    ...
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from .. import manifest as manifest_mod
from .. import notes, schema
from ..config import Config
from ..errors import PipelineError, TranscriptionError
from ..timestamps import timestamp_marker
from .base import Segment, TranscriptResult


def render_transcript_body(segments: Sequence[Segment], *, group_seconds: float = 0.0) -> str:
    """Timestamped transcript body. Text is copied verbatim."""
    if not segments:
        raise TranscriptionError("Refusing to write an empty transcript.")
    blocks: list[str] = []
    current_start: float | None = None
    buffer: list[str] = []

    for segment in segments:
        text = segment.text.strip()
        if not text:
            continue
        if current_start is None:
            current_start = segment.start
            buffer = [text]
            continue
        if group_seconds > 0 and (segment.start - current_start) < group_seconds:
            buffer.append(text)
            continue
        blocks.append(f"{timestamp_marker(current_start)}\n\n{' '.join(buffer)}")
        current_start = segment.start
        buffer = [text]

    if current_start is not None and buffer:
        blocks.append(f"{timestamp_marker(current_start)}\n\n{' '.join(buffer)}")
    return "\n\n".join(blocks) + "\n"


def write_transcript(
    folder: str | Path,
    result: TranscriptResult,
    *,
    config: Config,
    group_seconds: float = 0.0,
    logger: logging.Logger | None = None,
) -> Path:
    """Write transcript.md for a staged source and update integration.json."""
    directory = Path(folder)
    source_note = directory / schema.SOURCE_NOTE_NAME
    if not source_note.is_file():
        raise TranscriptionError(f"{directory} is not a staged source folder (no {schema.SOURCE_NOTE_NAME}).")

    front, _ = notes.read_note(source_note)
    source_id = str(front.get("source_id") or "")
    title = str(front.get("title") or directory.name)
    media_file = str(front.get("media_file") or f"{schema.MEDIA_STEM}.mp4")
    language = result.language or front.get("language")

    body = render_transcript_body(result.segments, group_seconds=group_seconds)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    confidence = result.mean_confidence()

    values = notes.build_transcript_values(
        source_id=source_id,
        title=title,
        media_file=media_file,
        language=language,
        transcript_status="completed",
        body=body,
        postprocessed=result.postprocessed,
        engine=result.engine,
        model=result.model,
        confidence=confidence,
        generated_at=generated_at,
    )
    path = notes.write_transcript_note(directory / schema.TRANSCRIPT_NOTE_NAME, values, config.templates_dir)

    manifest_path = directory / schema.MANIFEST_NAME
    if manifest_path.is_file():
        try:
            manifest_mod.update_manifest(manifest_path, {"transcript_status": "completed"})
        except (PipelineError, ValueError) as exc:  # pragma: no cover - manual edits
            if logger:
                logger.warning("Could not update %s: %s", manifest_path, exc)
    if logger:
        details: dict[str, Any] = {"segments": len(result.segments), "engine": result.engine}
        if confidence is not None:
            details["confidence"] = round(confidence, 3)
        logger.info(
            "    transcript written: %d segments, engine %s%s",
            len(result.segments),
            result.engine,
            f", mean confidence {confidence:.2f}" if confidence is not None else "",
        )
    return path
