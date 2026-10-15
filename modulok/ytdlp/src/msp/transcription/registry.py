"""Backend registry: name -> instance, plus the ``auto`` selection order."""

from __future__ import annotations

from pathlib import Path

from ..config import Config
from ..errors import TranscriptionError
from .base import TranscriptionBackend
from .faster_whisper import FasterWhisperBackend
from .mlx_whisper import MlxWhisperBackend
from .subtitles import SubtitlesBackend
from .whisper_cpp import WhisperCppBackend

#: Order used when ``transcript.backend`` is ``auto``. Provider subtitles come
#: first: they exist only when explicitly downloaded, cost nothing to read and
#: are usually closer to what was said than a local ASR model. faster-whisper
#: comes next: on the sample material MLX was ~3x faster but dropped the first
#: 30 seconds of speech, and a source transcript with a hole in it is worse
#: than a slow one. MLX stays available as an explicit --backend choice.
AUTO_ORDER = ("subtitles", "faster_whisper", "mlx_whisper", "whisper_cpp")

_FACTORIES = {
    "subtitles": SubtitlesBackend,
    "mlx_whisper": MlxWhisperBackend,
    "faster_whisper": FasterWhisperBackend,
    "whisper_cpp": WhisperCppBackend,
}


def backend_names() -> tuple[str, ...]:
    return tuple(_FACTORIES)


def get_backend(name: str, config: Config) -> TranscriptionBackend:
    key = str(name).strip().lower()
    if key not in _FACTORIES:
        raise TranscriptionError(
            f"Unknown transcription backend: {name}",
            hint=f"Available backends: {', '.join(backend_names())}",
        )
    return _FACTORIES[key](config)


def available_backends(config: Config, folder: Path | None = None) -> list[TranscriptionBackend]:
    return [
        backend
        for backend in (get_backend(name, config) for name in AUTO_ORDER)
        if backend.is_available(folder)
    ]


def backend_status(config: Config, folder: Path | None = None) -> list[tuple[str, str | None]]:
    """``[(name, unavailable_reason_or_None), ...]`` for every known backend."""
    return [(name, get_backend(name, config).unavailable_reason(folder)) for name in AUTO_ORDER]


def describe_backends(config: Config, folder: Path | None = None) -> str:
    return "\n".join(get_backend(name, config).describe(folder) for name in AUTO_ORDER)


def select_backend(
    config: Config,
    name: str | None = None,
    folder: Path | None = None,
) -> TranscriptionBackend:
    """Resolve ``--backend`` / ``transcript.backend`` into a usable backend."""
    requested = (name or config.transcript.backend or "auto").strip().lower()
    if requested == "none":
        raise TranscriptionError(
            "Transcription is switched off (backend: none).",
            hint="Choose a backend with --backend, or set transcript.backend in config/config.yaml.",
        )
    if requested != "auto":
        backend = get_backend(requested, config)
        reason = backend.unavailable_reason(folder)
        if reason:
            raise TranscriptionError(
                f"Backend '{backend.name}' is not usable: {reason}",
                hint="See 'python3 scripts/transcribe.py --list-backends'.",
            )
        return backend

    for candidate in available_backends(config, folder):
        return candidate
    details = "; ".join(f"{name}: {reason}" for name, reason in backend_status(config, folder) if reason)
    raise TranscriptionError(
        "No transcription backend is available.",
        hint=f"{details}\n     The transcript stays 'pending' - nothing was invented.",
    )
