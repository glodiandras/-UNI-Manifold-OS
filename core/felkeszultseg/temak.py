"""A felkészülési jegyzet témái (C28a): a jegyzet `Source` és `NN` frontmatter-mezőinek **jegyzet-linkjei**.

A valódi vaulton a felkészülési jegyzetek `Source` mezője háromféle: témajegyzetek linkjei, tankönyv-PDF oldalai
(`[[11 - Matematika.pdf#page=18]]` oldalanként), képek; a PDF-forrású jegyzetnél a tényleges témák az `NN:` mezőben állnak.
Ezért: **téma** = a `Source` és az `NN` feloldott `.md` linkjei (az index feloldásával, L42 — itt saját feloldás nincs);
a PDF és a kép **forrás** (nem téma, az oldalak tartományokba vonva); ha nincs téma, a **felkészülési jegyzet maga** az
egyetlen téma (`onmaga`). A duplikátum, az önhivatkozás és a másik felkészülési jegyzet kimarad.
"""
from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, field

KULCSOK = ("source", "nn")
_KEP = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".bmp", ".tif", ".tiff", ".avif", ".svg"}
_MEDIA = {".m4a", ".mp3", ".wav", ".aac", ".flac", ".ogg", ".mp4", ".mov", ".m4v", ".webm", ".mkv"}
_OLDAL = re.compile(r"page=(\d+)")


@dataclass(frozen=True)
class Forras:
    ut: str
    tipus: str                    # pdf | kep | media | egyeb
    oldalak: str | None = None    # „18–28, 31” (csak a PDF-nél)


@dataclass(frozen=True)
class Temak:
    temak: tuple[str, ...]        # a témajegyzetek útjai (vagy a jegyzet maga)
    forrasok: tuple[Forras, ...]
    onmaga: bool                  # nincs témajegyzet: a felkészülési jegyzet maga a téma
    feloldatlan: list[str] = field(default_factory=list)   # a nem feloldható linkek nyers célja


def tipus(ut: str) -> str:
    kit = posixpath.splitext(ut)[1].lower()
    if kit == ".md":
        return "md"
    if kit == ".pdf":
        return "pdf"
    if kit in _KEP:
        return "kep"
    return "media" if kit in _MEDIA else "egyeb"


def _tartomanyok(oldalak: set[int]) -> str:
    ki, lista = [], sorted(oldalak)
    i = 0
    while i < len(lista):
        j = i
        while j + 1 < len(lista) and lista[j + 1] == lista[j] + 1:
            j += 1
        ki.append(str(lista[i]) if i == j else f"{lista[i]}–{lista[j]}")
        i = j + 1
    return ", ".join(ki)


def kinyer(jegyzet: dict, felkeszulesi_utak: set[str]) -> Temak:
    """Az `Index.jegyzet()` válaszából: `jegyzet["ut"]`, `jegyzet["linkek"]` (`cel`, `cel_nyers`, `alcel`, `tulajdonsag`).
    `felkeszulesi_utak`: az összes felkészülési jegyzet útja (azok nem témák)."""
    maga = jegyzet["ut"]
    temak: list[str] = []
    forrasok: dict[str, tuple[str, set[int]]] = {}
    feloldatlan: list[str] = []
    for l in jegyzet.get("linkek", ()):
        if (l.get("tulajdonsag") or "").lower() not in KULCSOK:
            continue
        cel = l.get("cel")
        if not cel:
            feloldatlan.append(l.get("cel_nyers") or "")
            continue
        t = tipus(cel)
        if t == "md":
            if cel != maga and cel not in felkeszulesi_utak and cel not in temak:
                temak.append(cel)
            continue
        _, oldalak = forrasok.setdefault(cel, (t, set()))
        m = _OLDAL.search(l.get("alcel") or "")
        if t == "pdf" and m:
            oldalak.add(int(m.group(1)))
    f = tuple(Forras(ut, t, _tartomanyok(o) or None) for ut, (t, o) in forrasok.items())
    if not temak:
        return Temak((maga,), f, True, feloldatlan)
    return Temak(tuple(temak), f, False, feloldatlan)
