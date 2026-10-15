"""Dolgozat ↔ felkészülési jegyzet kötése (C28a; LEGACY-SZERZODESEK L59) — a legacy `szemelyes/dolgozat.py` `kotes`-ének
portja, tiszta függvényekkel (útlista és naptáresemények be, kötés ki).

A jegyzet útja `…/<mappa>/ÉÉÉÉ-HH-NN - <Tantárgy>.md` (a mappa neve az `os.toml` `[naplo] dolgozat_mappa` kulcsa, a
legacy szerint a mappanév **részsztring-egyezés**). A kötés két menetben megy, jegyzetenként, (nap, út) sorrendben:

1. *biztos*: aznap van `fajta == "dolgozat"` esemény, amelynek tantárgy-halmaza metszi a jegyzetét, és még nincs lekötve;
   *valószínű*: nincs biztos, és aznap pontosan egy lekötetlen, tantárgy nélküli dolgozat vagy határidő van.
   Egy esemény egy jegyzethez köthető.
2. a még kötetlen jegyzetre: *áthelyezve?* — azonos tantárgyú, lekötetlen dolgozat 1–7 napra (a legközelebbi); ha nincs,
   *órarend szerint* — van aznapi azonos tantárgyú óra, de dolgozat nincs a naptárban; különben *nincs*.

A tantárgyat a `naptar.targy()` adja a jegyzet nevéből (a „Matek” a Matematika), ugyanazzal a térképpel, mint az események.
Az `ma._felkeszules` (C15) egyszerűbb, esemény felől induló kötése változatlanul él a Ma oldalon.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date

from .. import naptar

NEV = re.compile(r"^(\d{4}-\d{2}-\d{2}) - (.+)\.md$")
ATHELYEZES_MAX_NAP = 7


@dataclass(frozen=True)
class Jegyzet:
    ut: str
    nap: str
    tantargy_nev: str
    targyak: tuple[str, ...]


@dataclass(frozen=True)
class Kotes:
    jegyzet: str
    fok: str          # biztos | valoszinu | athelyezve
    ok: str           # magyar magyarázat a felületnek


@dataclass(frozen=True)
class Kotesek:
    esemenyek: dict[str, Kotes]          # az esemény azonosítója → a hozzá kötött jegyzet
    jegyzetek: dict[str, str]            # a jegyzet útja → biztos | valoszinu | athelyezve | orarend | nincs


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def jegyzetek(utak, mappa: str, targyak: dict[str, list[str]] | None = None) -> list[Jegyzet]:
    """A felkészülési jegyzetek az útlistából: a szülőmappa neve tartalmazza a `mappa` nevét (ékezet- és
    kis-nagybetű-függetlenül), a fájlnév `ÉÉÉÉ-HH-NN - Tantárgy.md`. Rendezve: (nap, út)."""
    mappa_n = naptar.norm(mappa)
    ki = []
    for u in utak:
        u = _nfc(u)
        reszek = u.split("/")
        if len(reszek) < 2 or mappa_n not in naptar.norm(reszek[-2]):
            continue
        m = NEV.match(reszek[-1])
        if not m:
            continue
        nev = m.group(2)
        ki.append(Jegyzet(u, m.group(1), nev, tuple(naptar.targy(nev, targyak))))
    return sorted(ki, key=lambda j: (j.nap, j.ut))


def _nap(e: dict) -> str:
    return (e.get("nap") or e.get("kezd") or "")[:10]


def _napok_kozott(a: str, b: str) -> int:
    try:
        return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)
    except ValueError:
        return 10 ** 6


def kot(jegyz: list[Jegyzet], esemenyek: list[dict]) -> Kotesek:
    """A jegyzetek kötése a naptáresemények (`naptar.esemenyek` alakja: `azon`, `nap`, `fajta`, `kategoria`, `targyak`)
    dolgozataihoz — lásd a modul leírását."""
    dolgozatok = [e for e in esemenyek if e.get("fajta") == "dolgozat"]
    napra: dict[str, list[dict]] = {}
    for e in esemenyek:
        napra.setdefault(_nap(e), []).append(e)
    kotott: dict[str, Kotes] = {}            # esemény azonosítója → kötés
    jegyzet_fok: dict[str, str] = {}

    def szabad(e):
        return e["azon"] not in kotott

    for j in jegyz:                                                   # 1. menet
        aznap = napra.get(j.nap, [])
        talalt = [e for e in aznap if e.get("fajta") == "dolgozat" and szabad(e) and set(e.get("targyak") or ()) & set(j.targyak)]
        if talalt:
            tantargy = sorted(set(talalt[0]["targyak"]) & set(j.targyak))[0]
            kotott[talalt[0]["azon"]] = Kotes(j.ut, "biztos", f"azonos nap és tantárgy ({tantargy})")
            jegyzet_fok[j.ut] = "biztos"
            continue
        egyetlen = [e for e in aznap if e.get("fajta") in ("dolgozat", "hatarido") and not e.get("targyak") and szabad(e)]
        if len(egyetlen) == 1:
            kotott[egyetlen[0]["azon"]] = Kotes(j.ut, "valoszinu", "aznap ez az egyetlen tantárgy nélküli dolgozat vagy határidő")
            jegyzet_fok[j.ut] = "valoszinu"

    for j in jegyz:                                                   # 2. menet
        if j.ut in jegyzet_fok:
            continue
        jeloltek = sorted(
            (e for e in dolgozatok if szabad(e) and set(e.get("targyak") or ()) & set(j.targyak)
             and 0 < _napok_kozott(_nap(e), j.nap) <= ATHELYEZES_MAX_NAP and j.targyak),
            key=lambda e: (_napok_kozott(_nap(e), j.nap), _nap(e), e["azon"]))
        if jeloltek:
            e = jeloltek[0]
            kotott[e["azon"]] = Kotes(j.ut, "athelyezve", f"a jegyzet {j.nap}-ra szól, a dolgozat {_nap(e)}-án van "
                                                           f"({_napok_kozott(_nap(e), j.nap)} nap eltérés): áthelyezték?")
            jegyzet_fok[j.ut] = "athelyezve"
            continue
        ora = any(e.get("kategoria") == "orarend" and set(e.get("targyak") or ()) & set(j.targyak) for e in napra.get(j.nap, []))
        jegyzet_fok[j.ut] = "orarend" if ora else "nincs"
    return Kotesek(kotott, jegyzet_fok)
