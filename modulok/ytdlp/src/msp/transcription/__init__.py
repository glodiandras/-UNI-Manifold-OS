"""Pluggable transcription layer.

Transcription is deliberately decoupled from downloading (spec section 10):
a download only ever creates a ``transcript_status: pending`` placeholder, and
a separate run fills it in with whichever backend is available.

Fidelity rule: the text is written exactly as the engine produced
it. No punctuation repair, no paraphrasing, no "tidying up" - a beautified
transcript cannot serve as a character-exact quote source later. Any deviation
must be recorded in ``transcript_postprocessed``.
"""

from .base import Segment, TranscriptResult, TranscriptionBackend
from .registry import (
    available_backends,
    backend_status,
    describe_backends,
    get_backend,
    select_backend,
)
from .writer import render_transcript_body, write_transcript

__all__ = [
    "Segment",
    "TranscriptResult",
    "TranscriptionBackend",
    "available_backends",
    "backend_status",
    "describe_backends",
    "get_backend",
    "select_backend",
    "render_transcript_body",
    "write_transcript",
]
