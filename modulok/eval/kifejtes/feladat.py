"""Aranyhalmaz: a kijelölés kifejtése (router-feladat: `kifejtes`; J4) — az asszisztens ⌘J-je kijelöléssel.

12 kijelölés a felhasználó saját jegyzeteiből (hat tantárgy), fagyasztva (`modulok/eval/kijeloles_keszit.py`). A tétel kérése
az éles `kifejt` kérés: `core.kiegeszites_modell.keres('kifejt', elotte, '', kijeloles)` — a prompt egyetlen forrása; a
regiszter mérés-beállítása (`[meres.feladat.kifejtes]`, a modell `meres.kifejtes` alszakasza) élesben és a mérésben ugyanaz.

A `VERZIO` a halmaz verziója és a kérés lenyomata (`kiegeszites_modell.prompt_lenyomat`): a prompt változása után a régi
kalibrált sor nem routol, a mód visszaesik próbára. A pontozó: `modulok/eval/kozos/kijeloles.py` (formai kapu, ellentmondás-kapu,
témánál marad, új tartalom).
"""
from __future__ import annotations

import sys
from pathlib import Path

ITT = Path(__file__).resolve().parent
REPO = ITT.parents[2]
for _p in (str(REPO), str(ITT.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core.kiegeszites_modell import keres, prompt_lenyomat  # noqa: E402
from kozos import kijeloles as K  # noqa: E402

MOD = "kifejt"
ROUTER_FELADAT = "kifejtes"
ARANY = K.betolt(ITT)
VERZIO = K.verzio(ROUTER_FELADAT, ARANY, prompt_lenyomat(MOD))
KORLAT = ("12 kijelölés; lexikai pontozó: a szinonimával mondott ellentmondást, a pontatlan, de a jegyzettel nem ellentétes "
          "állítást és a stílust nem látja — a jóváhagyáskor (K430) a válaszokat kézzel is át kell nézni.")


def tetelek(cfg):
    for t in ARANY["tetel"]:
        if "kijeloles" not in t:
            raise ValueError(f"kifejtes/{t['id']}: nincs fagyasztva — futtasd a `modulok/eval/kijeloles_keszit.py`-t")
        yield {"id": t["id"], "keres": keres(MOD, t["elotte"], "", t["kijeloles"]), "vart": t}


def formatum_ok(valasz, vart) -> bool:
    return K.kifejtes_formatum(valasz, vart)


def pontoz(rekordok):
    return K.pontoz(rekordok, K.kifejtes_pont, KORLAT)
