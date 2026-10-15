"""whisper.cpp backend (local, offline).

Constraint worth knowing before choosing it: a stock whisper.cpp build reads
16 kHz mono WAV input, so a video container has to be decoded first. That is
done here with the same FFmpeg the downloader uses (bundled with the project),
into a temporary file that is deleted afterwards - the media file itself is
never touched. Without FFmpeg the backend accepts WAV input only; the
``faster_whisper`` backend decodes containers on its own.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

from ..config import Config
from ..errors import TranscriptionError
from .base import Segment, TranscriptionBackend, TranscriptResult, modell_betoltes_tiltva

_WAV_SUFFIXES = {".wav", ".wave"}


@contextmanager
def _as_wav(media: Path, config: Config):
    """Yield a 16 kHz mono WAV for *media*, converting with FFmpeg if needed.

    A converted file lives in a temporary directory and is removed afterwards;
    the downloaded media file is never modified.
    """
    if media.suffix.lower() in _WAV_SUFFIXES:
        yield media
        return
    from ..downloader import resolve_ffmpeg

    ffmpeg = resolve_ffmpeg(config)
    if not ffmpeg:
        raise TranscriptionError(
            f"whisper.cpp expects a WAV file, got {media.name}, and no FFmpeg was found to convert it",
            hint="Install FFmpeg (pip install imageio-ffmpeg), use --backend faster_whisper, "
                 "or point this backend at a WAV file.",
        )
    with tempfile.TemporaryDirectory(prefix="msp-whisper-") as tmp:
        wav_path = Path(tmp) / f"{media.stem}.wav"
        command = [ffmpeg, "-nostdin", "-y", "-i", str(media),
                   "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", str(wav_path)]
        try:
            proc = subprocess.run(command, capture_output=True, text=True)
        except OSError as exc:
            raise TranscriptionError(f"Cannot run FFmpeg: {exc}") from exc
        if proc.returncode != 0 or not wav_path.is_file():
            raise TranscriptionError(
                f"FFmpeg could not extract audio from {media.name}: {proc.stderr.strip()[-400:]}"
            )
        yield wav_path


class WhisperCppBackend(TranscriptionBackend):
    name = "whisper_cpp"
    summary = "Local whisper.cpp CLI; needs transcript.whisper_cpp.binary + .model in config."

    def __init__(self, config: Config) -> None:
        self._config = config
        self._settings = config.transcript.whisper_cpp

    # -- availability -------------------------------------------------------

    def _binary(self) -> str | None:
        configured = self._settings.binary
        if configured:
            path = Path(configured).expanduser()
            if path.is_file():
                return str(path)
            return shutil.which(configured)
        for candidate in ("whisper-cli", "whisper-cpp", "main"):
            found = shutil.which(candidate)
            if found:
                return found
        return None

    def unavailable_reason(self, folder: Path | None = None) -> str | None:
        if not self._binary():
            return "whisper.cpp binary not found (set transcript.whisper_cpp.binary)"
        model = self._settings.model
        if not model:
            return "no model configured (set transcript.whisper_cpp.model to a .bin file)"
        if not Path(model).expanduser().is_file():
            return f"model file not found: {model}"
        return None

    # -- run ----------------------------------------------------------------

    def transcribe(
        self,
        media_path: Path,
        *,
        language: str | None = None,
        folder: Path | None = None,
    ) -> TranscriptResult:
        modell_betoltes_tiltva("whisper_cpp")
        reason = self.unavailable_reason(folder)
        if reason:
            raise TranscriptionError(f"whisper.cpp backend unavailable: {reason}")
        binary = self._binary()
        model = str(Path(self._settings.model).expanduser())  # type: ignore[arg-type]
        media = Path(media_path)
        with _as_wav(media, self._config) as wav_path:
            output_prefix = wav_path.with_suffix("")
            command = [binary, "-m", model, "-f", str(wav_path), "-oj", "-of", str(output_prefix)]
            if language:
                command += ["-l", language]
            command += list(self._settings.extra_args)

            try:
                proc = subprocess.run(command, capture_output=True, text=True)
            except OSError as exc:
                raise TranscriptionError(f"Cannot run whisper.cpp: {exc}") from exc
            if proc.returncode != 0:
                raise TranscriptionError(
                    f"whisper.cpp failed (exit {proc.returncode}): {proc.stderr.strip()[-500:]}"
                )

            json_path = Path(f"{output_prefix}.json")
            if not json_path.is_file():
                raise TranscriptionError(f"whisper.cpp produced no JSON output at {json_path}")
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise TranscriptionError(f"Cannot read whisper.cpp output {json_path}: {exc}") from exc

        segments = _segments_from_json(data)
        if not segments:
            raise TranscriptionError("whisper.cpp returned no speech segments.")
        return TranscriptResult(
            segments=segments,
            engine=f"whisper.cpp:{Path(model).name}",
            language=language or (data.get("result") or {}).get("language"),
            model=Path(model).name,
            postprocessed=False,
            extra={"json_output": json_path.name},
        )


def _segments_from_json(data: dict) -> list[Segment]:
    entries = data.get("transcription")
    if not isinstance(entries, list):
        return []
    segments: list[Segment] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        offsets = entry.get("offsets") or {}
        start_ms = offsets.get("from")
        end_ms = offsets.get("to")
        text = str(entry.get("text") or "")
        if start_ms is None or not text.strip():
            continue
        segments.append(
            Segment(
                start=float(start_ms) / 1000.0,
                end=float(end_ms) / 1000.0 if end_ms is not None else None,
                text=text,
            ).cleaned()
        )
    return segments
