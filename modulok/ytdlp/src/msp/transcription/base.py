"""Backend interface and the data a transcription produces."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: Motors that would load an ASR model. **2.0 port (Javító 3, A3-22):** loading a model is forbidden in this port (CLAUDE.md §4: only the
#: model host/loader may load a model: shared lock, memory frame, memory guard); the transcript is the C20b job on the worker.
MODELLT_TOLTO = ("faster_whisper", "mlx_whisper", "whisper_cpp")


def modell_betoltes_tiltva(motor: str) -> None:
    """Always raises :class:`TranscriptionError`: called first in every model-loading ``transcribe`` of the port."""
    from ..errors import TranscriptionError  # noqa: PLC0415

    raise TranscriptionError(
        f"{motor}: loading an ASR model is forbidden in the Manifold-OS port - only the model host (modellgazda) may load a model.",
        hint="The transcript is produced by the worker's audio path (C20b); the transcript stays 'pending'.",
    )


@dataclass(frozen=True)
class Segment:
    """One timed chunk of recognised speech."""

    start: float
    text: str
    end: float | None = None
    confidence: float | None = None

    def cleaned(self) -> "Segment":
        """Whitespace-normalised copy.

        Collapsing surrounding whitespace is the only text change the pipeline
        ever makes; no word, form or punctuation mark is altered.
        """
        return Segment(
            start=self.start,
            text=" ".join(self.text.split()),
            end=self.end,
            confidence=self.confidence,
        )


@dataclass
class TranscriptResult:
    segments: list[Segment]
    engine: str
    language: str | None = None
    model: str | None = None
    postprocessed: bool = False
    confidence: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not any(segment.text.strip() for segment in self.segments)

    def mean_confidence(self) -> float | None:
        values = [s.confidence for s in self.segments if s.confidence is not None]
        if self.confidence is not None:
            return self.confidence
        if not values:
            return None
        return sum(values) / len(values)


class TranscriptionBackend:
    """Interface every speech-to-text (or subtitle) backend implements."""

    name = "abstract"
    #: Short description shown by ``transcribe.py --list-backends``.
    summary = ""

    def is_available(self, folder: Path | None = None) -> bool:
        return self.unavailable_reason(folder) is None

    def unavailable_reason(self, folder: Path | None = None) -> str | None:
        """Why this backend cannot run right now, or ``None`` when it can."""
        raise NotImplementedError

    def transcribe(
        self,
        media_path: Path,
        *,
        language: str | None = None,
        folder: Path | None = None,
    ) -> TranscriptResult:
        raise NotImplementedError

    def describe(self, folder: Path | None = None) -> str:
        reason = self.unavailable_reason(folder)
        state = "available" if reason is None else f"unavailable - {reason}"
        return f"{self.name:16} {state}\n{' ' * 17}{self.summary}"
