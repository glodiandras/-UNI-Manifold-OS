"""A jegyzetbe írható ```plot blokk (C35a; docs/PLOT-FORMATUM.md, docs/C35-TERV.md): formátum, determinisztikus felismerés,
CAS-jellemzők. Ez a csomag a **szülő-oldali burok**: a CAS-könyvtárat nem importálja. A jegyzet sorai nem megbízható bemenet
(CLAUDE.md 46. döntés), ezért a felismerés és az elemzés a CAS-homokozó gyermekében fut (`grafikon.felismeres`,
`grafikon.elemzes` művelet, `muveletek.py`); a kivágás (`jegyzet.py`) és a blokk szövege (`formatum.py`) CAS-import nélküli.

    felismer(keplet)                         → javaslat-szótár (`bizonyossag`: biztos | bizonytalan | nincs)
    felismer_jegyzet(szoveg, mindet=False)   → javaslatok jegyzetbeli sorral és „már van blokk alatta” jelzéssel
    elemzes(kifejezes, ablak)                → zérushely, szélsőérték, aszimptota az ablakon
    elemzesek([kifejezes…], ablak)           → ugyanez több függvényre, egy gyermekben

Ha a homokozó nem fut, az eredmény `nem_ellenorizheto` (felismerés) vagy `homokozo_hiba` (elemzés), magyar
üzenettel; csupasz, elzáratlan számítás nincs. A C35b (modell-ág, automatikus írás) ezt a burkot hívja.
"""
from __future__ import annotations

from . import formatum as F
from . import jegyzet as J

MAX_FUGGVENY = 8                  # egy elemzés-kérésben (a core API és a CLI is ezt tartja)


def _homokozo(homokozo):
    if homokozo is not None:
        return homokozo
    from homokozo import Homokozo
    return Homokozo()


def _nem_ellenorizheto(keplet: str, e: dict) -> dict:
    return {"allapot": "nem_ellenorizheto", "fajta": "nem_abra", "bizonyossag": "ismeretlen",
            "ok": f"homokozó: {e['allapot']} — {e['uzenet']}", "forras_keplet": keplet, "kulcs": "", "abra": None,
            "blokk": ""}


def _felismeres_eredmeny(keplet: str, e: dict) -> dict:
    return e["ertek"] if e["allapot"] == "ok" else _nem_ellenorizheto(keplet, e)


def _felismeres_feladat(keplet: str) -> dict:
    return {"muvelet": "hivas", "nev": "grafikon.felismeres", "args": {"keplet": keplet}}


def felismerek(kepletek: list[str], homokozo=None) -> list[dict]:
    """Több képlet felismerése egy gyermekben (a SymPy-import egyszer fizetődik)."""
    hk = _homokozo(homokozo)
    return [_felismeres_eredmeny(k, e) for k, e in zip(kepletek, hk.futtat([_felismeres_feladat(k) for k in kepletek]))]


def felismer(keplet: str, homokozo=None) -> dict:
    return felismerek([keplet], homokozo=homokozo)[0]


def felismer_jegyzet(szoveg: str, mindet: bool = False, homokozo=None) -> list[dict]:
    """A jegyzet képletei (és TikZ/pgfplots blokkjai) → javaslatok. A kivágás itt, a felismerés kifejezésenként a
    gyermekben fut (egy gyermek, így a SymPy-import egyszer fizetődik); alapból a `nincs` tételek kimaradnak."""
    szoveg = szoveg or ""
    jelolt = J.jeloltek(szoveg)
    if not jelolt:
        return []
    blokkok = F.blokkok(szoveg)
    ki = []
    for (i, k), j in zip(jelolt, felismerek([k for _, k in jelolt], homokozo=homokozo)):
        if j["bizonyossag"] == "nincs" and not mindet:
            continue
        ki.append({**j, **J.hely(szoveg, i, k, blokkok)})
    return ki


def _elemzes_feladat(kifejezes: str, ablak, lepes: float) -> dict:
    return {"muvelet": "hivas", "nev": "grafikon.elemzes",
            "args": {"kifejezes": kifejezes, "ablak": list(ablak), "lepes_idokorlat_s": lepes},
            "idokorlat_s": lepes * 6 + 2}


def elemzesek(kifejezesek: list[str], ablak, homokozo=None, lepes_idokorlat_s: float | None = None) -> list[dict]:
    hk = _homokozo(homokozo)
    lepes = float(lepes_idokorlat_s if lepes_idokorlat_s is not None else hk.beall["lepes_idokorlat_s"])
    ki = []
    for e in hk.futtat([_elemzes_feladat(k, ablak, lepes) for k in kifejezesek], idokorlat_s=lepes * 6 + 2):
        ki.append(e["ertek"] if e["allapot"] == "ok"
                  else {"allapot": "homokozo_hiba", "uzenet": f"homokozó: {e['allapot']} — {e['uzenet']}"})
    return ki


def elemzes(kifejezes: str, ablak, homokozo=None, lepes_idokorlat_s: float | None = None) -> dict:
    return elemzesek([kifejezes], ablak, homokozo=homokozo, lepes_idokorlat_s=lepes_idokorlat_s)[0]
