"""Markdown ↔ Anki-HTML a kártyák mezőihez (`docs/C23-TERV.md` 4.3) — a támogatott részhalmaz:

| Markdown | Anki-HTML |
|---|---|
| `$…$` / `$$…$$` | `\\(…\\)` / `\\[…\\]` (az Anki MathJax-jele) |
| `**b**` / `*i*` | `<b>` / `<i>` |
| `` `k` `` | `<code>` |
| sorvég | `<br>` |
| `![[kép.png]]` | `<img src="kép.png">` |
| `[[cél\\|szöveg]]` / `[[cél]]` | a megjelenő szöveg (az Anki nem tud wikilinket) |

Visszafelé minden más tag lecsupaszítva, a `<div>`/`<p>` sorvéggé, az entitások visszafejtve. A részhalmazon belül
a körút szövegre pontos.
"""
from __future__ import annotations

import html as _html
import os
import re

_TOKEN = re.compile(
    r"\$\$(?P<blokk>.+?)\$\$"
    r"|\$(?=[^\s$])(?P<sor>[^$\n]*?[^\s\\$])\$"
    r"|`(?P<kod>[^`\n]+)`"
    r"|!\[\[(?P<kep>[^\]|\n]+)(?:\|[^\]\n]*)?\]\]"
    r"|\[\[(?P<cel>[^\]|\n]+)(?:\|(?P<alias>[^\]\n]+))?\]\]", re.S)
_FELKOVER = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
_DOLT = re.compile(r"(?<![*\w])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![*\w])")


def _szoveg(s: str) -> str:
    s = _html.escape(s, quote=False)
    s = _FELKOVER.sub(r"<b>\1</b>", s)
    s = _DOLT.sub(r"<i>\1</i>", s)
    return s.replace("\n", "<br>")


def md_html(md: str) -> str:
    """Markdown → az Anki mezőjének HTML-je."""
    ki, i = [], 0
    for m in _TOKEN.finditer(md):
        ki.append(_szoveg(md[i:m.start()]))
        i = m.end()
        if m.group("blokk") is not None:
            ki.append("\\[" + _html.escape(m.group("blokk"), quote=False).replace("\n", "<br>") + "\\]")
        elif m.group("sor") is not None:
            ki.append("\\(" + _html.escape(m.group("sor"), quote=False) + "\\)")
        elif m.group("kod") is not None:
            ki.append("<code>" + _html.escape(m.group("kod"), quote=False) + "</code>")
        elif m.group("kep") is not None:
            ki.append('<img src="' + _html.escape(os.path.basename(m.group("kep").strip())) + '">')
        else:
            felirat = m.group("alias") or os.path.basename(m.group("cel").split("#", 1)[0]) or m.group("cel")
            ki.append(_html.escape(felirat.strip(), quote=False))
    ki.append(_szoveg(md[i:]))
    return "".join(ki)


def kepek(md: str) -> list[str]:
    """A Markdown-szövegben beágyazott képek link-céljai (`![[…]]`), sorrendben, ismétlés nélkül."""
    ki: list[str] = []
    for m in _TOKEN.finditer(md):
        if m.group("kep") is not None and m.group("kep").strip() not in ki:
            ki.append(m.group("kep").strip())
    return ki


_IMG_ATTR = re.compile(r"img\b[^>]*?\bsrc\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))", re.I)
_CIMKE_NEV = re.compile(r"(/?)([A-Za-z][A-Za-z0-9_]*)")
_FAJLNEV_TILTOTT = re.compile(r"[\[\]|#^<>\x00-\x1f\x7f]")


def fajlnev(src: str) -> str:
    """Egy `<img src>` célja a beágyazáshoz: **csak fájlnév** (import-védelem). Az URL-ek (`://`, `data:`, `javascript:`,
    `file:`) és a mappa-út (`..`, `/`, `\\`) kiesik, a link-szintaxist törő jelek (`[ ] | # ^`), a vezérlőjelek és a
    255 bájtnál hosszabb név is; ami nem marad, az üres szöveg (a kép elhagyva)."""
    s = _html.unescape(src).strip()
    if "://" in s or s.lower().startswith(("data:", "javascript:", "file:", "vbscript:")):
        return ""
    s = _FAJLNEV_TILTOTT.sub("", s.replace("\\", "/").rsplit("/", 1)[-1]).strip()
    if s in ("", ".", "..") or len(s.encode("utf-8", "replace")) > 255:
        return ""
    return s


def _cimkek(s: str, atalakit) -> str:
    """Lineáris címke-bejárás (a `re.sub(r"<[^>]+>")` négyzetes volt a záró `>` nélküli `<`-tömegen): minden `<…>` párt egyszer
    néz; ha nincs több `>`, a maradék szöveg. Az üres `<>` szövegként marad."""
    ki, i = [], 0
    while True:
        a = s.find("<", i)
        if a < 0:
            break
        b = s.find(">", a + 1)
        if b < 0:
            break
        tartalom = s[a + 1:b]
        if tartalom == "":
            ki.append(s[i:b + 1])
        else:
            ki.append(s[i:a])
            ki.append(atalakit(tartalom))
        i = b + 1
    ki.append(s[i:])
    return "".join(ki)


def _md_cimke(c: str) -> str:
    m = _CIMKE_NEV.match(c)
    if not m:
        return ""
    zar, nev, mellek = m.group(1), m.group(2).lower(), c[m.end():]
    if nev == "br" and not zar and re.fullmatch(r"\s*/?", mellek):
        return "\n"
    if nev in ("div", "p"):
        return "" if zar else "\n"
    if nev == "img" and not zar:
        k = _IMG_ATTR.match(c)
        if k:
            f = fajlnev(k.group(1) or k.group(2) or k.group(3) or "")
            return f"![[{f}]]" if f else ""
        return ""
    if nev in ("b", "strong"):
        return "**"
    if nev in ("i", "em"):
        return "*"
    if nev == "code":
        return "`"
    return ""


def _csupasz_cimke(c: str) -> str:
    m = _CIMKE_NEV.match(c)
    if not m:
        return ""
    zar, nev, mellek = m.group(1), m.group(2).lower(), c[m.end():]
    if nev == "br" and not zar and re.fullmatch(r"\s*/?", mellek):
        return " "
    if nev == "div" and not zar:
        return " "
    if nev == "img" and not zar:
        k = _IMG_ATTR.match(c)
        return " " + (k.group(1) or k.group(2) or k.group(3) or "") + " " if k else ""
    return ""


def _keret_csere(s: str, nyit: str, zar: str, elo: str, uto: str) -> str:
    """`nyit…zar` → `elo…uto` — a `re.sub` lineáris párja: legalább egy karakter a keretben; ha nincs több lezáró, vége."""
    ki, i = [], 0
    while True:
        a = s.find(nyit, i)
        if a < 0:
            break
        b = s.find(zar, a + len(nyit) + 1)
        if b < 0:
            break
        ki.append(s[i:a])
        ki.append(elo + s[a + len(nyit):b] + uto)
        i = b + len(zar)
    ki.append(s[i:])
    return "".join(ki)


def html_md(h: str) -> str:
    """Az Anki mezőjének HTML-je → Markdown (a támogatott részhalmaz; a többi tag lecsupaszítva). Lineáris futásidejű, a
    kép-cél csak fájlnév (`fajlnev`)."""
    s = h.replace("\r\n", "\n").replace("\n", " ") if "<" in h else h
    s = _cimkek(s, _md_cimke)
    s = _keret_csere(s, "\\[", "\\]", "$$", "$$")
    s = _keret_csere(s, "\\(", "\\)", "$", "$")
    s = _html.unescape(s).replace("\xa0", " ")
    return "\n".join(x.rstrip() for x in s.split("\n")).strip("\n")


def csupasz(h: str) -> str:
    """Az Anki `sfld`/`csum` alakja: a tagok nélkül (a képek neve marad), entitások visszafejtve."""
    return _html.unescape(_cimkek(h, _csupasz_cimke)).strip()
