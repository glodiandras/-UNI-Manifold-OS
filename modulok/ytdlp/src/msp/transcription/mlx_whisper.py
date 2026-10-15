"""MLX Whisper backend (local, offline, Apple Silicon GPU).

Runs Whisper on the Apple Silicon GPU through MLX, which makes a large model
affordable on a laptop: about three times faster than the CPU backend on the
same `large-v3-turbo` weights.

Not the default, and not because of availability: on the sample material it was
about three times faster than faster-whisper but dropped the first 30 seconds of
speech (a musical intro), which faster-whisper's VAD handles correctly. Choose
it explicitly with ``--backend mlx_whisper`` when speed matters more than
completeness, and check the result.

Audio is decoded with the pipeline's own FFmpeg into memory, so the media file
is never modified and no ffmpeg binary has to be on PATH.

Install with:  pip install -e ".[mlx]"
"""

from __future__ import annotations

import math
import subprocess
from pathlib import Path
from typing import Any

from ..config import Config
from ..errors import TranscriptionError
from ..logging_setup import get_logger
from .base import Segment, TranscriptionBackend, TranscriptResult, modell_betoltes_tiltva

SAMPLE_RATE = 16000


class MlxWhisperBackend(TranscriptionBackend):
    name = "mlx_whisper"
    summary = "Local MLX Whisper on the Apple Silicon GPU; large-v3-turbo by default."

    def __init__(self, config: Config) -> None:
        self._config = config
        self._settings = config.transcript.mlx_whisper

    def unavailable_reason(self, folder: Path | None = None) -> str | None:
        try:
            import mlx_whisper  # noqa: F401,PLC0415
        except ImportError:
            return 'not installed (pip install -e ".[mlx]"; Apple Silicon only)'
        from ..downloader import resolve_ffmpeg  # noqa: PLC0415

        try:
            if not resolve_ffmpeg(self._config):
                return "no FFmpeg found to decode the audio"
        except Exception:  # noqa: BLE001 - a bad ffmpeg path is reported by the downloader
            return "no usable FFmpeg found to decode the audio"
        return None

    def transcribe(
        self,
        media_path: Path,
        *,
        language: str | None = None,
        folder: Path | None = None,
    ) -> TranscriptResult:
        modell_betoltes_tiltva("mlx_whisper")
        reason = self.unavailable_reason(folder)
        if reason:
            raise TranscriptionError(f"mlx_whisper backend unavailable: {reason}")

        import mlx_whisper  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415

        logger = get_logger("transcribe")
        audio = _decode_audio(media_path, self._config)
        logger.info(
            "    decoded %.1f minutes of audio, running %s on the GPU",
            len(audio) / SAMPLE_RATE / 60,
            self._settings.model,
        )
        try:
            raw: dict[str, Any] = mlx_whisper.transcribe(
                np.asarray(audio),
                path_or_hf_repo=self._settings.model,
                language=language,
                word_timestamps=False,
                verbose=None,
                # With conditioning on, a single mis-decoded window is repeated
                # for the rest of the video.
                condition_on_previous_text=False,
            )
        except TranscriptionError:
            raise
        except Exception as exc:  # noqa: BLE001 - third-party failures vary widely
            raise TranscriptionError(
                f"MLX Whisper failed: {exc}",
                hint="First use downloads the model; check the network, or set "
                     "transcript.mlx_whisper.model to a locally available one.",
            ) from exc

        segments = [
            Segment(
                start=float(item.get("start") or 0.0),
                end=float(item["end"]) if item.get("end") is not None else None,
                text=str(item.get("text") or ""),
                confidence=_confidence(item.get("avg_logprob")),
            ).cleaned()
            for item in raw.get("segments") or []
        ]
        segments = [segment for segment in segments if segment.text]
        if not segments:
            raise TranscriptionError("MLX Whisper returned no speech segments.")
        return TranscriptResult(
            segments=segments,
            engine=f"mlx-whisper:{self._settings.model}",
            language=language or raw.get("language"),
            model=self._settings.model,
            postprocessed=False,
        )


def _decode_audio(media: Path, config: Config):
    """Decode any container to 16 kHz mono float32 with the pipeline's FFmpeg."""
    import numpy as np  # noqa: PLC0415

    from ..downloader import resolve_ffmpeg  # noqa: PLC0415

    ffmpeg = resolve_ffmpeg(config)
    if not ffmpeg:
        raise TranscriptionError("No FFmpeg found to decode the audio.")
    command = [
        ffmpeg, "-nostdin", "-loglevel", "error", "-i", str(media),
        "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "f32le", "-",
    ]
    try:
        proc = subprocess.run(command, capture_output=True)
    except OSError as exc:
        raise TranscriptionError(f"Cannot run FFmpeg: {exc}") from exc
    if proc.returncode != 0 or not proc.stdout:
        raise TranscriptionError(
            f"FFmpeg could not decode {media.name}: "
            f"{proc.stderr.decode('utf-8', 'replace').strip()[-400:]}"
        )
    return np.frombuffer(proc.stdout, dtype=np.float32)


def _confidence(avg_logprob: float | None) -> float | None:
    """Average log probability -> a 0..1 confidence estimate."""
    if avg_logprob is None:
        return None
    try:
        return max(0.0, min(1.0, math.exp(float(avg_logprob))))
    except (OverflowError, ValueError, TypeError):  # pragma: no cover
        return None
