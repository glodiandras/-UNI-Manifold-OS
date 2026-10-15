"""Aranyhalmaz: beágyazó modell a keresésben (router-feladat: `beagyazas`) — 50 kérdés–jegyzet pár.

Tételek: a korpusz darabjai kötegekben és az 50 kérdés (`tipus: embed`). A pontozó a vektorokból koszinusz-
hasonlóságot számol, a jegyzet pontja a legjobb darabjáé; mutatók: recall@1/5/10 és MRR, kérdéstípusonként is.
A pontszám a recall@5 (a keresőfelület első találatai).

Mit nem lát: a korpusz ~300 jegyzet (a célok és a mappabeli szomszédaik), nem a teljes vault — a szám a
modellek sorrendjére jó, az abszolút értéke a teljes vaulton kisebb lesz (azt a C25 méri a `kereses/parok.json`
párjaival). A kérdés és a dokumentum ugyanazzal a hívással, modell-specifikus utasítás-előtag nélkül megy.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

ITT = Path(__file__).resolve().parent
sys.path.insert(0, str(ITT.parent))
sys.path.insert(0, str(ITT.parent / "kereses"))
from kozos import arany as A  # noqa: E402
import korpusz as K  # noqa: E402

PAROK = K.parok()
VERZIO = "beagyazas-" + A.verzio(PAROK)
ROUTER_FELADAT = "beagyazas"
KOTEG = 16


def tetelek_ebbol(vault, parlista: list[dict]):
    korp = K.korpusz(vault, parlista)
    darabok = [(ut, d) for ut, dk in korp.items() for d in dk]
    for i in range(0, len(darabok), KOTEG):
        koteg = darabok[i:i + KOTEG]
        yield {"id": f"korpusz-{i // KOTEG:03d}", "keres": {"tipus": "embed", "input": [d for _, d in koteg]},
               "vart": {"fajta": "korpusz", "utak": [ut for ut, _ in koteg]}}
    for p in parlista:
        yield {"id": f"kerdes-{p['id']}", "keres": {"tipus": "embed", "input": [p["kerdes"]]},
               "vart": {"fajta": "kerdes", "cel": p["cel"], "tipus": p["tipus"]}}


def tetelek(cfg):
    yield from tetelek_ebbol(K.forras(cfg, PAROK), PAROK["parok"])


def pontoz(rekordok) -> dict:
    import numpy as np
    utak, vektorok, kerdesek, hibas = [], [], [], 0
    for r in rekordok:
        v, valasz = r["vart"], r.get("valasz")
        if not isinstance(valasz, list) or not valasz:
            hibas += 1
            if v["fajta"] == "kerdes":
                kerdesek.append((r["id"], v, None))
            continue
        if v["fajta"] == "korpusz":
            if len(valasz) != len(v["utak"]):
                hibas += 1
                continue
            utak += v["utak"]
            vektorok += valasz
        else:
            kerdesek.append((r["id"], v, valasz[0]))
    helyek, tipus, rossz = [], defaultdict(list), []
    if vektorok:
        m = np.asarray(vektorok, dtype="float32")
        m /= np.linalg.norm(m, axis=1, keepdims=True) + 1e-12
    for azon, v, q in kerdesek:
        hely = None
        if vektorok and q is not None:
            qv = np.asarray(q, dtype="float32")
            pont = m @ (qv / (np.linalg.norm(qv) + 1e-12))
            legjobb: dict[str, float] = {}
            for ut, p in zip(utak, pont):
                if p > legjobb.get(ut, -2.0):
                    legjobb[ut] = float(p)
            sorrend = sorted(legjobb, key=lambda u: (-legjobb[u], u))
            hely = sorrend.index(v["cel"]) + 1 if v["cel"] in legjobb else None
        helyek.append(hely)
        tipus[v["tipus"]].append(hely)
        if not hely or hely > 5:
            rossz.append({"id": azon, "hely": hely})
    mut = K.rangmutatok(helyek)
    return {"pontszam": mut["recall5"], **mut, "kerdesek": len(kerdesek), "korpusz_darab": len(utak),
            "korpusz_jegyzet": len(set(utak)), "hibas_rekord": hibas,
            "tipusok": {t: K.rangmutatok(h) for t, h in sorted(tipus.items())}, "rossz": rossz}
