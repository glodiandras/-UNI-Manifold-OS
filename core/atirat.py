"""A médiafájl átirata (C16): a melléklet-mappa megkeresése és a VTT elemzése a lejátszónak.

`GET /api/media/atirat?ut=<média>` → `{ut, vtt, nyelv, gepi, leiro, cuek: [{k, v, szoveg}], figyelmeztetes}`.

A melléklet-mappa a legacy `vaultlib.sidecar_dir` olvasó szabálya (LEGACY-SZERZODESEK L44): a
videómappán (`<kisero_elotag>Videos`, `[media] video_mappa`) kívül álló médiánál a fájl saját mappája; a videómappában állónál a
`<Téma>/Média/` rétegek közül az, amelyben a törzs `.info.json`-ja vagy forrásleíró `.md`-je áll (a témák
ábécérendjében az első). Nincs találat: üres átirat, hiány és nem tévedés. A felirat `<törzs>.<nyelv>.vtt`
vagy `<törzs>.vtt`; több nyelvnél a beállított elsőbbség (`[media] nyelvek`), utána ábécé. Gépi a felirat, ha
az első 600 bájtjában `NOTE manifold-asr` áll (L44), különben kiadói.

Csak olvas; a vaultba nem ír.
"""
from __future__ import annotations

import os
import re
import unicodedata

from . import kiserok, mediatipus, utkapu
from .utvonalak import HttpError
from .vaultio import Invalid, NotFound, norm_path
from .hibakod import kodol

ALAP_VIDEO_MAPPA = kiserok.alap_mappa("video")
ALAP_RETEG = "Média"
ALAP_NYELVEK = ("hu", "en")
# Az átiratot adó médiatípusok: a videó és a hang a `mediatipus` egyetlen listájából (C20a, T142).
MEDIA_KIT = tuple(k for k, t in mediatipus.MEDIA_TIPUS.items() if t.startswith(("video/", "audio/")))
MAX_VTT = 8 * 1024 * 1024
GEPI_JEL = "NOTE manifold-asr"

_IDO = re.compile(r"^(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})$")
_CIMKE = re.compile(r"</?(?:c|v|b|i|u|ruby|rt|lang)(?:[.\s][^>]*)?>|<\d{1,2}:\d{2}(?::\d{2})?[.,]\d{1,3}>")
_ENTITAS = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&nbsp;": " ", "&lrm;": "‎", "&rlm;": "‏"}


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def beallitasok(cfg) -> dict:
    s = cfg.section("media") if cfg is not None else {}
    nyelvek = s.get("nyelvek", list(ALAP_NYELVEK))
    return {"video_mappa": kiserok.kisero_mappa(cfg, "video"), "reteg": nfc(s.get("reteg_mappa", ALAP_RETEG)),
            "nyelvek": [str(x) for x in nyelvek] if isinstance(nyelvek, list) else list(ALAP_NYELVEK)}


# ---------------------------------------------------------------------- VTT

def ido(szoveg: str) -> float | None:
    """`HH:MM:SS.mmm` / `MM:SS.mmm` (vesszővel is) → másodperc; hibás: None."""
    m = _IDO.match(szoveg.strip())
    if not m:
        return None
    h, p, mp, ms = m.groups()
    if int(p) >= 60 or int(mp) >= 60:
        return None
    return int(h or 0) * 3600 + int(p) * 60 + int(mp) + int(ms.ljust(3, "0")) / 1000


def _tisztit(sor: str) -> str:
    s = _CIMKE.sub("", sor)
    for e, c in _ENTITAS.items():
        s = s.replace(e, c)
    return s.strip()


def elemez(szoveg: str) -> list[dict]:
    """A WebVTT cue-jai `{k, v, szoveg}` alakban, kezdés szerint. A `NOTE`, `STYLE`, `REGION` blokk és a hibás
    időzítésű cue kimarad; a cue-beállítások (`align:` …) és a formázó címkék levágva; a többsoros szöveg egy
    sorba (szóközzel). Az üres szövegű cue kimarad."""
    szoveg = szoveg.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    blokkok = re.split(r"\n[ \t]*\n", szoveg)
    cuek: list[dict] = []
    for i, blokk in enumerate(blokkok):
        sorok = [s for s in blokk.split("\n")]
        while sorok and not sorok[0].strip():
            sorok.pop(0)
        if not sorok:
            continue
        elso = sorok[0].strip()
        if i == 0 and elso.startswith("WEBVTT"):
            continue
        if elso.startswith(("NOTE", "STYLE", "REGION")) and "-->" not in elso:
            continue
        j = next((n for n, s in enumerate(sorok[:2]) if "-->" in s), None)
        if j is None:
            continue
        bal, _, jobb = sorok[j].partition("-->")
        k, v = ido(bal), ido(jobb.strip().split()[0] if jobb.strip() else "")
        if k is None or v is None or v < k:
            continue
        szov = " ".join(t for t in (_tisztit(s) for s in sorok[j + 1:]) if t)
        if szov:
            cuek.append({"k": round(k, 3), "v": round(v, 3), "szoveg": szov})
    cuek.sort(key=lambda c: (c["k"], c["v"]))
    return cuek


_MONDAT_VEG = re.compile(r"[.!?…:;][\"'”’»)\]]*$")
MONDAT_MAX = 400


def mondatok(cuek: list[dict], max_hossz: int = MONDAT_MAX) -> list[tuple[float, str]]:
    """A cue-k mondatokká vonva a kereséshez (C25c): `[(kezdés másodpercben, mondat)…]`. A cue a következővel egy mondat, ha
    nem mondatvégi írásjellel zárul, amíg a mondat `max_hossz` karakternél rövidebb; a mondat ideje az első cue-jának kezdete.
    Az egymás után ismétlődő azonos cue (a gördülő felirat) egyszer számít."""
    ki: list[tuple[float, str]] = []
    kezd, reszek, hossz, elozo = None, [], 0, None
    for c in cuek:
        sz = " ".join(c["szoveg"].split())
        if not sz or sz == elozo:
            continue
        elozo = sz
        if kezd is None:
            kezd = c["k"]
        reszek.append(sz)
        hossz += len(sz) + 1
        if _MONDAT_VEG.search(sz) or hossz >= max_hossz:
            ki.append((kezd, " ".join(reszek)))
            kezd, reszek, hossz = None, [], 0
    if reszek:
        ki.append((kezd, " ".join(reszek)))
    return ki


ABLAK_MP = 60.0
ABLAK_MAX = 2000


def kereso_szakaszok(nyers: bytes, ablak_mp: float = ABLAK_MP, ablak_max: int = ABLAK_MAX) -> list[tuple[str, float, int, list]]:
    """A VTT kereshető szakaszai az indexnek (C25c): a mondatok (soronként egy) legfeljebb `ablak_mp` másodperces, legfeljebb
    `ablak_max` karakteres ablakokban — `[(szöveg, az ablak kezdete, az első sor sorszáma 1-től, [soronkénti kezdő mp])…]`.
    Az ablak a keresés egysége (az „a b” mindkét szava benne legyen), a sor a találat helye. A túl nagy (`MAX_VTT` fölötti) vagy
    cue nélküli felirat üres."""
    if len(nyers) > MAX_VTT:
        return []
    ki: list[tuple[str, float, int, list]] = []
    sorok: list[str] = []
    idok: list[float] = []
    elso = 1
    for i, (k, mondat) in enumerate(mondatok(elemez(nyers.decode("utf-8", errors="replace"))), 1):
        if sorok and (k - idok[0] >= ablak_mp or sum(map(len, sorok)) + len(mondat) > ablak_max):
            ki.append(("\n".join(sorok), idok[0], elso, idok))
            sorok, idok, elso = [], [], i
        sorok.append(nfc(mondat))
        idok.append(k)
    if sorok:
        ki.append(("\n".join(sorok), idok[0], elso, idok))
    return ki


# ---------------------------------------------------------------------- melléklet-keresés

def _listaz(d: str) -> list[str]:
    try:
        return sorted(os.listdir(d))
    except OSError:
        return []


def melleklet_mappa(gyoker: str, rel: str, b: dict) -> str | None:
    """A melléklet-mappa abszolút útja a lemezen (a `rel` média vault-relatív útja), vagy None (nincs találat)."""
    reszek = rel.split("/")
    sajat = os.path.join(gyoker, *reszek[:-1])
    if not (len(reszek) == 2 and nfc(reszek[0]) == b["video_mappa"]):
        return sajat
    torzs = nfc(os.path.splitext(reszek[-1])[0])
    jelek = {torzs + ".info.json", torzs + ".md"}
    for t in _listaz(gyoker):
        if t.startswith(".") or nfc(t) == b["video_mappa"]:
            continue
        q = os.path.join(gyoker, t)
        reteg = next((n for n in _listaz(q) if nfc(n) == b["reteg"]), None)
        if reteg and any(nfc(n) in jelek for n in _listaz(os.path.join(q, reteg))):
            return os.path.join(q, reteg)
    return None


def feliratok(mappa: str, torzs: str, b: dict) -> list[tuple[str, str | None]]:
    """A mappa `<törzs>.vtt` / `<törzs>.<nyelv>.vtt` fájljai `(lemez-név, nyelv)` alakban, elsőbbség szerint."""
    t = nfc(torzs)
    talalat: list[tuple[str, str | None]] = []
    for n in _listaz(mappa):
        nn = nfc(n)
        if not nn.lower().endswith(".vtt"):
            continue
        alap = nn[:-4]
        if alap == t:
            talalat.append((n, None))
        elif alap.startswith(t + ".") and re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", alap[len(t) + 1:]):
            talalat.append((n, alap[len(t) + 1:]))
    rend = {ny: i for i, ny in enumerate(b["nyelvek"])}
    return sorted(talalat, key=lambda x: (rend.get((x[1] or "").split("-")[0].lower(), len(rend)), x[1] or "", x[0]))


_NYELV = re.compile(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*")


def felirat_torzs(nev: str) -> list[str]:
    """A feliratfájl nevéből a lehetséges média-törzsek (`X.hu.vtt` → `["X", "X.hu"]`, `X.vtt` → `["X"]`), a `feliratok`
    névszabályának fordítottja."""
    n = nfc(nev)
    if not n.lower().endswith(".vtt"):
        return []
    alap = n[:-4]
    ki = []
    t, _, ny = alap.rpartition(".")
    if t and _NYELV.fullmatch(ny):
        ki.append(t)
    ki.append(alap)
    return ki


def media_feliratbol(gyoker: str, vtt_rel: str, jeloltek, b: dict) -> str | None:
    """A felirathoz tartozó média vault-útja (C25c: a keresés a VTT-találatot a videó másodpercére nyitja), vagy None. A
    `jeloltek` a vault élő videó- és hangfájljainak útjai (az indexből); az a média tartozik a felirathoz, amelynek a törzse a
    felirat nevéből jön, és amelynek a melléklet-mappája (`melleklet_mappa`, L44) ez a mappa, és a feliratai (`feliratok`) között ez a fájl
    is ott van — a szabály tehát egyetlen helyen él, itt csak visszafelé alkalmazzuk."""
    vtt_rel = nfc(vtt_rel)
    mappa_rel, _, nev = vtt_rel.rpartition("/")
    torzsek = set(felirat_torzs(nev))
    if not torzsek:
        return None
    for ut in sorted(jeloltek):
        m_nev = nfc(ut).rsplit("/", 1)[-1]
        if os.path.splitext(m_nev)[0] not in torzsek or not m_nev.lower().endswith(MEDIA_KIT):
            continue
        mappa = melleklet_mappa(gyoker, ut, b)
        if not mappa:
            continue
        m_rel = nfc(os.path.relpath(mappa, gyoker)).replace(os.sep, "/")
        if (m_rel if m_rel != "." else "") != mappa_rel:
            continue
        if any(nfc(n) == nev for n, _ in feliratok(mappa, os.path.splitext(m_nev)[0], b)):
            return ut
    return None


def atirat(vault, rel) -> dict:
    """A média átirata a lejátszónak (lásd a modul leírását)."""
    rel = norm_path(rel)
    if not rel.lower().endswith(MEDIA_KIT):
        raise kodol(Invalid(f"nem videó- vagy hangfájl: {rel}"), "atirat.video_hangfajl_rel", {"rel": rel})
    p = vault.lemezen(rel)
    if not p.is_file():
        raise kodol(NotFound(f"nincs ilyen fájl: {rel}"), "atirat.nincs_ilyen_fajl_rel", {"rel": rel})
    gyoker = str(vault.root)
    b = beallitasok(vault.cfg)
    torzs = os.path.splitext(rel.rsplit("/", 1)[-1])[0]
    valasz = {"ut": rel, "vtt": None, "nyelv": None, "gepi": None, "leiro": None, "cuek": [], "figyelmeztetes": None}
    mappa = melleklet_mappa(gyoker, rel, b)
    if not mappa:
        return valasz
    mappa_rel = nfc(os.path.relpath(mappa, gyoker)).replace(os.sep, "/")
    leiro = next((n for n in _listaz(mappa) if nfc(n) == nfc(torzs) + ".md"), None)
    if leiro:
        valasz["leiro"] = f"{mappa_rel}/{nfc(leiro)}" if mappa_rel != "." else nfc(leiro)
    jeloltek = feliratok(mappa, torzs, b)
    if not jeloltek:
        return valasz
    nev, nyelv = jeloltek[0]
    f = os.path.join(mappa, nev)
    if not utkapu.belul(gyoker, f):                  # T098: vaulton kívülre mutató symlink tartalma nem kerülhet az átiratba
        valasz["figyelmeztetes"] = "a felirat a vaulton kívülre mutató symlink: nem olvasható"
        return valasz
    try:
        if os.path.getsize(f) > MAX_VTT:
            valasz["figyelmeztetes"] = "a felirat túl nagy, nem töltődött be"
            return valasz
        with open(f, "rb") as fh:
            nyers = fh.read()
    except OSError as e:
        valasz["figyelmeztetes"] = f"a felirat nem olvasható: {e.strerror or e}"
        return valasz
    szoveg = nyers.decode("utf-8", errors="replace")
    valasz.update({"vtt": f"{mappa_rel}/{nfc(nev)}" if mappa_rel != "." else nfc(nev), "nyelv": nyelv,
                   "gepi": GEPI_JEL in nyers[:600].decode("utf-8", errors="replace"), "cuek": elemez(szoveg)})
    if not valasz["cuek"]:
        valasz["figyelmeztetes"] = "a feliratfájlban nincs olvasható cue"
    return valasz


def utvonalak(r) -> None:
    def kezelo(k):
        ut = k.q.get("ut")
        if not ut:
            raise HttpError(400, "hiányzik az `ut`", kod="atirat.hianyzik_ut")
        return atirat(k.app.vault, ut)

    r.get("/api/media/atirat", kezelo)
