"""„Test this model” (F6; az 5. audit §6.1): előfeltétel → előpróba → mérés → értékelés → jel (kalibrált vagy próba).

Feladatsor-lépés: `python -m core.modell.teszt <modell> <feladat> [--halmaz szallitott|sajat]` (a `modell_teszt` feladattípus,
`resources={"modell"}`; csak a `POST /api/modellek/<id>/teszt` indítja). A worker az app workere (a feladatsor adja a címét); a
mérés `auto` módban fut (aktív használatkor szünetel; a távol-keretes modell tétlenségre vár). A stop-fájlra a folyó tétel után
megáll; újraindítva a kész tételektől folytatja (az `eval` sorkulcsa).

A jel szabálya (D9, változatlan kapuk + a kódba költözött küszöb):
  1. előfeltétel: a modell a manifesztben és a regiszterben, telepítve (`kesz`/`ellenorizetlen`), nem `konvertalas`, a csúcs-RAM
     a távol-keretbe fér, a feladatnak van mérhető aranyhalmaza;
  2. előpróba: 3 tétel a `{tmp}/eval-proba` alá; érvénytelen (levágás, hurok, üres, hiba) → megáll, jel: próba;
  3. teljes mérés, értékelés;
  4. kalibrált jel csak akkor, ha a mérés teljes, érvényes, az arany jóváhagyott, és a küszöb-kapu (`kuszob.dont`) átengedi;
     különben a sor jel nélkül íródik (a meglévő jelet a teljes, érvényes, de küszöb alatti mérés leveszi).
Eredmény: `{runs}/modell-teszt/<modell>/<feladat>-riport.json` (`jel`: `kalibralt` | `proba`; `okok`: `[{kod, param}]`).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from pathlib import Path

from .. import config
from . import beallitas as B
from . import eval as ev, kliens, kuszob, manifeszt
from .kalibracio import vazlat

ELOPROBA_TETEL = 3


def riport_ut(cfg, modell: str, feladat: str) -> Path:
    return Path(cfg.path("runs")) / "modell-teszt" / modell / f"{feladat}-riport.json"


def _ir(ut: Path, adat: dict) -> None:
    ut.parent.mkdir(parents=True, exist_ok=True)
    tmp = ut.with_name(f".{ut.name}.manifold-tmp")
    tmp.write_text(json.dumps(adat, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, ut)


def elofeltetel(cfg, modell: str, feladat: str, halmaz: str = "szallitott") -> list[dict]:
    """A mérés előfeltételeinek hiányai `[{kod, param}]` (üres: indítható). Modellt nem tölt, hálózatot nem ér."""
    okok: list[dict] = []
    try:
        man = manifeszt.betolt(cfg)
        m = manifeszt.modell(man, modell)
    except manifeszt.ManifesztHiba as e:
        return [{"kod": e.kod, "param": e.param}]
    try:
        reg = B.betolt(cfg).modell(modell)
    except B.RegiszterHiba:
        return [{"kod": "modell.ismeretlen", "param": {"modell": modell}}]
    if feladat not in kuszob.ALAP:
        return [{"kod": "modell.feladat_ismeretlen", "param": {"feladat": str(feladat)[:64]}}]
    t = manifeszt.telepitettseg(cfg.path("models"), modell, m)
    if t["allapot"] == "konvertalasra_var":
        okok.append({"kod": "modell.konvertalas_kell", "param": {"modell": modell}})
    elif t["allapot"] not in manifeszt.HASZNALHATO:
        okok.append({"kod": "modell.nincs_telepitve", "param": {"modell": modell, "allapot": t["allapot"]}})
    b = B.betolt(cfg)
    if reg.csucs_gb is not None and reg.csucs_gb > b.keret_gb("tavol"):
        okok.append({"kod": "modell.tul_nagy", "param": {"modell": modell, "csucs_gb": reg.csucs_gb,
                                                         "keret_gb": b.keret_gb("tavol")}})
    try:
        mod_ = ev.feladat_modul(cfg, feladat, halmaz)
        arany = getattr(mod_, "ARANY", None)
        if isinstance(arany, dict) and (arany.get("hianyzik") or arany.get("allapot") == "hianyzik"):
            okok.append({"kod": "modell.halmaz_nincs", "param": {"feladat": feladat}})
        elif vazlat(str(mod_.VERZIO)):
            okok.append({"kod": "modell.halmaz_vazlat", "param": {"feladat": feladat}})
    except Exception as e:  # noqa: BLE001 — a hiányzó/hibás halmaz a mérés akadálya
        okok.append({"kod": getattr(e, "kod", "modell.halmaz_nincs"), "param": {"feladat": feladat}})
    return okok


def futtat(cfg, modell: str, feladat: str, u: str, halmaz: str = "szallitott", stop=lambda: False, log=print,
           mod: str = "auto") -> dict:
    """A teljes folyamat; az eredmény a riportba is kiíródik. Megszakításkor `allapot: "megallitva"` (folytatható)."""
    alap = {"modell": modell, "feladat": feladat, "halmaz": halmaz, "datum": _dt.datetime.now().isoformat(timespec="seconds")}
    ki = riport_ut(cfg, modell, feladat)
    okok = elofeltetel(cfg, modell, feladat, halmaz)
    if okok:
        e = {**alap, "allapot": "elofeltetel", "jel": "proba", "okok": okok}
        _ir(ki, e)
        return e
    k = kuszob.hatalyos(feladat, manifeszt.kalibracio_konfig(cfg))
    alap.update(kuszob=k.kuszob if k else None, min_tetel=k.min_tetel if k else None)
    # 1. előpróba (3 tétel, külön kimenet: az éles sorokat nem érinti)
    proba_d = Path(cfg.path("tmp")) / "eval-proba" / ("sajat" if halmaz == "sajat" else "szallitott")
    log(f"[teszt] {modell} · {feladat}: előpróba ({ELOPROBA_TETEL} tétel)")
    ev.futtat(cfg, modell, feladat, u, limit=ELOPROBA_TETEL, mod=mod, log=log, kimenet=proba_d, halmaz=halmaz, stop=stop)
    if stop():
        e = {**alap, "allapot": "megallitva", "jel": "proba", "okok": []}
        _ir(ki, e)
        return e
    elo = ev.ertekel(cfg, modell, feladat, limit=ELOPROBA_TETEL, kimenet=proba_d, halmaz=halmaz)
    print("[manifold-progress] 5.0%", flush=True)
    if not elo["ervenyes"]:
        e = {**alap, "allapot": "eloproba_bukott", "jel": "proba", "eloproba": _kivonat(elo),
             "okok": [{"kod": "modell.eloproba_ervenytelen", "param": _erv_param(elo)}]}
        _ir(ki, e)
        return e
    # 2. teljes mérés (folytatható), 3. értékelés
    log(f"[teszt] {modell} · {feladat}: mérés")
    ev.futtat(cfg, modell, feladat, u, mod=mod, log=log, halmaz=halmaz, stop=stop)
    ert = ev.ertekel(cfg, modell, feladat, halmaz=halmaz)
    if stop() and ert.get("ervenyesseg", {}).get("hianyzo"):
        e = {**alap, "allapot": "megallitva", "jel": "proba", "okok": [], "ertekeles": _kivonat(ert)}
        _ir(ki, e)
        return e
    # 4. jel
    okok = []
    if not ert.get("teljes"):
        okok.append({"kod": "modell.nem_teljes", "param": {"n": ert.get("n"), "tetelszam": ert.get("tetelszam")}})
    if not ert.get("ervenyes"):
        okok.append({"kod": "modell.ervenytelen", "param": _erv_param(ert)})
    if vazlat(str(ert.get("aranyhalmaz_verzio") or "")):
        okok.append({"kod": "modell.halmaz_vazlat", "param": {"feladat": feladat}})
    dontes = kuszob.dont(ert["router_feladat"], ert, manifeszt.kalibracio_konfig(cfg))
    okok += dontes["okok"]
    kalibralt = not okok
    sor = None
    if ert.get("teljes"):
        # teljes, érvényes, de küszöb alatti mérés: a jel lekerül (False); érvénytelennél csak naplósor (None: a tábla dönt)
        jel = True if kalibralt else (False if ert.get("ervenyes") else None)
        sor = ev.rogzit(cfg, ert, jel, megjegyzes=f"Test this model, n={ert['n']}")
    e = {**alap, "allapot": "kesz", "jel": "kalibralt" if kalibralt else "proba", "okok": okok,
         "ertekeles": _kivonat(ert), "rogzitve": bool(sor), "figyelmeztetes": ev.csucs_figyelmeztetes(cfg, ert)}
    _ir(ki, e)
    print("[manifold-progress] 100.0%", flush=True)
    return e


def _erv_param(ert: dict) -> dict:
    """Az érvényességi kapu számai (a felület ebből ír szöveget): levágott, hurok, üres, hiba, hiányzó, n."""
    e = ert.get("ervenyesseg") or {}
    return {k: e[k] for k in ("levagott", "hurok", "ures", "hiba", "hianyzo", "n") if isinstance(e.get(k), int)}


def _kivonat(ert: dict) -> dict:
    return {k: ert.get(k) for k in ("pontszam", "n", "tetelszam", "teljes", "ervenyes", "aranyhalmaz_verzio", "router_feladat",
                                    "mero", "modok")} | {"ervenyesseg": ert.get("ervenyesseg"), "futas": ert.get("futas")}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m core.modell.teszt")
    ap.add_argument("modell")
    ap.add_argument("feladat")
    ap.add_argument("--halmaz", choices=("szallitott", "sajat"), default="szallitott")
    a = ap.parse_args(argv)
    cfg = config.load()
    stop_fajl = os.environ.get("MANIFOLD_STOP_FAJL")
    stop = (lambda: Path(stop_fajl).exists()) if stop_fajl else (lambda: False)
    try:
        e = futtat(cfg, a.modell, a.feladat, kliens.url(cfg), a.halmaz, stop=stop)
    except (kliens.KliensHiba, ValueError, FileNotFoundError) as exc:
        e = {"modell": a.modell, "feladat": a.feladat, "allapot": "hiba", "jel": "proba",
             "okok": [{"kod": "modell.teszt_hiba", "param": {"hiba": type(exc).__name__}}], "uzenet": str(exc)[:500]}
        _ir(riport_ut(cfg, a.modell, a.feladat), e)
    print(f"Riport: {riport_ut(cfg, a.modell, a.feladat)}", flush=True)
    return {"kesz": 0, "megallitva": 3}.get(e["allapot"], 1 if e["allapot"] in ("eloproba_bukott", "elofeltetel") else 2)


if __name__ == "__main__":
    sys.exit(main())
