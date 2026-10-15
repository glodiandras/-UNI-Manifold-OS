"""A kártya-állapot rekonstrukciója egy múltbeli időpontra (C28b; `docs/C28-TERV.md` 7.): **külön becslés-napló nélkül**, a
`tanulas.sqlite` meglévő naplóiból — a `kartya.letrehozva`/`torolve` és a `valasz` (`mikor`, `elotte`, `utana`, `visszavonva`) sorokból.

Egy kártya az `ekkor` időpontban:

- **létezik**, ha `letrehozva ≤ ekkor` és (`torolve` üres vagy `torolve > ekkor`); a felfüggesztés a **jelenlegi** jelző szerint
  (a felfüggesztés története nincs naplózva — ismert korlát);
- **állapota** a legutóbbi *akkor érvényes* értékelés `utana` állapota: `mikor ≤ ekkor` és (`visszavonva` üres vagy `visszavonva > ekkor`);
  a később visszavont értékelés tehát a visszavonás előtti időpontra még számít, az előtte visszavont nem. Ha nincs ilyen értékelés:
  a kártya első (időrendben legkorábbi) értékelésének `elotte` állapota (az importált kártya kiinduló állapota), ha nincs értékelés
  sem: a jelenlegi tárolt állapot, ha az utolsó átnézése `ekkor` előtt volt, különben új;
- **utolsó ismétlése** (a frissesség jelzéséhez) az akkor érvényes értékelések legkésőbbi ideje.

Csak olvas (a hívó `mode=ro` kapcsolatot ad); a `tanulas_db`-hez nem nyúl.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from modulok.kartya.utemezo import MEZOK, UJ


def idopont(iso: str | None) -> datetime | None:
    """A DB ISO-ideje időzónásan (az időzóna nélküli UTC-nek számít); hibás szöveg → `None`."""
    if not iso:
        return None
    try:
        t = datetime.fromisoformat(iso)
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


UJ_ALLAPOT = {"allapot": UJ, "lepes": None, "stabilitas": None, "nehezseg": None, "esedekes": None, "utolso": None}


def _allapot(json_szoveg: str | None) -> dict | None:
    try:
        a = json.loads(json_szoveg) if json_szoveg else None
    except ValueError:
        return None
    return {k: a.get(k) for k in MEZOK} if isinstance(a, dict) and "allapot" in a else None


def kartyak_ekkor(c, ekkor: datetime) -> tuple[list[dict], dict[str, str]]:
    """Az `ekkor` (időzónás) időpontban létező, nem felfüggesztett kártyák az akkori állapotukkal, és a kártyánkénti utolsó
    (akkor érvényes) ismétlés ideje → `([kártya-sor], {azon: mikor})`. A sor alakja azonos a `Adatok.kartyak()` soráéval."""
    ekkor = ekkor if ekkor.tzinfo else ekkor.astimezone()
    valaszok: dict[str, list[dict]] = {}
    for r in c.execute("SELECT id, kartya, mikor, elotte, utana, visszavonva FROM valasz WHERE forras = 'ismetles' "
                       "ORDER BY mikor, id"):
        valaszok.setdefault(r["kartya"], []).append(dict(r))
    ki: list[dict] = []
    utolso_valasz: dict[str, str] = {}
    for r in c.execute("SELECT azon, jegyzet, forras, kerdes, allapot, lepes, stabilitas, nehezseg, esedekes, utolso, letrehozva, torolve "
                       "FROM kartya WHERE felfuggesztve = 0 ORDER BY azon"):
        letre = idopont(r["letrehozva"])
        torolt = idopont(r["torolve"])
        if letre is None or letre > ekkor or (torolt is not None and torolt <= ekkor):
            continue
        lista = valaszok.get(r["azon"], [])
        ervenyes = [v for v in lista if idopont(v["mikor"]) is not None and idopont(v["mikor"]) <= ekkor
                    and (v["visszavonva"] is None or (idopont(v["visszavonva"]) or ekkor) > ekkor)]
        allapot = None
        if ervenyes:
            allapot = _allapot(ervenyes[-1]["utana"])
            utolso_valasz[r["azon"]] = ervenyes[-1]["mikor"]
        elif lista:
            allapot = _allapot(lista[0]["elotte"])
        else:
            tarolt = {k: r[k] for k in MEZOK}
            ut_ = idopont(r["utolso"])
            allapot = tarolt if (tarolt["allapot"] == UJ or ut_ is None or ut_ <= ekkor) else None
        sor = {k: r[k] for k in ("azon", "jegyzet", "forras", "kerdes")}
        sor.update(allapot or UJ_ALLAPOT)
        ki.append(sor)
    return ki, utolso_valasz
