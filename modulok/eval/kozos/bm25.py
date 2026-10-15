"""Kis BM25-rangsoroló szózsákokon (a füzet-átirat lexikai bírójához és a keresés nehéz negatívjaihoz)."""
from __future__ import annotations

import math
from collections import Counter


class Bm25:
    def __init__(self, k1: float = 1.4, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs: dict[str, Counter] = {}
        self.hossz: dict[str, int] = {}
        self.df: Counter = Counter()

    def hozzaad(self, azon: str, tokenek) -> None:
        """`tokenek`: lista vagy `{token: darab}` szótár."""
        c = Counter(tokenek) if not isinstance(tokenek, dict) else Counter(tokenek)
        self.docs[azon] = c
        self.hossz[azon] = sum(c.values())
        self.df.update(c.keys())

    def rangsor(self, kerdes, k: int | None = None) -> list[tuple[str, float]]:
        """A dokumentumok pontszám szerint csökkenően; azonos pontnál az azonosító dönt (determinisztikus)."""
        n = len(self.docs)
        if not n:
            return []
        atlag = sum(self.hossz.values()) / n or 1.0
        q = Counter(kerdes)
        pont: dict[str, float] = {}
        for t, qf in q.items():
            df = self.df.get(t)
            if not df:
                continue
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            for azon, c in self.docs.items():
                tf = c.get(t)
                if tf:
                    nev = tf + self.k1 * (1 - self.b + self.b * self.hossz[azon] / atlag)
                    pont[azon] = pont.get(azon, 0.0) + idf * tf * (self.k1 + 1) / nev * min(qf, 3)
        sor = sorted(pont.items(), key=lambda p: (-p[1], p[0]))
        return sor[:k] if k else sor
