"""Orchestration: URL -> staged source folder.

One public entry point per use case:

* :func:`ingest_url`      - a single video
* :func:`ingest_playlist` - an explicitly requested playlist/collection
* :func:`ingest_many`     - a batch that keeps going when an item fails
* :func:`ingest_crawl`    - every video page a listing page leads to (``--crawl``)

Everything the pipeline writes lands under ``output_root`` in the layout

    <Provider>/<Subject>/<Title>/{video.*, source.md, transcript.md,
                                  metadata.json, integration.json}
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Sequence
from urllib.parse import urlparse

from . import crawl as crawl_mod
from . import manifest as manifest_mod
from . import metadata as metadata_mod
from . import notes, schema
from .archive import Archive, ArchiveEntry, source_folder_is_complete
from .config import Config
from .downloader import (
    DownloadRequest,
    Downloader,
    create_downloader,
    is_playlist,
    subtitle_request_from_config,
)
from .errors import (
    CrawlError,
    DownloadFailedError,
    FilesystemError,
    InvalidURLError,
    MetadataError,
    PipelineError,
    PlaylistGuardError,
)
from .fsio import write_json_atomic
from .logging_setup import error_event, get_logger, info_event, warn_event
from .naming import ensure_within, make_source_id, sanitize_component, short_hash
from .paths import ensure_directory
from .providers import resolve_provider
from .subjects import resolve_subject

STATUS_DOWNLOADED = "downloaded"
STATUS_SKIPPED = "skipped"
STATUS_FAILED = "failed"
STATUS_DRY_RUN = "dry-run"


def now_iso() -> str:
    """UTC ISO-8601 timestamp with an explicit offset."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# results
# ---------------------------------------------------------------------------

@dataclass
class IngestOutcome:
    status: str
    url: str
    source_id: str | None = None
    title: str | None = None
    path: Path | None = None
    message: str = ""
    error: PipelineError | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status in {STATUS_DOWNLOADED, STATUS_SKIPPED, STATUS_DRY_RUN}


@dataclass
class BatchSummary:
    outcomes: list[IngestOutcome] = field(default_factory=list)

    def add(self, outcome: IngestOutcome) -> IngestOutcome:
        self.outcomes.append(outcome)
        return outcome

    def count(self, status: str) -> int:
        return sum(1 for outcome in self.outcomes if outcome.status == status)

    @property
    def downloaded(self) -> int:
        return self.count(STATUS_DOWNLOADED)

    @property
    def skipped(self) -> int:
        return self.count(STATUS_SKIPPED)

    @property
    def failed(self) -> int:
        return self.count(STATUS_FAILED)

    @property
    def dry_run(self) -> int:
        return self.count(STATUS_DRY_RUN)

    @property
    def total(self) -> int:
        return len(self.outcomes)

    def render(self) -> str:
        lines = [
            f"Downloaded: {self.downloaded}",
            f"Skipped: {self.skipped}",
            f"Failed: {self.failed}",
        ]
        if self.dry_run:
            lines.append(f"Dry-run: {self.dry_run}")
        lines.append(f"Total: {self.total}")
        return "\n".join(lines)


@dataclass(frozen=True)
class UrlItem:
    url: str
    subject: str | None = None
    line_number: int | None = None


# ---------------------------------------------------------------------------
# input handling
# ---------------------------------------------------------------------------

def validate_url(url: str) -> str:
    """Accept http(s) URLs only; everything else is rejected before extraction."""
    text = str(url or "").strip()
    if not text:
        raise InvalidURLError("Empty URL.")
    parsed = urlparse(text)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise InvalidURLError(
            f"Only http(s) URLs are supported, got: {text}",
            hint="Pass the address of the video page, e.g. https://zanza.tv/...",
        )
    if not parsed.netloc:
        raise InvalidURLError(f"URL has no host: {text}")
    return text


def parse_url_list(path: str | Path) -> list[UrlItem]:
    """Read a batch file.

    One URL per line. ``#`` starts a comment. An optional ``| Subject`` suffix
    sets the subject for that one URL::

        https://zanza.tv/tortenelem/az-okori-athen | Történelem
        https://zanza.tv/fizika/newton-torvenyei   # subject guessed
    """
    target = Path(path)
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as exc:
        raise InvalidURLError(f"Cannot read URL list {target}: {exc}") from exc

    items: list[UrlItem] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        subject: str | None = None
        if "|" in line:
            line, _, subject_part = line.partition("|")
            subject = subject_part.split("#", 1)[0].strip() or None
            line = line.strip()
        if "#" in line and not line.startswith("http"):
            line = line.split("#", 1)[0].strip()
        elif " #" in line:
            line = line.split(" #", 1)[0].strip()
        if not line:
            continue
        items.append(UrlItem(url=line, subject=subject, line_number=number))
    if not items:
        raise InvalidURLError(f"No URLs found in {target}")
    return items


def looks_like_url_list(value: str) -> bool:
    """``download.py urls.txt`` vs ``download.py https://...`` (spec section 12)."""
    text = str(value).strip()
    if text.lower().startswith(("http://", "https://")):
        return False
    return Path(text).is_file()


# ---------------------------------------------------------------------------
# staging layout
# ---------------------------------------------------------------------------

def _existing_source_id(folder: Path) -> str | None:
    note = folder / schema.SOURCE_NOTE_NAME
    if not note.is_file():
        return None
    try:
        front, _ = notes.read_note(note)
    except PipelineError:
        return None
    value = front.get("source_id")
    return str(value) if value else None


def plan_target_dir(
    config: Config,
    *,
    provider_folder: str,
    subject: str | None,
    title: str,
    source_id: str,
) -> Path:
    """Build the staging folder path, resolving collisions deterministically."""
    root = config.output_root
    parts: list[str] = []
    if config.organization.provider_folder and provider_folder:
        parts.append(sanitize_component(provider_folder, fallback="Web"))
    if config.organization.subject_folder and subject:
        parts.append(sanitize_component(subject, fallback="Besorolatlan"))
    folder_name = sanitize_component(title, fallback=source_id)

    candidate = root.joinpath(*parts, folder_name)
    existing = _existing_source_id(candidate)
    if candidate.exists() and existing is not None and existing != source_id:
        # A different source already owns this name: append the stable id, so
        # the same video always lands in the same folder on every re-run.
        candidate = root.joinpath(*parts, sanitize_component(f"{folder_name} ({source_id})"))
    return ensure_within(root, candidate)


def iter_source_dirs(root: str | Path) -> Iterator[Path]:
    """Every staged source folder (a directory that contains source.md)."""
    base = Path(root)
    if not base.is_dir():
        return
    for note in sorted(base.rglob(schema.SOURCE_NOTE_NAME)):
        if note.is_file():
            yield note.parent


# ---------------------------------------------------------------------------
# single-URL ingestion
# ---------------------------------------------------------------------------

def _write_transcript_placeholder(
    folder: Path,
    *,
    source_id: str,
    title: str,
    media_file: str,
    language: str | None,
    config: Config,
    logger: logging.Logger,
) -> None:
    """Create transcript.md, but never overwrite finished transcript work."""
    path = folder / schema.TRANSCRIPT_NOTE_NAME
    if path.exists():
        try:
            front, _ = notes.read_note(path)
            status = str(front.get("transcript_status", "")).strip()
        except PipelineError:
            status = ""
        if status and status != "pending":
            warn_event(
                logger,
                f"Keeping the existing transcript ({status}); it was not overwritten.",
                event_name="transcript.preserved",
                path=str(path),
                transcript_status=status,
            )
            return
    values = notes.build_transcript_values(
        source_id=source_id,
        title=title,
        media_file=media_file,
        language=language,
        transcript_status=config.transcript.status,
    )
    notes.write_transcript_note(path, values, config.templates_dir)


def _maybe_transcribe(media_path: Path, *, config: Config, logger: logging.Logger) -> None:
    """Transcribe right after the download when ``transcript.enabled`` is set.

    A failure here is a warning, never a failed download: the media, the
    metadata and the source note are already on disk and correct, and the
    transcript stays ``pending`` so ``transcribe.py --pending`` can retry it
    later.
    """
    if not config.transcript.enabled:
        return
    from .transcription.registry import select_backend  # noqa: PLC0415 - optional dependency
    from .transcription.writer import write_transcript  # noqa: PLC0415

    folder = media_path.parent
    try:
        backend = select_backend(config, config.transcript.backend, folder)
        logger.info("    transcribing with '%s' (language: %s)",
                    backend.name, config.transcript.language or "auto-detect")
        result = backend.transcribe(media_path, language=config.transcript.language, folder=folder)
        write_transcript(folder, result, config=config, logger=logger)
    except PipelineError as exc:
        warn_event(
            logger,
            f"    transcript not created: {exc.message}",
            event_name="transcript.failed",
            folder=str(folder),
        )
        if exc.hint:
            logger.warning("      -> %s", exc.hint)
    except Exception as exc:  # noqa: BLE001 - a broken ASR backend must not lose the download
        warn_event(
            logger,
            f"    transcript not created ({type(exc).__name__}): {exc}",
            event_name="transcript.failed",
            folder=str(folder),
        )


def _log_quality(logger: logging.Logger, info: dict[str, Any], config: Config, source_id: str) -> None:
    """Record what resolution was really obtained (spec section 5)."""
    resolution = metadata_mod.resolution_of(info)
    height = info.get("height")
    best_progressive = metadata_mod.best_progressive_height(info)
    best_available = metadata_mod.best_available_height(info)
    merged = metadata_mod.was_merged(info)
    info_event(
        logger,
        f"    quality: {resolution or 'unknown'}"
        + (" (merged video+audio)" if merged else "")
        + (f", best offered: {best_available}p" if best_available else ""),
        event_name="download.quality",
        source_id=source_id,
        resolution=resolution,
        height=height,
        fps=info.get("fps"),
        best_progressive_height=best_progressive,
        best_available_height=best_available,
        max_height_config=config.video.max_height,
        ffmpeg_used=merged,
    )
    if not isinstance(height, int) or height >= config.video.max_height:
        return
    if isinstance(best_available, int) and height >= best_available:
        # Not a limitation of this pipeline: the platform has nothing better.
        info_event(
            logger,
            f"    {height}p is the highest resolution this video is published in.",
            event_name="download.quality_source_limited",
            source_id=source_id,
            height=height,
        )
        return
    reason = (
        "video.allow_merge is false, so only single-file formats were considered"
        if not config.video.allow_merge
        else "higher formats exist but could not be used - check FFmpeg and the JS "
             "runtime with:  python3 scripts/download.py --check"
    )
    warn_event(
        logger,
        f"    {height}p is below both the {config.video.max_height}p target and the "
        f"{best_available}p this video offers - {reason}.",
        event_name="download.quality_capped",
        source_id=source_id,
        height=height,
        best_available_height=best_available,
        max_height_config=config.video.max_height,
    )


def ingest_url(
    url: str,
    *,
    config: Config,
    downloader: Downloader | None = None,
    archive: Archive | None = None,
    logger: logging.Logger | None = None,
    subject: str | None = None,
    subject_hint: str | None = None,
    language: str | None = None,
    force: bool = False,
    dry_run: bool = False,
    allow_playlist: bool = False,
    page_url: str | None = None,
    page_title: str | None = None,
    user_agent: str | None = None,
) -> IngestOutcome:
    """Download and stage one video. Never raises for expected failures.

    Manifold-OS 2.0 (84. döntés, javasolt kiegészítés): ``page_url``/``page_title`` stage a *direct media file*
    (``url``) found on a web page as that page's source - the page is the source link (source.md ``url``, the
    archive entry, the provider), its title names the folder, and the source id is a hash of the media URL (a file
    name like ``lecture1-1080p`` is not unique across courses). ``user_agent`` replaces yt-dlp's browser-like
    User-Agent with the crawler's honest one for this request (probe and download).
    """
    logger = logger or get_logger()
    url = validate_url(url)
    record_url = validate_url(page_url) if page_url else url
    downloader = downloader or create_downloader(config)
    archive = archive if archive is not None else Archive(config.archive_dir, enabled=config.archive.enabled)
    ua_kw = {"user_agent": user_agent} if user_agent else {}

    try:
        info = downloader.probe(url, allow_playlist=allow_playlist, **ua_kw)
    except PipelineError as exc:
        error_event(logger, f"FAILED {url}: {exc.message}", event_name="probe.failed", url=url)
        return IngestOutcome(STATUS_FAILED, record_url, message=exc.message, error=exc)
    if page_url:
        # the file name (``lecture1-1080p``) is no identity across courses: the id is a hash of the media URL
        info = {**info, "id": f"u{short_hash(url)}", "original_id": info.get("id")}
        if page_title and page_title.strip():
            info["title"] = page_title.strip()

    if is_playlist(info) and not allow_playlist:
        exc = PlaylistGuardError(
            f"This URL is a playlist/collection ({len(info.get('entries') or [])} items): {url}",
            hint="Re-run with --playlist to download it, or pass the URL of a single video.",
        )
        error_event(logger, f"FAILED {url}: {exc.message}", event_name="playlist.guard", url=url)
        return IngestOutcome(STATUS_FAILED, url, message=exc.message, error=exc)

    provider = resolve_provider(record_url, info, config)
    video_id = info.get("id")
    source_id = make_source_id(provider.slug, str(video_id) if video_id else None, info.get("webpage_url") or url)
    title = str(info.get("title") or "").strip() or source_id
    subject_resolution = resolve_subject(record_url, info, config, explicit=subject, hint=subject_hint)
    resolved_language = language or info.get("language") or config.metadata.default_language

    target_dir = plan_target_dir(
        config,
        provider_folder=provider.folder_name,
        subject=subject_resolution.name,
        title=title,
        source_id=source_id,
    )
    relative_dir = _relative_to_root(target_dir, config.output_root)

    # --- duplicate protection (spec section 11) ----------------------------
    known = archive.get(source_id)
    on_disk = source_folder_is_complete(target_dir)
    if not force and (on_disk or (known and source_folder_is_complete(config.output_root / known.path))):
        existing_path = target_dir if on_disk else config.output_root / (known.path if known else "")
        info_event(
            logger,
            f"SKIPPED - already downloaded: {title}",
            event_name="ingest.skipped",
            url=url,
            source_id=source_id,
            path=str(existing_path),
        )
        return IngestOutcome(
            STATUS_SKIPPED, record_url, source_id=source_id, title=title, path=existing_path,
            message="already downloaded",
        )
    if known and not on_disk:
        warn_event(
            logger,
            f"    archive knows {source_id} but the folder is gone - downloading again.",
            event_name="archive.stale", source_id=source_id, path=known.path,
        )

    if dry_run:
        best = metadata_mod.best_progressive_height(info)
        reachable = metadata_mod.best_available_height(info) if config.video.allow_merge else best
        message = (
            f"would download -> {relative_dir}  "
            f"[format {config.video.effective_format_selector}"
            + (f", best reachable {reachable}p" if reachable else "")
            + (f" (pre-muxed only: {best}p)" if best and reachable and best < reachable else "")
            + "]"
        )
        info_event(
            logger, f"DRY-RUN {title}: {message}", event_name="ingest.dry_run",
            url=url, source_id=source_id, path=str(target_dir),
            best_progressive_height=best, subject=subject_resolution.name,
        )
        return IngestOutcome(
            STATUS_DRY_RUN, record_url, source_id=source_id, title=title, path=target_dir,
            message=message,
            details={"subject": subject_resolution.name, "best_progressive_height": best},
        )

    # --- download ----------------------------------------------------------
    info_event(
        logger, f"Downloading: {title}", event_name="download.start",
        url=url, source_id=source_id, path=str(target_dir), subject=subject_resolution.name,
    )
    try:
        ensure_directory(target_dir)
        request = DownloadRequest(
            url=url,
            target_dir=target_dir,
            format_selector=config.video.effective_format_selector,
            stem=schema.MEDIA_STEM,
            resume=config.download.resume,
            overwrite=force,
            retries=config.download.retries,
            fragment_retries=config.download.fragment_retries,
            socket_timeout=config.download.socket_timeout,
            ratelimit=config.download.ratelimit,
            subtitles=subtitle_request_from_config(config),
            user_agent=user_agent,
        )
        result = downloader.download(request)
        if result.media_path is None or not Path(result.media_path).is_file():
            raise DownloadFailedError(
                f"yt-dlp reported success but no media file was written into {target_dir}",
                hint="Check the log for the format that was chosen, then try "
                     "'python3 scripts/inspect.py URL --formats'.",
            )
        media_path = Path(result.media_path)
        if media_path.stat().st_size == 0:
            raise DownloadFailedError(f"The downloaded file is empty: {media_path}")

        merged_info = {**info, **result.info}
        if page_url:  # the page's identity and title, not the generic extractor's file name
            merged_info.update({key: info[key] for key in ("id", "original_id", "title") if key in info})
        written = _write_source_files(
            folder=target_dir,
            config=config,
            info=merged_info,
            url=record_url,
            source_id=source_id,
            title=title,
            provider_name=provider.display_name,
            provider_video_id=str(video_id) if video_id else None,
            media_url=str(merged_info.get("webpage_url") or "") or None,
            subject=subject_resolution.name,
            subject_source=subject_resolution.source,
            language=resolved_language,
            media_file=media_path.name,
            downloader=downloader,
            logger=logger,
        )
        _log_quality(logger, merged_info, config, source_id)

        archive.add(
            ArchiveEntry(
                source_id=source_id,
                url=record_url,
                path=str(relative_dir),
                downloaded_at=written["downloaded_at"],
                provider=provider.display_name,
                title=title,
                media_file=media_path.name,
                extractor=str(merged_info.get("extractor_key") or merged_info.get("extractor") or provider.extractor),
                video_id=str(video_id or ""),
            )
        )
        info_event(
            logger, f"OK: {title} -> {relative_dir}", event_name="ingest.ok",
            url=url, source_id=source_id, path=str(target_dir), media_file=media_path.name,
        )
        return IngestOutcome(
            STATUS_DOWNLOADED, record_url, source_id=source_id, title=title, path=target_dir,
            message=str(relative_dir), details={"media_file": media_path.name},
        )
    except PipelineError as exc:
        error_event(
            logger, f"FAILED {title or url}: {exc.message}", event_name="ingest.failed",
            url=url, source_id=source_id, error_type=type(exc).__name__,
        )
        if exc.hint:
            logger.warning("  -> %s", exc.hint)
        return IngestOutcome(STATUS_FAILED, record_url, source_id=source_id, title=title,
                             message=exc.message, error=exc)
    except OSError as exc:
        wrapped = FilesystemError(f"Filesystem error while staging {title}: {exc}")
        error_event(logger, f"FAILED {title}: {wrapped.message}", event_name="ingest.failed",
                    url=url, source_id=source_id, error_type="FilesystemError")
        return IngestOutcome(STATUS_FAILED, record_url, source_id=source_id, title=title,
                             message=wrapped.message, error=wrapped)


def _relative_to_root(path: Path, root: Path) -> Path:
    try:
        return Path(path).relative_to(root)
    except ValueError:  # pragma: no cover - only when output_root moved mid-run
        return Path(path)


def _write_source_files(
    *,
    folder: Path,
    config: Config,
    info: dict[str, Any],
    url: str,
    source_id: str,
    title: str,
    provider_name: str,
    provider_video_id: str | None,
    media_url: str | None,
    subject: str | None,
    subject_source: str,
    language: str | None,
    media_file: str,
    downloader: Downloader,
    logger: logging.Logger,
) -> dict[str, Any]:
    """Write metadata.json, source.md, transcript.md and integration.json."""
    downloaded_at = now_iso()

    if config.metadata.save_json:
        curated = metadata_mod.curate(
            info,
            page_url=url,
            source_id=source_id,
            downloaded_at=downloaded_at,
            media_file=media_file,
            format_selector=config.video.effective_format_selector,
            ytdlp_version=downloader.version,
            schema_version=schema.SCHEMA_VERSION,
        )
        write_json_atomic(folder / schema.METADATA_NAME, curated)
    if config.metadata.save_raw_info:
        write_json_atomic(folder / schema.RAW_METADATA_NAME, info)

    source_values = notes.build_source_values(
        source_id=source_id,
        title=title,
        provider=provider_name,
        url=url,
        media_file=media_file,
        downloaded_at=downloaded_at,
        subject=subject,
        language=language,
        duration_seconds=info.get("duration"),
        resolution=metadata_mod.resolution_of(info),
        uploader=info.get("uploader"),
        upload_date=info.get("upload_date"),
        provider_video_id=provider_video_id,
        media_url=media_url,
        pipeline_status="downloaded",
    )
    notes.write_source_note(folder / schema.SOURCE_NOTE_NAME, source_values, config.templates_dir)

    _write_transcript_placeholder(
        folder,
        source_id=source_id,
        title=title,
        media_file=media_file,
        language=language,
        config=config,
        logger=logger,
    )
    _maybe_transcribe(folder / media_file, config=config, logger=logger)

    transcript_status = config.transcript.status
    transcript_path = folder / schema.TRANSCRIPT_NOTE_NAME
    if transcript_path.is_file():
        try:
            front, _ = notes.read_note(transcript_path)
            transcript_status = str(front.get("transcript_status") or transcript_status)
        except PipelineError:  # pragma: no cover - malformed manual edit
            pass

    manifest_path = folder / schema.MANIFEST_NAME
    nn_anchorable: bool | None = None
    integration_status = "pending"
    if manifest_path.is_file():
        # Preserve decisions a human (or the integration step) already made.
        try:
            previous = manifest_mod.read_manifest(manifest_path)
            nn_anchorable = previous.get("nn_anchorable", None)
            integration_status = str(previous.get("integration_status") or "pending")
            if integration_status not in schema.INTEGRATION_STATUSES:
                integration_status = "pending"
        except (ValueError, PipelineError):  # pragma: no cover - malformed manual edit
            pass
    manifest_mod.write_manifest(
        manifest_path,
        manifest_mod.build_manifest(
            source_id=source_id,
            title=title,
            provider=provider_name,
            url=url,
            media_file=media_file,
            language=language,
            duration_seconds=info.get("duration"),
            suggested_subject=subject,
            subject_source=subject_source,
            transcript_status=transcript_status if transcript_status in schema.TRANSCRIPT_STATUSES else "pending",
            integration_status=integration_status,
            nn_anchorable=nn_anchorable if isinstance(nn_anchorable, bool) else None,
        ),
    )
    return {"downloaded_at": downloaded_at}


# ---------------------------------------------------------------------------
# batch and playlist
# ---------------------------------------------------------------------------

def ingest_many(
    items: Sequence[UrlItem] | Iterable[str],
    *,
    config: Config,
    downloader: Downloader | None = None,
    archive: Archive | None = None,
    logger: logging.Logger | None = None,
    subject: str | None = None,
    force: bool = False,
    dry_run: bool = False,
    pause_seconds: float = 0.0,
    sleep: Callable[[float], None] = time.sleep,
) -> BatchSummary:
    """Process many URLs, continuing after failures (spec section 12).

    ``pause_seconds`` spaces the items out; a crawl passes the site's delay so
    the downloads keep the pace the crawl itself kept.
    """
    logger = logger or get_logger()
    downloader = downloader or create_downloader(config)
    archive = archive if archive is not None else Archive(config.archive_dir, enabled=config.archive.enabled)

    normalised: list[UrlItem] = [
        item if isinstance(item, UrlItem) else UrlItem(url=str(item)) for item in items
    ]
    summary = BatchSummary()
    total = len(normalised)
    for index, item in enumerate(normalised, start=1):
        if index > 1 and pause_seconds > 0:
            sleep(pause_seconds)
        logger.info("[%d/%d] %s", index, total, item.url)
        try:
            outcome = ingest_url(
                item.url,
                config=config,
                downloader=downloader,
                archive=archive,
                logger=logger,
                subject=subject,
                subject_hint=item.subject,
                force=force,
                dry_run=dry_run,
            )
        except PipelineError as exc:  # pragma: no cover - defensive
            outcome = IngestOutcome(STATUS_FAILED, item.url, message=exc.message, error=exc)
            error_event(logger, f"FAILED {item.url}: {exc.message}", event_name="ingest.failed", url=item.url)
        summary.add(outcome)
    return summary


def ingest_playlist(
    url: str,
    *,
    config: Config,
    downloader: Downloader | None = None,
    archive: Archive | None = None,
    logger: logging.Logger | None = None,
    subject: str | None = None,
    force: bool = False,
    dry_run: bool = False,
    max_items: int | None = None,
) -> BatchSummary:
    """Expand a playlist and ingest its entries (spec section 13)."""
    logger = logger or get_logger()
    downloader = downloader or create_downloader(config)
    url = validate_url(url)
    limit = max_items if max_items is not None else config.playlist.max_items

    info = downloader.probe(url, allow_playlist=True, flat=True)
    entries = [entry for entry in (info.get("entries") or []) if isinstance(entry, dict)]
    if not entries:
        if is_playlist(info):
            raise MetadataError(f"The playlist is empty or could not be expanded: {url}")
        # A single video was passed to --playlist: treat it as a one-item batch.
        entries = [info]

    if len(entries) > limit:
        raise PlaylistGuardError(
            f"The playlist has {len(entries)} items, above the limit of {limit}.",
            hint=f"Raise it for this run with --max-items {len(entries)}, "
                 "or change playlist.max_items in config/config.yaml.",
        )

    items: list[UrlItem] = []
    for entry in entries:
        entry_url = entry.get("webpage_url") or entry.get("url") or entry.get("original_url")
        if not entry_url:
            warn_event(logger, "    playlist entry without a URL was skipped",
                       event_name="playlist.entry_skipped", playlist=url)
            continue
        items.append(UrlItem(url=str(entry_url)))

    playlist_title = info.get("title") or url
    info_event(
        logger, f"Playlist: {playlist_title} ({len(items)} items)",
        event_name="playlist.start", url=url, count=len(items),
    )
    return ingest_many(
        items, config=config, downloader=downloader, archive=archive, logger=logger,
        subject=subject, force=force, dry_run=dry_run,
    )


def ingest_crawl(
    url: str,
    *,
    config: Config,
    downloader: Downloader | None = None,
    archive: Archive | None = None,
    logger: logging.Logger | None = None,
    subject: str | None = None,
    subject_hint: str | None = None,
    force: bool = False,
    dry_run: bool = False,
    max_items: int | None = None,
    fetch: crawl_mod.Fetcher | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> BatchSummary:
    """Stage every video page a listing page leads to (``download.py --crawl``).

    Discovery is :func:`msp.crawl.crawl`; everything after it is the ordinary
    batch. A page whose URL is already staged (archive entry plus a complete
    folder) is neither fetched nor probed again, so re-running the same crawl
    only picks up what is new. ``--force`` re-downloads everything.
    """
    logger = logger or get_logger()
    downloader = downloader or create_downloader(config)
    archive = archive if archive is not None else Archive(config.archive_dir, enabled=config.archive.enabled)
    url = validate_url(url)

    def staged_entry(candidate: str) -> ArchiveEntry | None:
        if force:
            return None
        entry = archive.find_by_url(candidate)
        if entry and source_folder_is_complete(config.output_root / entry.path):
            return entry
        return None

    result = crawl_mod.crawl(
        url, config=config, fetch=fetch, sleep=sleep, logger=logger,
        is_known=lambda candidate: staged_entry(candidate) is not None,
        max_items=max_items,
    )
    if not result.video_urls:
        raise CrawlError(
            f"No video page found under {url}",
            hint="Pass a subject or topic page whose links lead to the videos. Pages more than "
                 f"crawl.max_depth ({config.crawl.max_depth}) links below it are not reached.",
        )

    summary = BatchSummary()
    todo: list[UrlItem] = []
    for video_url in result.video_urls:
        entry = staged_entry(video_url)
        if entry is None:
            todo.append(UrlItem(url=video_url, subject=subject_hint))
            continue
        info_event(
            logger, f"SKIPPED - already downloaded: {entry.title or video_url}",
            event_name="ingest.skipped", url=video_url, source_id=entry.source_id, path=entry.path,
        )
        summary.add(IngestOutcome(
            STATUS_SKIPPED, video_url, source_id=entry.source_id, title=entry.title,
            path=config.output_root / entry.path, message="already downloaded",
        ))

    info_event(
        logger, f"Crawl: {len(todo)} to stage, {summary.skipped} already staged",
        event_name="crawl.batch", url=url, todo=len(todo), skipped=summary.skipped,
    )
    if todo:
        batch = ingest_many(
            todo, config=config, downloader=downloader, archive=archive, logger=logger,
            subject=subject, force=force, dry_run=dry_run,
            pause_seconds=result.delay_seconds, sleep=sleep,
        )
        summary.outcomes.extend(batch.outcomes)
    return summary
