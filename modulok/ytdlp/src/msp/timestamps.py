"""Zero-padded ``HH:MM:SS`` timestamps and video anchors.

The Manifold vault anchors every claim to a page (``[[FILE.pdf#page=NN]]``).
For a video the equivalent is a timestamp, so the format has to be stable to
the character - ``00:01:32``, never ``1:32`` or ``92s`` (spec section 9).
"""

from __future__ import annotations

import re

TIMESTAMP_RE = re.compile(r"\A(\d{2,}):([0-5]\d):([0-5]\d)\Z")
TIMESTAMP_LINE_RE = re.compile(r"\A\[(\d{2,}:[0-5]\d:[0-5]\d)\]\s*\Z")


def format_timestamp(seconds: float | int) -> str:
    """Seconds -> ``HH:MM:SS`` (hours grow past 99, never wrap)."""
    if seconds is None:
        raise ValueError("seconds must not be None")
    total = int(float(seconds))
    if total < 0:
        raise ValueError(f"negative timestamp: {seconds}")
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def parse_timestamp(value: str) -> int:
    """``HH:MM:SS`` -> seconds. Raises ``ValueError`` on any other shape."""
    match = TIMESTAMP_RE.match(str(value).strip())
    if not match:
        raise ValueError(f"not a zero-padded HH:MM:SS timestamp: {value!r}")
    hours, minutes, seconds = (int(part) for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def is_valid_timestamp(value: str) -> bool:
    return bool(TIMESTAMP_RE.match(str(value).strip()))


def timestamp_marker(seconds: float | int) -> str:
    """The line the transcript writer emits: ``[00:01:32]``."""
    return f"[{format_timestamp(seconds)}]"


def video_anchor(media_file: str, seconds: float | int) -> str:
    """``[[video.mp4#t=00:01:32]]`` - the video counterpart of a page anchor.

    Provided for later integration tooling; the staging pipeline itself only
    writes plain ``[HH:MM:SS]`` markers, because whether video timestamps may
    become vault anchors at all is still the vault owner's open decision.
    """
    return f"[[{media_file}#t={format_timestamp(seconds)}]]"
