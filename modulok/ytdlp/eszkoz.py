"""A videólánc pinelt eszközei (Javító 3, A3-17/A3-18): az ffmpeg a `[utak] ffmpeg`-ből és hash-ellenőrzéssel fut, nem a környezetből.

A `bin/mos video eszkoz-ellenorzes` és a `doctor` eddig csak jelentett; a lánc futáskor a `MOS_FFMPEG`-et vagy bármely létező
`ffmpeg_location`-t használta, így az ellenőrzött és a futtatott bináris eltérhetett (47(a)). Most a futás előtt a `[utak] ffmpeg`
sha256-ja egyezik a `config/runtime-pins.env` `FFMPEG_BIN_SHA256`-jával, különben **zárva hibázik**: a hiányzó pin is hiba (a pin nélküli
bináris nem bizonyítottan a pinelt build), a PATH-os, home-beli vagy környezeti tartalék nincs.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path


class EszkozHiba(RuntimeError):
    """A pinelt eszköz hiányzik vagy nem az, amit rögzítettünk (a lánc nem indul)."""


def sha256(ut: str | Path) -> str:
    h = hashlib.sha256()
    with open(ut, "rb") as f:
        for blokk in iter(lambda: f.read(1 << 20), b""):
            h.update(blokk)
    return h.hexdigest()


def pin(cfg, kulcs: str) -> str | None:
    """Egy érték a `config/runtime-pins.env`-ből."""
    p = cfg.root / "config" / "runtime-pins.env"
    if p.is_file():
        m = re.search(rf"^{kulcs}=(\S+)", p.read_text(encoding="utf-8"), re.M)
        return m.group(1) if m else None
    return None


def ffmpeg_ellenorzott(cfg) -> Path:
    """A `[utak] ffmpeg` útja, ha létezik, futtatható, és a sha256-ja egyezik a rögzítettel; különben `EszkozHiba` (magyar üzenettel)."""
    ff = cfg.path("ffmpeg")
    if not (ff.is_file() and os.access(ff, os.X_OK)):
        raise EszkozHiba(f"hiányzik a pinelt ffmpeg ({ff}): bin/mos runtime fetch ffmpeg (a home-beli és a PATH-os ffmpeg tiltott)")
    rogzitett = pin(cfg, "FFMPEG_BIN_SHA256")
    if not rogzitett:
        raise EszkozHiba("nincs rögzített FFMPEG_BIN_SHA256 a config/runtime-pins.env-ben: a pin nélküli ffmpeg nem futtatható")
    van = sha256(ff)
    if van.lower() != rogzitett.lower():
        raise EszkozHiba(f"az ffmpeg sha256-ja eltér a rögzítettől ({van[:12]}… ≠ {rogzitett[:12]}…): {ff} — bin/mos runtime fetch ffmpeg")
    return ff
