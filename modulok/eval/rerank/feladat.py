"""Aranyhalmaz: újrarangsoroló modell (router-feladat: `rerank`) — 50 kérdés, kérdésenként 20 jelölt.

A jelöltek: a céljegyzet (a választ tartalmazó darabja) és 19 lexikai nehéz negatív (a BM25 szerint a
kérdéshez leginkább hasonló más jegyzetek legjobb darabja), rögzített, de kevert sorrendben. A modell
jelöltenként pontot ad; mutatók: MRR, recall@1/3, kérdéstípusonként is. A pontszám az MRR.

Mit nem lát: a jelöltlista a mérőkorpuszból jön, nem a C25 valódi első körös kereséséből; a negatívok
lexikailag nehezek, de a beágyazó tévesztéseit nem tartalmazzák.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ITT = Path(__file__).resolve().parent
sys.path.insert(0, str(ITT.parent))
sys.path.insert(0, str(ITT.parent / "kereses"))
from kozos import arany as A  # noqa: E402
from kozos import idezet  # noqa: E402
import korpusz as K  # noqa: E402

PAROK = K.parok()
VERZIO = "rerank-" + A.verzio(PAROK)
ROUTER_FELADAT = "rerank"
JELOLT = 20


def _cel_darab(dk: list[str], idezet_: str, b, ut: str, kerdes: str) -> str:
    """A cél azon darabja, amelyben az arany idézete áll; ha nem található, a kérdéshez lexikailag legjobb."""
    for d in dk:
        if idezet.Forras(d).keres(idezet_)["talalt"]:
            return d
    for u, azon in K.jegyzet_rangsor(b, kerdes):
        if u == ut:
            return dk[int(azon.rsplit("#", 1)[1])]
    return dk[0]


def tetelek_ebbol(vault, parlista: list[dict]):
    korp = K.korpusz(vault, parlista)
    b = K.lexikai(korp)
    for p in parlista:
        jeloltek = [(p["cel"], _cel_darab(korp[p["cel"]], p.get("idezet", ""), b, p["cel"], p["kerdes"]))]
        for ut, azon in K.jegyzet_rangsor(b, p["kerdes"]):
            if len(jeloltek) >= JELOLT:
                break
            if ut != p["cel"]:
                jeloltek.append((ut, korp[ut][int(azon.rsplit("#", 1)[1])]))
        for ut in sorted(korp):                                 # ha a lexikai lista rövid: feltöltés
            if len(jeloltek) >= JELOLT:
                break
            if ut not in {u for u, _ in jeloltek}:
                jeloltek.append((ut, korp[ut][0]))
        jeloltek.sort(key=lambda j: A.szoveg_sha256(p["id"] + j[0]))          # rögzített, de kevert sorrend
        yield {"id": f"rerank-{p['id']}",
               "keres": {"tipus": "rerank", "query": p["kerdes"], "documents": [d for _, d in jeloltek]},
               "vart": {"cel_index": [u for u, _ in jeloltek].index(p["cel"]), "tipus": p["tipus"], "n": len(jeloltek)}}


def tetelek(cfg):
    yield from tetelek_ebbol(K.forras(cfg, PAROK), PAROK["parok"])


def pontoz(rekordok) -> dict:
    helyek, tipus, rossz = [], defaultdict(list), []
    for r in rekordok:
        v, pont = r["vart"], r.get("valasz")
        hely = None
        if isinstance(pont, list) and len(pont) == v["n"] and all(isinstance(x, (int, float)) for x in pont):
            cel = pont[v["cel_index"]]
            # holtversenyben a cél a csoport végére kerül: az azonos pontot adó modell nem kap ingyen helyezést
            hely = 1 + sum(1 for i, x in enumerate(pont) if i != v["cel_index"] and x >= cel)
        helyek.append(hely)
        tipus[v["tipus"]].append(hely)
        if hely != 1:
            rossz.append({"id": r["id"], "hely": hely})
    mut = K.rangmutatok(helyek, (1, 3))
    return {"pontszam": mut["mrr"], **mut, "tipusok": {t: K.rangmutatok(h, (1, 3)) for t, h in sorted(tipus.items())},
            "rossz": rossz}
