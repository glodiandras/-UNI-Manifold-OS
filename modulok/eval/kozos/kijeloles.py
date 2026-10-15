"""Az asszisztens kijelölés-módjainak közös pontozója (J4): a kifejtés (`kifejtes`) és a kijelölés összefoglalása
(`osszefoglal_kijeloles`) aranyhalmaza.

A tétel a felhasználó egy valódi jegyzetének kijelölése (bekezdés, lista, táblázat), fagyasztva: a `kijeloles` a kijelölt
szöveg, az `elotte` a jegyzet nyers szövege a kijelölés előtt (legfeljebb 1500 karakter — az éles kérés is ennyit lát). A kérés
a `core.kiegeszites_modell.keres` — ugyanaz, amit élesben a ⌘J / ⇧⌘J küld.

A „magyar” próba durva: van ékezetes magyar betű, és legfeljebb 3 (hosszabb szövegben negyed) az angol függvényszó.

**Összefoglalás** (tételenként 0–1): formai kapu (nem üres, magyar, legfeljebb 4 mondat és 700 karakter, legfeljebb a kijelölés
0,8-szerese, nem ismétli a kijelölést, nincs kódblokk) — ha bukik, 0. Különben 0,5 × **lefedettség** (a kijelölés kulcstényei
közül hányat említ: a tény egy vagy több alternatív kulcsszó-csoport, a szavak toldalékolt alakban is számítanak) + 0,5 ×
**hűség** (a mondatok hányad része megy át a közös forráshűség-kapun — `modulok/kapuk`, `[kapuk]` profil — úgy, hogy a forrás
maga a kijelölés a jegyzet címével: a tartalmi szavak legalább fele a kijelölésben áll, minden szám és tulajdonnév benne van,
és nincs a kijelölésben nem álló tagadás).

**Kifejtés** (tételenként 0–1): formai kapu (nem üres, magyar, 1–4 mondat, legfeljebb 900 karakter, nem ismétli a kijelölést,
nincs kódblokk) és **ellentmondás-kapu** (nincs a jegyzetben nem álló szám — a 0–12 kivételével —; nincs olyan mondat, amely egy
kijelölt mondattal nagyrészt egyezik, de a tagadása ellentétes; nincs a tétel tiltott állítása tagadás nélküli mondatban) — ha
bármelyik bukik, 0. Ha nem marad **a témánál** (a tétel témaszavai közül legalább egy, és a tartalmi szavak legalább 15%-a a
kijelölésből vagy az előtte álló szövegből), szintén 0; a témánál maradó válasz 0,5, és még 0,5, ha **új tartalmat** ad (legalább 3
tartalmi szó, amely a kijelölésben nem áll — a puszta átfogalmazás 0,5).

Mit nem lát: a lexikai vizsgálat az átfogalmazott hamis állítást, a szinonimával mondott ellentmondást és a stílust nem fogja
meg; a felhasználó a jóváhagyáskor (K430) a pontozó tételenkénti részleteit (`tetelek`) is átnézi.
"""
from __future__ import annotations

import dataclasses
import json
import re
import sys
from pathlib import Path

ITT = Path(__file__).resolve().parent
REPO = ITT.parents[2]
for _p in (str(REPO), str(ITT.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from kozos import arany as A  # noqa: E402
from kozos import tavolsag  # noqa: E402
from modulok.kapuk import forras as KF  # noqa: E402
from modulok.kapuk import huseg as KH  # noqa: E402
from modulok.kapuk import tokenek as KT  # noqa: E402

ELOTTE_MAX = 1500                      # a `uzenetek_kijeloles` ennyit küld a kijelölés előtti szövegből (teszt őrzi)
KIS_SZAMOK = {str(i) for i in range(13)}   # felsorolás, mondatszám: nem tényállítás
OSSZ_MAX_KARAKTER, OSSZ_MAX_MONDAT, OSSZ_ARANY = 700, 4, 0.8
KIF_MAX_KARAKTER, KIF_MAX_MONDAT = 900, 4
TEMA_ATFEDES, UJ_MIN, TAGADAS_ATFEDES = 0.15, 3, 0.6
SULY = 0.5

_EN = frozenset("the and of is are to in that this with for it as be by on was were which".split())
_HU_BETU = re.compile(r"[áéíóöőúüűÁÉÍÓÖŐÚÜŰ]")
_LISTA = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+", re.M)
_JELOLES = re.compile(r"\*\*|__|~~|`")
_MONDATHATAR = re.compile(r"(?<=[.!?…])\s+|\n+")


def profil(cfg) -> KH.Profil:
    """A közös kapu `[kapuk]` profilja (cfg nélkül az alapértékek), a kijelöléshez igazítva: az „idézet” maga a kijelölés,
    ezért a hossz-határ nem értelmezett; a bizonyíték a kijelölés a jegyzet címével (`mondat+cim`)."""
    p = KH.profil(cfg) if cfg is not None else KH.Profil()
    return dataclasses.replace(p, nev="kijeloles", idezet_min_szo=1, idezet_max_szo=None, bizonyitek="mondat+cim",
                               mondat_max_karakter=100_000)


def betolt(mappa: Path) -> dict:
    return A.betolt(mappa)


def verzio(feladat: str, arany: dict, prompt_lenyomat: str) -> str:
    """`<feladat>-<verzio>.p<prompt-lenyomat>[-vazlat]`: a kalibrált sor a prompthoz is kötött — ha a kérés szövege változik,
    a régi sor nem routol (a mód visszaesik próbára), amíg az új kérésen nem mérnek."""
    return f"{feladat}-" + A.verzio({**arany, "verzio": f"{arany['verzio']}.p{prompt_lenyomat}"})


# ---------------------------------------------------------------------- szöveg-segédek

def tiszta(s: str) -> str:
    return _JELOLES.sub("", _LISTA.sub("", s or "")).strip()


def mondatok(s: str) -> list[str]:
    return [m.strip() for m in _MONDATHATAR.split(tiszta(s)) if m and len(KT.szavak(m)) >= 2]


def magyar(s: str) -> bool:
    """Durva nyelvi próba: van magyar ékezetes betű, és kevés az angol függvényszó (a kódnév — `for … in` — még belefér)."""
    w = [x.lower() for x in KT.szavak(s)]
    if not w:
        return False
    en = sum(1 for x in w if x in _EN)
    return bool(_HU_BETU.search(s)) and en <= max(3, len(w) // 4)


def _kulcsok(s: str) -> list[str]:
    return [tavolsag.hajt(w)[:KT.TOVEK_HOSSZ] for w in KT.szavak(s)]


def fedi(kifejezes: str, szoveg: str) -> bool:
    """A kifejezés minden szava (toldalékolva is) áll a szövegben: a szó hajtott, legfeljebb 5 betűs eleje egy szöveg-szó
    eleje (`híd` ↔ `hidaknál`, `szegénység` ↔ `szegénységben`)."""
    szo = [tavolsag.hajt(w) for w in KT.szavak(szoveg)]
    return all(any(x.startswith(k) for x in szo) for k in _kulcsok(kifejezes)) and bool(_kulcsok(kifejezes))


def fedett_csoportok(csoportok: list[list[str]], szoveg: str) -> list[bool]:
    """Csoportonként: valamelyik alternatívája fedve van-e."""
    return [any(fedi(alt, szoveg) for alt in cs) for cs in csoportok]


def forras(t: dict) -> KF.ForrasSzoveg:
    return KF.ForrasSzoveg.jegyzetbol(t["kijeloles"], cim=t.get("cim"))


def _ismetli(valasz: str, fs: KF.ForrasSzoveg) -> bool:
    """A válasz a kijelölés egészét (vagy 120 karakternél hosszabb első részét) szó szerint tartalmazza."""
    v = re.sub(r"\s+", " ", tavolsag.hajt(tiszta(valasz)))
    k = re.sub(r"\s+", " ", tavolsag.hajt(fs.szoveg)).strip()
    return bool(k) and (k in v or (len(k) > 120 and k[:120] in v))


# ---------------------------------------------------------------------- összefoglalás

def osszefoglalas_formatum(valasz, vart: dict) -> bool:
    if not isinstance(valasz, str) or not valasz.strip() or "```" in valasz:
        return False
    fs = forras(vart)
    m = mondatok(valasz)
    return (len(valasz.strip()) <= min(OSSZ_MAX_KARAKTER, OSSZ_ARANY * len(fs.szoveg)) and 1 <= len(m) <= OSSZ_MAX_MONDAT
            and magyar(valasz) and not _ismetli(valasz, fs))


def osszefoglalas_pont(valasz, vart: dict, p: KH.Profil) -> dict:
    if not osszefoglalas_formatum(valasz, vart):
        return {"pont": 0.0, "okok": ["formatum"]}
    fs = forras(vart)
    fed = fedett_csoportok(vart["kulcs"], valasz)
    ver = [(m, KH.ellenoriz(fs, m, fs.szoveg, p)) for m in mondatok(valasz)]
    huseg = sum(1 for _, v in ver if v.ok) / len(ver)
    lef = sum(fed) / len(fed)
    okok = [f"hianyzo_kulcs:{i + 1}" for i, f in enumerate(fed) if not f]
    okok += [f"huseg:{'/'.join(v.okok)}:{m[:60]}" for m, v in ver if not v.ok]
    return {"pont": round(SULY * lef + (1 - SULY) * huseg, 4), "lefedettseg": round(lef, 4), "huseg": round(huseg, 4),
            "okok": okok}


# ---------------------------------------------------------------------- kifejtés

def kifejtes_formatum(valasz, vart: dict) -> bool:
    if not isinstance(valasz, str) or not valasz.strip() or "```" in valasz:
        return False
    m = mondatok(valasz)
    return (len(valasz.strip()) <= KIF_MAX_KARAKTER and 1 <= len(m) <= KIF_MAX_MONDAT and magyar(valasz)
            and not _ismetli(valasz, forras(vart)))


def ellentmondas(valasz: str, vart: dict) -> list[str]:
    """A kifejtés ellentmondás-kapuja: a bukott szabályok (üres lista: átment)."""
    okok = []
    megengedett = (set(vart.get("szamok") or ()) | KT.szamok(vart["kijeloles"]) | KT.szamok(vart.get("elotte") or "")
                   | KIS_SZAMOK)
    idegen = sorted(KT.szamok(valasz) - megengedett)
    if idegen:
        okok.append("szam:" + ",".join(idegen))
    sajat = mondatok(KF.ForrasSzoveg.jegyzetbol(vart["kijeloles"]).szoveg)
    for m in mondatok(valasz):
        tm = KT.tovek(m)
        if len(tm) < 3:
            continue
        for s in sajat:
            atfed = len(KT.lefedett(tm, KT.tovek(s, stop=False))) / len(tm)
            if atfed >= TAGADAS_ATFEDES and KT.tagado(m) != KT.tagado(s):
                okok.append(f"tagadas:{m[:60]}")
                break
        if not KT.tagado(m):
            for minta in vart.get("tiltott") or ():
                if re.search(minta, m, re.I):
                    okok.append(f"tiltott:{minta}")
    return okok


def kifejtes_pont(valasz, vart: dict) -> dict:
    if not kifejtes_formatum(valasz, vart):
        return {"pont": 0.0, "okok": ["formatum"]}
    rossz = ellentmondas(valasz, vart)
    if rossz:
        return {"pont": 0.0, "okok": rossz}
    tv = KT.tovek(tiszta(valasz))
    kornyezet = KT.tovek(vart["kijeloles"] + "\n" + (vart.get("elotte") or ""), stop=False)
    atfed = len(KT.lefedett(tv, kornyezet)) / len(tv) if tv else 0.0
    tema = any(fedett_csoportok(vart["tema"], valasz)) and atfed >= TEMA_ATFEDES
    uj = len(tv - KT.lefedett(tv, KT.tovek(vart["kijeloles"], stop=False))) >= UJ_MIN
    okok = ([] if tema else [f"tema:{atfed:.2f}"]) + ([] if uj else ["nincs_uj_tartalom"])
    pont = (SULY + (1 - SULY) * uj) if tema else 0.0           # a témától eltérő kifejtés nem ér pontot
    return {"pont": round(pont, 4), "tema": tema, "uj": uj, "atfedes": round(atfed, 4), "okok": okok}


# ---------------------------------------------------------------------- közös pontozás

def pontoz(rekordok: list[dict], egy, korlat: str) -> dict:
    reszl = []
    for r in rekordok:
        e = egy(r.get("valasz"), r["vart"])
        reszl.append({"id": r["id"], **e})
    n = len(rekordok)
    return {"pontszam": round(sum(x["pont"] for x in reszl) / n, 4) if n else 0.0,
            "teljes_pont": sum(1 for x in reszl if x["pont"] >= 1.0), "osszes": n, "tetelek": reszl, "korlat": korlat}


def json_ki(arany: dict) -> str:
    return json.dumps(arany, ensure_ascii=False, indent=1) + "\n"
