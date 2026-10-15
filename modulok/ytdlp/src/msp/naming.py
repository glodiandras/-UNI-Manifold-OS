"""Filename, folder-name and identifier generation.

Two independent requirements meet here:

* **Filesystem safety** - macOS (and, for portability, Windows) forbid a set of
  characters and reserved names; a component must stay inside 255 UTF-8 bytes;
  nothing coming from a remote page may ever escape the staging root
  (path traversal, spec section 23).
* **Obsidian safety** - the generated notes link to each other with wikilinks,
  and ``[``, ``]``, ``#``, ``^``, ``|`` break a ``[[wikilink]]``. They are
  therefore removed from every name that can appear inside a link.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path

# Characters that are illegal on some filesystem, plus the ones that break an
# Obsidian wikilink. Replaced with a single separator.
_UNSAFE_CHARS = re.compile(r'[\\/:*?"<>|\[\]#^\x00-\x1f\x7f]')
_WHITESPACE = re.compile(r"\s+")
_MULTI_DASH = re.compile(r"-{2,}")
_SLUG_STRIP = re.compile(r"[^a-z0-9]+")

_RESERVED_NAMES = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}

MAX_COMPONENT_BYTES = 120
"""Conservative cap per path component.

The macOS limit is 255 bytes, but a source folder name is later concatenated
with provider/subject folders and an iCloud path, so 120 leaves head-room and
keeps names readable.
"""


def _truncate_bytes(text: str, max_bytes: int) -> str:
    """Cut a string to *max_bytes* UTF-8 bytes without splitting a character."""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    cut = encoded[:max_bytes]
    while cut:
        try:
            return cut.decode("utf-8").rstrip()
        except UnicodeDecodeError:
            cut = cut[:-1]
    return ""


def sanitize_component(
    name: str,
    *,
    max_bytes: int = MAX_COMPONENT_BYTES,
    fallback: str = "untitled",
) -> str:
    """Turn arbitrary remote text into one safe path component.

    The result never contains a path separator, never equals ``.`` or ``..``,
    never ends in a dot or space, and is safe inside an Obsidian wikilink.
    """
    text = unicodedata.normalize("NFC", str(name or ""))
    text = _UNSAFE_CHARS.sub("-", text)
    text = _WHITESPACE.sub(" ", text)
    text = _MULTI_DASH.sub("-", text)
    text = text.strip(" .-_")
    text = _truncate_bytes(text, max_bytes).strip(" .-_")
    if not text or text in {".", ".."}:
        return fallback
    if text.lower() in _RESERVED_NAMES or text.split(".")[0].lower() in _RESERVED_NAMES:
        text = f"_{text}"
    return text


def sanitize_filename(stem: str, extension: str | None = None, *, fallback: str = "file") -> str:
    """Sanitize a file name, keeping a (sanitized) extension."""
    safe_stem = sanitize_component(stem, fallback=fallback)
    if not extension:
        return safe_stem
    safe_ext = re.sub(r"[^A-Za-z0-9]", "", str(extension))[:12].lower()
    return f"{safe_stem}.{safe_ext}" if safe_ext else safe_stem


def slugify(text: str, *, fallback: str = "source") -> str:
    """ASCII slug (``Zanza.tv`` -> ``zanza-tv``) for identifiers."""
    decomposed = unicodedata.normalize("NFKD", str(text or ""))
    ascii_text = decomposed.encode("ascii", "ignore").decode("ascii").lower()
    slug = _SLUG_STRIP.sub("-", ascii_text).strip("-")
    slug = _MULTI_DASH.sub("-", slug)
    return slug or fallback


def short_hash(text: str, length: int = 10) -> str:
    """Stable short digest, used when a provider exposes no usable video id."""
    digest = hashlib.sha1(str(text).encode("utf-8")).hexdigest()
    return digest[:length]


def sanitize_id_part(value: str, *, max_length: int = 48) -> str:
    """Keep an upstream video id usable as an identifier fragment.

    Case is preserved (YouTube ids are case sensitive); only characters that
    would be unsafe in a filename or a wikilink are replaced.
    """
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "-", str(value or "")).strip("-.")
    cleaned = _MULTI_DASH.sub("-", cleaned)
    return cleaned[:max_length]


def make_source_id(provider_slug: str, video_id: str | None, url: str) -> str:
    """Build the stable ``<provider>-<id>`` source identifier.

    Uses the platform's own video id when there is one (spec section 6), and
    falls back to a hash of the canonical URL otherwise. The fallback is marked
    with a ``u`` prefix so that a hashed id is recognisable at a glance.
    """
    provider = slugify(provider_slug)
    ident = sanitize_id_part(video_id) if video_id else ""
    if not ident:
        ident = f"u{short_hash(url)}"
    return f"{provider}-{ident}"


def ensure_within(base: Path, candidate: Path) -> Path:
    """Guarantee that *candidate* stays inside *base* (path-traversal guard)."""
    from .errors import FilesystemError

    base_resolved = Path(base).expanduser().resolve()
    candidate_resolved = Path(candidate).expanduser().resolve()
    if base_resolved != candidate_resolved and base_resolved not in candidate_resolved.parents:
        raise FilesystemError(
            f"Refusing to write outside the staging root: {candidate_resolved} is not inside {base_resolved}"
        )
    return candidate_resolved
