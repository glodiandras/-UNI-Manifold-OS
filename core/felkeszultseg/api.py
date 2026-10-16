"""A felkészültség végpontjai (C28a, C28b): `GET /api/felkeszultseg`, `GET /api/felkeszultseg/dolgozat` (C28a; mind csak olvas),
`GET /api/felkeszultseg/kalibracio` (C28b; csak olvas) és `POST /api/felkeszultseg/ertekeles` (C28b; **nem ír**, de modellt hív).

A `datum` (ÉÉÉÉ-HH-NN) a „ma”-t írja felül (déli időponttal): a tesztek és az időutazás-nézet használja; nélküle a
mostani idő. Egy kérés egy `Adatok` példány: a források egyszer töltődnek be. A hiányzó forrás (nincs naptáradat, nincs
kártya, még épülő index) nem hiba: a válasz `hiba` / `adatok` / `figyelmeztetesek` mezője mondja meg.

A szöveges értékelés (`ertekeles.py`) a dolgozat-részlet számaiból készül; a modellt a `kereses_api.szolgalat` köti a workerhez (D9:
élesben a router `szoveg` feladatának kalibrált modellje; kalibrált sor nélkül 503; kifejezett `modell` csak próbaként, `proba: true`).
"""
from __future__ import annotations

from datetime import datetime, time

from .. import naplo
from ..utvonalak import HttpError
from ..modell.hibaszerzodes import ai_mezo
from . import ertekeles, forras, kalibracio, osszesit   # noqa: F401 — a `forras` import regisztrálja a javaslat-forrást a C29 horgán
from .adat import Adatok


def _olvaso(app):
    """A vault jegyzetének szövege (csak olvasva) az eredmény-kinyerőnek."""
    return lambda rp: app.vault.read(rp)["tartalom"]


def _adatok_datumbol(app, szoveg, **kw):
    nap = naplo.datum_ertek(szoveg)
    most = datetime.combine(nap, time(12, 0)).astimezone() if szoveg else None
    return nap, Adatok(app.cfg, app.index, most, olvas=_olvaso(app), **kw)


def _adatok(k):
    return _adatok_datumbol(k.app, k.q.get("datum"))


def lista(k) -> dict:
    nap, a = _adatok(k)
    return osszesit.lista(a, nap)


def dolgozat(k) -> dict:
    azon = k.q.get("azon")
    if not azon:
        raise HttpError(400, "az `azon` (a dolgozat naptár-azonosítója) kötelező", kod="felkeszultseg.api.azon_kell")
    _, a = _adatok(k)
    return osszesit.reszlet(a, azon)


def kalibracio_jelentes(k) -> dict:
    """`GET /api/felkeszultseg/kalibracio?datum=`: a súlyok önkalibrációjának állapota és a mért becslési hiba (csak olvas)."""
    szoveg = k.q.get("datum")
    nap = naplo.datum_ertek(szoveg)
    most = datetime.combine(nap, time(12, 0)).astimezone() if szoveg else None
    return kalibracio.jelentes_adatbol(k.app.cfg, k.app.index, _olvaso(k.app), most)


# ------------------------------------------------------------------ a szöveges értékelés

def _hivo(app, modell_nev):
    """A modellhívó és a D9-jelzők → `(hívó, modell neve | None, kalibrált)`. Kalibrált sor nélkül 503 (kifejezett modell nélkül)."""
    from .. import kereses_api
    from ..kereses_modell import WorkerModell
    from ..modell import beallitas as B
    sz = kereses_api.szolgalat(app)
    sz.worker_kot()
    if modell_nev is not None:
        if not isinstance(modell_nev, str) or not modell_nev:
            raise HttpError(400, "A `modell` egy regisztrált modell neve legyen.", kod="felkeszultseg.api.modell_nev")
        try:
            m = B.betolt(app.cfg).modell(modell_nev)
        except B.RegiszterHiba as e:
            raise HttpError(400, str(e), kod="felkeszultseg.modell_hibas") from None
        if "szoveg" not in m.feladat:
            raise HttpError(400, f"A(z) {m.nev} nem `szoveg`-modell (a regiszter `feladat` listája).", kod="felkeszultseg.api.nem_szoveg_modell", param={"nev": m.nev})
        w = sz._worker()
        if w is None:
            raise HttpError(503, "A modell-worker nem érhető el.", kod="felkeszultseg.api.worker_nem_erheto_el",
                            ai=ai_mezo("szoveg", None, "felkeszultseg", kod="nincs_ai_runtime"))
        return WorkerModell(w.biztosit, proba_modell=m.nev), m.nev, False
    if sz.modell is None:
        raise HttpError(503, "A szöveges értékelés modellje nincs kötve (a router-táblában nincs kalibrált `szoveg` modell).", kod="felkeszultseg.api.modell_nincs_kotve",
                        ai=ai_mezo("szoveg", None, "felkeszultseg"))
    return sz.modell, None, bool(sz.kalibralt)


def ertekeles_valasz(app, t: dict) -> dict:
    """`POST /api/felkeszultseg/ertekeles {azon, datum?, modell?}` törzse külön függvényben (a tesztek az `app`-pal hívják)."""
    from ..modell.kliens import KliensHiba
    azon = t.get("azon")
    if not isinstance(azon, str) or not azon:
        raise HttpError(400, "az `azon` (a dolgozat naptár-azonosítója) kötelező", kod="felkeszultseg.api.azon_kell")
    datum = t.get("datum")
    if datum is not None and not isinstance(datum, str):
        raise HttpError(400, "a `datum` ÉÉÉÉ-HH-NN szöveg legyen", kod="felkeszultseg.api.datum_alak")
    _, a = _adatok_datumbol(app, datum)
    r = osszesit.reszlet(a, azon)
    ten = ertekeles.tenyek(r, a.ma)
    ki = {"ok": True, "kulcs": ten["kulcs"], "prompt_verzio": ertekeles.PROMPT_VERZIO, "szoveg": None, "modell": None, "proba": False,
          "kalibralt": False, "probalkozas": 0, "tiltott_szamok": []}
    if not ten["szam_van"]:
        return {**ki, "allapot": "nincs_mert_adat",
                "uzenet": "There is no measured card or quiz data yet, so the model has not run."}
    hivo, nev, kalibralt = _hivo(app, t.get("modell"))
    try:
        ered = ertekeles.futtat(hivo, ten)
    except KliensHiba as e:
        raise HttpError(503, f"A szöveges értékelés modellje nem érhető el: {e}", kod="felkeszultseg.api.modell_nem_erheto_el", param={"e": e}) from None
    modell_neve = getattr(hivo, "nev", None) or nev
    proba = (not kalibralt) or bool(getattr(hivo, "proba", False))
    uzenet = {"kesz": None, "kapu_bukott": "The model twice included numbers that are not in the data. Its assessment is hidden.",
              "ures": "The model returned an empty response."}[ered["allapot"]]
    return {**ki, "allapot": ered["allapot"], "szoveg": ered["szoveg"], "modell": modell_neve, "proba": proba,
            "kalibralt": bool(kalibralt) and not proba, "probalkozas": ered["probalkozas"], "tiltott_szamok": ered["tiltott"],
            "uzenet": uzenet}


def ertekeles_vegpont(k) -> dict:
    return ertekeles_valasz(k.app, k.torzs())


def utvonalak(r) -> None:
    from . import keret
    r.get('/api/felkeszultseg/keret', lambda k: {'napi_perc': keret.olvas(k.app.cfg)})
    def keret_ir(k):
        ered = keret.ir(k.app.cfg, k.torzs())
        k.app.naptar.javaslatok.frissit()
        return ered
    r.put('/api/felkeszultseg/keret', keret_ir)
    r.get("/api/felkeszultseg", lista)
    r.get("/api/felkeszultseg/dolgozat", dolgozat)
    r.get("/api/felkeszultseg/kalibracio", kalibracio_jelentes)
    r.post("/api/felkeszultseg/ertekeles", ertekeles_vegpont)
