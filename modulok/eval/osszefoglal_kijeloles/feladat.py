"""Aranyhalmaz: a kijelölés összefoglalása (router-feladat: `osszefoglal_kijeloles`; J4) — az asszisztens ⇧⌘J-je.

12 kijelölés (bekezdés, lista, táblázat) a felhasználó saját jegyzeteiből (hat tantárgy), fagyasztva
(`modulok/eval/kijeloles_keszit.py`). A tétel kérése az éles `osszefoglal` kérés:
`core.kiegeszites_modell.keres('osszefoglal', elotte, '', kijeloles)` — a prompt egyetlen forrása; a regiszter mérés-beállítása
élesben és a mérésben ugyanaz. (Nem azonos a `szoveg` feladat jegyzet-összefoglalójával: az idézetes, kísérőjegyzetbe kerülő
összefoglaló — 70. döntés —, ez a kijelölés helyére kerülő egy-két mondat.)

A `VERZIO` a halmaz verziója és a kérés lenyomata (`kiegeszites_modell.prompt_lenyomat`). A pontozó:
`modulok/eval/kozos/kijeloles.py` (formai kapu, a kulcstények lefedettsége, a mondatok hűsége a közös forráshűség-kapun).
A kapu profilja az `os.toml` `[kapuk]` szakaszából jön: a `pontoz(rekordok)` nem kap `cfg`-t, ezért a `tetelek(cfg)` eltárolja
(a hívási sorrend az `eval.ertekel`-ben: tételek, majd pontozás); `tetelek` nélkül az alapértékek állnak.
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

MOD = "osszefoglal"
ROUTER_FELADAT = "osszefoglal_kijeloles"
ARANY = K.betolt(ITT)
VERZIO = K.verzio(ROUTER_FELADAT, ARANY, prompt_lenyomat(MOD))
KORLAT = ("12 kijelölés; lexikai pontozó: az átfogalmazott hamis állítást és a mondaton belüli felcserélést nem látja, a "
          "kulcsszó-lefedettség a tartalom közelítése — a jóváhagyáskor a válaszokat kézzel is át kell nézni.")

_profil = {"p": K.profil(None)}


def tetelek(cfg):
    _profil["p"] = K.profil(cfg)
    for t in ARANY["tetel"]:
        if "kijeloles" not in t:
            raise ValueError(f"osszefoglal_kijeloles/{t['id']}: nincs fagyasztva — futtasd a `modulok/eval/kijeloles_keszit.py`-t")
        yield {"id": t["id"], "keres": keres(MOD, t["elotte"], "", t["kijeloles"]), "vart": t}


def formatum_ok(valasz, vart) -> bool:
    return K.osszefoglalas_formatum(valasz, vart)


def pontoz(rekordok):
    return K.pontoz(rekordok, lambda v, vart: K.osszefoglalas_pont(v, vart, _profil["p"]), KORLAT)
