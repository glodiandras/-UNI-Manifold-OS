"""A hibrid keresés mérése a teljes vaulton a `parok.json` 50 párjával (C25b; 2. audit T153, M12) és a regresszió-kapu.

Négy változat (CHATKALAUZ C25b 6. pont): `fts` (FTS5 `bm25`), `fts_rerank` (az első `rerank_n` jelölt rerankerrel),
`fts_vektor` (FTS5 + vektor RRF-fel), `fts_vektor_rerank`. A pontozó a keresés-aranyhalmaz közös `korpusz.rangmutatok`-ja
(recall@1/5/10, MRR; a cél a jegyzet útja), kérdéstípusonként is. A halmaz **fagyasztott**: a riport a verzióját rögzíti.

- `dontes(mutatok)` — tiszta függvény (M12): a reranker csak akkor kell, ha a `fts`-hez képest mérhetően javít; a vektorindex
  csak akkor, ha a vektoros változat mérhetően jobb a *rerankeresnél* (a legjobb vektor nélkülinél).
- `regresszio(uj, alap)` — tiszta függvény: a hibrid mód egyik mutatója sem eshet a lexikai alapszint (vagy egy rögzített
  korábbi mérés) alá a tűrésen túl.
- `futtat(…)` — a négy változat egy `HibridKereso`-val; ami nincs kötve (beágyazó, reranker), az `nem_mert`.

Modellt nem tölt be: a hívó adja a beágyazót és a rerankert (a Macen a worker, a tesztben álhívó).
"""
from __future__ import annotations

import dataclasses
import sys
from collections import defaultdict
from pathlib import Path
from typing import Callable

ITT = Path(__file__).resolve().parent
sys.path.insert(0, str(ITT.parent))
sys.path.insert(0, str(ITT))
import korpusz as K  # noqa: E402

VALTOZATOK = ("fts", "fts_rerank", "fts_vektor", "fts_vektor_rerank")
MUTATOK = ("recall5", "recall10", "mrr")


def helyek(parlista: list[dict], rangsorolo: Callable[[str], list[str]]) -> list[int | None]:
    """A cél helye (1-től) a rangsoroló találati útjai között; nincs a listán: `None`."""
    ki = []
    for p in parlista:
        utak = rangsorolo(p["kerdes"])
        ki.append(utak.index(p["cel"]) + 1 if p["cel"] in utak else None)
    return ki


def mer(parlista: list[dict], rangsorolo: Callable[[str], list[str]]) -> dict:
    h = helyek(parlista, rangsorolo)
    tipus: dict[str, list] = defaultdict(list)
    for p, x in zip(parlista, h):
        tipus[p.get("tipus", "?")].append(x)
    rossz = [{"id": p["id"], "hely": x} for p, x in zip(parlista, h) if not x or x > 5]
    return {**K.rangmutatok(h), "tipusok": {t: K.rangmutatok(v) for t, v in sorted(tipus.items())}, "rossz": rossz}


def dontes(mutatok: dict[str, dict], min_javulas: float = 0.02, mutato: str = "recall5") -> dict:
    """M12: `{valtozat: {mutato: szám}}` → `{rerank, vektor, javasolt, indok}`. A nem mért változat nem nyerhet."""
    def m(v):
        x = mutatok.get(v)
        return x.get(mutato) if isinstance(x, dict) and isinstance(x.get(mutato), (int, float)) else None
    fts, fr, fv, fvr = (m(v) for v in VALTOZATOK)
    if fts is None:
        return {"rerank": False, "vektor": False, "javasolt": None, "indok": "az FTS5 alapszint nincs mérve"}
    rerank = fr is not None and fr >= fts + min_javulas
    vektor_nelkul = max(fts, fr) if rerank else fts
    legjobb_vektor = max((x for x in (fv, fvr) if x is not None), default=None)
    vektor = legjobb_vektor is not None and legjobb_vektor >= vektor_nelkul + min_javulas
    if vektor:          # holtversenyben az olcsóbb (reranker nélküli) változat
        javasolt = "fts_vektor" if fv is not None and fv >= legjobb_vektor else "fts_vektor_rerank"
    else:
        javasolt = "fts_rerank" if rerank else "fts"
    indok = (f"{mutato}: fts {fts:.3f}" + (f", +rerank {fr:.3f}" if fr is not None else "")
             + (f", +vektor {fv:.3f}" if fv is not None else "") + (f", +vektor+rerank {fvr:.3f}" if fvr is not None else "")
             + f"; a küszöb +{min_javulas:.3f}")
    return {"rerank": rerank, "vektor": vektor, "javasolt": javasolt, "indok": indok}


def regresszio(uj: dict, alap: dict, tures: float = 0.0, mutatok=MUTATOK) -> list[str]:
    """A hibák listája (üres: zöld): minden mutató `uj ≥ alap − tures`."""
    hibak = []
    for k in mutatok:
        a, u = alap.get(k), uj.get(k)
        if isinstance(a, (int, float)) and (not isinstance(u, (int, float)) or u < a - tures):
            hibak.append(f"{k}: {u} < {a} − {tures}")
    return hibak


def futtat(kereso, parlista: list[dict], limit: int = 10, halmaz: str | None = None) -> dict:
    """A négy változat a `HibridKereso`-val (a beállítása változatonként módosul, utána visszaáll). Ami nem mérhető (nincs
    beágyazó, vektortár vagy reranker): `{"nem_mert": ok}`."""
    from core.index.hibrid import rangsor
    eredeti = kereso.b
    ki: dict = {"halmaz": halmaz, "parok": len(parlista), "valtozatok": {}}

    def fts(q):
        with kereso.index_olvaso() as c:
            return kereso._lexikai(c, q)["utak"][:max(limit, eredeti.rerank_n)]

    def fts_rerank(q):
        utak = fts(q)
        rr = rangsor.rerankel(q, [(u, kereso.legjobb_szoveg(u, q)) for u in utak], kereso.reranker, eredeti.rerank_n)
        return [u for u, _ in rr]

    def hibrid(q):
        return [t["ut"] for t in kereso.keres(q, limit, "hibrid")["talalatok"]]

    try:
        for v in VALTOZATOK:
            if "vektor" in v and kereso.miert_lexikai() is not None:
                ki["valtozatok"][v] = {"nem_mert": kereso.miert_lexikai()}
                continue
            if v.endswith("rerank") and kereso.reranker is None:
                ki["valtozatok"][v] = {"nem_mert": "nincs_reranker"}
                continue
            kereso.b = dataclasses.replace(eredeti, rerank=v.endswith("rerank"))
            fv = {"fts": fts, "fts_rerank": fts_rerank}.get(v, hibrid)
            ki["valtozatok"][v] = mer(parlista, lambda q, fv=fv: fv(q)[:limit])
    finally:
        kereso.b = eredeti
    ki["dontes"] = dontes(ki["valtozatok"])
    return ki
