"""yt-dlp adapter.

The rest of the pipeline talks to :class:`Downloader`, never to yt-dlp
directly, so the extractor can be swapped or mocked (the test-suite uses a fake
downloader and never touches the network).

Two real backends exist:

``YtDlpPythonDownloader``
    Preferred. Uses the ``yt_dlp`` Python API, which gives structured info
    dicts and precise error types.
``YtDlpCliDownloader``
    Fallback for setups where only the ``yt-dlp`` binary is present.

**Quality.** Resolutions above ~360p exist on most platforms only as separate
video and audio streams, so the pipeline downloads both and lets FFmpeg mux
them into one file (``video.allow_merge``). Two dependencies decide what is
reachable: FFmpeg for the muxing, and a JavaScript runtime for YouTube's
player challenges - without the latter YouTube offers the single 360p
pre-muxed format only. ``download.py --check`` reports both.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .config import Config
from .errors import (
    CertificateError,
    DependencyError,
    DownloadFailedError,
    InterruptedDownloadError,
    MetadataError,
    NetworkError,
    NoProgressiveFormatError,
    UnsupportedURLError,
    VideoUnavailableError,
)
from .logging_setup import get_logger

YTDLP_INSTALL_HINT = (
    "Install it into the project environment:\n"
    "     python3 -m venv .venv && source .venv/bin/activate && pip install -e .\n"
    "   or on its own:  pip install yt-dlp\n"
    "   or point config/config.yaml -> ytdlp.local_source_path at a yt-dlp source checkout."
)

CERTIFICATE_HINT = (
    "TLS certificates are missing for this Python. On a python.org macOS build run\n"
    '     open "/Applications/Python 3.x/Install Certificates.command"\n'
    "   or install the certificate bundle:  pip install certifi"
)


# ---------------------------------------------------------------------------
# data objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SubtitleRequest:
    enabled: bool = False
    languages: tuple[str, ...] = ()
    formats: str = "vtt/srt/best"
    include_auto: bool = False


@dataclass(frozen=True)
class DownloadRequest:
    url: str
    target_dir: Path
    format_selector: str
    stem: str = "video"
    resume: bool = True
    overwrite: bool = False
    retries: int = 5
    fragment_retries: int = 5
    socket_timeout: int = 30
    ratelimit: str | None = None
    subtitles: SubtitleRequest = field(default_factory=SubtitleRequest)
    # Manifold-OS 2.0 (84. döntés, javasolt kiegészítés): an honest User-Agent instead of yt-dlp's browser-like default
    user_agent: str | None = None


@dataclass
class DownloadResult:
    media_path: Path | None
    info: dict[str, Any]
    subtitle_files: list[Path] = field(default_factory=list)


@dataclass(frozen=True)
class DependencyReport:
    ytdlp_available: bool
    ytdlp_version: str | None
    backend: str
    ffmpeg_present: bool
    yaml_backend: str
    ffmpeg_path: str | None = None
    js_runtime: str | None = None

    def render(self) -> str:
        lines = [
            f"yt-dlp        : {'yes' if self.ytdlp_available else 'MISSING'}"
            + (f" ({self.ytdlp_version}, {self.backend})" if self.ytdlp_available else ""),
            f"YAML reader   : {self.yaml_backend}",
            f"FFmpeg        : {self.ffmpeg_path if self.ffmpeg_present else 'MISSING (needed for 1080p merging)'}",
            f"JS runtime    : {self.js_runtime or 'MISSING (YouTube then offers 360p only)'}",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# error classification
# ---------------------------------------------------------------------------

_ERROR_PATTERNS: tuple[tuple[str, Callable[[str], Exception]], ...] = (
    (r"certificate verify failed|CERTIFICATE_VERIFY_FAILED|SSL: ",
     lambda msg: CertificateError(f"TLS certificate verification failed: {msg}", hint=CERTIFICATE_HINT)),
    (r"Unsupported URL",
     lambda msg: UnsupportedURLError(
         f"yt-dlp has no extractor for this URL: {msg}",
         hint="Check the URL, or see 'yt-dlp --list-extractors' for supported sites.")),
    (r"Private video|is private|Sign in to confirm your age|members-only|only available to Music Premium|Join this channel",
     lambda msg: VideoUnavailableError(
         f"The video is not publicly accessible: {msg}",
         hint="This pipeline never bypasses access restrictions (spec section 24). "
              "Download it only where you have the right to.")),
    (r"[Vv]ideo unavailable|is unavailable|has been removed|been terminated|no longer available|"
     r"This video does not exist|HTTP Error 404|Unable to find video|not found",
     lambda msg: VideoUnavailableError(f"The video is gone or unavailable: {msg}")),
    (r"blocked it (in|on) your country|geo restricted|not available from your location|GeoRestricted",
     lambda msg: VideoUnavailableError(
         f"The video is geo-restricted: {msg}",
         hint="No circumvention is implemented on purpose (spec section 24).")),
    (r"Requested format is not available|You have requested merging|ffmpeg is not installed|requested format not available",
     lambda msg: NoProgressiveFormatError(
         f"No single-file (video+audio) format matched the request: {msg}",
         hint="Inspect what the site really offers with:  "
              "python3 scripts/inspect.py URL --formats\n"
              "     Check that FFmpeg and a JS runtime are present (download.py --check); "
              "without them only the 360p pre-muxed format is reachable.")),
    (r"HTTP Error 429|Too Many Requests",
     lambda msg: NetworkError(f"Rate limited by the provider: {msg}",
                              hint="Wait a few minutes, or set download.ratelimit in config/config.yaml.")),
    (r"Unable to download webpage|urlopen error|Temporary failure in name resolution|"
     r"timed out|Connection reset|Network is unreachable|getaddrinfo failed|Remote end closed",
     lambda msg: NetworkError(f"Network error while contacting the provider: {msg}",
                              hint="Check the connection and try again; the pipeline can resume.")),
    (r"Unable to extract|Failed to parse JSON|Unable to recognize",
     lambda msg: MetadataError(f"The provider page could not be parsed: {msg}",
                               hint="The site may have changed. Try updating yt-dlp:  pip install -U yt-dlp")),
)


def classify_error(message: str) -> Exception:
    """Map a yt-dlp error message onto a typed pipeline error."""
    text = str(message).strip()
    for pattern, factory in _ERROR_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return factory(text)
    return DownloadFailedError(f"Download failed: {text}")


# ---------------------------------------------------------------------------
# yt-dlp loading
# ---------------------------------------------------------------------------

def load_ytdlp_module(config: Config | None = None):
    """Import ``yt_dlp``, honouring ``ytdlp.local_source_path``."""
    local_path = config.ytdlp.local_source_path if config else None
    if local_path:
        resolved = Path(local_path).expanduser()
        if not resolved.is_dir():
            raise DependencyError(
                f"ytdlp.local_source_path points to a missing directory: {resolved}",
                hint="Fix the path in config/config.yaml or set it to null.",
            )
        if str(resolved) not in sys.path:
            sys.path.insert(0, str(resolved))
    try:
        import yt_dlp  # noqa: PLC0415 - deliberately late/optional import
    except ImportError as exc:
        raise DependencyError("yt-dlp is not installed (module 'yt_dlp' not importable).",
                              hint=YTDLP_INSTALL_HINT) from exc
    return yt_dlp


def find_ytdlp_binary(config: Config | None = None) -> str | None:
    """The yt-dlp CLI binary, **only** when ``ytdlp.binary`` names an existing file. **2.0 port (Javító 3, A3-18): no PATH lookup**: a
    ``yt-dlp`` found on PATH is not the pinned, hash-locked one (it can self-update); the pinned module in ``var/venv`` is the backend."""
    configured = config.ytdlp.binary if config else None
    if configured:
        path = Path(configured).expanduser()
        if path.is_file():
            return str(path)
        raise DependencyError(f"ytdlp.binary is set but not an existing file: {configured}",
                              hint="Fix the path in config/config.yaml or set it to null.")
    return None


def _explicit_tool(configured: str | None, label: str) -> str | None:
    """A tool path that was handed in explicitly (never searched for): ``None`` for ``auto``/empty, the path when it is an executable
    file, else a :class:`DependencyError`."""
    if not configured or configured == "auto":
        return None
    candidate = Path(configured).expanduser()
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return str(candidate)
    raise DependencyError(f"{label} is set but is not an executable file: {configured}",
                          hint="Run  bin/mos runtime fetch ffmpeg  (the pinned build goes to runtime/ffmpeg/).")


def resolve_ffmpeg(config: Config | None = None) -> str | None:
    """The ffmpeg binary: **only** the path in ``ytdlp.ffmpeg_location``. **2.0 port (C20a, Javító 3 A3-17).**

    Manifold-OS hands the pinned, hash-verified ``[utak] ffmpeg`` in (``modulok/ytdlp/lanc.py``); there is deliberately **no**
    ``MOS_FFMPEG`` override, **no** search of ``<os>/runtime`` (the checked and the executed binary must be the same one), **no PATH and no
    imageio-ffmpeg fallback** (a binary in the home folder or a Save4K symlink is forbidden in Manifold-OS). ``auto`` means: none.

    FFmpeg is what makes >360p possible at all: everything above the one
    pre-muxed format exists only as separate video and audio streams that have
    to be muxed after downloading.
    """
    return _explicit_tool(config.ytdlp.ffmpeg_location if config else None, "ytdlp.ffmpeg_location")


def _js_runtime_path(name: str, config: Config | None = None) -> str | None:
    """Path of a JavaScript runtime: only the pinned node handed in as ``ytdlp.node_location`` (Manifold-OS: ``[utak] node``). **No env
    override and no PATH lookup** (Javító 3, A3-18); deno is not pinned, so it never resolves."""
    if name.lower() != "node" or config is None:
        return None
    return _explicit_tool(config.ytdlp.node_location, "ytdlp.node_location")


def resolve_js_runtime(config: Config | None = None) -> str | None:
    """First usable (pinned) JavaScript runtime for YouTube's player challenges, or ``None``."""
    names = config.ytdlp.js_runtimes if config else ["deno", "node"]
    for name in names:
        if _js_runtime_path(name, config):
            return name
    return None


def check_dependencies(config: Config | None = None) -> DependencyReport:
    """Startup check (spec section 2): is yt-dlp there, and in which form?"""
    from .yamlio import backend_name

    version: str | None = None
    backend = "none"
    available = False
    try:
        module = load_ytdlp_module(config)
        version = getattr(module.version, "__version__", None)
        backend = "python-module"
        available = True
    except DependencyError:
        binary = find_ytdlp_binary(config)
        if binary:
            available = True
            backend = f"cli ({binary})"
            try:
                proc = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=20)
                version = proc.stdout.strip() or None
            except (OSError, subprocess.SubprocessError):
                version = None
    try:
        ffmpeg_path = resolve_ffmpeg(config)
    except DependencyError:
        ffmpeg_path = None
    return DependencyReport(
        ytdlp_available=available,
        ytdlp_version=version,
        backend=backend,
        ffmpeg_present=ffmpeg_path is not None,
        ffmpeg_path=ffmpeg_path,
        js_runtime=resolve_js_runtime(config),
        yaml_backend=backend_name(),
    )


def require_ytdlp(config: Config | None = None) -> DependencyReport:
    report = check_dependencies(config)
    if not report.ytdlp_available:
        raise DependencyError("yt-dlp is required but was not found.", hint=YTDLP_INSTALL_HINT)
    return report


# ---------------------------------------------------------------------------
# backends
# ---------------------------------------------------------------------------

class Downloader:
    """Interface implemented by every backend (and by the test fake)."""

    name = "abstract"

    def probe(self, url: str, *, allow_playlist: bool = False, flat: bool = False,
              user_agent: str | None = None) -> dict[str, Any]:
        raise NotImplementedError

    def download(self, request: DownloadRequest) -> DownloadResult:
        raise NotImplementedError

    @property
    def version(self) -> str | None:
        return None


class _YtDlpLoggerBridge:
    """Routes yt-dlp's own messages into the pipeline log."""

    def __init__(self, logger) -> None:
        self._logger = logger

    def debug(self, message: str) -> None:
        text = str(message)
        if text.startswith("[debug] "):
            self._logger.debug(text[8:])
        else:
            self._logger.debug(text)

    def info(self, message: str) -> None:  # pragma: no cover - yt-dlp rarely calls this
        self._logger.debug(str(message))

    def warning(self, message: str) -> None:
        text = str(message).replace("WARNING: ", "")
        # yt-dlp retries loudly; the final outcome is reported either way.
        if "Retrying" in text or "Giving up after" in text:
            self._logger.debug("yt-dlp: %s", text)
        else:
            self._logger.warning("yt-dlp: %s", text)

    def error(self, message: str) -> None:
        self._logger.debug("yt-dlp error: %s", message)


class YtDlpPythonDownloader(Downloader):
    """Backend using the yt_dlp Python API."""

    name = "python-module"

    def __init__(self, config: Config, *, progress: bool = True) -> None:
        self._config = config
        self._module = load_ytdlp_module(config)
        self._logger = get_logger("ytdlp")
        self._ffmpeg = resolve_ffmpeg(config) if config.video.allow_merge else None
        self._progress = progress and sys.stderr.isatty()
        self._last_progress = 0.0

    @property
    def version(self) -> str | None:
        return getattr(self._module.version, "__version__", None)

    # -- option construction ------------------------------------------------

    def _base_options(self) -> dict[str, Any]:
        return {
            "quiet": True,
            "no_warnings": False,
            "noprogress": True,
            "logger": _YtDlpLoggerBridge(self._logger),
            "ignoreerrors": False,
            "no_color": True,
            # Never weaken transport security, never bypass access controls.
            "nocheckcertificate": False,
            "postprocessors": [],
            "socket_timeout": self._config.download.socket_timeout,
            "retries": self._config.download.retries,
            "extractor_retries": 2,
            # Passed through from config (ytdlp.extractor_args). Needed for
            # sites that only serve their videos through an embedded player.
            "extractor_args": {
                extractor: dict(args)
                for extractor, args in self._config.ytdlp.extractor_args.items()
            },
            # Without a JS runtime YouTube hands out only the 360p pre-muxed
            # format; yt-dlp enables deno by default, node must be named.
            # Only pinned runtimes; an empty dict also switches off yt-dlp's own default (deno from PATH).
            "js_runtimes": {
                name.lower(): {"path": path}
                for name in self._config.ytdlp.js_runtimes
                if (path := _js_runtime_path(name, self._config))
            },
            **({"ffmpeg_location": self._ffmpeg} if self._ffmpeg else {}),
        }

    def _progress_hook(self, status: dict[str, Any]) -> None:
        state = status.get("status")
        if state == "downloading" and self._progress:
            now = time.monotonic()
            if now - self._last_progress < 1.0:
                return
            self._last_progress = now
            total = status.get("total_bytes") or status.get("total_bytes_estimate")
            done = status.get("downloaded_bytes") or 0
            percent = f"{done * 100 / total:5.1f}%" if total else "  ?  "
            speed = status.get("speed")
            speed_text = f"{speed / 1024 / 1024:.1f} MiB/s" if speed else "-"
            sys.stderr.write(f"\r    downloading {percent}  {speed_text}   ")
            sys.stderr.flush()
        elif state in {"finished", "error"}:
            if self._progress:
                sys.stderr.write("\r" + " " * 48 + "\r")
                sys.stderr.flush()
            if state == "finished":
                self._logger.debug("download finished: %s", status.get("filename"))

    # -- API ----------------------------------------------------------------

    def probe(self, url: str, *, allow_playlist: bool = False, flat: bool = False,
              user_agent: str | None = None) -> dict[str, Any]:
        options = self._base_options()
        if user_agent:
            options["http_headers"] = {"User-Agent": user_agent}
        options.update({
            "skip_download": True,
            "noplaylist": not allow_playlist,
            "extract_flat": "in_playlist" if flat else False,
        })
        with self._module.YoutubeDL(options) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
            except KeyboardInterrupt:  # pragma: no cover - interactive only
                raise
            except Exception as exc:
                raise classify_error(getattr(exc, "msg", None) or str(exc)) from exc
        if not isinstance(info, dict):
            raise MetadataError(f"No metadata returned for {url}")
        return self._module.YoutubeDL.sanitize_info(info)

    def download(self, request: DownloadRequest) -> DownloadResult:
        target = Path(request.target_dir)
        target.mkdir(parents=True, exist_ok=True)
        options = self._base_options()
        options.update({
            "format": request.format_selector,
            "outtmpl": {"default": str(target / f"{request.stem}.%(ext)s")},
            "noplaylist": True,
            "continuedl": request.resume,
            "overwrites": True if request.overwrite else None,
            "retries": request.retries,
            "fragment_retries": request.fragment_retries,
            "socket_timeout": request.socket_timeout,
            "ratelimit": _parse_ratelimit(request.ratelimit),
            "progress_hooks": [self._progress_hook],
            "writesubtitles": request.subtitles.enabled,
            "writeautomaticsub": request.subtitles.enabled and request.subtitles.include_auto,
            "subtitleslangs": list(request.subtitles.languages) or ["all"],
            "subtitlesformat": request.subtitles.formats,
            # One video + one audio stream, merged into a single container.
            "allow_multiple_video_streams": False,
            "allow_multiple_audio_streams": False,
            "merge_output_format": self._config.video.merge_output_format,
        })
        if request.user_agent:
            options["http_headers"] = {"User-Agent": request.user_agent}
        with self._module.YoutubeDL(options) as ydl:
            try:
                info = ydl.extract_info(request.url, download=True)
            except KeyboardInterrupt as exc:  # pragma: no cover - interactive only
                raise InterruptedDownloadError(
                    "Download interrupted by the user; partial data was kept.",
                    hint="Run the same command again to resume.",
                ) from exc
            except Exception as exc:
                raise classify_error(getattr(exc, "msg", None) or str(exc)) from exc
            if not isinstance(info, dict):
                raise DownloadFailedError(f"yt-dlp returned no result for {request.url}")
            info = self._module.YoutubeDL.sanitize_info(info)
        media_path = _resolve_media_path(info, target, request.stem)
        return DownloadResult(
            media_path=media_path,
            info=info,
            subtitle_files=_find_subtitle_files(target, request.stem),
        )


class YtDlpCliDownloader(Downloader):
    """Fallback backend driving the yt-dlp command line binary."""

    name = "cli"

    def __init__(self, config: Config) -> None:
        binary = find_ytdlp_binary(config)
        if not binary:
            raise DependencyError("yt-dlp binary not found.", hint=YTDLP_INSTALL_HINT)
        self._binary = binary
        self._config = config
        self._logger = get_logger("ytdlp-cli")

    @property
    def version(self) -> str | None:
        try:
            proc = subprocess.run([self._binary, "--version"], capture_output=True, text=True, timeout=20)
            return proc.stdout.strip() or None
        except (OSError, subprocess.SubprocessError):  # pragma: no cover
            return None

    def _extractor_arg_flags(self) -> list[str]:
        """config ytdlp.extractor_args -> repeated --extractor-args flags."""
        flags: list[str] = []
        for extractor, args in self._config.ytdlp.extractor_args.items():
            for key, values in args.items():
                flags += ["--extractor-args", f"{extractor}:{key}={','.join(values)}"]
        return flags

    def _run(self, args: list[str], *, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
        command = [self._binary, *args]
        self._logger.debug("running: %s", " ".join(command))
        try:
            return subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError as exc:  # pragma: no cover
            raise DependencyError(f"yt-dlp binary disappeared: {self._binary}", hint=YTDLP_INSTALL_HINT) from exc
        except subprocess.TimeoutExpired as exc:
            raise NetworkError(f"yt-dlp timed out after {timeout}s") from exc
        except KeyboardInterrupt as exc:  # pragma: no cover - interactive only
            raise InterruptedDownloadError("Interrupted by the user; partial data was kept.",
                                           hint="Run the same command again to resume.") from exc

    def probe(self, url: str, *, allow_playlist: bool = False, flat: bool = False,
              user_agent: str | None = None) -> dict[str, Any]:
        args = ["-J", "--no-warnings", "--no-color", *self._extractor_arg_flags()]
        if user_agent:
            args += ["--user-agent", user_agent]
        args.append("--yes-playlist" if allow_playlist else "--no-playlist")
        if flat:
            args.append("--flat-playlist")
        args.append(url)
        proc = self._run(args, timeout=180)
        if proc.returncode != 0:
            raise classify_error(proc.stderr.strip() or f"yt-dlp exited with {proc.returncode}")
        try:
            info = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise MetadataError(f"yt-dlp returned unparsable JSON for {url}: {exc}") from exc
        if not isinstance(info, dict):
            raise MetadataError(f"No metadata returned for {url}")
        return info

    def download(self, request: DownloadRequest) -> DownloadResult:
        target = Path(request.target_dir)
        target.mkdir(parents=True, exist_ok=True)
        args = [
            "-f", request.format_selector,
            "-o", str(target / f"{request.stem}.%(ext)s"),
            "--no-playlist", "--no-color", "--no-warnings", "--no-progress",
            "--retries", str(request.retries),
            "--fragment-retries", str(request.fragment_retries),
            "--socket-timeout", str(request.socket_timeout),
            "--print", "after_move:filepath",
            "--no-simulate",
            *self._extractor_arg_flags(),
        ]
        if request.resume:
            args.append("--continue")
        if request.overwrite:
            args.append("--force-overwrites")
        if request.ratelimit:
            args += ["--limit-rate", request.ratelimit]
        if request.user_agent:
            args += ["--user-agent", request.user_agent]
        if request.subtitles.enabled:
            args += ["--write-subs", "--sub-format", request.subtitles.formats]
            if request.subtitles.languages:
                args += ["--sub-langs", ",".join(request.subtitles.languages)]
            if request.subtitles.include_auto:
                args.append("--write-auto-subs")
        args.append(request.url)

        proc = self._run(args)
        if proc.returncode != 0:
            raise classify_error(proc.stderr.strip() or f"yt-dlp exited with {proc.returncode}")

        printed = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        media_path = Path(printed[-1]) if printed and Path(printed[-1]).exists() else None
        if media_path is None:
            media_path = _scan_media_path(target, request.stem)
        info = self.probe(request.url, user_agent=request.user_agent)
        return DownloadResult(
            media_path=media_path,
            info=info,
            subtitle_files=_find_subtitle_files(target, request.stem),
        )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_MEDIA_EXTENSIONS = {".mp4", ".mkv", ".webm", ".m4v", ".mov", ".avi", ".flv", ".mp3", ".m4a", ".opus", ".wav"}


def _parse_ratelimit(value: str | None) -> float | None:
    if not value:
        return None
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([KMG]?)\s*", str(value), re.IGNORECASE)
    if not match:
        return None
    factor = {"": 1, "K": 1024, "M": 1024 ** 2, "G": 1024 ** 3}[match.group(2).upper()]
    return float(match.group(1)) * factor


def _scan_media_path(target: Path, stem: str) -> Path | None:
    candidates = [
        path for path in target.glob(f"{stem}.*")
        if path.is_file() and path.suffix.lower() in _MEDIA_EXTENSIONS
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_size)


def _resolve_media_path(info: dict[str, Any], target: Path, stem: str) -> Path | None:
    downloads = info.get("requested_downloads")
    if isinstance(downloads, list):
        for entry in downloads:
            if isinstance(entry, dict):
                for key in ("filepath", "_filename", "filename"):
                    value = entry.get(key)
                    if value and Path(value).exists():
                        return Path(value)
    for key in ("filepath", "_filename", "filename"):
        value = info.get(key)
        if value and Path(value).exists():
            return Path(value)
    return _scan_media_path(target, stem)


def _find_subtitle_files(target: Path, stem: str) -> list[Path]:
    return sorted(
        path for path in target.glob(f"{stem}.*")
        if path.is_file() and path.suffix.lower() in {".vtt", ".srt", ".ass", ".ttml", ".srv3", ".json3"}
    )


def create_downloader(config: Config, *, progress: bool = True) -> Downloader:
    """Pick the best available backend (Python module first, CLI second)."""
    try:
        return YtDlpPythonDownloader(config, progress=progress)
    except DependencyError:
        return YtDlpCliDownloader(config)


def subtitle_request_from_config(config: Config) -> SubtitleRequest:
    return SubtitleRequest(
        enabled=config.subtitles.download,
        languages=tuple(config.subtitles.languages),
        formats=config.subtitles.formats,
        include_auto=config.subtitles.include_auto,
    )


def is_playlist(info: dict[str, Any]) -> bool:
    if info.get("_type") in {"playlist", "multi_video"}:
        return True
    entries = info.get("entries")
    return isinstance(entries, list)
