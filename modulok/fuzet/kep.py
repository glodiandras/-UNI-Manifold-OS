"""A füzetfotó előkészítése (C21, 11. pont): papírkivágás, oldalpárra bontás, forgatás — modell nélkül.

A legacy `fuzet.oldalak`, `fuzet.papir_arany`, `fuzet_eros.kivagas` és `fuzet_eros.lapok` 1:1-es portja (a számok a legacy
`calibration.json → fuzet` kalibrációjából):

- **a papír** a legnagyobb, képszélt nem érintő világos folt (Otsu-küszöb, legalább 120, a 600 px-es szürke képen; morfológiai
  nyitás); a legnagyobb folt 15%-ánál nagyobb belső foltok befoglalója. A laptop és a kéz a képszélen áll, kiesik;
- **a vágás** a spirál sötét sávjánál, a középső 40%-ban (a profil minimuma); fekvő papírnál bal/jobb, álló papírnál (oldalra
  fordított füzet) felső/alsó oldal — az álló oldalakat a hívó forgatja (`forgatas`), a ±90° irányt egy rövid próbaolvasás dönti el;
- **hihetőség** (`kivagas`): ha a kivágás területe a kép 20%-ánál kisebb, vagy a közepe a 0,25–0,75 sávon kívül esik, a kivágás nem
  hihető („teljes”): fekvő fotón a teljes kép két fele (a spirálnál vágva), álló fotón az egész kép egyben, forgatás nélkül
  (mérve a legacyben 2026-09-26: a hibás kivágás 0,01–0,18 vagy a kép szélén; a valóban oldalra fordított füzet ≥ 0,23, középen).

Az **olvashatóság** (I7): a ≥ 4 betűs szavak hány %-a szótő-egyezik (5 betűs, ékezet nélküli előtag) a vault szókincsével — az
elforgatott oldal irányai közül ez választ. A vaultban semmi nem változik: a képek a hívó `{tmp}` mappájába íródnak.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

VERZIO = "kep-2026-10-07.1"            # a gyorsítótárazott oldalképek kulcsa (a vágás szabálya ezzel változik)
OLDAL_PX = 1400                        # a legacy `olvaso.oldal_hossz_px`-e: az olvasó oldalmérete
MERO_PX = 600                          # a folt-keresés képmérete
PAPIR_MIN_TERULET = 0.2                # `fuzet.eros.papir_min_terulet`
PAPIR_KOZEP = (0.25, 0.75)             # `fuzet.eros.papir_kozep`
# A próbaolvasás irányai (PIL: pozitív = az óramutatóval ellentétes). A legacy csak a ±90°-ot próbálta; a C21 kézi ellenőrzése
# (2026-10-07, a 9 álló papírú aranyfotó oldalképe mindhárom irányban megnézve) szerint 2 fotón (IMG_1545, IMG_1557) a papír
# egyenesen álló lap, a felső/alsó fele forgatás nélkül olvasható — ezért a 0° is jelölt. Döntetlennél a sorrend dönt (−90° elöl).
FORGATASOK = (-90, 90, 0)
KEP_KITERJESZTESEK = (".jpg", ".jpeg", ".png", ".heic")      # a legacy `fuzet.kep_ext`-je
STOP = frozenset(
    "a az és is vagy hogy nem de ha mint egy ez azt ami van vannak lesz csak még már meg fel le ki be el át rá ide oda itt ott "
    "minden sem mert akkor pedig illetve igaz hamis feladat feladatok példa megoldás".split())
_SZO = re.compile(r"[^\wáéíóöőúüűÁÉÍÓÖŐÚÜŰ]+")


@dataclass
class Elokeszites:
    """Egy fotó oldalképei: `kivagas` („papir” | „teljes”), `fekvo` (igaz: nincs forgatás), `lapok`: [(név, kép)]."""
    kivagas: str
    fekvo: bool
    lapok: list = field(default_factory=list)


def kep_e(nev: str) -> bool:
    return nev.lower().endswith(KEP_KITERJESZTESEK) and not nev.startswith(".")


def sha256(ut: str | Path) -> str:
    h = hashlib.sha256()
    with open(ut, "rb") as f:
        for d in iter(lambda: f.read(1 << 20), b""):
            h.update(d)
    return h.hexdigest()


def betolt(ut: str | Path, tmp: str | Path | None = None):
    """A kép RGB-ben, az EXIF-forgatással. A HEIC-et (a Pillow nem olvassa) a `sips` alakítja JPEG-gé a `tmp` alá."""
    from PIL import Image, ImageOps
    ut = Path(ut)
    try:
        im = Image.open(ut)
        im.load()
    except Exception:  # noqa: BLE001 — a nem olvasható formátum (HEIC) a sips-szel
        if tmp is None or not shutil.which("sips"):
            raise
        cel = Path(tmp) / f"{ut.name}.jpg"
        cel.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["sips", "-s", "format", "jpeg", str(ut), "--out", str(cel)], check=True, capture_output=True)
        im = Image.open(cel)
    return ImageOps.exif_transpose(im).convert("RGB")


def _otsu(g) -> int:
    import numpy as np
    h, _ = np.histogram(g, bins=256, range=(0, 256))
    p = h / max(h.sum(), 1)
    w = np.cumsum(p)
    mu = np.cumsum(p * np.arange(256))
    with np.errstate(divide="ignore", invalid="ignore"):
        s = (mu[-1] * w - mu) ** 2 / (w * (1 - w) + 1e-12)
    return int(np.nanargmax(s))


def _foltok(im):
    """A kicsinyített szürke kép (`g`), a mérete és a papír befoglalója `(x0, y0, x1, y1)` a kicsinyített képen (None: nincs folt)."""
    import numpy as np
    from scipy import ndimage as ndi
    sm = im.copy()
    sm.thumbnail((MERO_PX, MERO_PX))
    g = np.asarray(sm.convert("L"), dtype=np.float32)
    m = ndi.binary_opening(g > max(_otsu(g), 120), iterations=2)
    lab, n = ndi.label(m)
    H, W = m.shape
    if not n:
        return g, sm.size, None
    darabok = []
    for sl, sz in zip(ndi.find_objects(lab), ndi.sum(m, lab, range(1, n + 1))):
        y0, y1, x0, x1 = sl[0].start, sl[0].stop, sl[1].start, sl[1].stop
        darabok.append((sz, y0 == 0 or x0 == 0 or y1 == H or x1 == W, (x0, y0, x1, y1)))
    belso = [d for d in darabok if not d[1]] or darabok
    nagy = max(d[0] for d in belso)
    bb = [d[2] for d in belso if d[0] > 0.15 * nagy]
    return g, sm.size, (min(b[0] for b in bb), min(b[1] for b in bb), max(b[2] for b in bb), max(b[3] for b in bb))


def papir_arany(im) -> tuple[float, float]:
    """A papírkivágás hihetősége: (a kivágás területe / a kép területe, a kivágás közepének vízszintes helye 0..1-en)."""
    g, (W, H), bb = _foltok(im)
    if bb is None:
        return 1.0, 0.5
    x0, y0, x1, y1 = bb
    return (x1 - x0) * (y1 - y0) / float(W * H), (x0 + x1) / 2.0 / W


def kivagas(im) -> str:
    """„papir” (a megszokott papírkivágás) vagy „teljes”, ha a kivágás nem hihető."""
    ter, kozep = papir_arany(im)
    lo, hi = PAPIR_KOZEP
    return "papir" if ter >= PAPIR_MIN_TERULET and lo <= kozep <= hi else "teljes"


def oldalak(im, teljes: bool = False, px: int = OLDAL_PX) -> tuple[bool, list]:
    """Papírkivágás és oldalpárra bontás → (fekvő, [(név, kép)]). `teljes=True`: kivágás nélkül, a teljes képből."""
    import numpy as np
    g, (W, H), bb = _foltok(im)
    x0, y0, x1, y1 = bb if (bb is not None and not teljes) else (0, 0, W, H)
    s = im.width / W
    im = im.crop((int(x0 * s), int(y0 * s), int(x1 * s), int(y1 * s)))
    g = g[y0:y1, x0:x1]
    w, h = im.size
    fekvo = w >= h
    prof = g.mean(0) if fekvo else g.mean(1)
    nn = len(prof)
    a, b_ = int(nn * 0.3), int(nn * 0.7)
    vag = (a + int(np.argmin(prof[a:b_]))) / nn if b_ > a else 0.5
    if fekvo:
        c = int(w * vag)
        fel = [("bal", im.crop((0, 0, c, h))), ("jobb", im.crop((c, 0, w, h)))]
    else:
        c = int(h * vag)
        fel = [("felso", im.crop((0, 0, w, c))), ("also", im.crop((0, c, w, h)))]
    ki = []
    for nev, p in fel:
        p = p.copy()
        p.thumbnail((px, px))
        ki.append((nev, p))
    return fekvo, ki


def elokeszit(im, px: int = OLDAL_PX) -> Elokeszites:
    """A legacy `fuzet_eros.lapok(kivagas(...))`: az 1. lépés oldalképei (forgatás nélkül)."""
    kiv = kivagas(im)
    if kiv == "papir":
        fekvo, lapok = oldalak(im, px=px)
    elif im.width >= im.height:
        fekvo, lapok = oldalak(im, teljes=True, px=px)
    else:
        egesz = im.copy()
        egesz.thumbnail((px, px))
        fekvo, lapok = True, [("egesz", egesz)]
    return Elokeszites(kiv, fekvo, lapok)


def forgat(kep, fok: int | None):
    return kep.rotate(fok, expand=True) if fok else kep


def ment(kep, ut: str | Path, quality: int = 90) -> Path:
    ut = Path(ut)
    ut.parent.mkdir(parents=True, exist_ok=True)
    tmp = ut.with_name(f".{ut.name}.{os.getpid()}.manifold-tmp")
    kep.save(tmp, format="JPEG", quality=quality)
    os.replace(tmp, ut)
    return ut


def oldalkepek(forras: str | Path, cel_mappa: str | Path, forgatas: int | None = None, px: int = OLDAL_PX) -> tuple[dict, list[Path]]:
    """A fotó oldalképei a `cel_mappa` alatt (gyorsítótárazva: a forrás mtime-ja és a `VERZIO` a kulcs) → (meta, utak).

    `meta`: `{"kivagas", "fekvo", "lapok": [név…]}`. `forgatas` (csak álló papírnál értelmes): a lapok ennyi fokkal elforgatva
    (a forgatott változat a forgatás nélküli oldalképből készül, külön fájlba)."""
    import json
    forras, cel_mappa = Path(forras), Path(cel_mappa)
    torzs = f"{forras.stem}-{px}-{VERZIO}"
    jelolo = cel_mappa / f"{torzs}.json"
    meta = None
    if jelolo.exists() and jelolo.stat().st_mtime >= forras.stat().st_mtime:
        try:
            meta = json.loads(jelolo.read_text(encoding="utf-8"))
            if not all((cel_mappa / f"{torzs}-{n}.jpg").is_file() for n in meta["lapok"]):
                meta = None
        except (OSError, ValueError, KeyError):
            meta = None
    if meta is None:
        e = elokeszit(betolt(forras, cel_mappa), px)
        for nev, lap in e.lapok:
            ment(lap, cel_mappa / f"{torzs}-{nev}.jpg")
        meta = {"kivagas": e.kivagas, "fekvo": e.fekvo, "lapok": [n for n, _ in e.lapok]}
        tmp = jelolo.with_name(f".{jelolo.name}.{os.getpid()}.manifold-tmp")
        tmp.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, jelolo)
    utak = [cel_mappa / f"{torzs}-{n}.jpg" for n in meta["lapok"]]
    if forgatas:
        from PIL import Image
        forgatott = []
        for u in utak:
            cel = u.with_name(f"{u.stem}-r{forgatas}.jpg")
            if not (cel.is_file() and cel.stat().st_mtime >= u.stat().st_mtime):
                with Image.open(u) as im:
                    ment(forgat(im.convert("RGB"), forgatas), cel)
            forgatott.append(cel)
        utak = forgatott
    return meta, utak


# ---------------------------------------------------------------- olvashatóság (I7)

def hajt(s: str) -> str:
    """Kisbetű, ékezet nélkül."""
    d = unicodedata.normalize("NFKD", unicodedata.normalize("NFC", s or "").lower())
    return "".join(c for c in d if not unicodedata.combining(c))


def tovek(s: str, n: int = 5) -> list[str]:
    """A legacy `fuzet.tokenek(s, 5)`-je ékezet nélkül: szóhatár, betűk, ≥ 4 betű, stopszó ki, `n` betűs előtag."""
    ki = []
    for w in _SZO.split(unicodedata.normalize("NFC", s or "").lower()):
        w = "".join(ch for ch in w if ch.isalpha())
        if len(w) >= 4 and w not in STOP:
            ki.append(hajt(w)[:n])
    return ki


def olvashatosag(szoveg: str, szokincs: set[str]) -> float:
    ws = tovek(szoveg)
    return sum(1 for w in ws if w in szokincs) / len(ws) if ws else 0.0


def forgatas_dontes(olvasatok: dict[int, str], szokincs: set[str]) -> tuple[int, dict[int, float]]:
    """A próbaolvasások (irány → szöveg) közül a vault szókincsével legjobban egyező irány; döntetlennél a legacy alapja (−90°)."""
    pont = {fok: round(olvashatosag(olvasatok.get(fok) or "", szokincs), 4) for fok in FORGATASOK}
    legjobb = FORGATASOK[0]
    for fok in FORGATASOK:
        if pont[fok] > pont[legjobb]:
            legjobb = fok
    return legjobb, pont
