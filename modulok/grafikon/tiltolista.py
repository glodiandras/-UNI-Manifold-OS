"""A tiltólista döntései (C35b-mag; 5. döntés, `docs/PLOT-FORMATUM.md`): **tiszta függvények**, SymPy és hálózat nélkül.

A kulcs a képlet ujjlenyomata (`felismeres.kulcs`-szal azonos: `sha1(latex.normalizal(képlet))[:16]`), a szülő-oldalon, a
`kozos.latex` (stdlib) segítségével számolva — így az automatikus mód a SymPy-t nem hozza be a szülőbe (46. döntés).

`torles_dontes(rekord, most, visszavonva)`: a gép egy korábbi beírására (`core/plot_allapot.Beirasok`) a jegyzet mostani
szövegéből eldönti, hogy a felhasználó **törölte-e** a blokkot. Csak a tiszta törlés tiltólistáz:

| eredmény | jelentés | tiltólista |
|---|---|---|
| `torolve` | a képlet megvan, alatta nincs plot blokk, máshol sincs ugyanilyen | **igen** |
| `megvan` | a beírt blokk (szó szerint vagy ábrájában azonosan) megvan a képlet alatt | nem |
| `szerkesztve` | a képlet alatt plot blokk áll, de nem a beírt | nem (a kézi szerkesztés nem törlés) |
| `athelyezve` | a blokk ugyanazzal az ábrával máshol áll a jegyzetben | nem |
| `visszavonva` | a gépi commitot a felhasználó visszavonta (az nem tiltólistáz) | nem |
| `keplet_eltunt` | a képlet már nincs a jegyzetben (a blokk vele együtt tűnhetett el) | nem |
| `nincs_jegyzet` | a jegyzet nem olvasható / átnevezték / törölték | nem |
"""
from __future__ import annotations

import hashlib

from . import formatum as F
from . import jegyzet as J

TORLES, MEGVAN, SZERKESZTVE, ATHELYEZVE, VISSZAVONVA, KEPLET_ELTUNT, NINCS_JEGYZET = (
    "torolve", "megvan", "szerkesztve", "athelyezve", "visszavonva", "keplet_eltunt", "nincs_jegyzet")


def kulcs_szoveg(keplet: str) -> str:
    """A képlet kulcsa — megegyezik a `felismeres.kulcs`-csal (a tesztek összevetik), SymPy nélkül."""
    return hashlib.sha1(J._latex().normalizal(keplet).encode("utf-8")).hexdigest()[:16]


def keplet_helyek(szoveg: str) -> list[dict]:
    """A jegyzet felismerendő szövegrészei kulccsal és jegyzetbeli sorral: `{kulcs, sor, veg_sor, blokk_kovetkezik}`."""
    szoveg = szoveg or ""
    blokkok = F.blokkok(szoveg)
    ki = []
    for i, k in J.jeloltek(szoveg):
        h = J.hely(szoveg, i, k, blokkok)
        veg = J.tarolo_veg_sor(szoveg, i, k)             # a `$$…$$`/```math tároló vége, ahová a gép a blokkot írja
        if veg is not None:
            h = {**h, "veg_sor": max(veg, h["veg_sor"] or 0),
                 "blokk_kovetkezik": h["blokk_kovetkezik"] or J.van_blokk_alatta(blokkok, veg)}
        ki.append({"kulcs": kulcs_szoveg(k), **h})
    return ki


def _abra(forras: str):
    return F.elemez(forras)


def torles_dontes(rekord: dict, most: str | None, visszavonva: bool = False) -> str:
    """Egy beírási rekord helyzete a jegyzet mostani szövegében (`most`: `None` = a jegyzet nincs meg)."""
    if visszavonva:
        return VISSZAVONVA
    if most is None:
        return NINCS_JEGYZET
    helyek = [h for h in keplet_helyek(most) if h["kulcs"] == rekord["kulcs"]]
    if not helyek:
        return KEPLET_ELTUNT
    blokkok = F.blokkok(most)
    beirt = _abra(rekord["blokk"])
    if any(b.lezart and b.abra == beirt for b in blokkok if b.abra is not None):
        if any(h["blokk_kovetkezik"] for h in helyek):
            return MEGVAN
        return ATHELYEZVE
    if any(h["blokk_kovetkezik"] for h in helyek):
        return SZERKESZTVE
    return TORLES
