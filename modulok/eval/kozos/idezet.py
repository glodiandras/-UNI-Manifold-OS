"""Idézet visszakeresése a forrásszövegben (összefoglalás- és kártya-pontozó).

Előbb normalizált pontos egyezés (kisbetű, írásjel és Markdown-jelölés nélkül), utána közelítő,
szószintű csúszóablak: a modell egy-két elütése vagy kihagyott jelölése még idézet, a kitalált mondat nem.
"""
from __future__ import annotations

import difflib
import re

from . import tavolsag

_SZO = re.compile(r"[0-9A-Za-zÀ-ɏ]+", re.UNICODE)
# a műveleti jel is token (C22a): nélküle „(a+b)^2 = a^2 + 2ab + b^2” és „(a-b)^2 = a^2 - 2ab + b^2” ugyanaz a sorozat, és
# az idézet a rossz mondatra is illeszkedne (a legacy kvízlánc füstpróbáján mérve, 2026-09-27). A `*` és a `^` nem
# token: a Markdown kiemelése (`**vastag**`) és a blokkazonosító (`^id`) nem tartalom.
SZO_ES_JEL = re.compile(r"[0-9A-Za-zÀ-ɏ]+|[+\-−=<>≤≥/·×÷]", re.UNICODE)


def szavak_helyekkel(szoveg: str, minta: re.Pattern = _SZO) -> list[tuple[str, int, int]]:
    """(kisbetűs szó, kezdet, vég) a szöveg eredeti karakterhelyeivel. A `minta` adja a szavakat (alap: betű-számjegy)."""
    s = tavolsag.nfc(szoveg)
    return [(m.group(0).lower(), m.start(), m.end()) for m in minta.finditer(s)]


class Forras:
    """Egy forrásszöveg szóindexe: ugyanabban a jegyzetben sok idézetet keresünk. A `minta` a szavak és az idézet
    tokenizálása (alap: betű-számjegy; `SZO_ES_JEL`: a műveleti jelek is tokenek)."""

    def __init__(self, szoveg: str, minta: re.Pattern = _SZO):
        self.szoveg = tavolsag.nfc(szoveg)
        self._minta = minta
        self.szavak = szavak_helyekkel(self.szoveg, minta)
        self._lista = [w for w, _, _ in self.szavak]
        self._hol: dict[str, list[int]] = {}
        for i, w in enumerate(self._lista):
            self._hol.setdefault(w, []).append(i)

    def keres(self, idezet: str, kuszob: float = 0.85) -> dict:
        """→ `{talalt, hasonlosag, szo: (i0, i1) | None, hely: (k, v) | None, szoszam}`.
        A `szo` a forrás szóindex-tartománya, a `hely` a karakterhelye."""
        q = [w for w, _, _ in szavak_helyekkel(idezet, self._minta)]
        n = len(q)
        ures = {"talalt": False, "hasonlosag": 0.0, "szo": None, "hely": None, "szoszam": n}
        if not n or not self._lista:
            return ures
        for i in self._hol.get(q[0], []):                      # pontos egyezés
            if self._lista[i:i + n] == q:
                return self._eredmeny(i, i + n, 1.0, n)
        legj, hol = 0.0, None
        qs = " ".join(q)                                       # betűszintű hasonlóság: az elütés még idézet
        kezdetek = set()
        for eltolas, w in enumerate(q[:4]):                    # horgony: az első négy szó bármelyike
            for i in self._hol.get(w, []):
                kezdetek.add(max(0, i - eltolas))
        for i in sorted(kezdetek):
            for hossz in {n, max(1, n - 1), n + 1, max(1, n - 2), n + 2}:
                ablak = self._lista[i:i + hossz]
                if not ablak:
                    continue
                h = difflib.SequenceMatcher(None, qs, " ".join(ablak), autojunk=False).ratio()
                if h > legj:
                    legj, hol = h, (i, i + len(ablak))
        if hol and legj >= kuszob:
            return self._eredmeny(hol[0], hol[1], legj, n)
        ures["hasonlosag"] = round(legj, 3)
        return ures

    def _eredmeny(self, i0: int, i1: int, h: float, n: int) -> dict:
        return {"talalt": True, "hasonlosag": round(h, 3), "szo": (i0, i1),
                "hely": (self.szavak[i0][1], self.szavak[i1 - 1][2]), "szoszam": n}

    @property
    def szoszam(self) -> int:
        return len(self._lista)


def atfedes(a: tuple[int, int] | None, b: tuple[int, int] | None) -> int:
    """Két szóindex-tartomány közös szavainak száma."""
    if not a or not b:
        return 0
    return max(0, min(a[1], b[1]) - max(a[0], b[0]))


def lefedi(idezet: tuple[int, int] | None, kulcs: tuple[int, int] | None, arany: float = 0.5) -> bool:
    """Az idézet lefedi-e a kulcsrészt: a kulcsrész szavainak legalább `arany` része az idézetben áll."""
    if not idezet or not kulcs:
        return False
    return atfedes(idezet, kulcs) >= arany * (kulcs[1] - kulcs[0])
