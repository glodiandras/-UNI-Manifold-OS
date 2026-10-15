"""Aranyhalmaz: levezetés ellenőrzése (router-feladat: `matek_ellenorzo`) — 10 hibás + 10 helyes levezetés.

A hibás levezetésekben pontosan egy beültetett hiba van (előjel, átrendezés, osztás nullával, hamis gyök);
a kontrollok a `matek` halmaz lépéses feladatainak helyes megoldásmenetei. A modell az utolsó sorban ítél:
`ÍTÉLET: HELYES` vagy `ÍTÉLET: HIBA <az első hibás sor száma>`.

A pontszám a helyes ítéletek aránya: a hibásnál a sorszámnak is egyeznie kell, a helyesnél a téves riasztás
hiba. A halmaz kiegyensúlyozott, így a mindig „HIBA” vagy mindig „HELYES” válasz legfeljebb 0,5-öt ér.

Mit nem lát: az indoklás minőségét, és azt, ha a modell a hibát jó helyen, de rossz okkal jelöli.
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

ITT = Path(__file__).resolve().parent
sys.path.insert(0, str(ITT.parent))
from kozos import arany as A  # noqa: E402
from kozos import kimenet, tavolsag  # noqa: E402

MATEK = A.betolt(ITT.parent / "matek")
VERZIO = "matek_ellenorzo-" + A.verzio(MATEK)
ROUTER_FELADAT = "matek_ellenorzo"
CIMKE = "ÍTÉLET"

PROMPT = ("Az alábbi feladat megoldása számozott sorokban áll. Ellenőrizd sorról sorra: minden sor helyesen "
          "következik-e az előzőből, és a végeredmény helyes-e (nem veszett-e el megoldás, nem maradt-e benne "
          "hamis gyök). Röviden indokolj, majd a legutolsó sorban pontosan így ítélj:\n"
          "{cimke}: HELYES\nvagy\n{cimke}: HIBA <az első hibás sor száma>\n\nFELADAT:\n{szoveg}\n\nLEVEZETÉS:\n{sorok}")


def levezetesek() -> list[dict]:
    """A 10 hibás levezetés és a 10 helyes kontroll, egységes alakban."""
    feladat = {f["id"]: f for f in MATEK["feladatok"]}
    ki = [{"id": h["id"], "szoveg": feladat[h["alap"]]["szoveg"], "sorok": h["sorok"], "hibas_sor": h["hibas_sor"],
           "hiba": h["hiba"]} for h in MATEK["levezetesek"]]
    ki += [{"id": f"jo-{f['id']}", "szoveg": f["szoveg"], "sorok": f["lepesek"], "hibas_sor": None, "hiba": None}
           for f in MATEK["feladatok"] if f.get("lepesek")]
    return ki


def tetelek(cfg):
    for lv in sorted(levezetesek(), key=lambda x: A.szoveg_sha256(x["id"])):          # hibás és helyes keverve
        sorok = "\n".join(f"({i}) ${s['latex']}$" for i, s in enumerate(lv["sorok"], 1))
        prompt = PROMPT.format(cimke=CIMKE, szoveg=lv["szoveg"], sorok=sorok)
        yield {"id": lv["id"], "keres": {"messages": [{"role": "user", "content": prompt}], "max_tokens": 1200},
               "vart": {"hibas_sor": lv["hibas_sor"], "hiba": lv["hiba"]}}


def formatum_ok(valasz, vart) -> bool:
    """C18.1 (csak jelentés): van-e a válaszban `ÍTÉLET:` zárósor."""
    return kimenet.zarosor(valasz, CIMKE) is not None


def itelet(valasz) -> tuple[str | None, int | None]:
    """→ (`helyes` | `hiba` | None, sorszám)."""
    sor = kimenet.zarosor(valasz, CIMKE)
    if sor is None:
        return None, None
    h = tavolsag.hajt(sor)
    if h.startswith("helyes"):
        return "helyes", None
    if h.startswith("hiba"):
        m = re.search(r"\d+", sor)
        return "hiba", int(m.group(0)) if m else None
    return None, None


def pontoz(rekordok) -> dict:
    jo = felismert = riasztas = hibas = helyes = nincs = 0
    fajta, rossz = defaultdict(lambda: [0, 0]), []
    for r in rekordok:
        v = r["vart"]
        mit, sor = itelet(r.get("valasz"))
        nincs += mit is None
        if v["hibas_sor"] is None:
            helyes += 1
            ok = mit == "helyes"
            riasztas += mit == "hiba"
        else:
            hibas += 1
            felismert += mit == "hiba"
            ok = mit == "hiba" and sor == v["hibas_sor"]
            fajta[v["hiba"]][0] += ok
            fajta[v["hiba"]][1] += 1
        jo += ok
        if not ok:
            rossz.append({"id": r["id"], "itelet": mit, "sor": sor, "vart_sor": v["hibas_sor"]})
    n = len(rekordok)
    return {"pontszam": round(jo / n, 4) if n else 0.0, "helyes_itelet": jo,
            "felismert_hiba": f"{felismert}/{hibas}", "teves_riasztas": f"{riasztas}/{helyes}", "nincs_itelet": nincs,
            "hibafajtak": {k: f"{a}/{b}" for k, (a, b) in sorted(fajta.items())}, "rossz": rossz}
