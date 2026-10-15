"""Szó-szintű segédek a forráshűség-kapuhoz: tövek, számok, nagybetűs szavak, tagadás.

A magyar toldalékolás miatt a szavakat hajtott (ékezet nélküli, kisbetűs) 5 karakteres tövekre vetjük
(`Crassust` ≈ `Crassusszal`): közelítés, nem elemzés. A függvényszavak és a kérdőszavak nem hordoznak tartalmat,
ezért a lefedettségből kiesnek.
"""
from __future__ import annotations

import re

from modulok.eval.kozos import idezet as _IDEZET
from modulok.eval.kozos import tavolsag

TOVEK_HOSSZ = 5
_SZAM = re.compile(r"\d+")
_SZAMRAG = re.compile(r"(?<=\d)-[^\W\d_]+")           # „60-ban”, „49-ben”: a rag nem szó
_SZO = re.compile(r"[0-9A-Za-zÀ-ɏ]+")
_NAGY = re.compile(r"(?<![0-9A-Za-zÀ-ɏ])([A-ZÁÉÍÓÖŐÚÜŰ][0-9A-Za-zÀ-ɏ]*)")
_MONDATKEZDET = ".!?:\n"
_NYITO = " \t„“\"'(«[–—*_~="                # nyitó idézőjel, zárójel, gondolatjel és Markdown-kiemelés a szó előtt

# hajtott alakban; a tagadószavak külön szabály (`tagado`), ezért itt is kiesnek
FUGGVENYSZOK = frozenset("""
hogy nem egy vagy mint aki ami amely amelyek amelyet akik amik ezt azt ezek azok van volt lett meg mar csak pedig
mely melyik mit miert hogyan mikor kit hol hany mennyi milyen kik mik aztan ezert mert akkor majd tehat igy ugy itt ott
sem soha senki semmi nelkul ket szerint kozul
""".split())
NEGATOROK = frozenset({"nem", "sem", "soha", "senki", "semmi", "sehol", "semmilyen", "nelkul", "ne", "se"})


def szavak(s: str) -> list[str]:
    """A szöveg szavai (számragok nélkül), a nagybetű megtartva."""
    return _SZO.findall(_SZAMRAG.sub(" ", tavolsag.nfc(s)))


def tovek(s: str, stop: bool = True) -> set[str]:
    """A tartalmi szavak hajtott 5 karakteres tövei. `stop`: a függvény- és kérdőszavak, a számok és a 3 karakternél
    rövidebb szavak nélkül (a lefedettséghez); `stop=False`: minden szó (a bizonyíték oldalán)."""
    ki = set()
    for w in szavak(s):
        h = tavolsag.hajt(w)
        if len(h) < 3 or h.isdigit():
            continue
        if stop and h in FUGGVENYSZOK:
            continue
        ki.add(h[:TOVEK_HOSSZ])
    return ki


def to(szo: str) -> str:
    return tavolsag.hajt(szo)[:TOVEK_HOSSZ]


def lefedett(tovek: set[str], bizonyitek: set[str]) -> set[str]:
    """A `tovek` közül azok, amelyek a bizonyítékban állnak: pontos tő, vagy a 4 betűs szó (`hang`, `Róma`) ragozott alakja a
    másik oldalon (`hangot`, `Rómában`) — az 5 karakteres tő a rövid szavakat nem vonja össze."""
    rovid = {b for b in bizonyitek if len(b) == 4}
    return {t for t in tovek if t in bizonyitek or any(t.startswith(r) for r in rovid)
            or (len(t) == 4 and any(b.startswith(t) for b in bizonyitek))}


def jelek(s: str) -> set[str]:
    """Minden token (szó, szám, betű, műveleti jel) hajtott alakban: a képletes állítás lefedettségéhez, ahol nincs
    3 betűs tartalmi szó (`(a+b)(a-b)`)."""
    return {tavolsag.hajt(m.group(0)) for m in _IDEZET.SZO_ES_JEL.finditer(_SZAMRAG.sub(" ", tavolsag.nfc(s)))}


def szamok(s: str) -> set[str]:
    """A számjegy-csoportok (évszám, mennyiség); a számragokat nem."""
    return set(_SZAM.findall(_SZAMRAG.sub(" ", tavolsag.nfc(s))))


def nagybetus(s: str) -> list[tuple[str, bool]]:
    """(szó, mondatkezdő-e): a nagybetűvel kezdődő szavak; mondatkezdő a szöveg elején, mondatvég-jel (`.!?:`) vagy
    sortörés után (az idézőjel és a nyitó zárójel nem számít a szó és a jel közt)."""
    s = tavolsag.nfc(s)
    ki = []
    for m in _NAGY.finditer(s):
        i = m.start() - 1
        while i >= 0 and s[i] in _NYITO:
            i -= 1
        ki.append((m.group(1), i < 0 or s[i] in _MONDATKEZDET))
    return ki


def tagado(s: str) -> bool:
    """Van-e tagadószó a szövegben."""
    return any(tavolsag.hajt(w) in NEGATOROK for w in szavak(s))
