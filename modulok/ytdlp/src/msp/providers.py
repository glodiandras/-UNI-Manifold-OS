"""Provider identity (folder name + id prefix) derived from a URL/info dict.

The pipeline must not be YouTube- or Zanza-specific (spec section 30), so a
provider is resolved generically:

* the **slug** (``zanza``, ``youtube``) comes from the registrable part of the
  host name and becomes the ``source_id`` prefix;
* the **display name** (``Zanza``, ``YouTube``) is the staging folder name and
  can be overridden per host or per yt-dlp extractor key in
  ``organization.provider_names``.

Sites without a dedicated yt-dlp extractor (zanza.tv today) are handled by the
generic extractor; that is why the host, not the extractor key, is the primary
source of identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from .config import Config
from .naming import sanitize_component, slugify

# Hosts that are the same service under different names.
_HOST_ALIASES = {
    "youtu.be": "youtube.com",
    "m.youtube.com": "youtube.com",
    "music.youtube.com": "youtube.com",
    "www.youtube.com": "youtube.com",
}

_KNOWN_DISPLAY_NAMES = {
    "youtube.com": "YouTube",
    "vimeo.com": "Vimeo",
    "zanza.tv": "Zanza",
}


@dataclass(frozen=True)
class Provider:
    """Identity of the platform a source came from."""

    slug: str
    display_name: str
    host: str
    extractor: str

    @property
    def folder_name(self) -> str:
        return sanitize_component(self.display_name, fallback="Web")


def normalize_host(url: str) -> str:
    """Lowercase host without ``www.``/mobile prefixes, aliases collapsed."""
    host = (urlparse(str(url)).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return _HOST_ALIASES.get(host, host)


def host_slug(host: str) -> str:
    """``m.youtube.com`` -> ``youtube``; ``zanza.tv`` -> ``zanza``."""
    labels = [label for label in host.split(".") if label]
    if not labels:
        return ""
    if len(labels) == 1:
        return slugify(labels[0], fallback="")
    return slugify(labels[-2], fallback="")


def resolve_provider(url: str, info: dict[str, Any] | None, config: Config) -> Provider:
    """Determine the provider for a URL (+ optional yt-dlp info dict).

    Identity follows the **requested** URL, not the resolved media URL. Sites
    like zanza.tv host no video of their own: they embed a YouTube player, so
    yt-dlp reports ``webpage_url`` on youtube.com. The source being staged is
    still the zanza.tv page the owner asked for - that is what a later citation
    would name - while the fact that the stream came from YouTube is preserved
    in metadata.json (``extractor``, ``webpage_url``) and in source.md
    (``media_url``).
    """
    info = info or {}
    host = normalize_host(url) or normalize_host(info.get("webpage_url") or "")
    extractor = str(info.get("extractor_key") or info.get("extractor") or "generic")

    names = config.organization.provider_names
    lookup_keys = [host, host_slug(host), extractor, extractor.lower()]
    display = next((names[key] for key in lookup_keys if key and key in names), None)
    if display is None:
        display = _KNOWN_DISPLAY_NAMES.get(host)
    if display is None and extractor and extractor.lower() not in {"generic", ""}:
        display = extractor
    if display is None:
        display = host or "Web"

    slug = host_slug(host) or slugify(extractor, fallback="source")
    return Provider(slug=slug, display_name=str(display), host=host, extractor=extractor)
