"""Typed configuration objects loaded from config/config.yaml."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import yamlio
from .errors import ConfigError
from .paths import find_project_root, resolve_path

DEFAULT_CONFIG_RELPATH = "config/config.yaml"

# Format selectors that would require FFmpeg to merge separate video/audio
# streams. The pipeline refuses them on purpose (spec section 2 and 5).
_MERGING_TOKENS = ("+", "bestvideo", "bestaudio", "worstvideo", "worstaudio")


# ---------------------------------------------------------------------------
# small typed readers
# ---------------------------------------------------------------------------

def _section(data: dict[str, Any], key: str, where: str) -> dict[str, Any]:
    value = data.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"{where}: '{key}' must be a mapping, got {type(value).__name__}")
    return value


def _boolean(data: dict[str, Any], key: str, default: bool, where: str) -> bool:
    value = data.get(key)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ConfigError(f"{where}.{key}: expected true/false, got {value!r}")
    return value


def _integer(data: dict[str, Any], key: str, default: int, where: str, *, minimum: int | None = None) -> int:
    value = data.get(key)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{where}.{key}: expected an integer, got {value!r}")
    if minimum is not None and value < minimum:
        raise ConfigError(f"{where}.{key}: must be >= {minimum}, got {value}")
    return value


def _text(data: dict[str, Any], key: str, default: str | None, where: str) -> str | None:
    value = data.get(key)
    if value is None:
        return default
    if not isinstance(value, str):
        raise ConfigError(f"{where}.{key}: expected a string, got {value!r}")
    return value


def _text_required(data: dict[str, Any], key: str, default: str, where: str) -> str:
    value = _text(data, key, default, where)
    if not value:
        raise ConfigError(f"{where}.{key}: must not be empty")
    return value


def _string_list(data: dict[str, Any], key: str, default: list[str], where: str) -> list[str]:
    value = data.get(key)
    if value is None:
        return list(default)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{where}.{key}: expected a list of strings, got {value!r}")
    return list(value)


def _string_map(data: dict[str, Any], key: str, default: dict[str, str], where: str) -> dict[str, str]:
    value = data.get(key)
    if value is None:
        return dict(default)
    if not isinstance(value, dict) or not all(isinstance(v, str) for v in value.values()):
        raise ConfigError(f"{where}.{key}: expected a mapping of string -> string, got {value!r}")
    return {str(k): v for k, v in value.items()}


# ---------------------------------------------------------------------------
# sections
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VideoConfig:
    max_height: int = 1080
    preferred_extension: str = "mp4"
    format_selector: str | None = None
    #: Merge separate video+audio streams into one file. Requires FFmpeg, and
    #: is the only way to get more than ~360-720p on most platforms, because
    #: higher resolutions exist exclusively as separate DASH streams.
    allow_merge: bool = True
    merge_output_format: str = "mp4"

    @property
    def effective_format_selector(self) -> str:
        """The yt-dlp format string actually used.

        With ``allow_merge`` the selector asks for the best video and the best
        audio stream separately (FFmpeg muxes them afterwards) and falls back
        to a pre-muxed file when no separate streams exist. Without it, only
        single-file (progressive) formats can be selected - there would be
        nothing to merge with.
        """
        if self.format_selector:
            return self.format_selector
        height = self.max_height
        ext = self.preferred_extension
        progressive = f"best[height<={height}][ext={ext}]/best[height<={height}]/best"
        if not self.allow_merge:
            return progressive
        audio_ext = "m4a" if ext == "mp4" else "bestaudio"
        return (
            f"bestvideo[height<={height}][ext={ext}]+bestaudio[ext={audio_ext}]/"
            f"bestvideo[height<={height}]+bestaudio/"
            f"{progressive}"
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any], where: str) -> "VideoConfig":
        selector = _text(data, "format_selector", None, where)
        allow_merge = _boolean(data, "allow_merge", True, where)
        if selector and not allow_merge:
            lowered = selector.lower()
            for token in _MERGING_TOKENS:
                if token in lowered:
                    raise ConfigError(
                        f"{where}.format_selector: {selector!r} would need FFmpeg to merge "
                        f"separate streams (contains {token!r}), but video.allow_merge is false",
                        hint="Set video.allow_merge: true (and install FFmpeg), or use a "
                             "single-file selector such as 'best[height<=720][ext=mp4]/best'.",
                    )
        return cls(
            max_height=_integer(data, "max_height", 1080, where, minimum=1),
            preferred_extension=_text_required(data, "preferred_extension", "mp4", where),
            format_selector=selector,
            allow_merge=allow_merge,
            merge_output_format=_text_required(data, "merge_output_format", "mp4", where),
        )


@dataclass(frozen=True)
class MetadataConfig:
    save_json: bool = True
    save_raw_info: bool = False
    #: Language recorded when the provider reports none. Setting it is the
    #: owner's assertion about their own corpus, not a guess by the pipeline.
    default_language: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any], where: str) -> "MetadataConfig":
        return cls(
            save_json=_boolean(data, "save_json", True, where),
            save_raw_info=_boolean(data, "save_raw_info", False, where),
            default_language=_text(data, "default_language", None, where),
        )


@dataclass(frozen=True)
class WhisperCppConfig:
    binary: str | None = None
    model: str | None = None
    extra_args: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any], where: str) -> "WhisperCppConfig":
        return cls(
            binary=_text(data, "binary", None, where),
            model=_text(data, "model", None, where),
            extra_args=_string_list(data, "extra_args", [], where),
        )


@dataclass(frozen=True)
class FasterWhisperConfig:
    model: str = "large-v3-turbo"
    device: str = "auto"
    compute_type: str = "int8"
    #: Voice-activity detection. Keeps music and silence from being decoded as
    #: speech - without it the model loses whole passages around an intro.
    vad_filter: bool = True
    #: Feeding the previous text back in makes Whisper repeat itself when it
    #: gets one window wrong; each window is decoded independently instead.
    condition_on_previous_text: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any], where: str) -> "FasterWhisperConfig":
        return cls(
            model=_text_required(data, "model", "large-v3-turbo", where),
            device=_text_required(data, "device", "auto", where),
            compute_type=_text_required(data, "compute_type", "int8", where),
            vad_filter=_boolean(data, "vad_filter", True, where),
            condition_on_previous_text=_boolean(data, "condition_on_previous_text", False, where),
        )


@dataclass(frozen=True)
class MlxWhisperConfig:
    model: str = "mlx-community/whisper-large-v3-turbo"

    @classmethod
    def from_dict(cls, data: dict[str, Any], where: str) -> "MlxWhisperConfig":
        return cls(model=_text_required(data, "model", "mlx-community/whisper-large-v3-turbo", where))


@dataclass(frozen=True)
class TranscriptConfig:
    enabled: bool = False
    status: str = "pending"
    backend: str = "auto"
    language: str | None = None
    postprocess: bool = False
    whisper_cpp: WhisperCppConfig = field(default_factory=WhisperCppConfig)
    faster_whisper: FasterWhisperConfig = field(default_factory=FasterWhisperConfig)
    mlx_whisper: MlxWhisperConfig = field(default_factory=MlxWhisperConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any], where: str) -> "TranscriptConfig":
        return cls(
            enabled=_boolean(data, "enabled", False, where),
            status=_text_required(data, "status", "pending", where),
            backend=_text_required(data, "backend", "auto", where),
            language=_text(data, "language", None, where),
            postprocess=_boolean(data, "postprocess", False, where),
            whisper_cpp=WhisperCppConfig.from_dict(
                _section(data, "whisper_cpp", where), f"{where}.whisper_cpp"
            ),
            faster_whisper=FasterWhisperConfig.from_dict(
                _section(data, "faster_whisper", where), f"{where}.faster_whisper"
            ),
            mlx_whisper=MlxWhisperConfig.from_dict(
                _section(data, "mlx_whisper", where), f"{where}.mlx_whisper"
            ),
        )


@dataclass(frozen=True)
class SubtitlesConfig:
    download: bool = False
    languages: list[str] = field(default_factory=lambda: ["hu", "en"])
    formats: str = "vtt/srt/best"
    include_auto: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any], where: str) -> "SubtitlesConfig":
        return cls(
            download=_boolean(data, "download", False, where),
            languages=_string_list(data, "languages", ["hu", "en"], where),
            formats=_text_required(data, "formats", "vtt/srt/best", where),
            include_auto=_boolean(data, "include_auto", False, where),
        )


@dataclass(frozen=True)
class OrganizationConfig:
    provider_folder: bool = True
    subject_folder: bool = True
    default_subject: str = "Besorolatlan"
    provider_names: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any], where: str) -> "OrganizationConfig":
        return cls(
            provider_folder=_boolean(data, "provider_folder", True, where),
            subject_folder=_boolean(data, "subject_folder", True, where),
            default_subject=_text_required(data, "default_subject", "Besorolatlan", where),
            provider_names=_string_map(data, "provider_names", {}, where),
        )


@dataclass(frozen=True)
class SubjectsConfig:
    taxonomy: list[str] = field(default_factory=list)
    aliases: dict[str, str] = field(default_factory=dict)
    #: subject -> topic words looked for in the title/description/tags when
    #: nothing more reliable identifies the subject.
    keywords: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any], where: str) -> "SubjectsConfig":
        raw = data.get("keywords")
        keywords: dict[str, list[str]] = {}
        if raw is not None:
            if not isinstance(raw, dict):
                raise ConfigError(f"{where}.keywords: expected a mapping of subject -> word list")
            for subject, words in raw.items():
                if not isinstance(words, list) or not all(isinstance(w, str) for w in words):
                    raise ConfigError(f"{where}.keywords.{subject}: expected a list of strings")
                # Matching is substring based, so a very short word matches
                # inside unrelated ones ("ero" inside "Nero"). Refuse those
                # instead of silently mis-filing videos.
                short = [word for word in words if len(word.strip()) < 4]
                if short:
                    raise ConfigError(
                        f"{where}.keywords.{subject}: keywords must be at least 4 characters, "
                        f"got {short}",
                        hint="Short words match inside unrelated ones. Use a longer form "
                             "('energia' instead of 'erő').",
                    )
                keywords[str(subject)] = list(words)
        return cls(
            taxonomy=_string_list(data, "taxonomy", [], where),
            aliases=_string_map(data, "aliases", {}, where),
            keywords=keywords,
        )


@dataclass(frozen=True)
class ArchiveConfig:
    enabled: bool = True
    dir: str = "./archive"

    @classmethod
    def from_dict(cls, data: dict[str, Any], where: str) -> "ArchiveConfig":
        return cls(
            enabled=_boolean(data, "enabled", True, where),
            dir=_text_required(data, "dir", "./archive", where),
        )


@dataclass(frozen=True)
class LoggingConfig:
    dir: str = "./logs"
    level: str = "INFO"
    json_events: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any], where: str) -> "LoggingConfig":
        level = _text_required(data, "level", "INFO", where).upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ConfigError(f"{where}.level: unknown log level {level!r}")
        return cls(
            dir=_text_required(data, "dir", "./logs", where),
            level=level,
            json_events=_boolean(data, "json_events", True, where),
        )


@dataclass(frozen=True)
class PlaylistConfig:
    enabled: bool = False
    max_items: int = 50

    @classmethod
    def from_dict(cls, data: dict[str, Any], where: str) -> "PlaylistConfig":
        return cls(
            enabled=_boolean(data, "enabled", False, where),
            max_items=_integer(data, "max_items", 50, where, minimum=1),
        )


#: What marks a page as a video page during --crawl: an embedded player.
DEFAULT_EMBED_PATTERNS = (
    r"youtube(?:-nocookie)?\.com/embed/[A-Za-z0-9_-]{6,}",
    r"""<iframe[^>]+src=["']?https?://(?:www\.)?youtu\.be/[A-Za-z0-9_-]{6,}""",
    r"video\.cs50\.io/[A-Za-z0-9_-]{6,}",  # CS50's player: video.cs50.io/<YouTube id>
    r"player\.vimeo\.com/video/\d+",
    r"<video[\s>]",
)
DEFAULT_CRAWL_USER_AGENT = "Manifold video fetcher (honours robots.txt)"


@dataclass(frozen=True)
class CrawlConfig:
    #: Minimum pause between two page requests. A longer robots.txt
    #: Crawl-delay always wins.
    delay_seconds: int = 10
    #: Link levels followed below the start page (subject -> topic -> video = 2).
    max_depth: int = 2
    #: Hard stop on fetched pages, so a wrong start page cannot wander off.
    max_pages: int = 400
    #: A crawl that finds more video pages than this aborts (--max-items).
    max_items: int = 200
    embed_patterns: list[str] = field(default_factory=lambda: list(DEFAULT_EMBED_PATTERNS))
    user_agent: str = DEFAULT_CRAWL_USER_AGENT

    @classmethod
    def from_dict(cls, data: dict[str, Any], where: str) -> "CrawlConfig":
        patterns = _string_list(data, "embed_patterns", list(DEFAULT_EMBED_PATTERNS), where)
        if not patterns:
            raise ConfigError(f"{where}.embed_patterns: at least one pattern is needed to recognise a video page")
        for pattern in patterns:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ConfigError(f"{where}.embed_patterns: invalid regular expression {pattern!r}: {exc}") from exc
        return cls(
            delay_seconds=_integer(data, "delay_seconds", 10, where, minimum=0),
            max_depth=_integer(data, "max_depth", 2, where, minimum=0),
            max_pages=_integer(data, "max_pages", 400, where, minimum=1),
            max_items=_integer(data, "max_items", 200, where, minimum=1),
            embed_patterns=patterns,
            user_agent=_text_required(data, "user_agent", DEFAULT_CRAWL_USER_AGENT, where),
        )


@dataclass(frozen=True)
class DownloadConfig:
    retries: int = 5
    fragment_retries: int = 5
    socket_timeout: int = 30
    ratelimit: str | None = None
    resume: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any], where: str) -> "DownloadConfig":
        return cls(
            retries=_integer(data, "retries", 5, where, minimum=0),
            fragment_retries=_integer(data, "fragment_retries", 5, where, minimum=0),
            socket_timeout=_integer(data, "socket_timeout", 30, where, minimum=1),
            ratelimit=_text(data, "ratelimit", None, where),
            resume=_boolean(data, "resume", True, where),
        )


def _extractor_args(data: dict[str, Any], key: str, where: str) -> dict[str, dict[str, list[str]]]:
    """Parse ``{extractor: {arg: [values]}}`` - yt-dlp's --extractor-args."""
    value = data.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"{where}.{key}: expected a mapping of extractor -> arguments, got {value!r}")
    result: dict[str, dict[str, list[str]]] = {}
    for extractor, args in value.items():
        if not isinstance(args, dict):
            raise ConfigError(f"{where}.{key}.{extractor}: expected a mapping of argument -> list")
        parsed: dict[str, list[str]] = {}
        for arg, items in args.items():
            if isinstance(items, str):
                items = [items]
            if not isinstance(items, list) or not all(isinstance(item, (str, int)) for item in items):
                raise ConfigError(
                    f"{where}.{key}.{extractor}.{arg}: expected a string or a list of strings"
                )
            parsed[str(arg)] = [str(item) for item in items]
        result[str(extractor)] = parsed
    return result


@dataclass(frozen=True)
class YtDlpConfig:
    local_source_path: str | None = None
    binary: str | None = None
    extractor_args: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    #: JavaScript runtimes yt-dlp may use to solve YouTube's player challenges.
    #: Without one, YouTube hands out only the 360p pre-muxed format. yt-dlp
    #: enables "deno" by default; "node" has to be named explicitly.
    js_runtimes: list[str] = field(default_factory=lambda: ["deno", "node"])
    #: Path to the ffmpeg binary. "auto" (default) means: none (Manifold-OS port: no PATH, no imageio-ffmpeg, no runtime search;
    #: the pinned, hash-verified build is handed in by modulok/ytdlp/lanc.py).
    ffmpeg_location: str = "auto"
    #: Path to the pinned node binary for yt-dlp's JS challenge solver ("auto" = none; Manifold-OS port: never searched on PATH).
    node_location: str = "auto"

    @classmethod
    def from_dict(cls, data: dict[str, Any], where: str) -> "YtDlpConfig":
        return cls(
            local_source_path=_text(data, "local_source_path", None, where),
            binary=_text(data, "binary", None, where),
            extractor_args=_extractor_args(data, "extractor_args", where),
            js_runtimes=_string_list(data, "js_runtimes", ["deno", "node"], where),
            ffmpeg_location=_text_required(data, "ffmpeg_location", "auto", where),
            node_location=_text_required(data, "node_location", "auto", where),
        )


@dataclass(frozen=True)
class IntegrationConfig:
    """Hand-off of a freshly staged source to a downstream integrator (owner decision 2026-09-19).

    The pipeline itself never reads or writes a vault. When ``enabled`` (or with
    ``download.py --integrate``) it runs ``command`` once per staged source folder, with
    ``{folder}`` replaced by the folder's absolute path - see :mod:`msp.integration`.
    """

    enabled: bool = False
    command: tuple[str, ...] = ()
    timeout_seconds: int = 3600

    @classmethod
    def from_dict(cls, data: dict[str, Any], where: str) -> "IntegrationConfig":
        command = _string_list(data, "command", [], where)
        enabled = _boolean(data, "enabled", False, where)
        if enabled and not command:
            raise ConfigError(f"{where}.command: must be set when {where}.enabled is true")
        if command and not any("{folder}" in part for part in command):
            raise ConfigError(f"{where}.command: must contain the {{folder}} placeholder")
        return cls(
            enabled=enabled,
            command=tuple(command),
            timeout_seconds=_integer(data, "timeout_seconds", 3600, where, minimum=1),
        )


# ---------------------------------------------------------------------------
# root config
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Config:
    project_root: Path
    config_path: Path | None
    output_root: Path
    video: VideoConfig = field(default_factory=VideoConfig)
    metadata: MetadataConfig = field(default_factory=MetadataConfig)
    transcript: TranscriptConfig = field(default_factory=TranscriptConfig)
    subtitles: SubtitlesConfig = field(default_factory=SubtitlesConfig)
    organization: OrganizationConfig = field(default_factory=OrganizationConfig)
    subjects: SubjectsConfig = field(default_factory=SubjectsConfig)
    archive: ArchiveConfig = field(default_factory=ArchiveConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    playlist: PlaylistConfig = field(default_factory=PlaylistConfig)
    crawl: CrawlConfig = field(default_factory=CrawlConfig)
    download: DownloadConfig = field(default_factory=DownloadConfig)
    ytdlp: YtDlpConfig = field(default_factory=YtDlpConfig)
    integration: IntegrationConfig = field(default_factory=IntegrationConfig)

    # -- derived paths ------------------------------------------------------

    @property
    def archive_dir(self) -> Path:
        return resolve_path(self.archive.dir, self.project_root)

    @property
    def log_dir(self) -> Path:
        return resolve_path(self.logging.dir, self.project_root)

    @property
    def templates_dir(self) -> Path:
        return self.project_root / "templates"

    # -- loading ------------------------------------------------------------

    @classmethod
    def load(
        cls,
        config_path: str | Path | None = None,
        *,
        project_root: str | Path | None = None,
        output_root: str | Path | None = None,
    ) -> "Config":
        """Load configuration, falling back to defaults when no file exists.

        `output_root` (CLI ``--output-root``) always wins over the file.
        """
        root = Path(project_root).expanduser().resolve() if project_root else find_project_root()

        path: Path | None
        if config_path is not None:
            path = Path(config_path).expanduser()
            if not path.is_absolute():
                path = (Path.cwd() / path).resolve()
            if not path.exists():
                raise ConfigError(f"Config file not found: {path}")
        else:
            env_path = os.environ.get("MSP_CONFIG")
            if env_path:
                path = Path(env_path).expanduser()
                if not path.exists():
                    raise ConfigError(f"MSP_CONFIG points to a missing file: {path}")
            else:
                candidate = root / DEFAULT_CONFIG_RELPATH
                path = candidate if candidate.exists() else None

        data: dict[str, Any] = {}
        if path is not None:
            loaded = yamlio.load_file(path)
            if loaded is None:
                loaded = {}
            if not isinstance(loaded, dict):
                raise ConfigError(f"{path}: the top level of the config must be a mapping")
            data = loaded

        return cls.from_dict(data, project_root=root, config_path=path, output_root=output_root)

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        *,
        project_root: str | Path,
        config_path: str | Path | None = None,
        output_root: str | Path | None = None,
    ) -> "Config":
        root = Path(project_root).expanduser().resolve()
        where = str(config_path) if config_path else "<config>"
        raw_output_root = output_root if output_root is not None else _text_required(
            data, "output_root", "./staging", where
        )
        return cls(
            project_root=root,
            config_path=Path(config_path) if config_path else None,
            output_root=resolve_path(raw_output_root, root),
            video=VideoConfig.from_dict(_section(data, "video", where), "video"),
            metadata=MetadataConfig.from_dict(_section(data, "metadata", where), "metadata"),
            transcript=TranscriptConfig.from_dict(_section(data, "transcript", where), "transcript"),
            subtitles=SubtitlesConfig.from_dict(_section(data, "subtitles", where), "subtitles"),
            organization=OrganizationConfig.from_dict(
                _section(data, "organization", where), "organization"
            ),
            subjects=SubjectsConfig.from_dict(_section(data, "subjects", where), "subjects"),
            archive=ArchiveConfig.from_dict(_section(data, "archive", where), "archive"),
            logging=LoggingConfig.from_dict(_section(data, "logging", where), "logging"),
            playlist=PlaylistConfig.from_dict(_section(data, "playlist", where), "playlist"),
            crawl=CrawlConfig.from_dict(_section(data, "crawl", where), "crawl"),
            download=DownloadConfig.from_dict(_section(data, "download", where), "download"),
            ytdlp=YtDlpConfig.from_dict(_section(data, "ytdlp", where), "ytdlp"),
            integration=IntegrationConfig.from_dict(_section(data, "integration", where), "integration"),
        )

    def describe(self) -> str:
        """One-paragraph summary used by --help style diagnostics."""
        return (
            f"project_root : {self.project_root}\n"
            f"config       : {self.config_path or '<defaults>'}\n"
            f"output_root  : {self.output_root}\n"
            f"archive_dir  : {self.archive_dir}\n"
            f"log_dir      : {self.log_dir}\n"
            f"format       : {self.video.effective_format_selector}\n"
            f"yaml backend : {yamlio.backend_name()}\n"
            f"integration  : {'on' if self.integration.enabled else 'off'}"
            + (f" ({self.integration.command[0]} ...)" if self.integration.command else " (no command)")
        )
