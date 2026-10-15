"""Typed pipeline errors.

Every error carries a human-readable message and, where a user action can fix
the situation, a `hint`. Errors are never swallowed silently (spec section 21):
the CLI prints message + hint and exits with `exit_code`.
"""

from __future__ import annotations


class PipelineError(Exception):
    """Base class for every error the pipeline raises on purpose."""

    exit_code: int = 1

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message

    def render(self) -> str:
        """Message plus remediation hint, ready to print."""
        if self.hint:
            return f"{self.message}\n  -> {self.hint}"
        return self.message


# --- configuration / environment --------------------------------------------

class ConfigError(PipelineError):
    """config.yaml is missing, unreadable or semantically wrong."""
    exit_code = 78  # EX_CONFIG


class DependencyError(PipelineError):
    """A required external dependency (yt-dlp, PyYAML, ...) is unavailable."""
    exit_code = 69  # EX_UNAVAILABLE


class YamlSubsetError(ConfigError):
    """The bundled minimal YAML reader met a construct it refuses to guess at."""


# --- input ------------------------------------------------------------------

class InvalidURLError(PipelineError):
    """The given string is not a usable http(s) URL."""
    exit_code = 64  # EX_USAGE


class UnsupportedURLError(PipelineError):
    """yt-dlp has no extractor that can handle this URL."""
    exit_code = 65  # EX_DATAERR


class PlaylistGuardError(PipelineError):
    """A playlist was hit without --playlist, or it exceeds the item limit."""
    exit_code = 64


class CrawlError(PipelineError):
    """A listing page could not be crawled, or it leads to no video page."""
    exit_code = 65


class CrawlLimitError(CrawlError):
    """A crawl grew past crawl.max_pages or found more videos than the item limit."""
    exit_code = 64


# --- extraction / download --------------------------------------------------

class MetadataError(PipelineError):
    """Metadata could not be extracted, or is too incomplete to be usable."""
    exit_code = 65


class DownloadFailedError(PipelineError):
    """Generic download failure."""
    exit_code = 70  # EX_SOFTWARE


class NetworkError(DownloadFailedError):
    """Connection problem while talking to the provider."""
    exit_code = 75  # EX_TEMPFAIL


class CertificateError(NetworkError):
    """TLS certificate verification failed (common on python.org macOS builds)."""


class VideoUnavailableError(DownloadFailedError):
    """Deleted, private, region-locked or otherwise inaccessible video."""
    exit_code = 65


class NoProgressiveFormatError(DownloadFailedError):
    """No single-file (video+audio) format exists; merging would need FFmpeg."""
    exit_code = 65


class InterruptedDownloadError(DownloadFailedError):
    """The user interrupted the download; partial data was kept for resume."""
    exit_code = 130


# --- filesystem -------------------------------------------------------------

class FilesystemError(PipelineError):
    """Could not create/write the staging layout."""
    exit_code = 73  # EX_CANTCREAT


class NameCollisionError(FilesystemError):
    """Two different sources want the same folder and it could not be resolved."""


# --- later stages -----------------------------------------------------------

class TranscriptionError(PipelineError):
    """The transcription step failed or no backend is available."""
    exit_code = 70


class ValidationFailed(PipelineError):
    """validate.py found at least one ERROR-level problem."""
    exit_code = 1
