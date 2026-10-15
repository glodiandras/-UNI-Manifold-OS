"""Kicsinyített képek a média-végponton (C11a, audit M9, a legacy L55 gyorsítótára): `/media/<token>/<út>?w=N`.

A WebView egy 8064×6048 px-es fotót ~195 MB bitmapként dekódol; egy 26 fotós jegyzet ezért több GB-ot és
folyamatos CPU-t kér (Kézi kör F1). A beágyazott kép a megjelenített szélességnek megfelelő változatot kéri,
az eredetit csak kattintásra.

- A `w` vödörre kerekül felfelé (400, 800, 1600 → kevés gyorsítótár-fájl); a legnagyobb vödörnél nagyobb kérés a
  1600-ast kapja (a `w` nélküli kérés az eredeti, a nagyításé). Ha a vödör nem kisebb az eredeti (megjelenített)
  szélességnél, az eredeti megy ki — másolat nem készül.
- A gyorsítótár a `{vault_kepek}` alatt él (`var/cache/vault-kepek`, bármikor törölhető, a vaultba nem írunk);
  a kulcs az út, az mtime, a méret és a vödör: a módosult kép új kulcsot kap.
- JPEG-nél `Image.draft` (DCT-skálázás: a dekódolás a kért méret közelében marad), az EXIF-tájolás érvényesül,
  az ICC-profil megmarad (a telefonok Display P3 képei); alfás kép PNG-ként, a többi JPEG-ként tárolódik.
- Kulcsonkénti zár (ugyanazt egyszer generáljuk) és egy globális szemafor (egyszerre legfeljebb 2 dekódolás);
  az írás ideiglenes fájllal és `os.replace`-szel. A zárak egy rögzített zártömbből jönnek a kulcs hash-e szerint
  (C33, T177): a korábbi kulcsonkénti szótár korlátlanul nőtt.
- Bármilyen hiba (sérült kép, dekompressziós bomba, hiányzó Pillow): az eredeti fájl megy ki, ahogy a `w` nélkül.
  A bukás kulcsonként megjegyzett (`BUKAS_LEJARAT_MP`, legfeljebb `BUKAS_MAX` kulcs): a lejáratig ugyanaz a kép
  (út, mtime, méret, vödör) nem dekódolódik újra, és a bukás egyszer kerül a naplóba (2026-10-14, F1).
- **Takarítás** (C33, T177): a bejegyzés mellett egy kis kísérőfájl (`<kulcs>.forras`: az út, az mtime és a méret) áll, így
  az árva (a forrás eltűnt vagy módosult) bejegyzés felismerhető; a `takarit` ezeket törli, majd a méretkorlát
  (`[media] kepek_max_mb`, alap 500) és a kor (`kepek_max_nap`, alap 90) szerint LRU-ban (a találat a kísérő mtime-ját frissíti; a kép mtime-ja az ETag része, nem változik).
  Az indulás után a D8-szünettel és a rendezett leálláskor (időkerettel) fut; csak a saját `{vault_kepek}` mappájában töröl.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import threading
import time
import uuid
from collections import OrderedDict
from pathlib import Path

VODROK = (400, 800, 1600)
KICSINYITHETO = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/bmp", "image/tiff", "image/avif"}
JPEG_MINOSEG = 85
MAX_MB = 500                    # a gyorsítótár mérete fölött a legrégebben használt bejegyzések törlődnek (T177)
MAX_NAP = 90                    # az ennél régebben használt bejegyzés törlődik
FORRAS_KIT = ".forras"
BUKAS_LEJARAT_MP = 600          # a bukott kicsinyítés/poszter ennyi ideig nem próbálkozik újra (ugyanazon a kulcson)
BUKAS_MAX = 1024                # a bukás-memó legfeljebb ennyi kulcsot tart (a legrégebbi esik ki)
_szemafor = threading.BoundedSemaphore(2)
_ZARTOMB = tuple(threading.Lock() for _ in range(64))
_bukasok: "OrderedDict[str, float]" = OrderedDict()
_bukas_zar = threading.Lock()


def _bukott(kulcs: str) -> bool:
    """A kulcs a közelmúltban bukott (a lejárat előtt): ne próbáljuk újra."""
    with _bukas_zar:
        lejar = _bukasok.get(kulcs)
        if lejar is None:
            return False
        if lejar <= time.monotonic():
            del _bukasok[kulcs]
            return False
        return True


def _bukas(kulcs: str, mit: str, p: Path, hiba: object) -> None:
    """A bukás megjegyzése (lejárattal, korlátos méretben) és egyetlen naplósor; a vault-útból csak a fájlnév kerül ki."""
    with _bukas_zar:
        uj = kulcs not in _bukasok
        _bukasok[kulcs] = time.monotonic() + BUKAS_LEJARAT_MP
        _bukasok.move_to_end(kulcs)
        while len(_bukasok) > BUKAS_MAX:
            _bukasok.popitem(last=False)
    if uj:
        print(f"[kepek] {mit} nem sikerült ({p.name}): {type(hiba).__name__ if isinstance(hiba, BaseException) else hiba}; "
              f"{BUKAS_LEJARAT_MP // 60} percig nem próbálkozunk újra", file=sys.stderr, flush=True)


def vodor(w: int) -> int:
    """A kért szélesség vödre: a legkisebb vödör, amely legalább `w`; a legnagyobbnál nagyobb kérés a legnagyobbat kapja."""
    return next((v for v in VODROK if v >= w), VODROK[-1])


def _zar(kulcs: str) -> threading.Lock:
    """A kulcs zára a rögzített zártömbből (a kulcs sha1-hexa: az első 4 jegye egyenletes)."""
    return _ZARTOMB[int(kulcs[:4], 16) % len(_ZARTOMB)]


def _kulcs(p: Path, st: os.stat_result, v: int) -> str:
    return hashlib.sha1(f"{p}|{st.st_mtime_ns}|{st.st_size}|{v}".encode("utf-8", "surrogateescape")).hexdigest()


def _talalat(mappa: Path, kulcs: str) -> tuple[Path, str] | None:
    for kit, tipus in ((".jpg", "image/jpeg"), (".png", "image/png")):
        c = mappa / kulcs[:2] / (kulcs + kit)
        if c.is_file():
            try:
                # LRU: a használat ideje a KÍSÉRŐ mtime-jában (az APFS atime-ja nem megbízható; a kép mtime-ja a média-válasz
                # ETag-jének része, azt nem érintjük — különben a böngésző gyorsítótára minden találatnál elavulna)
                os.utime(c.with_suffix(FORRAS_KIT))
            except OSError:
                pass
            return c, tipus
    return None


def _forras_jel(p: Path, st: os.stat_result) -> str:
    return f"{st.st_mtime_ns}|{st.st_size}|{p}"


def kicsinyitett(cfg, p: Path, tipus: str, w: int) -> tuple[Path, str]:
    """A `p` kép `w` szélességű (vödörre kerekített) változata és típusa; az eredeti, ha nincs mit kicsinyíteni."""
    if tipus not in KICSINYITHETO:
        return p, tipus
    v = vodor(w)
    kulcs = None
    try:
        st = p.stat()
        mappa = cfg.path("vault_kepek")
        kulcs = _kulcs(p, st, v)
        t = _talalat(mappa, kulcs)
        if t:
            return t
        if _bukott(kulcs):
            return p, tipus
        with _zar(kulcs):
            t = _talalat(mappa, kulcs)             # közben egy másik kérés elkészíthette
            if t:
                return t
            if _bukott(kulcs):                     # közben egy másik kérés megbukott rajta
                return p, tipus
            with _szemafor:
                return _keszit(p, mappa, kulcs, v) or (p, tipus)
    except Exception as e:  # noqa: BLE001 — a kicsinyítés hibája nem akadályozhatja a kép kiszolgálását
        if kulcs is not None:
            _bukas(kulcs, "a kicsinyítés", p, e)
        return p, tipus


def _keszit(p: Path, mappa: Path, kulcs: str, v: int) -> tuple[Path, str] | None:
    from PIL import Image, ImageOps

    with Image.open(p) as im:
        ow, oh = im.size
        if im.format in ("GIF", "WEBP", "PNG", "AVIF") and getattr(im, "n_frames", 1) > 1:
            return None                            # animált kép: az eredeti (a telefonok MPO-JPEG-je nem ilyen)
        forgatott = im.getexif().get(0x0112, 1) in (5, 6, 7, 8)
        if v >= (oh if forgatott else ow):         # a megjelenített szélesség: forgatásnál a magasság
            return None
        if im.format in ("JPEG", "MPO"):
            im.draft("RGB", (v, v))                # a skála mindkét oldalon ≥ v marad
        icc = im.info.get("icc_profile")
        kep = ImageOps.exif_transpose(im)
        kep.thumbnail((v, 100_000), Image.Resampling.LANCZOS)
        alfas = kep.mode in ("RGBA", "LA") or (kep.mode == "P" and "transparency" in kep.info)
        kit, tipus = (".png", "image/png") if alfas else (".jpg", "image/jpeg")
        kep = kep.convert("RGBA" if alfas else "RGB")
        cel = mappa / kulcs[:2] / (kulcs + kit)
        cel.parent.mkdir(parents=True, exist_ok=True)
        tmp = cel.with_name(f".{kulcs}.{uuid.uuid4().hex[:8]}.tmp")
        try:
            if alfas:
                kep.save(tmp, "PNG", optimize=True, icc_profile=icc)
            else:
                kep.save(tmp, "JPEG", quality=JPEG_MINOSEG, optimize=True, icc_profile=icc)
            # a kísérőfájl ELŐBB: a takarítás a kísérő nélküli bejegyzést régi (C33 előtti) gyorsítótárnak veszi
            (cel.parent / (kulcs + FORRAS_KIT)).write_text(_forras_jel(p, p.stat()), encoding="utf-8", errors="surrogateescape")
            os.replace(tmp, cel)
        finally:
            tmp.unlink(missing_ok=True)
    return cel, tipus


def _arva(kiseret: Path) -> bool:
    """A bejegyzés forrása eltűnt vagy módosult (a kísérőfájl szerint). Kísérő nélkül (régi bejegyzés): nem árva, csak LRU."""
    try:
        mtime, meret, ut = kiseret.read_text(encoding="utf-8", errors="surrogateescape").split("|", 2)
    except (OSError, ValueError):
        return False
    try:
        st = os.stat(ut)
    except OSError:
        return True
    return str(st.st_mtime_ns) != mtime or str(st.st_size) != meret


def takarit(cfg, max_mb: float | None = None, max_nap: float | None = None, hatarido_mp: float | None = None) -> dict:
    """A kicsinyített képek gyorsítótárának takarítása (T177): az árva bejegyzések, a `max_nap`-nál régebben használtak,
    és a `max_mb` fölötti rész a legrégebben használttól. Csak a `{vault_kepek}` alatt töröl (`.jpg`/`.png`/`.forras`/
    elhagyott `.tmp`). → `{torolve, arva, maradt_mb, ido_ms, levagva}`; `hatarido_mp`: időkeret (a leálláskor)."""
    t0 = time.monotonic()
    b = cfg.section("media") if hasattr(cfg, "section") else {}
    max_mb = float(b.get("kepek_max_mb", MAX_MB) if max_mb is None else max_mb)
    max_nap = float(b.get("kepek_max_nap", MAX_NAP) if max_nap is None else max_nap)
    mappa = Path(cfg.path("vault_kepek"))
    ki = {"torolve": 0, "arva": 0, "maradt_mb": 0.0, "ido_ms": 0, "levagva": False}
    if not mappa.is_dir():
        return ki
    most = time.time()
    bejegyzesek: list[tuple[float, int, Path]] = []

    def torol(f: Path) -> None:
        for x in (f, f.with_suffix(FORRAS_KIT)):
            try:
                x.unlink()
            except FileNotFoundError:
                pass
        ki["torolve"] += 1

    for al in mappa.iterdir():
        if hatarido_mp is not None and time.monotonic() - t0 > hatarido_mp:
            ki["levagva"] = True
            break
        if not al.is_dir() or al.is_symlink():
            continue
        for f in al.iterdir():
            try:
                if f.suffix == ".tmp" and most - f.stat().st_mtime > 3600:
                    f.unlink()
                    continue
                if f.suffix not in (".jpg", ".png"):
                    if f.suffix == FORRAS_KIT and not (f.with_suffix(".jpg").exists() or f.with_suffix(".png").exists()):
                        f.unlink()                           # a kép nélkül maradt kísérő
                    continue
                st = f.stat()
                try:
                    hasznalt = max(st.st_mtime, f.with_suffix(FORRAS_KIT).stat().st_mtime)
                except OSError:
                    hasznalt = st.st_mtime                   # kísérő nélküli (C33 előtti) bejegyzés: a kép ideje
                if _arva(f.with_suffix(FORRAS_KIT)):
                    torol(f)
                    ki["arva"] += 1
                elif most - hasznalt > max_nap * 86400:
                    torol(f)
                else:
                    bejegyzesek.append((hasznalt, st.st_size, f))
            except OSError:
                continue
    ossz = sum(m for _, m, _ in bejegyzesek)
    korlat = max_mb * 1024 * 1024
    for _, meret, f in sorted(bejegyzesek):                  # a legrégebben használt elöl
        if ossz <= korlat:
            break
        try:
            torol(f)
        except OSError:
            continue
        ossz -= meret
    ki["maradt_mb"] = round(ossz / 1024 / 1024, 1)
    ki["ido_ms"] = round((time.monotonic() - t0) * 1000)
    if ki["torolve"]:
        print(f"[kepek] a kicsinyített képek gyorsítótára: {ki['torolve']} bejegyzés törölve ({ki['arva']} árva), "
              f"maradt {ki['maradt_mb']} MB", file=sys.stderr, flush=True)
    return ki


# ---------------------------------------------------------------------- videó-poszter (E14)

POSZTER_SZEL = 800                    # a beágyazott videó előnézetének szélessége (egy vödör: 800)
POSZTER_ALAP_MP = 1.0                 # az „első értelmes képkocka”: ~1 mp (a 0. kocka gyakran fekete)
POSZTER_IDOKORLAT_MP = 25
_poszter_szemafor = threading.BoundedSemaphore(1)
_ffmpeg_ellenorzott: dict[str, tuple] = {}


def _ffmpeg(cfg) -> Path:
    """A pinelt ffmpeg (a videólánc 55(a) szabályai: `[utak] ffmpeg`, sha256 a `runtime-pins.env`-ből, zárva hibázik).
    Az ellenőrzés eredménye az út, az mtime és a méret kulcsán megjegyzett (a hash egy ~70 MB-os fájlon kérésenként drága)."""
    from modulok.ytdlp import eszkoz

    ff = cfg.path("ffmpeg")
    st = ff.stat()
    jel = (st.st_mtime_ns, st.st_size, eszkoz.pin(cfg, "FFMPEG_BIN_SHA256"))
    if _ffmpeg_ellenorzott.get(str(ff)) != jel:
        eszkoz.ffmpeg_ellenorzott(cfg)
        _ffmpeg_ellenorzott[str(ff)] = jel
    return ff


def poszter(cfg, p: Path, t: float | None = None) -> tuple[Path, str] | None:
    """A `p` videó előnézeti képe (JPEG, `POSZTER_SZEL` széles) a `t`. másodpercnél (alap ~1 mp; a videó végén túli idő a 0.
    kockára esik). A pinelt ffmpeg készíti (`-nostdin`, csak `file` protokoll, időkorlát, egyszerre egy); a gyorsítótár a
    kicsinyített képeké (`{vault_kepek}`, `.forras` kísérővel: a `takarit` LRU-ja és árva-takarítása erre is áll), a kulcs az
    út, az mtime, a méret és az időpont. Bármilyen hiba (hiányzó/hibás ffmpeg, sérült videó, időtúllépés) → `None`: a hívó 404-et
    ad, a felület a poszter nélküli videóra esik vissza. A vaultba nem ír."""
    kulcs = None
    try:
        t = POSZTER_ALAP_MP if t is None else max(0.0, min(float(t), 86400.0))
        st = p.stat()
        mappa = cfg.path("vault_kepek")
        kulcs = _kulcs(p, st, f"poszter{POSZTER_SZEL}-{t:.2f}")
        talalt = _talalat(mappa, kulcs)
        if talalt:
            return talalt
        if _bukott(kulcs):
            return None
        with _zar(kulcs):
            talalt = _talalat(mappa, kulcs)
            if talalt:
                return talalt
            if _bukott(kulcs):
                return None
            with _poszter_szemafor:
                ff = _ffmpeg(cfg)
                cel = mappa / kulcs[:2] / (kulcs + ".jpg")
                cel.parent.mkdir(parents=True, exist_ok=True)
                tmp = cel.with_name(f".{kulcs}.{uuid.uuid4().hex[:8]}.tmp")
                try:
                    ok: object = "üres kimenet"
                    for mikor in ((t, 0.0) if t > 0 else (0.0,)):
                        tmp.unlink(missing_ok=True)
                        cmd = [str(ff), "-nostdin", "-v", "error", "-protocol_whitelist", "file", "-ss", f"{mikor:.3f}", "-i", str(p),
                               "-frames:v", "1", "-vf", f"scale='min({POSZTER_SZEL},iw)':-2", "-q:v", "3", "-f", "image2", "-y", str(tmp)]
                        try:
                            subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                           timeout=POSZTER_IDOKORLAT_MP, check=True)
                        except subprocess.TimeoutExpired as e:
                            ok = e
                            break                  # időtúllépés: a 0. kockánál sem lenne gyorsabb, a szemafort nem tartjuk tovább
                        except (subprocess.SubprocessError, OSError) as e:
                            ok = e
                            continue
                        if tmp.is_file() and tmp.stat().st_size > 0:
                            break
                    else:
                        _bukas(kulcs, "a videó-előnézet", p, ok)
                        return None
                    if not (tmp.is_file() and tmp.stat().st_size > 0):
                        _bukas(kulcs, "a videó-előnézet", p, ok)
                        return None
                    (cel.parent / (kulcs + FORRAS_KIT)).write_text(_forras_jel(p, p.stat()), encoding="utf-8", errors="surrogateescape")
                    os.replace(tmp, cel)
                finally:
                    tmp.unlink(missing_ok=True)
                return cel, "image/jpeg"
    except Exception as e:  # noqa: BLE001 — a poszter hibája nem akadályozhatja a videó kiszolgálását
        if kulcs is not None:
            _bukas(kulcs, "a videó-előnézet", p, e)
        return None
