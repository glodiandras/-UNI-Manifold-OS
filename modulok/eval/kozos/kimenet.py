"""A modellválasz szerkezetének kinyerése: JSON (kódkerítésben, szöveg közepén, csonkán) és címkés zárósor."""
from __future__ import annotations

import json
import re

from . import tavolsag

_KERITES = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.S)
_GONDOLAT = re.compile(r"<think>.*?</think>|\[THINK\].*?\[/THINK\]", re.S)
_GONDOLAT_ZARO = ("</think>", "[/THINK]")


def tisztit(valasz) -> str:
    """A válasz szövege a gondolkodó modellek blokkja nélkül (`<think>…</think>`, a Ministral `[THINK]…[/THINK]`);
    nem szöveges válasz → üres."""
    if not isinstance(valasz, str):
        return ""
    s = _GONDOLAT.sub("", valasz)
    for zaro in _GONDOLAT_ZARO:                               # nyitó jel nélküli gondolkodás
        if zaro in s:
            s = s.split(zaro)[-1]
    return s.strip()


def _kiegyensulyozott(s: str, i: int) -> str | None:
    """Az `i`-n kezdődő, zárójelre kiegyensúlyozott JSON-részlet (szövegliterálon belül nem számol)."""
    nyit = s[i]
    zar = {"[": "]", "{": "}"}[nyit]
    melyseg, idezo, szokes = 0, False, False
    for j in range(i, len(s)):
        c = s[j]
        if idezo:
            if szokes:
                szokes = False
            elif c == "\\":
                szokes = True
            elif c == '"':
                idezo = False
        elif c == '"':
            idezo = True
        elif c in "[{":
            melyseg += 1
        elif c in "]}":
            melyseg -= 1
            if melyseg == 0:
                return s[i:j + 1] if c == zar else None
    return None


def _csonka_lista(s: str, i: int):
    """Csonka `[ {...}, {...}, {..` lista: az utolsó ép elemig megtartva."""
    elemek, j = [], i + 1
    while j < len(s):
        k = s.find("{", j)
        if k < 0:
            break
        resz = _kiegyensulyozott(s, k)
        if resz is None:
            break
        try:
            elemek.append(json.loads(resz))
        except ValueError:
            break
        j = k + len(resz)
    return elemek or None


def json_kinyer(valasz):
    """Az első értelmezhető JSON-érték a válaszból, vagy `None`."""
    s = tisztit(valasz)
    jeloltek = [m.group(1) for m in _KERITES.finditer(s)] + [s]
    for j in jeloltek:
        j = j.strip()
        try:
            return json.loads(j)
        except ValueError:
            pass
        for m in re.finditer(r"[\[{]", j):
            resz = _kiegyensulyozott(j, m.start())
            if resz:
                try:
                    return json.loads(resz)
                except ValueError:
                    continue
            elif j[m.start()] == "[":
                lista = _csonka_lista(j, m.start())
                if lista:
                    return lista
            break
    return None


def lista_kinyer(valasz, kulcsok: tuple[str, ...] = ()) -> list[dict]:
    """JSON-lista szótárakból; a `{"kartyak": [...]}` alakú burkot is kibontja. Hibás alak → üres lista."""
    adat = json_kinyer(valasz)
    if isinstance(adat, dict):
        listak = [v for v in adat.values() if isinstance(v, list)]
        adat = listak[0] if len(listak) == 1 else ([adat] if any(k in adat for k in kulcsok) else None)
    if not isinstance(adat, list):
        return []
    return [x for x in adat if isinstance(x, dict)]


def kulcs_turo(elemek: list, kulcsok: tuple[str, ...]) -> list:
    """A JSON-elemek elcsúszott kulcsai (`forrasz`, `forrasza`, `valaszzi` → `forras`, `valasz`) a várt kulcsra (C19 rétegzett
    minta: a gemma4_12b a kártyák közepén a kulcsot betűvel megtoldja, a tartalom jó). Az egyetlen hely: a `szoveg` mérés
    pontozója és a kártya-lánc (C23b) elemzője is ezt hívja, így élesben ugyanaz a tűrés, mint a mérésben."""
    ki = []
    for d in elemek:
        if isinstance(d, dict):
            d = dict(d)
            for k in kulcsok:
                if k not in d:
                    tarsa = next((x for x in d if isinstance(x, str) and x.startswith(k) and len(x) <= len(k) + 3), None)
                    if tarsa is not None:
                        d[k] = d.pop(tarsa)
        ki.append(d)
    return ki


def zarosor(valasz, cimke: str) -> str | None:
    """Az utolsó `CÍMKE: érték` sor értéke (a címke kis-nagybetűtől és ékezettől független)."""
    c = tavolsag.hajt(cimke)
    talalat = None
    for sor in tisztit(valasz).splitlines():
        tiszta = sor.strip().strip("*#>` ").strip()
        h = tavolsag.hajt(tiszta)
        if h.startswith(c):
            maradek = tiszta[len(cimke):].lstrip("*` ").lstrip(":").strip().strip("*`").strip()
            talalat = maradek
    return talalat


def mezo(valasz, cimke: str) -> str | None:
    """Az első `CÍMKE: érték` sor értéke (a füzet-válasz mezőihez)."""
    c = tavolsag.hajt(cimke)
    for sor in tisztit(valasz).splitlines():
        tiszta = sor.strip().strip("*#>` ").strip()
        if tavolsag.hajt(tiszta).startswith(c):
            return tiszta[len(cimke):].lstrip("*` ").lstrip(":").strip().strip("*`").strip()
    return None
