"""A jegyzetből a felismerendő képletek kivágása és a jegyzetbeli hely (C35a). **Nincs SymPy**: a kivágás a szülő-oldalon
fut (csak reguláris kifejezés), a felismerés kifejezésenként a homokozó gyermekében (CLAUDE.md 46. döntés).

`jeloltek(szoveg)` → [(karakterhely, képlet-szöveg)] előfordulási sorrendben (a `$…$`, `$$…$$`, `\\(…\\)`, `\\[…\\]`,
```` ```math ```` képletek és a TikZ/pgfplots blokkok); `hely(...)` → a jegyzetbeli sor és a „már van blokk alatta” jelzés.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

PGF_KULCS = re.compile(r"\\addplot|\\begin\{(?:tikzpicture|axis)\}|\\draw\b[^;]*\bplot\b")
PGF_BLOKK = re.compile(r"\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}|\\begin\{axis\}.*?\\end\{axis\}", re.S)


def _latex():
    """A `kozos.latex` (stdlib): a hely a `MOS_MODULOK`-ból vagy a csomag szülőjéből."""
    modulok = os.environ.get("MOS_MODULOK") or str(Path(__file__).resolve().parents[1])
    ut = str(Path(modulok) / "eval")
    if ut not in sys.path:
        sys.path.insert(0, ut)
    from kozos import latex
    return latex


def jeloltek(szoveg: str) -> list[tuple[int, str]]:
    """A jegyzet felismerendő szövegrészei (karakterhely, szöveg), helysorrendben; a pgf-blokk belsejéből kinyert
    töredék (ami maga nem pgf-kulcs) kimarad."""
    szoveg = szoveg or ""
    jelolt: list[tuple[int, str]] = []
    kurzor = 0
    for k in _latex().kepletek(szoveg):
        i = szoveg.find(k, kurzor)
        if i < 0:
            i = szoveg.find(k)
        if i >= 0:
            kurzor = i + len(k)
        jelolt.append((i, k))
    pgf_helyek = [(m.start(), m.end()) for m in PGF_BLOKK.finditer(szoveg)]
    jelolt += [(a, szoveg[a:b]) for a, b in pgf_helyek]
    ki = []
    for i, k in sorted(jelolt, key=lambda t: t[0]):
        if any(a <= i < b for a, b in pgf_helyek) and not PGF_KULCS.search(k):
            continue
        ki.append((i, k))
    return ki


def hely(szoveg: str, i: int, keplet: str, blokkok) -> dict:
    """A képlet jegyzetbeli sora (1-től), az utolsó sora, és hogy alatta (3 soron belül) van-e már plot blokk.
    `i < 0` (nem található): nincs sor."""
    if i is None or i < 0:
        return {"sor": None, "veg_sor": None, "blokk_kovetkezik": False}
    sor = (szoveg or "").count("\n", 0, i) + 1
    veg = sor + keplet.count("\n")
    return {"sor": sor, "veg_sor": veg, "blokk_kovetkezik": any(veg < b.kezdo_sor <= veg + 3 for b in blokkok)}


_NYITO_ZARO = (("$$", "$$"), ("\\[", "\\]"), ("\\(", "\\)"), ("$", "$"))
_MATH_NYITO = re.compile(r"(?:^|\n)[ \t]*(`{3,}|~{3,})[ \t]*math[ \t]*\n[ \t]*$", re.I)


def tarolo_veg_sor(szoveg: str, i: int, keplet: str) -> int | None:
    """Annak a sornak a száma (1-től), ahol a képletet tartalmazó jelölés (`$…$`, `$$…$$`, `\\(…\\)`, `\\[…\\]`, ```` ```math ````
    kerítés) lezárul — ide, EZ UTÁN írható blokk. A `jeloltek` a képlet **belsejét** adja (a `$$` nélkül), így a `hely` `veg_sor`-a
    egy többsoros `$$ … $$` blokkban a záró `$$` ELŐTTI sor: oda beszúrva a blokk a képletet törné szét. A pgf-blokk önmagában
    teljes (nincs nyitó jel). Ha a záró jel nem található: `None` (a hívó nem ír)."""
    if i is None or i < 0:
        return None
    veg = i + len(keplet)
    elotte = szoveg[:i]
    m = _MATH_NYITO.search(elotte)
    if m:                                               # ```math … ``` — a záró kerítés sora
        kerites = re.compile(r"^[ \t]*" + re.escape(m.group(1)[0]) + "{" + str(len(m.group(1))) + r",}[ \t]*$", re.M)
        z = kerites.search(szoveg, veg)
        return None if z is None else szoveg.count("\n", 0, z.end()) + 1
    vagott = elotte.rstrip(" \t\r\n")
    for nyito, zaro in _NYITO_ZARO:
        if vagott.endswith(nyito) and not (nyito == "$" and vagott.endswith("$$")):
            p = szoveg.find(zaro, veg)
            return None if p < 0 else szoveg.count("\n", 0, p + len(zaro) - 1) + 1
    return szoveg.count("\n", 0, max(veg - 1, 0)) + 1    # önálló szövegrész (pgf-blokk): a saját utolsó sora


def van_blokk_alatta(blokkok, veg_sor: int, tav: int = 3) -> bool:
    """Van-e a `veg_sor` után `tav` soron belül plot blokk (a `hely` `blokk_kovetkezik`-jének, a tároló végéhez mérve)."""
    return any(veg_sor < b.kezdo_sor <= veg_sor + tav for b in blokkok)
