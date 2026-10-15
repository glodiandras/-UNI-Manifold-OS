"""faster-whisper backend (local, offline). The default ASR here.

It decodes .mp4/.webm on its own and reports a per-segment average log
probability that is turned into a confidence value - useful when deciding which
passages are reliable enough to quote (spec section 10).

Two settings carry the quality, both measured on Hungarian material rather than
assumed (see README section 9):

* ``vad_filter`` - voice-activity detection. Without it a musical intro can
  swallow the speech around it: the model returned one garbled line for the
  first 30 seconds and skipped the rest of that window.
* ``condition_on_previous_text: false`` - with conditioning on, one bad window
  makes Whisper repeat that text for the whole video.

Install with:  pip install -e ".[faster-whisper]"
"""

from __future__ import annotations

import math
from pathlib import Path

from ..config import Config
from ..errors import TranscriptionError
from ..logging_setup import get_logger
from ..timestamps import format_timestamp
from .base import Segment, TranscriptionBackend, TranscriptResult, modell_betoltes_tiltva

#: How much transcribed audio passes between two progress lines.
_PROGRESS_INTERVAL_SECONDS = 30.0


def _log_progress(position: float, total: float) -> None:
    logger = get_logger("transcribe")
    if total > 0:
        logger.info(
            "    transcribed %s / %s  (%.0f%%)",
            format_timestamp(position), format_timestamp(total), 100 * position / total,
        )
    else:  # pragma: no cover - duration is normally known
        logger.info("    transcribed %s", format_timestamp(position))


class FasterWhisperBackend(TranscriptionBackend):
    name = "faster_whisper"
    summary = "Local faster-whisper ASR with per-segment confidence; reads mp4 directly."

    def __init__(self, config: Config) -> None:
        self._config = config
        self._settings = config.transcript.faster_whisper

    def unavailable_reason(self, folder: Path | None = None) -> str | None:
        try:
            import faster_whisper  # noqa: F401,PLC0415
        except ImportError:
            return 'not installed (pip install -e ".[faster-whisper]")'
        return None

    def transcribe(
        self,
        media_path: Path,
        *,
        language: str | None = None,
        folder: Path | None = None,
    ) -> TranscriptResult:
        modell_betoltes_tiltva("faster_whisper")
        try:
            from faster_whisper import WhisperModel  # noqa: PLC0415
        except ImportError as exc:
            raise TranscriptionError(
                'faster-whisper is not installed (pip install -e ".[faster-whisper]")'
            ) from exc

        try:
            model = WhisperModel(
                self._settings.model,
                device=self._settings.device,
                compute_type=self._settings.compute_type,
            )
            iterator, info = model.transcribe(
                str(media_path),
                language=language,
                word_timestamps=False,
                vad_filter=self._settings.vad_filter,
                condition_on_previous_text=self._settings.condition_on_previous_text,
            )
            # faster-whisper yields lazily, so this loop *is* the work. Report
            # progress while it runs: a 6 minute video takes minutes on CPU and
            # a silent process looks indistinguishable from a hung one.
            total = float(getattr(info, "duration", 0) or 0)
            segments = []
            last_report = 0.0
            for item in iterator:
                segments.append(
                    Segment(
                        start=float(item.start),
                        end=float(item.end) if item.end is not None else None,
                        text=str(item.text),
                        confidence=_confidence(getattr(item, "avg_logprob", None)),
                    ).cleaned()
                )
                position = float(item.end or item.start or 0)
                if position - last_report >= _PROGRESS_INTERVAL_SECONDS:
                    last_report = position
                    _log_progress(position, total)
        except TranscriptionError:
            raise
        except Exception as exc:  # noqa: BLE001 - third-party failures vary widely
            raise TranscriptionError(f"faster-whisper failed: {exc}") from exc

        segments = [segment for segment in segments if segment.text]
        if not segments:
            raise TranscriptionError("faster-whisper returned no speech segments.")
        return TranscriptResult(
            segments=segments,
            engine=f"faster-whisper:{self._settings.model}",
            language=language or getattr(info, "language", None),
            model=self._settings.model,
            postprocessed=False,
            extra={"language_probability": getattr(info, "language_probability", None)},
        )


def _confidence(avg_logprob: float | None) -> float | None:
    """Average log probability -> a 0..1 confidence estimate."""
    if avg_logprob is None:
        return None
    try:
        return max(0.0, min(1.0, math.exp(float(avg_logprob))))
    except (OverflowError, ValueError):  # pragma: no cover
        return None
