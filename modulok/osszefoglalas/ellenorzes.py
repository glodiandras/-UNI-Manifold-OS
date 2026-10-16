"""Egy összefoglaló-jegyzet elemzése a forrásához mérve (C26b: a CLI `ellenoriz` és a `GET /api/osszefoglalas/jegyzet` közös helye).

A **sodródás** (`sodrodott`): az állítás idézete (a jegyzet szó szerinti mondata) a forrásjegyzetben már nem áll szó szerint —
a jegyzet azóta megváltozott, az állítás elavult lehet. A **horgony hiánya** (`horgony_hianyzik`): a link `^blokk` vagy fejezet
célja már nincs a forrásban. A **forrás hiánya** (`forras_hianyzik`): a forrásjegyzet (vagy a videó) már nincs a vaultban.
A videó/hang forrás (`[[…#t=<mp>|m:ss]]`) szövege nem olvasható itt, ezért a sodródás nem vizsgálható: csak a fájl megléte.

Tiszta: a vault-olvasást a hívó adja (`olvas(rp) → szöveg | None`, `letezik(rp) → bool`); nem ír, modellt nem hív.
"""
from __future__ import annotations

from typing import Callable

from core.index import elemzo

from . import formatum as FM
from . import lanc as L
from . import szakaszolas as SZ


def vizsgal(txt: str, olvas: Callable[[str], str | None], letezik: Callable[[str], bool], b: L.Beallitas) -> tuple[dict, int]:
    """→ (a jelentés, kilépési kód: 1 hibánál vagy sodródásnál). A jelentés `reszletek` listája állításonként
    `{id, szoveg, idezet, cel, alcel, felirat, sodrodott, horgony_hianyzik, forras_hianyzik}` (a beágyazott megjelenítéshez)."""
    e = FM.elemez(txt, azon_tartalek="OSSZ-00000000-000000-kezi")
    ki: dict = {"hibak": e.hibak}
    rc = 1 if e.hibak else 0
    o = e.osszefoglalo
    if not (o and o.allitasok):
        return ki, rc
    ki.update(azon=o.azon, szint=o.szint, forrasok=o.forrasok, modell=o.modell, keszult=o.keszult, cim=o.cim, allitas=len(o.allitasok))
    sodrodott, horgony_hiany, hianyzo_forras, cache, reszletek = [], [], [], {}, []
    for al in o.allitasok:
        cel = al.horgony.cel
        alcel = al.horgony.alcel
        ido = bool(alcel and alcel.startswith("t="))
        if cel not in cache:
            if ido:
                cache[cel] = ("media", letezik(cel))
            else:
                md = olvas(cel + ".md")
                if md is None:
                    cache[cel] = None
                else:
                    t = elemzo.elemez(md)
                    cache[cel] = ("jegyzet", SZ.jegyzet_bemenet(md, cel, FM.cim_of(cel + ".md"), t.fejezetek, t.blokkok,
                                                                 b.darab_max_karakter, b.szakasz_min_karakter,
                                                                 b.kihagyott_szakaszok), t)
        r = {"id": al.id, "szoveg": al.szoveg, "idezet": al.idezet, "cel": cel, "alcel": alcel, "felirat": al.horgony.felirat,
             "sodrodott": False, "horgony_hianyzik": False, "forras_hianyzik": False}
        c = cache[cel]
        if c is None or (c[0] == "media" and not c[1]):
            r["forras_hianyzik"] = True
            if cel not in hianyzo_forras:
                hianyzo_forras.append(cel)
        elif c[0] == "jegyzet":
            _, bem, t = c
            tal = bem.fs.keres(al.idezet, 0.97)
            if tal is None or tal.hasonlosag < 1.0:                  # az idézet már nem áll szó szerint a forrásban
                r["sodrodott"] = True
                sodrodott.append(al.id)
            if alcel:
                lehetseges = {"^" + x["azon"] for x in t.blokkok} | {SZ.norm(x["szoveg"]) for x in t.fejezetek}
                if SZ.norm(alcel) not in lehetseges:
                    r["horgony_hianyzik"] = True
                    horgony_hiany.append(al.id)
        reszletek.append(r)
    ki.update(sodrodott=sodrodott, horgony_hianyzik=horgony_hiany, reszletek=reszletek)
    if hianyzo_forras:
        ki["forras_hianyzik"] = hianyzo_forras
    return ki, rc or int(bool(sodrodott or horgony_hiany or hianyzo_forras))
