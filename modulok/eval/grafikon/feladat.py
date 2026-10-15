"""Aranyhalmaz: képlet → grafikon-adatok (router-feladat `grafikon` a C35b óta — a [router] feladatok közt; a C19 kalibrációja erre a JSON-kiolvasó kérésre szól) — 15 képlet.

A modell a jegyzetrészletből kiolvassa a megnevezett függvényt, és JSON-ban adja a rajzoláshoz kellő adatokat:
`{"valtozo", "kifejezes", "zerushelyek": […], "szelsoertekek": [{"x", "y"}], "aszimptotak": ["x=0", "y=5"]}`.
Pontozás tételenként: a kifejezés egyezése (szimbolikusan, majd mintapontokon) 0,5; a zérushelyek 0,2, a
szélsőértékek 0,2, az aszimptoták 0,1 — de a nevezetes pontok csak jó kifejezés mellett számítanak.
A ```` ```plot ```` blokk alakja a C35-é; itt a tartalmi elvárás áll.

Mit nem lát: a javasolt ablak és a kiemelt pontok megjelenítési minőségét.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ITT = Path(__file__).resolve().parent
sys.path.insert(0, str(ITT.parent))
from kozos import arany as A  # noqa: E402
from kozos import kimenet, matek  # noqa: E402

ARANY = A.betolt(ITT)
VERZIO = "grafikon-" + A.verzio(ARANY)
ROUTER_FELADAT = "grafikon"
TURES = 0.01
SULY = {"kifejezes": 0.5, "zerushelyek": 0.2, "szelsoertekek": 0.2, "aszimptotak": 0.1}

PROMPT = (
    "Egy jegyzet részletében az alábbi függvény áll: ${keplet}$. Add meg a grafikon rajzolásához szükséges "
    "adatokat. A zérushelyeket és a szélsőértékeket a {ablak} intervallumon add meg (szélsőértéknek a belső "
    "pont és a töréspont számít, az intervallum végpontja nem).\n"
    "Csak JSON-t adj vissza, ebben az alakban:\n"
    '{{"valtozo": "x", "kifejezes": "<a függvény képlete sima írásmódban: * szorzás, ^ hatvány, sqrt(), abs(), '
    'sin(), log(x, alap)>", "zerushelyek": [<számok vagy pontos kifejezések szövegként>], '
    '"szelsoertekek": [{{"x": "…", "y": "…"}}], "aszimptotak": ["x=…" vagy "y=…"]}}\n\n'
    "A JEGYZET RÉSZLETE:\n{szoveg}")


def tetelek(cfg):
    for k in ARANY["kepletek"]:
        prompt = PROMPT.format(keplet=k["keplet"], ablak=k["vart"]["ablak"].replace(",", ";"), szoveg=k["szoveg"])
        yield {"id": k["id"], "keres": {"messages": [{"role": "user", "content": prompt}], "max_tokens": 600},
               "vart": k["vart"]}


_GYOK_ZAROJEL_NELKUL = re.compile(r"√\s*([0-9]+(?:\.[0-9]+)?|[a-zA-Zπ])")


def _elemez(x):
    """A modell egy értéke: a zárójel nélküli unicode gyökjel (`-√3`, `2√3`) is (C19 rétegzett minta: a pontozó a helyes
    `["-√3", "0", "√3"]` választ elutasította). A közös `matek.elemez`-hez nem nyúlunk (a ```plot TS-paritása)."""
    return matek.elemez(_GYOK_ZAROJEL_NELKUL.sub(r"√(\1)", str(x)))


def _szamok(lista) -> list | None:
    if not isinstance(lista, list):
        return None
    try:
        return [_elemez(x) for x in lista]
    except matek.MatekHiba:
        return None


def _halmaz(vart: list[str], kapott) -> bool:
    k = _szamok(kapott)
    return k is not None and matek._halmaz_egyezik([matek.elemez(v) for v in vart], k, TURES)


def _pontok(vart: list[dict], kapott) -> bool:
    if not isinstance(kapott, list) or len(kapott) != len(vart) or not all(isinstance(p, dict) for p in kapott):
        return False
    try:
        k = [(_elemez(p.get("x")), _elemez(p.get("y"))) for p in kapott]
    except matek.MatekHiba:
        return False
    for v in vart:
        vx, vy = matek.elemez(v["x"]), matek.elemez(v["y"])
        par = next((p for p in k if matek.kozel(p[0], vx, TURES) and matek.kozel(p[1], vy, TURES)), None)
        if par is None:
            return False
        k.remove(par)
    return True


def _aszimptotak(vart: list[str], kapott) -> bool:
    if not isinstance(kapott, list):
        return False
    try:
        def alak(s):
            bal, jobb = str(s).replace(" ", "").split("=", 1)
            return bal.lower(), matek.elemez(jobb)
        v, k = [alak(x) for x in vart], [alak(x) for x in kapott]
    except (ValueError, matek.MatekHiba):
        return False
    return len(v) == len(k) and all(any(a == b and matek.kozel(y, x, TURES) for b, y in k) for a, x in v)


def pontoz_egyet(vart: dict, valasz) -> dict:
    adat = kimenet.json_kinyer(valasz)
    resz = dict.fromkeys(SULY, False)
    if isinstance(adat, dict):
        try:
            kif = matek._mag(str(adat.get("kifejezes", "")))
            resz["kifejezes"] = matek.kifejezes_egyezik(matek.elemez(vart["kifejezes"]), matek.elemez(kif), 1e-6)
        except matek.MatekHiba:
            pass
        if resz["kifejezes"]:
            resz["zerushelyek"] = _halmaz(vart["zerushelyek"], adat.get("zerushelyek", []))
            resz["szelsoertekek"] = _pontok(vart["szelsoertekek"], adat.get("szelsoertekek", []))
            resz["aszimptotak"] = _aszimptotak(vart["aszimptotak"], adat.get("aszimptotak", []))
    return {"pont": sum(SULY[k] for k, v in resz.items() if v), **resz}


def formatum_ok(valasz, vart) -> bool:
    """C18.1 (csak jelentés): kinyerhető-e a válaszból JSON-objektum."""
    return isinstance(kimenet.json_kinyer(valasz), dict)


def pontoz(rekordok) -> dict:
    e = [(r["id"], pontoz_egyet(r["vart"], r.get("valasz"))) for r in rekordok]
    n = len(e)
    return {"pontszam": round(A.atlag(x["pont"] for _, x in e), 4),
            **{k: round(sum(x[k] for _, x in e) / n, 4) if n else 0.0 for k in SULY},
            "rossz": [{"id": i, **{k: v for k, v in x.items() if k != "pont"}} for i, x in e if x["pont"] < 1.0]}
