"""Az index feladat-táblájának olvasó lekérdezése a „Ma” oldalnak (C15): a mai és a lejárt, még nyitott feladatok.

Csak olvas, az `index.olvaso()` nyilvános kapcsolatán (a `graf_meta` mintájára): az index és a `feladat` tábla sémája
a C06 szerződése, ide nem nyúl. Nyitott az a feladat, amelynek jele nem `x`/`X`/`-` (kész, megszűnt), és amelynek
nincs `kesz` vagy `torolve` dátuma. „Ma” esedékes: a határideje (📅 / `[due::]`) vagy az ütemezett napja (⏳ /
`[scheduled::]`) a mai nap; lejárt: a határideje korábbi.
"""
from __future__ import annotations

import json
import re

KESZ_JEL = ("x", "X", "-")
_DATUMJEL = re.compile(r"(?:📅|⏳|🛫|✅|➕|❌)️?\s*\d{4}-\d{2}-\d{2}")
_DATAVIEW = re.compile(r"\[(?:due|scheduled|start|completion|created|cancelled)::[^\]]*\]")
LIMIT = 50                                   # szakaszonként legfeljebb ennyi sor; a `osszes` a valódi darabszám


def _tiszta(szoveg: str) -> str:
    """A feladat szövege a dátumjelek nélkül (a dátum külön mező)."""
    return re.sub(r"\s{2,}", " ", _DATAVIEW.sub("", _DATUMJEL.sub("", szoveg))).strip()


def esedekes(index, ma: str) -> dict:
    """`{ma: [...], lejart: [...], osszes_ma, osszes_lejart}`; a sor: `{ut, sor, szoveg, hatarido, utemezve}`."""
    mai: list[dict] = []
    lejart: list[dict] = []
    with index.olvaso() as c:
        for ut, sor, allapot, szoveg, hatarido, datumok in c.execute(
                "SELECT f.ut, t.sor, t.allapot, t.szoveg, t.hatarido, t.datumok FROM feladat t "
                "JOIN fajl f ON f.id = t.fajl_id WHERE f.torolve IS NULL AND "
                "(t.hatarido <= ? OR t.datumok LIKE ?)", (ma, f'%"utemezve": "{ma}"%')):
            if allapot in KESZ_JEL:
                continue
            try:
                d = json.loads(datumok) if datumok else {}
            except ValueError:
                d = {}
            if d.get("kesz") or d.get("torolve"):
                continue
            tetel = {"ut": ut, "sor": sor, "szoveg": _tiszta(szoveg), "hatarido": hatarido,
                     "utemezve": d.get("utemezve")}
            if hatarido == ma or d.get("utemezve") == ma:
                mai.append(tetel)
            elif hatarido and hatarido < ma:
                lejart.append(tetel)
    for lista in (mai, lejart):
        lista.sort(key=lambda t: (t["hatarido"] or t["utemezve"] or "", t["ut"], t["sor"]))
    return {"ma": mai[:LIMIT], "lejart": lejart[:LIMIT], "osszes_ma": len(mai), "osszes_lejart": len(lejart)}


def hataridosok(index) -> list[dict]:
    """Minden határidős (📅 / `[due::]`) feladat az indexből, a kész és a megszűnt is (az emlékeztető-tükör követi
    a kipipálást): `{ut, sor, allapot, szoveg, hatarido, kesz}`, `ut`, `sor` szerint rendezve; a `szoveg` a dátumjelek
    nélküli (tisztított) szöveg. Csak olvas (C29)."""
    ki: list[dict] = []
    with index.olvaso() as c:
        for ut, sor, allapot, szoveg, hatarido, datumok in c.execute(
                "SELECT f.ut, t.sor, t.allapot, t.szoveg, t.hatarido, t.datumok FROM feladat t "
                "JOIN fajl f ON f.id = t.fajl_id WHERE f.torolve IS NULL AND t.hatarido IS NOT NULL AND t.hatarido != '' "
                "ORDER BY f.ut, t.sor"):
            try:
                d = json.loads(datumok) if datumok else {}
            except ValueError:
                d = {}
            ki.append({"ut": ut, "sor": sor, "allapot": allapot, "szoveg": _tiszta(szoveg), "hatarido": hatarido,
                       "kesz": allapot in ("x", "X"), "megszunt": allapot == "-" or bool(d.get("torolve"))})
    return ki
