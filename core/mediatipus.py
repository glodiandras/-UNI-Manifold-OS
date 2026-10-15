"""A média-kiterjesztések EGYETLEN helye (C20a; 2. audit T142).

Eddig négy egymástól független lista élt (`vaultio.MEDIA_TIPUS`, az `os.toml` `kizar` médiamintái, az `atirat.MEDIA_KIT`
és az `indexelo._KIT_TIPUS`), és eltértek (avif, bmp, heif, tif, m4v, ogv, flac, ogg, opus, aac, 3gp, svg): egy ilyen
fájl szövegként került volna a pillanatkép-tárba. Ebből a modulból jön:

- a média-URL kiszolgálható típusai (`MEDIA_TIPUS`: kiterjesztés → Content-Type),
- a pillanatképből kizárt bináris kiterjesztések (`BINARIS_KITERJESZTESEK`, `kizar_mintak()`),
- a bináris mozgásnapló leltára (L19, `core/binaris_naplo.py`),
- az `.apkg`-import médiájának fehérlistája (`APKG_MEDIA`, 55(b)).

Csak a standard könyvtár: a `snapshot`, a `vaultio`, a `doctor` és a `binaris_naplo` körkörös import nélkül használhatja.
"""
from __future__ import annotations

import os

# A média-URL-en (`/media/<token>/<út>`) kiszolgálható fájlok: kiterjesztés → Content-Type (nem találgatott).
MEDIA_TIPUS = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp",
    ".avif": "image/avif", ".bmp": "image/bmp", ".svg": "image/svg+xml", ".heic": "image/heic",
    ".heif": "image/heif", ".tif": "image/tiff", ".tiff": "image/tiff",
    ".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm",
    ".mkv": "video/x-matroska", ".ogv": "video/ogg",
    ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".wav": "audio/wav", ".flac": "audio/flac", ".ogg": "audio/ogg",
    ".opus": "audio/ogg", ".aac": "audio/aac", ".3gp": "audio/3gpp",
    ".pdf": "application/pdf",
}

# Bináris, de nem a média-URL-en kiszolgált fájlok, amelyek a pillanatképbe sem kerülhetnek (a vault szöveges tár, 14. döntés):
# az index által felismert `.avi`, a dokumentum-/archívumformátumok, a WKWebView által nem játszott, de a letöltő által hozott
# médiakonténerek (`.mts`, `.mpg`, `.wmv`, `.aiff`; Javító 3, A3-09) és a videólánc átmeneti/megőrzött fájljai: a konvertálás előtti
# eredeti (`video.mkv.eredeti`) és a yt-dlp félkész letöltései (`.part`, `.ytdl`, `.temp`) — egy ilyen több GB-os fájl a staging
# `ytdlp.git`-jébe, onnan a belső lemezes bundle-be kerülhetett volna.
EGYEB_BINARIS = (".avi", ".epub", ".zip", ".pages", ".docx", ".pptx", ".xlsx",
                 ".mts", ".mpg", ".wmv", ".aiff", ".eredeti", ".part", ".ytdl", ".temp")

# Az Anki-csomag (`.apkg`) médiájából a vaultba vihető kiterjesztések (55(b), 83. döntés javaslata): a média-URL képei, hangjai és
# videói, KIVÉVE az `.svg`-t (szkriptet hordozhat, és a média-URL-en saját dokumentumként nyílna meg) és a `.pdf`-et (az Anki
# médiája nem dokumentum). Minden más (szkript, HTML, archívum, ismeretlen) kimarad, megnevezve.
APKG_MEDIA = tuple(sorted(k for k, t in MEDIA_TIPUS.items()
                          if k not in (".svg", ".pdf") and t.split("/")[0] in ("image", "audio", "video")))

# A pillanatképből kizárt (bináris) kiterjesztések: a média teljes listája + az egyéb bináris. A szöveges típusok
# (`.md`, `.canvas`, `.base`, `.txt`, `.vtt`, `.srt`, `.json`, …) a `vaultio.SZOVEGES` listán élnek.
BINARIS_KITERJESZTESEK = tuple(sorted({*MEDIA_TIPUS, *EGYEB_BINARIS}))


def kiterjesztes(ut: str) -> str:
    """Az út kisbetűs kiterjesztése ponttal (`""`, ha nincs)."""
    return os.path.splitext(str(ut))[1].lower()


def tipus(ut: str) -> str | None:
    """A média Content-Type-ja, vagy `None`, ha a kiterjesztés nem média."""
    return MEDIA_TIPUS.get(kiterjesztes(ut))


def media_e(ut: str) -> bool:
    return kiterjesztes(ut) in MEDIA_TIPUS


def binaris_e(ut: str) -> bool:
    """Bináris (pillanatképből kizárt) kiterjesztésű-e az út."""
    return kiterjesztes(ut) in BINARIS_KITERJESZTESEK


def kizar_mintak() -> list[str]:
    """A bináris kiterjesztések git-kizárási mintái, rendezve, kis- és nagybetűvel is (`*.mp4`, `*.MP4`): a
    `core.ignorecase=true` APFS-tárban a git amúgy is kis-nagybetű-független, a kis-nagybetűs fájlrendszerű tárban viszont nem."""
    out: list[str] = []
    for kit in BINARIS_KITERJESZTESEK:
        for minta in (f"*{kit}", f"*{kit.upper()}"):
            if minta not in out:
                out.append(minta)
    return out
