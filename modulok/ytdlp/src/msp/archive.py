"""Duplicate protection (spec section 11).

Three independent layers, deliberately not one:

1. ``archive/index.json`` - source_id -> where it was staged and when.
2. ``archive/downloaded.txt`` - the same information in yt-dlp's own
   ``--download-archive`` line format (``<extractor> <id>``), so the archive
   can be handed to a plain yt-dlp invocation if needed.
3. on-disk checks - a folder that already holds a ``source.md`` and a non-empty
   media file counts as downloaded even if the index was lost.

The yt-dlp archive file is written by the pipeline but never passed to yt-dlp
as ``download_archive``: yt-dlp would then silently skip the download and
report success without producing a file, which would defeat the check above.

The index is a single JSON file, so a save merges in whatever another run
wrote in the meantime (:meth:`Archive.save`); two runs at the same time - a
terminal command next to the web UI, say - therefore cannot drop each other's
entries. :func:`rebuild_missing_entries` restores what an interrupted run
never got to write, from the staged folders themselves.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .errors import PipelineError
from .fsio import read_json, write_json_atomic, write_text_atomic

INDEX_NAME = "index.json"
YTDLP_ARCHIVE_NAME = "downloaded.txt"
SCHEMA_VERSION = 1


@dataclass
class ArchiveEntry:
    source_id: str
    url: str
    path: str  # relative to the staging root
    downloaded_at: str
    provider: str = ""
    title: str = ""
    media_file: str = ""
    extractor: str = ""
    video_id: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if not data.get("extra"):
            data.pop("extra", None)
        return data

    @classmethod
    def from_dict(cls, source_id: str, data: dict[str, Any]) -> "ArchiveEntry":
        return cls(
            source_id=source_id,
            url=str(data.get("url", "")),
            path=str(data.get("path", "")),
            downloaded_at=str(data.get("downloaded_at", "")),
            provider=str(data.get("provider", "")),
            title=str(data.get("title", "")),
            media_file=str(data.get("media_file", "")),
            extractor=str(data.get("extractor", "")),
            video_id=str(data.get("video_id", "")),
            extra=dict(data.get("extra", {})),
        )

    @property
    def ytdlp_line(self) -> str | None:
        if not self.extractor or not self.video_id:
            return None
        return f"{self.extractor.lower()} {self.video_id}"


class Archive:
    """The download archive. Disabled instances behave as an empty archive."""

    def __init__(self, directory: str | Path, *, enabled: bool = True) -> None:
        self.directory = Path(directory)
        self.enabled = enabled
        self._entries: dict[str, ArchiveEntry] = {}
        self._removed: set[str] = set()
        self._loaded = False

    # -- paths --------------------------------------------------------------

    @property
    def index_path(self) -> Path:
        return self.directory / INDEX_NAME

    @property
    def ytdlp_archive_path(self) -> Path:
        return self.directory / YTDLP_ARCHIVE_NAME

    # -- loading / saving ---------------------------------------------------

    def load(self) -> "Archive":
        if self._loaded:
            return self
        self._loaded = True
        if not self.enabled or not self.index_path.exists():
            return self
        data = read_json(self.index_path)
        entries = data.get("entries") if isinstance(data, dict) else None
        if isinstance(entries, dict):
            for source_id, payload in entries.items():
                if isinstance(payload, dict):
                    self._entries[str(source_id)] = ArchiveEntry.from_dict(str(source_id), payload)
        return self

    def _merge_from_disk(self) -> None:
        """Adopt entries another process wrote since this one read the index.

        Own entries win, and anything removed here stays removed. Without this
        a concurrent run would save its own view over ours and the entries it
        never saw would be gone.
        """
        if not self.index_path.exists():
            return
        try:
            data = read_json(self.index_path)
        except PipelineError:
            return  # unreadable index: our own view is the best we have
        entries = data.get("entries") if isinstance(data, dict) else None
        if not isinstance(entries, dict):
            return
        for source_id, payload in entries.items():
            key = str(source_id)
            if key in self._entries or key in self._removed or not isinstance(payload, dict):
                continue
            self._entries[key] = ArchiveEntry.from_dict(key, payload)

    def save(self) -> None:
        if not self.enabled:
            return
        self.load()
        self._merge_from_disk()
        self.directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "entries": {
                source_id: entry.to_dict()
                for source_id, entry in sorted(self._entries.items())
            },
        }
        write_json_atomic(self.index_path, payload)
        lines = sorted({line for line in (e.ytdlp_line for e in self._entries.values()) if line})
        write_text_atomic(self.ytdlp_archive_path, "\n".join(lines) + ("\n" if lines else ""))

    # -- queries ------------------------------------------------------------

    def __contains__(self, source_id: str) -> bool:
        self.load()
        return source_id in self._entries

    def __iter__(self) -> Iterator[ArchiveEntry]:
        self.load()
        return iter(sorted(self._entries.values(), key=lambda entry: entry.source_id))

    def __len__(self) -> int:
        self.load()
        return len(self._entries)

    def get(self, source_id: str) -> ArchiveEntry | None:
        self.load()
        return self._entries.get(source_id)

    def find_by_url(self, url: str) -> ArchiveEntry | None:
        self.load()
        for entry in self._entries.values():
            if entry.url == url:
                return entry
        return None

    # -- mutation -----------------------------------------------------------

    def add(self, entry: ArchiveEntry, *, save: bool = True) -> ArchiveEntry:
        self.load()
        self._entries[entry.source_id] = entry
        if save:
            self.save()
        return entry

    def remove(self, source_id: str, *, save: bool = True) -> bool:
        self.load()
        self._removed.add(source_id)
        removed = self._entries.pop(source_id, None) is not None
        if removed and save:
            self.save()
        return removed


def source_folder_is_complete(folder: str | Path, media_file: str | None = None) -> bool:
    """On-disk completeness check used when the index is missing or stale."""
    from . import schema

    directory = Path(folder)
    if not (directory / schema.SOURCE_NOTE_NAME).is_file():
        return False
    candidates = (
        [directory / media_file]
        if media_file
        else [path for path in directory.glob(f"{schema.MEDIA_STEM}.*") if path.suffix != ".part"]
    )
    return any(path.is_file() and path.stat().st_size > 0 for path in candidates)


@dataclass
class RebuildResult:
    restored: list[ArchiveEntry] = field(default_factory=list)
    #: (path, reason) for a folder whose own files could not be read.
    unreadable: list[tuple[str, str]] = field(default_factory=list)


def rebuild_missing_entries(config, *, archive: "Archive | None" = None) -> RebuildResult:
    """Add an index entry for every staged folder that has none.

    The index is derived data - ``source.md`` is the truth - so this repairs
    what an interrupted or overwritten save lost. Nothing is downloaded and
    nothing is removed: a dangling entry (folder gone) is deliberate, it is
    what makes a re-download happen.
    """
    from . import schema
    from .notes import read_note
    from .pipeline import iter_source_dirs

    archive = archive if archive is not None else Archive(config.archive_dir, enabled=True)
    root = Path(config.output_root)
    result = RebuildResult()
    for folder in iter_source_dirs(root):
        try:
            front, _ = read_note(folder / schema.SOURCE_NOTE_NAME)
        except PipelineError as exc:
            result.unreadable.append((str(folder), exc.message))
            continue
        source_id = str(front.get("source_id") or "").strip()
        if not source_id:
            result.unreadable.append((str(folder), f"{schema.SOURCE_NOTE_NAME} has no source_id"))
            continue
        if archive.get(source_id) is not None:
            continue
        media_file = str(front.get("media_file") or "")
        if not source_folder_is_complete(folder, media_file or None):
            continue  # an unfinished folder is not something to remember

        extractor = ""
        video_id = str(front.get("provider_video_id") or "")
        metadata_path = folder / schema.METADATA_NAME
        if metadata_path.is_file():
            try:
                data = read_json(metadata_path)
            except PipelineError as exc:
                result.unreadable.append((str(metadata_path), exc.message))
                data = None
            if isinstance(data, dict):
                extractor = str(data.get("extractor") or "")
                video_id = video_id or str(data.get("id") or "")

        entry = ArchiveEntry(
            source_id=source_id,
            url=str(front.get("url") or ""),
            path=str(folder.relative_to(root)) if folder.is_relative_to(root) else str(folder),
            downloaded_at=str(front.get("downloaded_at") or ""),
            provider=str(front.get("provider") or ""),
            title=str(front.get("title") or ""),
            media_file=media_file,
            extractor=extractor,
            video_id=video_id,
        )
        archive.add(entry, save=False)
        result.restored.append(entry)

    if result.restored:
        archive.save()
    return result
