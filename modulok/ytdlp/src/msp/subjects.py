"""Subject (school subject) resolution and normalisation.

The staging folder layout is ``<Provider>/<Subject>/<Title>/``. The subject
name should match the Manifold vault's own taxonomy character for character
(accents and capitalisation included), because that removes the need for a
mapping table at integration time - see open decision #3 in CLAUDE.md.

Priority, highest first:

1. ``--subject`` on the command line
2. a ``| Subject`` hint in a batch URL list
3. a provider heuristic (metadata categories/tags, URL path segments)
4. ``organization.default_subject``
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from .config import Config
from .naming import sanitize_component, slugify


@dataclass(frozen=True)
class SubjectResolution:
    """The chosen subject plus where it came from (recorded in the manifest)."""

    name: str
    source: str  # cli | batch-hint | metadata | url | default
    in_taxonomy: bool


def _fold(text: str) -> str:
    """Accent-insensitive, case-insensitive comparison key."""
    decomposed = unicodedata.normalize("NFKD", str(text or ""))
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.casefold().strip()


def normalize_subject(value: str | None, config: Config) -> tuple[str | None, bool]:
    """Map a raw subject string onto the configured taxonomy.

    Returns ``(canonical_name_or_None, is_in_taxonomy)``. Unknown values are
    returned sanitized but unchanged - the pipeline records what it was told
    and validate.py reports it as a warning rather than inventing a subject.
    """
    if value is None:
        return None, False
    raw = str(value).strip()
    if not raw:
        return None, False

    taxonomy = config.subjects.taxonomy
    for entry in taxonomy:
        if entry == raw:
            return entry, True

    alias_target = config.subjects.aliases.get(slugify(raw)) or config.subjects.aliases.get(_fold(raw))
    if alias_target:
        return alias_target, alias_target in taxonomy

    for entry in taxonomy:
        if _fold(entry) == _fold(raw):
            return entry, True

    return sanitize_component(raw, fallback="Besorolatlan"), False


def _candidates_from_info(info: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("categories", "tags"):
        items = info.get(key)
        if isinstance(items, list):
            values.extend(str(item) for item in items if item)
    for key in ("category", "series", "season", "playlist_title", "channel", "uploader"):
        value = info.get(key)
        if isinstance(value, str) and value:
            values.append(value)
    return values


def _candidates_from_url(url: str) -> list[str]:
    path = urlparse(str(url)).path or ""
    return [segment for segment in path.split("/") if segment]


def _searchable_text(info: dict[str, Any]) -> str:
    """Title, description, tags and channel folded into one comparable string."""
    parts: list[str] = []
    for key in ("title", "description", "channel", "uploader", "playlist_title", "series"):
        value = info.get(key)
        if isinstance(value, str):
            parts.append(value)
    for key in ("tags", "categories"):
        items = info.get(key)
        if isinstance(items, list):
            parts.extend(str(item) for item in items if item)
    return _fold(" ".join(parts))


def match_keywords(text: str, config: Config) -> tuple[str, int] | None:
    """Score the configured topic words against *text*.

    Returns ``(subject, hits)`` for the best match, or None. Matching is accent-
    and case-insensitive substring matching on purpose: Hungarian suffixes
    ("kozepkorban" contains "kozepkor") would otherwise need a stemmer. A tie is
    broken by the longest matched word, i.e. the more specific one.
    """
    best: tuple[str, int, int] | None = None  # subject, hits, longest match
    for subject, words in config.subjects.keywords.items():
        hits = [folded for folded in (_fold(word) for word in words) if folded and folded in text]
        if not hits:
            continue
        candidate = (subject, len(hits), max(len(hit) for hit in hits))
        if best is None or (candidate[1], candidate[2]) > (best[1], best[2]):
            best = candidate
    return (best[0], best[1]) if best else None


def guess_subject(url: str, info: dict[str, Any] | None, config: Config) -> tuple[str, str] | None:
    """Heuristic subject guess. Returns ``(subject, source)`` or ``None``.

    Only *known* names are accepted here: a heuristic is allowed to recognise
    "tortenelem" in a URL, but it must never invent a brand-new subject folder
    out of an arbitrary tag.
    """
    info = info or {}
    for candidate in _candidates_from_info(info):
        name, known = normalize_subject(candidate, config)
        if name and known:
            return name, "metadata"
    # The requested URL first: on an embedding site (zanza.tv -> YouTube) the
    # subject lives in the requested page's path, not in the media URL.
    seen: set[str] = set()
    for candidate_url in (url, info.get("webpage_url")):
        if not candidate_url or candidate_url in seen:
            continue
        seen.add(str(candidate_url))
        for candidate in _candidates_from_url(str(candidate_url)):
            name, known = normalize_subject(candidate, config)
            if name and known:
                return name, "url"
    # Last resort: topic words in the title/description. A platform like
    # YouTube carries no subject anywhere in the URL, so without this every
    # video from there would land in the default folder and wait for manual
    # sorting. The guess is recorded as subject_source: "keywords", so it stays
    # visible that it was inferred from the text and not read off the source.
    keyword_match = match_keywords(_searchable_text(info), config)
    if keyword_match:
        name, known = normalize_subject(keyword_match[0], config)
        if name and known:
            return name, "keywords"
    return None


def resolve_subject(
    url: str,
    info: dict[str, Any] | None,
    config: Config,
    *,
    explicit: str | None = None,
    hint: str | None = None,
) -> SubjectResolution:
    """Pick the subject folder for a source."""
    if explicit:
        name, known = normalize_subject(explicit, config)
        if name:
            return SubjectResolution(name, "cli", known)
    if hint:
        name, known = normalize_subject(hint, config)
        if name:
            return SubjectResolution(name, "batch-hint", known)
    guessed = guess_subject(url, info, config)
    if guessed:
        name, source = guessed
        return SubjectResolution(name, source, True)
    default_name, known = normalize_subject(config.organization.default_subject, config)
    return SubjectResolution(default_name or "Besorolatlan", "default", known)
