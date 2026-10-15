"""Aranyhalmaz: matek-megoldás (router-feladat: `matek`) — 40 emelt szintű feladat ismert végeredménnyel.

A modell levezet, és az utolsó sorban `VÉGEREDMÉNY: …` alakban adja az eredményt. A pontozó csak ezt a
zárósort nézi (az utolsót): fehérlistán át elemzi, és sympy-val veti össze a várt eredménnyel
(megoldáshalmaz, szám tűréssel, intervallum, pár, kifejezés). A modell kimenete nem fut kódként.

Mit nem lát: a levezetés helyességét (jó végeredmény hibás úton is pontot ér), és a zárósor nélküli jó
megoldást hibának veszi — a formátum betartása a feladat része (a C24 matek-motorja is gépi alakot vár).
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ITT = Path(__file__).resolve().parent
sys.path.insert(0, str(ITT.parent))
from kozos import arany as A  # noqa: E402
from kozos import kimenet, matek  # noqa: E402

ARANY = A.betolt(ITT)
VERZIO = "matek-" + A.verzio(ARANY)
ROUTER_FELADAT = "matek"
CIMKE = "VÉGEREDMÉNY"

ALAK = {
    "halmaz": "az összes megoldás pontosvesszővel elválasztva (pl. x = 2; x = -3); ha nincs megoldás: nincs megoldás",
    "szam": "egyetlen szám vagy tört, mértékegység és szöveg nélkül",
    "intervallum": "intervallum vagy egyenlőtlenség (pl. 1 <= x < 3, vagy x < -1 vagy x >= 3)",
    "par": "az ismeretlenek értéke pontosvesszővel elválasztva (pl. x = 4; y = 1)",
    "kifejezes": "egyetlen kifejezés",
}
PROMPT = ("Oldd meg az alábbi matematikafeladatot. Dolgozz lépésenként, röviden.\n"
          "A legutolsó sorban add meg a végeredményt pontosan ebben az alakban:\n"
          "{cimke}: <{alak}>\n\nFELADAT:\n{szoveg}")


def tetelek(cfg):
    for f in ARANY["feladatok"]:
        prompt = PROMPT.format(cimke=CIMKE, alak=ALAK[f["vart"]["tipus"]], szoveg=f["szoveg"])
        yield {"id": f["id"], "keres": {"messages": [{"role": "user", "content": prompt}], "max_tokens": 1500},
               "vart": {**f["vart"], "tema": f["tema"]}}


def formatum_ok(valasz, vart) -> bool:
    """C18.1 (csak jelentés): van-e a válaszban `VÉGEREDMÉNY:` zárósor."""
    return kimenet.zarosor(valasz, CIMKE) is not None


def pontoz(rekordok) -> dict:
    jo, tema, rossz, nincs_sor = 0, defaultdict(lambda: [0, 0]), [], 0
    for r in rekordok:
        sor = kimenet.zarosor(r.get("valasz"), CIMKE)
        nincs_sor += sor is None
        ok, indok = matek.ekvivalens(r["vart"], sor)
        jo += ok
        t = tema[r["vart"].get("tema", "egyeb")]
        t[0] += ok
        t[1] += 1
        if not ok:
            rossz.append({"id": r["id"], "zarosor": sor, "indok": indok})
    n = len(rekordok)
    return {"pontszam": round(jo / n, 4) if n else 0.0, "helyes": jo, "nincs_zarosor": nincs_sor,
            "temak": {k: f"{a}/{b}" for k, (a, b) in sorted(tema.items())}, "rossz": rossz}
