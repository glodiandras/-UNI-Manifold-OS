"""Az aranyhalmaz-fájl (`arany.json`) betöltése és a verzió képzése.

Minden halmaz: `{"verzio": "v1", "allapot": "vazlat" | "jovahagyott", "keszult", "jovahagyva", …}`.
Amíg a felhasználó nem hagyta jóvá, a `VERZIO` `-vazlat` utótagot kap: a kalibrációs táblában így látszik,
hogy a pontszám nem végleges halmazon született.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


HIANYZIK = "hianyzik"


def betolt(mappa: Path | str, nev: str = "arany.json") -> dict:
    """Az aranyhalmaz-fájl; ha nincs a mappában (a termékkel nem szállított, személyes adatból épült halmaz), egy üres,
    `hianyzik` állapotú halmaz jön vissza, hogy a feladatmodul (a prompt és a pontozó) importálható maradjon: az éles
    láncok a promptot innen veszik, a mérés pedig `hianyzik(...)`-kal kimondja, hogy nincs mit mérni."""
    ut = Path(mappa) / nev
    if not ut.is_file():
        return {"verzio": "nincs", "allapot": HIANYZIK, "tetelek": [], "fejezetek": [], "jegyzetek": [], "parok": [],
                "hianyzik": True, "fajl": str(ut)}
    return json.loads(ut.read_text(encoding="utf-8"))


def hianyzik(arany: dict) -> bool:
    return bool(arany.get("hianyzik")) or arany.get("allapot") == HIANYZIK


def verzio(arany: dict) -> str:
    v = str(arany["verzio"])
    if hianyzik(arany):
        return f"{v}-{HIANYZIK}"
    return v if arany.get("allapot") == "jovahagyott" else f"{v}-vazlat"


def sha256(ut: Path | str) -> str:
    h = hashlib.sha256()
    with open(ut, "rb") as f:
        for darab in iter(lambda: f.read(1 << 20), b""):
            h.update(darab)
    return h.hexdigest()


def szoveg_sha256(szoveg: str) -> str:
    return hashlib.sha256(szoveg.encode("utf-8")).hexdigest()


def atlag(ertekek) -> float:
    lista = list(ertekek)
    return sum(lista) / len(lista) if lista else 0.0
