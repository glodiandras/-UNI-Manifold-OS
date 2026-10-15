"""A `## Füzet` szakasz tiszta függvényei (C21; a legacy `fuzet.beagyaz_szoveg` / `levalaszt_szoveg` portja, L48).

Egy fotó **blokkja**: a beágyazó sor (`![[IMG_1234.JPG]]`) és közvetlenül alatta — ha az átiratban volt képlet — egy összecsukott
callout a képletekkel (2. pont):

    ![[IMG_1234.JPG]]
    > [!info]- Képletek a fotóról
    > $$a^2+b^2=c^2$$

A szakasz a jegyzet végére kerül, ha még nincs; meglévőben a blokkok a fájlnév szerinti sorrendben állnak (a legacy rendje), a
callout utáni blokk üres sorral válik el (különben a következő beágyazás a callout lusta folytatása volna). Idempotens: a már
beágyazott fotó blokkja nem változik. A képlet a vault tartalmában `$$…$$` (Obsidian-kompatibilis, L47); a `==` nem kerül bele.
"""
from __future__ import annotations

import os
import re

CALLOUT_FEJ = "> [!info]- Képletek a fotóról"
_BEAGY = re.compile(r"^!\[\[([^\]]+)\]\]\s*$")
_FEJEZET = re.compile(r"^#{1,2}\s")
_BLOKK_KEPLET = re.compile(r"\$\$(.+?)\$\$", re.S)
_SOR_KEPLET = re.compile(r"(?<![\\$])\$(?!\$)([^$\n]+?)(?<![\\\s])\$(?!\$)")
_MATEK_JEL = re.compile(r"[=<>^_\\]|\d\s*[a-zA-Z]|[a-zA-Z]\s*\d")


def beagyazo_sor(link: str) -> str:
    return f"![[{link}]]"


def kepletek(atirat: str, max_db: int = 20) -> list[str]:
    """Az átirat képletei (`$$…$$`, `$…$`), előfordulási sorrendben, duplikátum és triviális (pl. `$x$`, `$12$`) nélkül."""
    if not atirat:
        return []
    talalat: list[tuple[int, str]] = []
    foglalt: list[tuple[int, int]] = []
    for m in _BLOKK_KEPLET.finditer(atirat):
        talalat.append((m.start(), m.group(1)))
        foglalt.append((m.start(), m.end()))
    for m in _SOR_KEPLET.finditer(atirat):
        if not any(a <= m.start() < b for a, b in foglalt):
            talalat.append((m.start(), m.group(1)))
    ki, latott = [], set()
    for _, k in sorted(talalat):
        k = " ".join(k.replace("\n", " ").split()).strip(" ,.;")
        kulcs = k.replace(" ", "")
        if len(kulcs) < 3 or not _MATEK_JEL.search(k) or kulcs in latott or "$" in k:
            continue
        latott.add(kulcs)
        ki.append(k)
        if len(ki) >= max_db:
            break
    return ki


def blokk(link: str, kepletek_: list[str] | tuple = ()) -> list[str]:
    sorok = [beagyazo_sor(link)]
    if kepletek_:
        sorok += [CALLOUT_FEJ] + [f"> $${k}$$" for k in kepletek_]
    return sorok


def _szakasz(lines: list[str], szakasz: str) -> tuple[int, int] | None:
    try:
        i = next(k for k, s in enumerate(lines) if s.rstrip() == szakasz)
    except StopIteration:
        return None
    j = next((k for k in range(i + 1, len(lines)) if _FEJEZET.match(lines[k])), len(lines))
    return i, j


def _blokkok(lines: list[str], i: int, j: int) -> list[tuple[int, int, str]]:
    """A szakasz fotó-blokkjai: (első sor, utolsó utáni sor, link) — a beágyazó sor és a közvetlenül alatta álló `>` sorok."""
    ki, k = [], i + 1
    while k < j:
        m = _BEAGY.match(lines[k])
        if not m:
            k += 1
            continue
        v = k + 1
        while v < j and lines[v].startswith(">"):
            v += 1
        ki.append((k, v, m.group(1)))
        k = v
    return ki


def beagyaz(text: str, link: str, kepletek_: list[str] | tuple = (), szakasz: str = "## Füzet") -> str:
    """A fotó blokkjának beillesztése (idempotens). Új szakasz a jegyzet végére kerül."""
    uj = blokk(link, kepletek_)
    lines = text.split("\n")
    sz = _szakasz(lines, szakasz)
    if sz is None:
        return text.rstrip("\n") + "\n\n" + szakasz + "\n\n" + "\n".join(uj) + "\n"
    i, j = sz
    blokkok = _blokkok(lines, i, j)
    if any(b[2] == link for b in blokkok):
        return text
    if not blokkok:
        at = i + 1
        while at < j and lines[at].strip() == "":
            at += 1
        return "\n".join(lines[:i + 1] + [""] + uj + ([""] if at < j else []) + lines[at:])
    kulcs = os.path.basename(link)
    hova, elozo = blokkok[-1][1], blokkok[-1]
    for n, b in enumerate(blokkok):
        if os.path.basename(b[2]) > kulcs:
            hova, elozo = b[0], (blokkok[n - 1] if n else None)
            break
    # üres sor kell a callout után (különben a következő sor a callout lusta folytatása): az előző blokk calloutja után és az
    # új blokk calloutja után, ha ott nem üres sor áll
    elotte = [""] if elozo is not None and elozo[1] - elozo[0] > 1 and lines[hova - 1].strip() != "" else []
    utana = [""] if len(uj) > 1 and hova < len(lines) and lines[hova].strip() != "" else []
    return "\n".join(lines[:hova] + elotte + uj + utana + lines[hova:])


def levalaszt(text: str, link: str, szakasz: str = "## Füzet") -> str:
    """A `beagyaz` inverze: a fotó blokkja (beágyazás + callout) kiesik; ha a szakasz ezzel kiürül, a szakasz is."""
    lines = text.split("\n")
    sz = _szakasz(lines, szakasz)
    if sz is None:
        return text
    i, j = sz
    talalt = [b for b in _blokkok(lines, i, j) if b[2] == link]
    if not talalt:
        return text
    a, b, _ = talalt[0]
    if a > i + 1 and b < j and lines[b].strip() == "" and (
            lines[a - 1].strip() == ""                                                     # a kettős üres sorból egy marad
            or (_BEAGY.match(lines[a - 1]) and b + 1 < j and _BEAGY.match(lines[b + 1]))):  # a callout utáni elválasztó sor
        b += 1
    lines = lines[:a] + lines[b:]
    j -= b - a
    maradek = lines[i + 1:j]
    if any(s.strip() for s in maradek):
        return "\n".join(lines)
    eleje = "\n".join(lines[:i]).rstrip("\n")
    utana = "\n".join(lines[j:])
    return eleje + "\n" + ("\n" + utana if utana.strip() else "")


def blokk_kivesz(text: str, link: str, szakasz: str = "## Füzet") -> list[str] | None:
    """A fotó meglévő blokkjának sorai (az átkötéshez: a callout a beágyazással együtt költözik); None, ha nincs."""
    lines = text.split("\n")
    sz = _szakasz(lines, szakasz)
    if sz is None:
        return None
    for a, b, l in _blokkok(lines, *sz):
        if l == link:
            return lines[a:b]
    return None


def callout_kepletei(sorok: list[str] | None) -> list[str]:
    """A blokk callout-sorainak képletei (az átkötéskor az új helyre ugyanezek kerülnek)."""
    ki = []
    for s in (sorok or [])[1:]:
        m = re.match(r"^>\s?\$\$(.*)\$\$\s*$", s)
        if m:
            ki.append(m.group(1))
    return ki
