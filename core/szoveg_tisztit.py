"""Markdown → egysoros, olvasható szöveg (C32b): a **megjelenített** kivonatokhoz (ma: a „Ma” oldal napi jegyzete).

Az **egyetlen hely**, ahol a core a jegyzet Markdown-jelölését szövegre egyszerűsíti. Csak megjelenítésre való: a vault
tartalmát nem módosítja, és sehová nem íródik vissza (a bemenet szövege marad érintetlen; a kimenet eldobható).

Szabályok (soronként, a kerítéses kódblokk, a `%%…%%` és a HTML-megjegyzés előbb kiesik):
- címsor és vízszintes vonal kiesik; az idézet-előtag (`>`) lekerül, a callout-fejléc (`[!típus]± Cím`) a címe lesz;
- a feladatjelölő `- [ ]` → `☐`, `- [x]` → `☑`; a sima lista- és sorszám-jelölő lekerül;
- a táblázatsor cellái ` · `-tal fűzve (az elválasztó sor kiesik);
- `[[Cél|alias]]` → az alias, `[[Mappa/Cél#Fejezet]]` → `Cél`, `[[#Fejezet]]` → `Fejezet`; `[szöveg](url)` → `szöveg`;
  a beágyazás (`![[…]]`, `![…](…)`) és a lábjegyzet-hivatkozás (`[^1]`) kiesik;
- `**vastag**`, `__vastag__`, `*dőlt*`, `_dőlt_`, `~~áthúzott~~`, `==kiemelt==`, `` `kód` `` → a belső szöveg;
- a sorvégi blokkazonosító (`^abc`) és a HTML-címkék kiesnek.
"""
from __future__ import annotations

import re

from .index import maszk

_KOMMENT = re.compile(r"%%.*?%%|<!--.*?-->", re.S)
_CIMSOR = re.compile(r"^#{1,6}(?:\s|$)")
_VONAL = re.compile(r"^(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,})$")
_TABLA_ELVALASZTO = re.compile(r"^\|?[\s:|-]*-[\s:|-]*\|?$")
_IDEZET = re.compile(r"^(?:>\s?)+")
_CALLOUT = re.compile(r"^\[![^\]]+\][+-]?\s*")
_FELADAT = re.compile(r"^[ \t]*[-*+][ \t]+\[(.)\][ \t]+")
_LISTAJEL = re.compile(r"^[ \t]*(?:[-*+]|\d{1,9}[.)])[ \t]+")
_BEAGYAZAS = re.compile(r"!\[\[[^\]\n]*\]\]|!\[[^\]\n]*\]\([^)\n]*\)")
_WIKI = re.compile(r"\[\[([^\]|\n]*?)(?:\|([^\]\n]*))?\]\]")
_MDLINK = re.compile(r"\[([^\]\n]+)\]\((?:<[^>\n]*>|[^)\n]*)\)")
_LABJEGYZET = re.compile(r"\[\^[^\]\n]+\]")
_BLOKK_ID = re.compile(r"[ \t]+\^[\w-]+$")
_HTML_CIMKE = re.compile(r"</?[A-Za-z][^>\n]*>")
_JELOLESEK = (
    (re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*"), r"\1"),
    (re.compile(r"(?<!\w)__(?=\S)(.+?)(?<=\S)__(?!\w)"), r"\1"),
    (re.compile(r"~~(?=\S)(.+?)(?<=\S)~~"), r"\1"),
    (re.compile(r"==(?=\S)(.+?)(?<=\S)=="), r"\1"),
    (re.compile(r"(?<![\w*])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![\w*])"), r"\1"),
    (re.compile(r"(?<![\w_])_(?=[^\s_])(.+?)(?<=[^\s_])_(?![\w_])"), r"\1"),
    (re.compile(r"`([^`\n]+)`"), r"\1"),
)


def _wiki(m: re.Match) -> str:
    alias = m.group(2)
    if alias is not None and alias.strip():
        return alias.strip()
    cel = m.group(1).strip()
    if cel.startswith(("#", "^")):                  # a jegyzeten belüli hivatkozás: a fejezet vagy a blokk
        return cel.lstrip("#^").strip()
    cel = re.split(r"[#^]", cel, maxsplit=1)[0].rsplit("/", 1)[-1].strip()
    return cel[:-3] if cel.lower().endswith(".md") else cel


def _kerites_nelkul(szoveg: str) -> str:
    ki, poz = [], 0
    for kezd, veg, _ in maszk.keritesek(szoveg):
        ki.append(szoveg[poz:kezd])
        poz = veg
    ki.append(szoveg[poz:])
    return "\n".join(ki)


def _sor(sor: str) -> str:
    sor = sor.strip()
    if not sor or _CIMSOR.match(sor) or _VONAL.match(sor):
        return ""
    if sor.startswith("|") and _TABLA_ELVALASZTO.match(sor):
        return ""
    elojel = ""
    if _IDEZET.match(sor):
        sor = _IDEZET.sub("", sor, count=1).strip()
        sor = _CALLOUT.sub("", sor, count=1)
        if not sor:
            return ""
    m = _FELADAT.match(sor)
    if m:
        elojel = "☑ " if m.group(1) in "xX" else "☐ "
        sor = sor[m.end():]
    else:
        sor = _LISTAJEL.sub("", sor, count=1)
    if sor.startswith("|"):
        cellak = [c.strip() for c in sor.strip("|").split("|")]
        sor = " · ".join(c for c in cellak if c)
    sor = _BEAGYAZAS.sub("", sor)
    sor = _WIKI.sub(_wiki, sor)
    sor = _MDLINK.sub(r"\1", sor)
    sor = _LABJEGYZET.sub("", sor)
    sor = _BLOKK_ID.sub("", sor)
    sor = _HTML_CIMKE.sub("", sor)
    for minta, csere in _JELOLESEK:
        sor = minta.sub(csere, sor)
    sor = re.sub(r"\s+", " ", sor).strip()
    return (elojel + sor).strip() if sor else ""


def egyszeru(szoveg: str) -> str:
    """A Markdown-szöveg (frontmatter nélkül) egyetlen sorba fűzött, jelölés nélküli alakja."""
    szoveg = _KOMMENT.sub("", _kerites_nelkul(szoveg.replace("\r\n", "\n").replace("\r", "\n")))
    return " ".join(s for s in (_sor(x) for x in szoveg.split("\n")) if s)
