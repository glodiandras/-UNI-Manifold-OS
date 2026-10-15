"""Füzetfotó előkészítése a méréshez: kicsinyítés és kivágás a `{tmp}` alá (a vaultban semmi nem változik)."""
from __future__ import annotations

from pathlib import Path


def _nyit(forras: Path):
    from PIL import Image, ImageOps
    return ImageOps.exif_transpose(Image.open(forras)).convert("RGB")


def kicsinyit(forras: Path, cel_mappa: Path, px: int = 1400) -> Path:
    """A fotó a hosszabb oldalán `px`-re kicsinyítve, EXIF szerint elforgatva. Ha már kész, nem készül újra."""
    cel = Path(cel_mappa) / f"{forras.stem}-{px}.jpg"
    if cel.exists() and cel.stat().st_mtime >= forras.stat().st_mtime:
        return cel
    cel.parent.mkdir(parents=True, exist_ok=True)
    im = _nyit(forras)
    im.thumbnail((px, px))
    im.save(cel, quality=90)
    return cel


def kivag(forras: Path, doboz: list[float], cel: Path, px: int = 1200, szegely: float = 0.0) -> Path:
    """A `doboz` (x0, y0, x1, y1; 0–1 arányban, az elforgatott képen) kivágása, legfeljebb `px` szélesen."""
    cel = Path(cel)
    if cel.exists() and cel.stat().st_mtime >= forras.stat().st_mtime:
        return cel
    cel.parent.mkdir(parents=True, exist_ok=True)
    im = _nyit(forras)
    sz, m = im.size
    x0, y0, x1, y1 = doboz
    x0, y0 = max(0.0, x0 - szegely), max(0.0, y0 - szegely)
    x1, y1 = min(1.0, x1 + szegely), min(1.0, y1 + szegely)
    resz = im.crop((int(x0 * sz), int(y0 * m), int(x1 * sz), int(y1 * m)))
    resz.thumbnail((px, px))
    resz.save(cel, quality=92)
    return cel


def oldalak(forras: Path, cel_mappa: Path, px: int = 1400, atfedes: float = 0.04) -> list[Path]:
    """A füzetfotó oldalképei: fekvő fotó (két oldal) → bal és jobb fél kis átfedéssel, álló fotó → egy kép.
    Mindegyik a hosszabb oldalán `px` (a legacy olvasó oldalmérete). A forgatást nem javítja: az elforgatott
    fotó a mérés része."""
    cel_mappa = Path(cel_mappa)
    jelolo = cel_mappa / f"{forras.stem}-{px}.kesz"
    if jelolo.exists() and jelolo.stat().st_mtime >= forras.stat().st_mtime:
        return [cel_mappa / n for n in jelolo.read_text(encoding="utf-8").split("\n") if n]
    cel_mappa.mkdir(parents=True, exist_ok=True)
    im = _nyit(forras)
    sz, m = im.size
    if sz >= 1.15 * m:
        fel = sz / 2
        reszek = [("bal", im.crop((0, 0, int(fel * (1 + atfedes)), m))),
                  ("jobb", im.crop((int(fel * (1 - atfedes)), 0, sz, m)))]
    else:
        reszek = [("egesz", im)]
    nevek = []
    for nev, resz in reszek:
        resz.thumbnail((px, px))
        ki = cel_mappa / f"{forras.stem}-{px}-{nev}.jpg"
        resz.save(ki, quality=90)
        nevek.append(ki.name)
    jelolo.write_text("\n".join(nevek), encoding="utf-8")
    return [cel_mappa / n for n in nevek]
