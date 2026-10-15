"""A kód- és képletmaszk — **egy helyen** (C10.6; CLAUDE.md 1. / 13. döntés: az Obsidian viselkedése, nem a legacyé).

Mi nem link, címke, fejezet vagy feladat: ami kódban áll; és mi nem link vagy említés: ami képletben áll. Az
index, a gráf, a visszahivatkozás, az említések és az átnevezés mind ezt a modult használja; saját maszk sehol
nem készül. A maszk a hosszt és a sortöréseket megtartja (minden más karakter szóköz lesz), így az eltolások és a
sorszámok az eredeti szövegre mutatnak.

- `keritesek`: a kerítéses kódblokkok (```` ``` ```` és `~~~`, 3+ jel; a záró legalább olyan hosszú, ugyanabból a
  jelből; idézetben és listaelemben is; a lezáratlan kerítés a tárolója végéig tart; a backtickes nyitó infójában
  nem állhat backtick — az soron belüli kód).
- `mask_code`: kerítések + soron belüli kód backtick-futamokkal (N backtick nyit, pontosan N zár; a bekezdésen
  belül több sorra is, üres soron és új blokk kezdetén nem megy át).
- `link_maszk`: a `mask_code` + a képletek (`$…$`, `$$…$$`, az index `KEPLET_*` szabályával).

A soron belüli menet balról jobbra halad, mint a szerkesztő elemzője: ami előbb nyit, az nyer (a képletben álló
backtick nem nyit kódot, a kódban álló `$` nem nyit képletet), és a zárt, egysoros `[[…]]` belsejében nem indul
se kód, se képlet. A két maszk ugyanabból az egy menetből jön (`maszkok`), így nem térhetnek el. A frontmatter
YAML, nem Markdown: ott maszk nincs (a tulajdonság-linkek linkek).

Két szerkezet a felhasználó Obsidian-próbájára vár (`tests/kezi/obsidian_link_proba.py`); amíg nincs válasz, a
kapcsolójuk ki van kapcsolva, vagyis a bennük álló `[[…]]` link, mint eddig: `BEHUZOTT_KOD`, `HTML_MEGJEGYZES`.
"""
from __future__ import annotations

import re

# L39, C29.8 (T130) kiegészítésekkel: az üres blokk (`---`/`---`: a `(.*?)` üres, a záró `---` közvetlenül a nyitó sor
# után áll — a `(?<=\n)`) és az elején álló BOM (`﻿`) is frontmatter; a nem üres blokk egyezése változatlan.
FM_RE = re.compile(r"\A﻿?---\r?\n(.*?)(?:(?<=\n)|\r?\n)---\r?\n?", re.S)
KEPLET_BLOKK = re.compile(r"\$\$(.+?)\$\$", re.S)
KEPLET_SOR = re.compile(r"\$(?<![\\$]\$)(?:(?=[^\s$])([^$\n]*?[^\s\\$])|([^\s$\\]))\$(?!\d)")

BEHUZOTT_KOD = False            # a 4+ szóközzel vagy tabbal behúzott kódblokk maszkolása
HTML_MEGJEGYZES = False         # a `<!-- … -->` maszkolása

_ELOTAG = re.compile(r"[ \t]*(?:>[ \t]*)*")
_LISTAJEL = r"(?:(?:[-*+]|\d{1,9}[.)])[ \t]+)?"
_NYITO = re.compile(r"(" + _ELOTAG.pattern + _LISTAJEL + r")(`{3,}|~{3,})(.*)")
_BLOKK_KEZDET = re.compile(_ELOTAG.pattern + r"(?:(?:[-*+]|\d{1,9}[.)])[ \t]|#{1,6}(?:[ \t]|$)|\||`{3,}|~{3,})")
_LISTAELEM = re.compile(r"[ \t]*(?:[-*+]|\d{1,9}[.)])(?:[ \t]|$)")
_BEHUZAS = re.compile(r"(?: {4}| {0,3}\t)")
_HTML = re.compile(r"<!--.*?-->", re.S)
_WIKI_ZART = re.compile(r"!?\[\[(?!\]\])[^\n]*?\]\]")       # az üres `[[]]` nem link
_FUTAM = re.compile(r"`+")
_JEL = re.compile(r"[\\`$<]|!?\[\[")
_TOROL = re.compile(r"[^\n]")


def _idezet_szint(sor: str) -> int:
    return _ELOTAG.match(sor).group(0).count(">")


def _nyit(sor: str, poz: int):
    m = _NYITO.match(sor)
    if m and not (m.group(2)[0] == "`" and "`" in m.group(3)):
        return poz, m.group(2)[0], len(m.group(2)), _idezet_szint(m.group(1)), m.group(3).strip()
    return None


def keritesek(txt: str) -> list[tuple[int, int, str]]:
    """A kerítéses kódblokkok: [(kezd, veg, info)] — a nyitó sor elejétől a záró sor végéig (a záró sortörés
    nélkül); `info` a nyitó jel utáni szöveg (a nyelv az első szava)."""
    if "```" not in txt and "~~~" not in txt:
        return []
    ki: list[tuple[int, int, str]] = []
    nyitva = None                   # (kezd, jel, hossz, idézetszint, info)
    poz = 0
    for sor in txt.split("\n"):
        veg = poz + len(sor)
        if nyitva is not None and _idezet_szint(sor) < nyitva[3]:       # az idézet (callout) véget ért: a kerítés is
            ki.append((nyitva[0], poz - 1, nyitva[4]))
            nyitva = None
        if nyitva is None:
            nyitva = _nyit(sor, poz)
        else:
            mag = sor[_ELOTAG.match(sor).end():].rstrip(" \t")
            if len(mag) >= nyitva[2] and mag == nyitva[1] * len(mag):
                ki.append((nyitva[0], veg, nyitva[4]))
                nyitva = None
        poz = veg + 1
    if nyitva is not None:
        ki.append((nyitva[0], len(txt), nyitva[4]))
    return ki


def _behuzott_kod(txt: str, foglalt: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """A behúzott kódblokkok sorai: 4+ szóköz vagy tab, üres sor (vagy a szöveg eleje) után, listán kívül.
    A lista alatti behúzott sor a listaelem folytatása, nem kód."""
    ki = []
    poz, listaban, kodban, elozo_ures = 0, False, False, True
    kerites = iter(sorted(foglalt))
    k = next(kerites, None)
    for sor in txt.split("\n"):
        veg = poz + len(sor)
        while k is not None and k[1] < poz:
            k = next(kerites, None)
        if k is not None and k[0] <= poz <= k[1]:
            kodban, elozo_ures = False, False
        elif not sor.strip():
            elozo_ures = True
        else:
            if _LISTAELEM.match(sor):
                listaban, kodban = True, False
            elif _BEHUZAS.match(sor):
                kodban = not listaban and (kodban or elozo_ures)
                if kodban:
                    ki.append((poz, veg))
            else:
                kodban = False
                if elozo_ures:              # behúzás nélküli bekezdés üres sor után: a lista véget ért
                    listaban = False
            elozo_ures = False
        poz = veg + 1
    return ki


def _bekezdes_vege(txt: str, i: int) -> int:
    """Az `i`-t tartalmazó bekezdés vége: az első üres vagy új blokkot kezdő sor előtti sortörés."""
    while True:
        j = txt.find("\n", i)
        if j < 0:
            return len(txt)
        k = txt.find("\n", j + 1)
        kov = txt[j + 1:k if k >= 0 else len(txt)]
        if not kov.strip() or _BLOKK_KEZDET.match(kov):
            return j
        i = j + 1


def _kitakar(txt: str, szakaszok: list[tuple[int, int]]) -> str:
    if not szakaszok:
        return txt
    ki, poz = [], 0
    for a, b in sorted(szakaszok):
        if a < poz:
            a = poz
        if b <= a:
            continue
        ki.append(txt[poz:a])
        ki.append(_TOROL.sub(" ", txt[a:b]))
        poz = b
    ki.append(txt[poz:])
    return "".join(ki)


def maszkok(txt: str, frontmatter: bool = True) -> tuple[str, str]:
    """→ (kódmaszk, link-maszk) egy menetből. `frontmatter=False`: a szöveg nem jegyzet (canvas szövegnode)."""
    fm = FM_RE.match(txt) if frontmatter else None
    eleje = fm.end() if fm else 0
    torzs = txt[eleje:] if eleje else txt
    blokkok = [(a, b) for a, b, _ in keritesek(torzs)]
    if BEHUZOTT_KOD:
        blokkok += _behuzott_kod(torzs, blokkok)
    szoveg = _kitakar(torzs, blokkok)       # a blokkok már üresek: a soron belüli menet nem lát beléjük
    kod: list[tuple[int, int]] = []
    keplet: list[tuple[int, int]] = []
    i = 0
    bek_veg = -1            # T146 (C21): a `_bekezdes_vege` bekezdésenként egyszer (az `i` csak nő: a bekezdésen belül ugyanaz)
    while True:
        m = _JEL.search(szoveg, i)
        if m is None:
            break
        i, c = m.start(), m.group(0)
        if c == "\\":
            i += 2
        elif c == "`":
            j = _FUTAM.match(szoveg, i).end()
            hossz, z = j - i, -1
            if i > bek_veg:
                bek_veg = _bekezdes_vege(szoveg, i)
            for f in _FUTAM.finditer(szoveg, j, bek_veg):
                if f.end() - f.start() == hossz:
                    z = f.end()
                    break
            if z >= 0:
                kod.append((i, z))
            i = z if z >= 0 else j
        elif c == "$":
            k = KEPLET_BLOKK.match(szoveg, i) or KEPLET_SOR.match(szoveg, i)
            if k:
                keplet.append((i, k.end()))
            i = k.end() if k else i + 1
        elif c == "<":
            k = _HTML.match(szoveg, i) if HTML_MEGJEGYZES else None
            if k:
                kod.append((i, k.end()))
            i = k.end() if k else i + 1
        else:                               # `[[` vagy `![[`: a zárt, egysoros wikilink belseje védett
            k = _WIKI_ZART.match(szoveg, i)
            i = k.end() if k else m.end()
    kodmaszk = _kitakar(szoveg, kod)
    linkmaszk = _kitakar(kodmaszk, keplet)
    if eleje:
        return txt[:eleje] + kodmaszk, txt[:eleje] + linkmaszk
    return kodmaszk, linkmaszk


def mask_code(txt: str, frontmatter: bool = True) -> str:
    """A kód kimaszkolása szóközzel: kerítéses blokk és soron belüli kód (a hossz és a sortörések megmaradnak)."""
    return maszkok(txt, frontmatter)[0]


def link_maszk(txt: str, frontmatter: bool = True) -> str:
    """A linkek és az említések maszkja: kód és képlet nélkül; a frontmatter (YAML) érintetlen."""
    return maszkok(txt, frontmatter)[1]
