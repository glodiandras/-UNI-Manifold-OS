"""Transcript from provider-supplied subtitle files (.vtt / .srt).

Often the highest-fidelity option available: a human-authored subtitle track is
closer to what was actually said than a small ASR model, and it needs neither a
GPU nor FFmpeg. Machine-generated captions are still ASR output - the engine
string records which kind was used, so nothing is silently passed off as human
transcription.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..config import Config
from ..errors import TranscriptionError
from .base import Segment, TranscriptionBackend, TranscriptResult

SUBTITLE_SUFFIXES = (".vtt", ".srt")

_TIMING_RE = re.compile(
    r"(?P<start>\d{1,3}:\d{2}:\d{2}[.,]\d{1,3}|\d{1,2}:\d{2}[.,]\d{1,3})\s*-->\s*"
    r"(?P<end>\d{1,3}:\d{2}:\d{2}[.,]\d{1,3}|\d{1,2}:\d{2}[.,]\d{1,3})"
)
_TAG_RE = re.compile(r"<[^>]+>")
_CUE_INDEX_RE = re.compile(r"\A\d+\Z")


def parse_time(value: str) -> float:
    """``00:01:32.500`` / ``01:32,500`` -> seconds."""
    text = value.strip().replace(",", ".")
    parts = text.split(":")
    if len(parts) == 3:
        hours, minutes, seconds = parts
    elif len(parts) == 2:
        hours, minutes, seconds = "0", parts[0], parts[1]
    else:
        raise ValueError(f"unparsable subtitle timestamp: {value!r}")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def parse_subtitle_file(path: Path) -> list[Segment]:
    """Parse a WebVTT or SubRip file into segments (text kept verbatim)."""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise TranscriptionError(f"Cannot read subtitle file {path}: {exc}") from exc

    segments: list[Segment] = []
    block_lines: list[str] = []
    timing: tuple[float, float] | None = None

    def flush() -> None:
        nonlocal timing, block_lines
        if timing is not None:
            body = " ".join(
                _TAG_RE.sub("", line).strip()
                for line in block_lines
                if line.strip() and not _CUE_INDEX_RE.match(line.strip())
            ).strip()
            if body:
                segments.append(Segment(start=timing[0], end=timing[1], text=body))
        timing = None
        block_lines = []

    skip_block = False
    for raw in text.splitlines():
        line = raw.rstrip("\r")
        if not line.strip():
            flush()
            skip_block = False
            continue
        if line.startswith(("WEBVTT", "NOTE", "STYLE", "REGION", "Kind:", "Language:")):
            skip_block = True
            continue
        if skip_block and "-->" not in line:
            continue
        match = _TIMING_RE.search(line)
        if match:
            flush()
            skip_block = False
            try:
                timing = (parse_time(match.group("start")), parse_time(match.group("end")))
            except ValueError:
                timing = None
            continue
        if timing is not None:
            block_lines.append(line)
    flush()
    return _deduplicate(segments)


def _deduplicate(segments: list[Segment]) -> list[Segment]:
    """Drop the repetition of rolling captions without changing any wording."""
    result: list[Segment] = []
    for segment in segments:
        clean = segment.cleaned()
        if not clean.text:
            continue
        if result:
            previous = result[-1]
            if clean.text == previous.text:
                result[-1] = Segment(previous.start, previous.text, clean.end, previous.confidence)
                continue
            if clean.text.startswith(previous.text) and len(previous.text) > 8:
                result[-1] = Segment(previous.start, clean.text, clean.end, previous.confidence)
                continue
        result.append(clean)
    return result


def find_subtitle_files(folder: Path) -> list[Path]:
    return sorted(
        path for path in Path(folder).glob("*")
        if path.is_file() and path.suffix.lower() in SUBTITLE_SUFFIXES
    )


def _language_of(path: Path) -> str | None:
    # video.hu.vtt -> "hu";  video.vtt -> None
    parts = path.name.split(".")
    return parts[-2] if len(parts) >= 3 else None


class SubtitlesBackend(TranscriptionBackend):
    name = "subtitles"
    summary = "Uses a .vtt/.srt file already present next to the video (no ASR, no FFmpeg)."

    def __init__(self, config: Config | None = None) -> None:
        self._config = config

    def unavailable_reason(self, folder: Path | None = None) -> str | None:
        if folder is None:
            return None  # cannot tell without a folder; checked again at run time
        if not find_subtitle_files(folder):
            return "no .vtt/.srt file in the source folder (enable subtitles.download in config)"
        return None

    def transcribe(
        self,
        media_path: Path,
        *,
        language: str | None = None,
        folder: Path | None = None,
    ) -> TranscriptResult:
        directory = Path(folder or Path(media_path).parent)
        candidates = find_subtitle_files(directory)
        if not candidates:
            raise TranscriptionError(
                f"No subtitle file found in {directory}",
                hint="Set subtitles.download: true in config/config.yaml and re-download, "
                     "or choose another backend with --backend.",
            )
        chosen = candidates[0]
        if language:
            preferred = [path for path in candidates if _language_of(path) == language]
            if preferred:
                chosen = preferred[0]
        segments = parse_subtitle_file(chosen)
        if not segments:
            raise TranscriptionError(f"The subtitle file contains no usable cues: {chosen}")
        return TranscriptResult(
            segments=segments,
            engine=f"subtitles:{chosen.name}",
            language=language or _language_of(chosen),
            model=None,
            postprocessed=False,
            extra={"subtitle_file": chosen.name},
        )
