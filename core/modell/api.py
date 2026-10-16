"""A modellréteg core-oldali végpontjai az útvonal-regiszterben (C11a, F6): ML nélkül, csak az `App` állapotát adják.

F6 — a Model Manager háttere (`/api/modellek/*`). A HTTP-szerződés (a felület a következő hullámban épül rá):

    GET  /api/modellek
         → {modellek: [Modell], feladatok: {<f>: {cim, leiras, kuszob, min_tetel, funkciok}}, funkciok: {<fn>: {cim, feladatok}},
            keretek: {munka, tavol}}
         Modell = {id, repo, revizio, licenc, nyelvek, szerep, ajanlott, feladat, meret_gb, csucs_gb, keret, futtato, konvertalas,
                   allapot (nincs|reszleges|ellenorizetlen|kesz|elter_revizio|konvertalasra_var — a lemezről), lemez_bajt,
                   ellenorizve, kalibracio: [{feladat, pontszam, kalibralt, aranyhalmaz_verzio, datum, mero}],
                   letoltes: {feladat_id, allapot, szazalek} | null, teszt: {feladat_id, allapot, szazalek, feladat} | null}
    GET  /api/modellek/<id>                         → Modell
    POST /api/modellek/<id>/letoltes                → 202 {feladat: Feladat}  (háttérfeladat `modell_letoltes`; haladás a
                                                      feladatsor WS-eseményein és a `/api/feladatok/<fid>`-n; 409 modell.letoltes_fut)
    POST /api/modellek/<id>/letoltes/megszakitas    → {feladat}  (azonnali leállítás; a félbehagyott fájl folytatható)
    POST /api/modellek/<id>/torles {megerosit: true}→ {id, felszabadult_bajt, kalibracio_levett: [feladat]}
                                                      (409 modell.megerosites_kell | modell.foglalt)
    POST /api/modellek/<id>/teszt {feladat, halmaz?: "szallitott"|"sajat"}
                                                    → 202 {feladat: Feladat, elofeltetel: []}  (`modell_teszt`; 409 modell.teszt_fut;
                                                      400 az előfeltétel hiányával: {kod, param, okok: [{kod, param}]})
    GET  /api/modellek/<id>/teszt/<feladat>         → a legutóbbi riport (`core/modell/teszt.py`) | 404 modell.nincs_teszt
    GET  /api/modellek/halmazok                     → {szallitott: [Halmaz], sajat: {<f>: Osszegzes}, tamogatott: [f]}
    POST /api/modellek/halmazok/<f>  {tetelek, nyelv?}      → Osszegzes (vázlat; a kijelölés-feladatoknál a vaultból fagyaszt)
    POST /api/modellek/halmazok/<f>/jovahagyas {tartott: [id]} → Osszegzes (jóváhagyott)
    POST /api/modellek/halmazok/<f>/valasztas {halmaz}      → Osszegzes (`sajat` | `szallitott`: a router aktuális verziója)
    POST /api/modellek/halmazok/<f>/torles                  → {feladat, torolve}  (a `.torolt/` alá kerül)

Hiba: `{hiba (angol), kod, param}` (`core/hibauzenetek.py` `modell.*`). Letöltés csak felhasználói kérésre, a manifeszt
HTTPS-hostjaira (`[forras] hostok`), csak a `{models}` alá (D3).
"""
from __future__ import annotations

import json
import re
import sys

from .. import tasks
from ..utvonalak import HttpError, Valasz

LETOLTES = "modell_letoltes"
TESZT = "modell_teszt"
_AKTIV = ("sorban", "fut")
_ID = r"([a-z0-9_]{1,64})"
_FELADAT = r"([a-z_]{1,40})"


# ---------------------------------------------------------------------- feladattípusok

def _letoltes_terv(cfg, p: dict, stop: str):
    from . import manifeszt
    nev = p.get("modell")
    try:
        man = manifeszt.betolt(cfg)
        m = manifeszt.modell(man, nev)
        manifeszt.vegpont(man)
    except manifeszt.ManifesztHiba as e:
        raise tasks.kodos(tasks.Invalid(str(e)), e.kod, **e.param) from None
    from .. import lepes_kapu
    return ([tasks.Step(f"Download {nev}", [sys.executable, "-B", "-m", "core.letoltes", "--feladat", nev], str(cfg.root),
                        jogok=lepes_kapu.JOGOK_NINCS)],
            f"Download and verify {m['repo']} ({float(m.get('meret_gb') or 0):.2f} GB) into the model store.", [])


def _teszt_terv(cfg, p: dict, stop: str):
    nev, feladat, halmaz = p.get("modell"), p.get("feladat"), p.get("halmaz") or "szallitott"
    if not isinstance(nev, str) or not re.fullmatch(_ID, nev) or not isinstance(feladat, str) or not re.fullmatch(_FELADAT, feladat) \
            or halmaz not in ("szallitott", "sajat"):
        raise tasks.kodos(tasks.Invalid("hibás modell-teszt kérés"), "modell.feladat_ismeretlen", feladat=str(feladat)[:40])
    return ([tasks.Step(f"Test {nev} on {feladat}",
                        [sys.executable, "-B", "-m", "core.modell.teszt", nev, feladat, "--halmaz", halmaz], str(cfg.root))],
            f"Trial run, measurement and calibration check of {nev} on {feladat}.", [])


def regisztral() -> None:
    """Idempotens; az `utvonalak` hívja (a többi feladattípus mintájára)."""
    tasks.register(tasks.TaskType(LETOLTES, "Download a model", _letoltes_terv, resources=frozenset(), graceful_stop=True))
    tasks.register(tasks.TaskType(TESZT, "Test a model", _teszt_terv, resources=frozenset({"modell"}), graceful_stop=True))


# ---------------------------------------------------------------------- segédek

def _hiba(e, status: int = 400) -> HttpError:
    return HttpError(status, str(e), kod=getattr(e, "kod", None), param=dict(getattr(e, "param", None) or {}))


def _manifeszt(cfg):
    from . import manifeszt
    try:
        return manifeszt.betolt(cfg)
    except manifeszt.ManifesztHiba as e:
        raise _hiba(e, 500) from None


def _modell(man, nev):
    from . import manifeszt
    try:
        return manifeszt.modell(man, nev)
    except manifeszt.ManifesztHiba as e:
        raise _hiba(e, 404) from None


def _feladatok(app, tipus: str) -> list[dict]:
    try:
        return [f for f in app.queue.list(200) if f.get("tipus") == tipus and f.get("allapot") in _AKTIV]
    except Exception:  # noqa: BLE001 — zárt sor: nincs aktív feladat
        return []


def _aktiv(app, tipus: str, nev: str) -> dict | None:
    return next((f for f in _feladatok(app, tipus) if (f.get("parameterek") or {}).get("modell") == nev), None)


def _feladat_kivonat(f: dict | None) -> dict | None:
    if not f:
        return None
    return {"feladat_id": f.get("id"), "allapot": f.get("allapot"), "szazalek": f.get("szazalek"),
            **({"feladat": (f.get("parameterek") or {}).get("feladat")} if f.get("tipus") == TESZT else {})}


def _kalibracio(cfg) -> dict[str, list[dict]]:
    from . import kalibracio
    try:
        t = kalibracio.megnyit(cfg)
    except Exception:  # noqa: BLE001 — olvashatatlan tábla: üres (a doctor jelzi)
        return {}
    try:
        sorok = t.tabla()
    finally:
        t.close()
    ki: dict[str, list[dict]] = {}
    for s in sorok:
        ki.setdefault(s["modell"], []).append({
            "feladat": s["feladat"], "pontszam": s["pontszam"], "kalibralt": bool(s["kalibralt"]), "datum": s["datum"],
            "aranyhalmaz_verzio": s["aranyhalmaz_verzio"],
            "mero": "sajat" if "-sajat-" in str(s["aranyhalmaz_verzio"]) else "szallitott"})
    return ki


def modell_adat(app, man: dict, nev: str, kal: dict | None = None) -> dict:
    from . import manifeszt
    m = man["modell"][nev]
    t = manifeszt.telepitettseg(app.cfg.path("models"), nev, m)
    return {"id": nev, **{k: m.get(k) for k in ("repo", "revizio", "licenc", "nyelvek", "szerep", "ajanlott", "feladat", "meret_gb",
                                                "csucs_gb", "keret", "futtato")},
            "konvertalas": bool(m.get("konvertalas")), **t,
            "kalibracio": (kal if kal is not None else _kalibracio(app.cfg)).get(nev, []),
            "letoltes": _feladat_kivonat(_aktiv(app, LETOLTES, nev)), "teszt": _feladat_kivonat(_aktiv(app, TESZT, nev))}


def lista(app) -> dict:
    from . import beallitas as B
    from . import kuszob
    man = _manifeszt(app.cfg)
    kal = _kalibracio(app.cfg)
    funkciok = {k: {"cim": v.get("cim"), "feladatok": list(v.get("feladatok") or [])} for k, v in man["funkcio"].items()}
    feladatok = {}
    for f, v in man["feladat"].items():
        k = kuszob.hatalyos(f, man["kalibracio"])
        feladatok[f] = {"cim": v.get("cim"), "leiras": v.get("leiras"), "kuszob": k.kuszob if k else None,
                        "min_tetel": k.min_tetel if k else None,
                        "funkciok": sorted(n for n, fn in funkciok.items() if f in fn["feladatok"])}
    try:
        keretek = dict(B.betolt(app.cfg).keretek)
    except Exception:  # noqa: BLE001
        keretek = {}
    return {"modellek": [modell_adat(app, man, n, kal) for n in man["modell"]], "feladatok": feladatok, "funkciok": funkciok,
            "keretek": keretek}


def _worker_hasznalja(app, nev: str) -> bool:
    from . import kliens
    try:
        u = getattr(getattr(app, "worker", None), "url", None) or kliens.fut_url(app.cfg)
        if not u:
            return False
        h = kliens.health(u)
    except Exception:  # noqa: BLE001 — nem fut / nem válaszol: nincs betöltve
        return False
    return h.get("modell") == nev or nev in (h.get("mellette") or [])


# ---------------------------------------------------------------------- útvonalak

def utvonalak(r) -> None:
    r.get("/api/modell", lambda k: k.app.modell_allapot())

    def modellek_attekintes(k):
        from .attekintes import attekintes
        return attekintes(k.app.cfg)
    r.get("/api/vezerlo/modellek", modellek_attekintes)          # C19: a vezérlő Modellek szakasza (csak olvas)

    def aktivitas(k):
        k.app.aktivitas.jel()
        return {"ok": True}
    r.post("/api/aktivitas", aktivitas)

    regisztral()

    # --- aranyhalmazok (a minták előbb: a `halmazok` nem modell-azonosító)
    def halmazok(k):
        from . import aranycsomag as A
        return {"szallitott": A.lista(k.app.cfg), "sajat": {f: A.osszegzes(k.app.cfg, f) for f in A.SAJAT_FELADATOK},
                "tamogatott": sorted(A.SAJAT_FELADATOK)}
    r.get("/api/modellek/halmazok", halmazok)

    def _halmaz_hivas(fn):
        def kezelo(k):
            from . import aranycsomag as A
            try:
                return fn(A, k, k.m.group(1))
            except A.HalmazHiba as e:
                raise _hiba(e, 404 if e.kod == "modell.halmaz_nincs" else 400) from None
        return kezelo

    r.post(re.compile(rf"/api/modellek/halmazok/{_FELADAT}/jovahagyas"),
           _halmaz_hivas(lambda A, k, f: A.jovahagy(k.app.cfg, f, k.torzs().get("tartott"))))
    r.post(re.compile(rf"/api/modellek/halmazok/{_FELADAT}/valasztas"),
           _halmaz_hivas(lambda A, k, f: A.valaszt(k.app.cfg, f, k.torzs().get("halmaz"))))
    r.post(re.compile(rf"/api/modellek/halmazok/{_FELADAT}/torles"), _halmaz_hivas(lambda A, k, f: A.torol(k.app.cfg, f)))
    r.post(re.compile(rf"/api/modellek/halmazok/{_FELADAT}"),
           _halmaz_hivas(lambda A, k, f: A.letrehoz(k.app.cfg, f, k.torzs().get("tetelek"), k.torzs().get("nyelv") or "hu")))

    # --- modellek
    r.get("/api/modellek", lambda k: lista(k.app))

    def egy(k):
        man = _manifeszt(k.app.cfg)
        _modell(man, k.m.group(1))
        return modell_adat(k.app, man, k.m.group(1))
    r.get(re.compile(rf"/api/modellek/{_ID}"), egy)

    def letoltes(k):
        nev = k.m.group(1)
        _modell(_manifeszt(k.app.cfg), nev)
        if _aktiv(k.app, LETOLTES, nev):
            raise HttpError(409, "a modell letöltése már fut", kod="modell.letoltes_fut", param={})
        return Valasz(202, {"feladat": k.app.queue.submit(LETOLTES, {"modell": nev})})
    r.post(re.compile(rf"/api/modellek/{_ID}/letoltes"), letoltes)

    def megszakitas(k):
        f = _aktiv(k.app, LETOLTES, k.m.group(1))
        if not f:
            raise HttpError(404, "a modell nem töltődik", kod="modell.nincs_letoltes", param={})
        return {"feladat": k.app.queue.stop(f["id"], True)}
    r.post(re.compile(rf"/api/modellek/{_ID}/letoltes/megszakitas"), megszakitas)

    def torles(k):
        from . import kalibracio, manifeszt
        nev = k.m.group(1)
        man = _manifeszt(k.app.cfg)
        m = _modell(man, nev)
        if k.torzs().get("megerosit") is not True:
            raise HttpError(409, "a törlést meg kell erősíteni", kod="modell.megerosites_kell", param={})
        if _aktiv(k.app, LETOLTES, nev) or _aktiv(k.app, TESZT, nev) or _worker_hasznalja(k.app, nev):
            raise HttpError(409, "a modellt egy letöltés, teszt vagy a worker használja", kod="modell.foglalt", param={})
        try:
            ki = manifeszt.torol(k.app.cfg.path("models"), nev, m)
        except manifeszt.ManifesztHiba as e:
            raise _hiba(e, 409) from None
        t = kalibracio.megnyit(k.app.cfg)
        try:
            levett = t.modell_jel_levesz(nev, "a modell törölve (Model Manager)")
        finally:
            t.close()
        return {"id": nev, **ki, "kalibracio_levett": levett}
    r.post(re.compile(rf"/api/modellek/{_ID}/torles"), torles)

    def teszt(k):
        from . import teszt as T
        nev = k.m.group(1)
        _modell(_manifeszt(k.app.cfg), nev)
        b = k.torzs()
        feladat, halmaz = b.get("feladat"), b.get("halmaz") or "szallitott"
        if not isinstance(feladat, str) or not re.fullmatch(_FELADAT, feladat) or halmaz not in ("szallitott", "sajat"):
            raise HttpError(400, "ismeretlen feladat vagy halmaz", kod="modell.feladat_ismeretlen",
                            param={"feladat": str(feladat)[:40]})
        if _feladatok(k.app, TESZT):
            raise HttpError(409, "már fut egy modell-teszt", kod="modell.teszt_fut", param={})
        okok = T.elofeltetel(k.app.cfg, nev, feladat, halmaz)
        if okok:
            raise HttpError(400, "a mérés előfeltétele hiányzik", kod=okok[0]["kod"], param=okok[0]["param"], okok=okok)
        return Valasz(202, {"feladat": k.app.queue.submit(TESZT, {"modell": nev, "feladat": feladat, "halmaz": halmaz}),
                            "elofeltetel": []})
    r.post(re.compile(rf"/api/modellek/{_ID}/teszt"), teszt)

    def teszt_riport(k):
        from . import teszt as T
        nev, feladat = k.m.group(1), k.m.group(2)
        try:
            return json.loads(T.riport_ut(k.app.cfg, nev, feladat).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise HttpError(404, "nincs tesztriport", kod="modell.nincs_teszt", param={}) from None
    r.get(re.compile(rf"/api/modellek/{_ID}/teszt/{_FELADAT}"), teszt_riport)
