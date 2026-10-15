"""A rangsorok összefésülése (tiszta függvények): RRF, jegyzetszintű összevonás, lexikai darabpont, reranker.

**RRF** (reciprocal rank fusion): `pont(x) = Σ_ág súly_ág / (k + hely_ág(x))`, a hely 1-től. Skálafüggetlen (a `bm25` és a
koszinusz nem vethető össze közvetlenül), és a C18 `kereses` halmazán a súly mérhető (`modulok/eval/kereses/hibrid.py`).
A `k` = 60 és az 1 : 1 súly **kalibrálatlan induló érték** (a szakirodalom szokásos értéke); a K160 méri a valódi vaulton.

A reranker (hívható: `(kérdés, dokumentumok) → pontok`) csak az első `n` jelöltet rendezi át; a többi utána, az eredeti
sorrendben. A holtverseny mindig determinisztikusan dől el (az azonosító szerint).
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Callable, Hashable, Iterable, Sequence

Reranker = Callable[[str, list[str]], list[float]]


def rrf(agak: dict[str, Sequence[Hashable]], k: float = 60.0, sulyok: dict[str, float] | None = None) -> list[tuple]:
    """`{ág: [azonosító… (legjobb elöl)]}` → `[(azonosító, pont, {ág: hely})…]` csökkenő pont szerint. Egy ágon belül
    az ismétlődő azonosító az első helyén számít."""
    pont: dict = {}
    helyek: dict = {}
    for ag, lista in agak.items():
        s = 1.0 if sulyok is None else float(sulyok.get(ag, 1.0))
        latott = set()
        for i, x in enumerate(lista, 1):
            if x in latott:
                continue
            latott.add(x)
            pont[x] = pont.get(x, 0.0) + s / (k + i)
            helyek.setdefault(x, {})[ag] = i
    return sorted(((x, round(p, 8), helyek[x]) for x, p in pont.items()), key=lambda t: (-t[1], str(t[0])))


def jegyzetre(darab_talalatok: Iterable[tuple[str, Hashable, float]]) -> list[tuple[str, Hashable, float]]:
    """Darabtalálatok `(út, darab, pont)` → jegyzetek a legjobb darabjuk szerint `(út, legjobb darab, pont)`, csökkenően."""
    legjobb: dict[str, tuple] = {}
    for ut, d, p in darab_talalatok:
        if ut not in legjobb or p > legjobb[ut][2]:
            legjobb[ut] = (ut, d, p)
    return sorted(legjobb.values(), key=lambda t: (-t[2], t[0]))


def bm25(kerdes_tovek: Sequence[str], dokumentumok: dict[Hashable, Sequence[str]], k1: float = 1.4,
         b: float = 0.75) -> dict[Hashable, float]:
    """BM25 kis jelölthalmazon (a darabok lexikai pontja a vault-válasz jelöltjeihez; a jegyzetszintű BM25 az FTS5-é).
    Az IDF a jelölthalmazon számol: a sorrendhez elég, abszolút értéke nem vethető össze más kérdésével."""
    n = len(dokumentumok)
    if not n:
        return {}
    tf = {d: Counter(t) for d, t in dokumentumok.items()}
    hossz = {d: sum(c.values()) for d, c in tf.items()}
    atlag = (sum(hossz.values()) / n) or 1.0
    df = Counter(t for c in tf.values() for t in c)
    pont: dict = {}
    for t, qf in Counter(kerdes_tovek).items():
        if not df.get(t):
            continue
        idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
        for d, c in tf.items():
            f = c.get(t)
            if f:
                pont[d] = pont.get(d, 0.0) + idf * f * (k1 + 1) / (f + k1 * (1 - b + b * hossz[d] / atlag)) * min(qf, 3)
    return pont


def fedes(kerdes_tovek: Sequence[str], dok_tovek: Iterable[str]) -> float:
    """A kérdés (különböző) töveinek aránya a dokumentumban: a „van-e elég forrás” modell nélküli jele."""
    q = set(kerdes_tovek)
    return len(q & set(dok_tovek)) / len(q) if q else 0.0


def rerankel(kerdes: str, jeloltek: Sequence[tuple[Hashable, str]], reranker: Reranker, n: int = 20) -> list[tuple]:
    """Az első `n` jelölt `(azonosító, szöveg)` a reranker pontja szerint, utána a többi az eredeti sorrendben:
    `[(azonosító, rerank-pont | None)…]`. Hibás válasz (hossz, nem szám) → `ValueError` (a hívó a fúziós sorrendnél marad)."""
    eleje, vege = list(jeloltek[:n]), list(jeloltek[n:])
    if not eleje:
        return []
    pontok = reranker(kerdes, [s for _, s in eleje])
    if (not isinstance(pontok, (list, tuple)) or len(pontok) != len(eleje)
            or not all(isinstance(p, (int, float)) and not isinstance(p, bool) and math.isfinite(p) for p in pontok)):
        raise ValueError("a reranker válasza nem a jelöltekre adott véges számok listája")
    rendezett = sorted(zip(eleje, pontok, range(len(eleje))), key=lambda t: (-t[1], t[2]))
    return [(j[0], float(p)) for j, p, _ in rendezett] + [(j[0], None) for j in vege]
