"""Curation of the yt-dlp info dict into a small, stable metadata.json.

Two deliberate choices (spec section 8: "no unnecessary or sensitive data"):

* The top-level ``url`` field holds the **original page URL**, not the direct
  media URL from the info dict. Direct URLs are signed, expire within hours and
  would be useless - occasionally even sensitive - in an archive.
* ``pipeline.ffmpeg_used`` records whether the file was muxed from separate
  video and audio streams, so the provenance of the media file stays explicit.
* Volatile counters (views, likes), the full ``formats`` list, HTTP headers,
  cookies and automatic-caption blobs are dropped. ``metadata.raw.json`` can be
  enabled in config when the complete dict is genuinely needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .timestamps import format_timestamp

#: Fields copied verbatim from the info dict when present.
_PASSTHROUGH = (
    "id",
    "title",
    "uploader",
    "uploader_id",
    "channel",
    "upload_date",
    "duration",
    "description",
    "webpage_url",
    "extractor",
    "extractor_key",
    "language",
    "ext",
    "format_id",
    "format_note",
    "width",
    "height",
    "fps",
    "vcodec",
    "acodec",
    "filesize",
    "filesize_approx",
)

#: Never written to metadata.json.
_EXCLUDED = frozenset({
    "formats", "requested_formats", "requested_downloads", "thumbnails", "url",
    "http_headers", "cookies", "automatic_captions", "heatmap", "fragments",
    "view_count", "like_count", "dislike_count", "comment_count",
    "concurrent_view_count", "average_rating", "_format_sort_fields",
})


@dataclass(frozen=True)
class FormatInfo:
    """One yt-dlp format, reduced to what the pipeline cares about."""

    format_id: str
    ext: str | None
    height: int | None
    width: int | None
    fps: float | None
    vcodec: str | None
    acodec: str | None
    filesize: int | None
    note: str | None

    @property
    def is_progressive(self) -> bool:
        """True when the format already carries video *and* audio in one file.

        Only progressive formats are usable here: merging separate streams
        would require FFmpeg, which is intentionally not part of the stack.
        """
        video = (self.vcodec or "none") != "none"
        audio = (self.acodec or "none") != "none"
        return video and audio

    @property
    def is_storyboard(self) -> bool:
        """Storyboard thumbnail tracks (mhtml) are not playable video."""
        return self.ext == "mhtml" or (self.vcodec or "") == "images"

    @property
    def resolution(self) -> str:
        if self.width and self.height:
            return f"{self.width}x{self.height}"
        if self.height:
            return f"{self.height}p"
        return "unknown"


def iter_formats(info: dict[str, Any]) -> list[FormatInfo]:
    """All formats reported for a video."""
    formats = info.get("formats")
    if not isinstance(formats, list):
        return []
    result: list[FormatInfo] = []
    for entry in formats:
        if not isinstance(entry, dict):
            continue
        result.append(
            FormatInfo(
                format_id=str(entry.get("format_id") or "?"),
                ext=entry.get("ext"),
                height=entry.get("height"),
                width=entry.get("width"),
                fps=entry.get("fps"),
                vcodec=entry.get("vcodec"),
                acodec=entry.get("acodec"),
                filesize=entry.get("filesize") or entry.get("filesize_approx"),
                note=entry.get("format_note"),
            )
        )
    return result


def progressive_formats(info: dict[str, Any]) -> list[FormatInfo]:
    """Progressive (pre-muxed) formats, best first by height."""
    formats = [fmt for fmt in iter_formats(info) if fmt.is_progressive]
    return sorted(formats, key=lambda fmt: (fmt.height or 0, fmt.fps or 0), reverse=True)


def best_progressive_height(info: dict[str, Any]) -> int | None:
    formats = progressive_formats(info)
    return formats[0].height if formats else None


def best_available_height(info: dict[str, Any]) -> int | None:
    """Best height of any format, merged or not - the real ceiling of a video."""
    heights = [fmt.height for fmt in iter_formats(info) if fmt.height and not fmt.is_storyboard]
    return max(heights) if heights else None


def was_merged(info: dict[str, Any]) -> bool:
    """True when the downloaded file was muxed from separate streams."""
    requested = info.get("requested_formats")
    return isinstance(requested, list) and len(requested) > 1


def resolution_of(info: dict[str, Any]) -> str | None:
    """Resolution actually obtained (``1280x720``), if the info dict says so."""
    if info.get("resolution"):
        return str(info["resolution"])
    width, height = info.get("width"), info.get("height")
    if width and height:
        return f"{width}x{height}"
    if height:
        return f"{height}p"
    return None


def subtitle_languages(info: dict[str, Any], *, automatic: bool = False) -> list[str]:
    key = "automatic_captions" if automatic else "subtitles"
    subs = info.get(key)
    if not isinstance(subs, dict):
        return []
    return sorted(str(lang) for lang in subs)


def curate(
    info: dict[str, Any],
    *,
    page_url: str,
    source_id: str,
    downloaded_at: str,
    media_file: str | None,
    format_selector: str,
    ytdlp_version: str | None = None,
    schema_version: int = 1,
    ffmpeg_used: bool | None = None,
) -> dict[str, Any]:
    """Build the metadata.json payload."""
    data: dict[str, Any] = {}
    for key in _PASSTHROUGH:
        if key in _EXCLUDED:
            continue
        value = info.get(key)
        if value is None or value == "":
            continue
        data[key] = value

    duration = info.get("duration")
    ordered: dict[str, Any] = {
        "id": data.get("id"),
        "title": data.get("title"),
        "url": page_url,
        "webpage_url": info.get("webpage_url") or page_url,
        "uploader": data.get("uploader"),
        "upload_date": data.get("upload_date"),
        "duration": duration,
        "duration_hms": format_timestamp(duration) if isinstance(duration, (int, float)) else None,
        "description": data.get("description"),
        "extractor": info.get("extractor_key") or info.get("extractor"),
        "language": data.get("language"),
        "resolution": resolution_of(info),
        "fps": data.get("fps"),
        "ext": data.get("ext"),
        "format_id": data.get("format_id"),
        "format_note": data.get("format_note"),
        "vcodec": data.get("vcodec"),
        "acodec": data.get("acodec"),
        "filesize": data.get("filesize") or data.get("filesize_approx"),
        "subtitles_available": subtitle_languages(info),
        "automatic_captions_available": subtitle_languages(info, automatic=True),
        "pipeline": {
            "schema_version": schema_version,
            "source_id": source_id,
            "downloaded_at": downloaded_at,
            "media_file": media_file,
            "format_selector": format_selector,
            "ffmpeg_used": was_merged(info) if ffmpeg_used is None else ffmpeg_used,
            "yt_dlp_version": ytdlp_version,
        },
    }
    return {key: value for key, value in ordered.items() if value is not None}
