"""A füzetlánc (C21) core-oldali segédei: a figyelt mappák és a fotók OCR-szövege az indexnek.

- **Figyelt mappák** (`figyelt_mappak`): a `{fuzet_bejovo}` (a felületen behúzott fotók beérkező mappája) és a `[fuzet] mappak`
  vaulton KÍVÜLI mappái, feloldott úton. A gépi írás `mozgat` művelete csak ezek alól visz fotót a vaultba, és a visszavonás
  (L19) csak ide hozhatja vissza (a bináris napló rekordja szerint, azonossággal).
- **OCR-szöveg** (7. pont): a lánc a fotó átiratát (`ocr_kezi`) a `{fuzet}/ocr.json`-ba írja (fájlnév → sha256, méret, szöveg); az
  indexelő a `kep` típusú fájl FTS-sorába ezt teszi, ha a fájlnév és a méret egyezik. A vaultba nem kerül semmi.
  Az átirat elejéről a modell bevezetője („Természetesen, itt van…”) és a kódkerítés levágódik (`atirat_tisztit`).
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import time
import os
import re
import threading
import unicodedata
from pathlib import Path

from . import utkapu

OCR_FAJL = "ocr.json"
KEP_KITERJESZTESEK = (".jpg", ".jpeg", ".png", ".heic")      # a legacy `fuzet.kep_ext`-je (L36)
_zar = threading.Lock()
_gyorsitotar: dict = {}

# a modell bevezető mondata (C19, docs/MERES-2026-10-07.md 4.: „Természetesen, itt van az átirat…”): az első sor, ha ilyen (a tartalom első sora sosem esik ki: a gyengébb jelöltnél kettőspont és „átirat/szöveg” kell)
_BEVEZETO = re.compile(r"\A\s*(?:(?:természetesen|persze|íme|rendben|sure|here is|here's)\b[^\n]{0,200}"
                       r"|[^\n]{0,120}(?:átirat|szöveg|olvasható|transcri)[^\n]{0,80}:)[ \t]*\n", re.I)
_KERITES = re.compile(r"\A\s*```[a-zA-Z]*[ \t]*\n(.*?)\n?```\s*\Z", re.S)


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s or "")


def sha256(ut: str | Path) -> str:
    h = hashlib.sha256()
    with open(ut, "rb") as f:
        for d in iter(lambda: f.read(1 << 20), b""):
            h.update(d)
    return h.hexdigest()


def figyelt_mappak(cfg) -> list[Path]:
    """A figyelt mappák feloldott útja (létezőtől függetlenül); a vaulton belüli (vagy a vaultot tartalmazó) mappa kimarad."""
    vault = Path(os.path.realpath(cfg.path("vault")))
    jeloltek = [cfg.path("fuzet_bejovo")]
    for m in (cfg.section("fuzet").get("mappak") or []):
        if isinstance(m, str) and m.strip():
            try:
                jeloltek.append(Path(os.path.expanduser(cfg.expand(m.strip()))))
            except (KeyError, ValueError):
                continue
    ki: list[Path] = []
    for m in jeloltek:
        if not m.is_absolute():
            continue
        r = Path(os.path.realpath(m))
        if r == vault or utkapu.alatta(vault, r) or utkapu.alatta(r, vault):
            continue
        if r not in ki:
            ki.append(r)
    return ki


def figyelt_alatt(cfg, ut: str | Path) -> Path | None:
    """A figyelt mappa, amelynek az `ut` (feloldva) szigorúan alatta áll; különben None."""
    for m in figyelt_mappak(cfg):
        if utkapu.alatta(m, ut):
            return m
    return None


# ---------------------------------------------------------------- OCR-szöveg

def atirat_tisztit(s: str | None) -> str:
    """Az átirat a modell bevezetője és a körülölelő kódkerítés nélkül (a gondolkodás-blokk is kiesik)."""
    if not isinstance(s, str):
        return ""
    s = re.sub(r"<think>.*?</think>", "", s, flags=re.S).strip()
    for _ in range(2):
        m = _BEVEZETO.match(s)
        if m:
            s = s[m.end():].lstrip("\n")
        k = _KERITES.match(s)
        if k:
            s = k.group(1)
    return s.strip()


def ocr_ut(cfg) -> Path:
    return cfg.path("fuzet") / OCR_FAJL


def _betolt(ut: Path) -> dict:
    try:
        st = ut.stat()
    except OSError:
        return {}
    kulcs = (str(ut), st.st_mtime_ns, st.st_size)
    with _zar:
        if _gyorsitotar.get("kulcs") == kulcs:
            return _gyorsitotar["adat"]
    try:
        adat = json.loads(ut.read_text(encoding="utf-8"))
        if not isinstance(adat, dict):
            adat = {}
    except (OSError, ValueError):
        adat = {}
    with _zar:
        _gyorsitotar.update(kulcs=kulcs, adat=adat)
    return adat


def ocr_szoveg(cfg, nev: str, meret: int) -> str:
    """A fotó (vault-beli fájlnév) OCR-szövege az indexnek; üres, ha nincs, vagy a méret nem egyezik (más fájl, ugyanazzal a névvel)."""
    r = _betolt(ocr_ut(cfg)).get(nfc(nev).casefold())
    if not isinstance(r, dict) or r.get("meret") != meret:
        return ""
    return r.get("szoveg") or ""


def ocr_ir(cfg, nev: str, sha256: str, meret: int, szoveg: str) -> None:
    """Egy fotó OCR-szövegének rögzítése (atomi csere; a lánc lépése hívja a vaultba írás ELŐTT, hogy az indexelő már lássa)."""
    ut = ocr_ut(cfg)
    with zar(cfg):
        try:
            adat = json.loads(ut.read_text(encoding="utf-8"))
            if not isinstance(adat, dict):
                adat = {}
        except (OSError, ValueError):
            adat = {}
        adat[nfc(nev).casefold()] = {"nev": nfc(nev), "sha256": sha256, "meret": int(meret), "szoveg": atirat_tisztit(szoveg)}
        tmp = ut.with_name(f".{ut.name}.{os.getpid()}.manifold-tmp")
        tmp.write_text(json.dumps(adat, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, ut)
        _gyorsitotar.clear()


# ---------------------------------------------------------------- a lánc állapota (I33: a vaulton kívül) és a visszavonás (L20)

ALLAPOT_FAJL = "allapot.json"
NAPLO_FAJL = "naplo.jsonl"


@contextlib.contextmanager
def zar(cfg):
    """Folyamatközi zár a `{fuzet}` állapotfájljaira (a lánc lépése és a core visszavonása is ír)."""
    d = cfg.path("fuzet")
    d.mkdir(parents=True, exist_ok=True)
    with open(d / ".zar", "a+") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def most() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def allapot_betolt(cfg) -> dict:
    """{sha256: rekord} — a fotók állapota: `kep` (a vaultbeli név), `forras`, `allapot` (`bekotve` | `hiba` | `visszavonva` |
    `kihagyva`), `bekotve` (jegyzetek), `kor`, `commit`, `ellenorzes` (az átkötések előzménye), `uzenet`, `ido`."""
    try:
        adat = json.loads((cfg.path("fuzet") / ALLAPOT_FAJL).read_text(encoding="utf-8"))
        return adat if isinstance(adat, dict) else {}
    except (OSError, ValueError):
        return {}


def _allapot_ment(cfg, st: dict) -> None:
    ut = cfg.path("fuzet") / ALLAPOT_FAJL
    tmp = ut.with_name(f".{ut.name}.{os.getpid()}.manifold-tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, ut)


def allapot_frissit(cfg, sha: str, **mezok) -> dict:
    with zar(cfg):
        st = allapot_betolt(cfg)
        rec = {**st.get(sha, {}), **mezok, "ido": most()}
        st[sha] = rec
        _allapot_ment(cfg, st)
    return rec


def naplo(cfg, esemeny: str, **kw) -> None:
    d = cfg.path("fuzet")
    d.mkdir(parents=True, exist_ok=True)
    with open(d / NAPLO_FAJL, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ido": most(), "esemeny": esemeny, **kw}, ensure_ascii=False) + "\n")


def _illik(commit: str | None, shak: list[str]) -> bool:
    c = (commit or "").lower()
    return len(c) >= 7 and any(len(s) >= 7 and (c.startswith(s.lower()) or s.lower().startswith(c)) for s in shak)


def visszavonas_utan(cfg, shak: list[str], kor: str | None = None) -> int:
    """L20: a visszavont gépi tételek hatása a lánc állapotára (a core `undo` hívja, a kör-zár alatt). A `mos-fuzet` bekötés
    visszavonása → „visszavonva” (a figyelő nem veszi újra; a fotó a bináris napló szerint a forrásmappájába tért vissza); a
    `mos-fuzet-ellenor` átkötésé → a régi kötés áll vissza. → az érintett fotók száma."""
    if not (cfg.path("fuzet") / ALLAPOT_FAJL).is_file():
        return 0
    n = 0
    with zar(cfg):
        st = allapot_betolt(cfg)
        for r in st.values():
            el = list(r.get("ellenorzes") or [])
            for i in range(len(el) - 1, -1, -1):          # az átkötés (mos-fuzet-ellenor) visszavonása: a régi kötés
                e = el[i]
                if not e.get("visszavonva") and (_illik(e.get("commit"), shak) or (kor and e.get("kor") == kor)):
                    el[i] = {**e, "visszavonva": most()}
                    r.update(bekotve=e.get("regi") or [], allapot="bekotve", ellenorzes=el, ido=most())
                    n += 1
                    break
            else:
                if r.get("allapot") == "bekotve" and (_illik(r.get("commit"), shak) or (kor and r.get("kor") == kor)):
                    r.update(allapot="visszavonva", visszavonva=most(), ido=most())
                    n += 1
        if n:
            _allapot_ment(cfg, st)
    if n:
        naplo(cfg, "visszavonas", commitok=list(shak), kor=kor, foto=n)
    return n
