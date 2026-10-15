"""A forrásjegyzet módosítása a kártyákhoz (C23b; `docs/C23-TERV.md` 1.3): `^m-…` blokkazonosító a forrásbekezdés végére és
a `## Gyakorlás` beágyazó sora — **egy szövegben**, mert a gépi írás egy tételében egy út egyszer szerepelhet (a forrás egy
`csere` művelet alap-hash-sel). Tiszta függvények: szöveg be, szöveg ki.

- A bekezdés a nyers Markdown üres sorral határolt blokkja a frontmatteren és a kódkerítésen kívül (a core kódmaszkjával);
  fejezet, táblázat és `$$` képletblokk nem kap azonosítót (az Obsidian ott külön sort kérne). A forrásrészt (a kapu
  találatát, tisztított szöveg) a bekezdések tisztított szövegében keressük (a kapu előkészítésének sor-tisztításával).
- A bekezdés végén már álló blokkazonosító (bármilyen, nem csak `m-`) újrahasznosul; az új azonosító `m-` + 4 hex a bekezdés
  szövegéből (determinisztikus), ütközésnél hosszabb.
- Ha a bekezdés nem horgonyozható, a kártya forrása a szakasz fejezetére mutat (`[[Jegyzet#Fejezet]]`), végső esetben a
  jegyzetre.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

from core.index.elemzo import _BLOKK
from core.index.maszk import FM_RE, mask_code
from modulok.kapuk import forras as KF

_FEJEZET = re.compile(r"^\s{0,3}#{1,6}[ \t]")
_SZO = re.compile(r"[^\W_]+")


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s or "")


def _szavak(s: str) -> list[str]:
    return [w.casefold() for w in _SZO.findall(nfc(s))]


def bekezdesek(md: str) -> list[tuple[int, int]]:
    """A horgonyozható bekezdések sortartományai `(első, utolsó)` (0-tól, zárt) a `\\n`-re hozott szövegben."""
    sorok = md.split("\n")
    maszk = mask_code(md).split("\n")
    fm = FM_RE.match(md)
    kezd = md[:fm.end()].count("\n") if fm else 0
    ki, cur = [], []
    matek = False
    for i in range(kezd, len(sorok)):
        s, m = sorok[i], maszk[i]
        kod = bool(s.strip()) and not m.strip()
        t = s.strip()
        nyit = t.startswith("$$") and not (len(t) > 2 and t.endswith("$$"))
        zar = matek and t.endswith("$$")
        if nyit or zar or matek:                    # a `$$ … $$` képletblokk belseje nem bekezdés
            matek = (nyit and not matek) or (matek and not zar)
            if cur:
                ki.append((cur[0], cur[-1]))
                cur = []
            continue
        if not t or kod or _FEJEZET.match(s) or t.startswith("|") or t in ("---", "***"):
            if cur:
                ki.append((cur[0], cur[-1]))
                cur = []
            continue
        cur.append(i)
    if cur:
        ki.append((cur[0], cur[-1]))
    return [(a, b) for a, b in ki if not sorok[b].rstrip().endswith("$$")]


def _tiszta(sorok: list[str]) -> list[str]:
    return _szavak(" ".join(KF._sor_tisztit(s) for s in sorok))


def keres(md: str, idezet: str, min_fedes: float = 0.6) -> tuple[int, int] | None:
    """Az `idezet` (tisztított forrásrész) bekezdése: a legtöbb szavát tartalmazó (legalább `min_fedes` arányban)."""
    cel = _szavak(idezet)
    if not cel:
        return None
    sorok = md.split("\n")
    legjobb, pont = None, 0.0
    for a, b in bekezdesek(md):
        szavak = _tiszta(sorok[a:b + 1])
        s = " ".join(szavak)
        if " ".join(cel) in s:
            return a, b
        halmaz = set(szavak)
        f = sum(1 for w in cel if w in halmaz) / len(cel)
        if f > pont:
            legjobb, pont = (a, b), f
    return legjobb if pont >= min_fedes else None


def azonositok(md: str) -> set[str]:
    return {m.group(1) for m in _BLOKK.finditer(md)}


def _uj_azon(szoveg: str, foglalt: set[str]) -> str:
    h = hashlib.sha1(nfc(szoveg).encode("utf-8")).hexdigest()
    for n in (4, 6, 8, 12):
        a = "m-" + h[:n]
        if a not in foglalt:
            return a
    i = 1
    while f"m-{h[:8]}{i}" in foglalt:
        i += 1
    return f"m-{h[:8]}{i}"


def horgonyoz(md: str, idezetek: list[str]) -> tuple[str, list[str | None]]:
    """A forrás új szövege és idézetenként a blokkazonosító (vagy `None`, ha a bekezdés nem horgonyozható). A sorvég a fájlé
    marad (CRLF-es fájl CRLF); a már meglévő azonosító újrahasznosul, a változatlan szöveg bájtra azonos."""
    crlf = "\r\n" in md
    lf = md.replace("\r\n", "\n") if crlf else md
    sorok = lf.split("\n")
    foglalt = azonositok(lf)
    kiosztva: dict[tuple[int, int], str] = {}
    ki: list[str | None] = []
    for idezet in idezetek:
        hely = keres(lf, idezet)
        if hely is None:
            ki.append(None)
            continue
        if hely not in kiosztva:
            utolso = sorok[hely[1]]
            m = _BLOKK.search(utolso)
            if m:
                kiosztva[hely] = m.group(1)
            else:
                a = _uj_azon("\n".join(sorok[hely[0]:hely[1] + 1]), foglalt)
                foglalt.add(a)
                sorok[hely[1]] = utolso.rstrip() + f" ^{a}"
                kiosztva[hely] = a
        ki.append(kiosztva[hely])
    uj = "\n".join(sorok)
    return (uj.replace("\n", "\r\n") if crlf else uj), ki


def link(cel: str, blokk: str | None, fejezet: str | None) -> str:
    """A kártya forrássorának link-célja: `Cél#^blokk`, `Cél#Fejezet` vagy `Cél`."""
    if blokk:
        return f"{cel}#^{blokk}"
    if fejezet:
        return f"{cel}#{fejezet}"
    return cel
