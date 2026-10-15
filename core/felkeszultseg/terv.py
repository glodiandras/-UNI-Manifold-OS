"""A napi terv a dolgozatig (C28a): determinisztikus, tiszta függvény.

Napok: `max(ma, dolgozat − max_nap)` … a dolgozat előtti nap (a dolgozat napján már nem tanulunk). Egy téma hiánya
`hₜ = max(0, cel − szám)`; a számtalan (nincs mért tudás) téma hiánya a teljes `cel`. A nap `napi_perc / szelet_perc`
szeletre oszlik, a j-edik szelet a legnagyobb `hₜ / (1 + kₜ)` témáé (kₜ az eddig kapott szeletei: csökkenő hozam,
a hiány arányában), döntetlennél az alacsonyabb szám, majd a név dönt. A szeletek sorban töltik a napokat, így a
gyenge téma többször, de nem egyhuzamban jön. Nincs hiány → egy átismétlés-szelet az utolsó napon. A FSRS-szimulációt
nem végzi (az esedékes kártyák napi száma külön, becsült mező az összesítőben).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .keplet import Beallitas


@dataclass(frozen=True)
class Tema:
    ut: str
    nev: str
    szam: float | None


@dataclass(frozen=True)
class Szelet:
    tema_ut: str | None
    tema: str
    perc: int
    ok: str


@dataclass(frozen=True)
class Nap:
    nap: str
    perc: int
    szeletek: tuple[Szelet, ...]


@dataclass(frozen=True)
class TervEredmeny:
    napok: list[Nap]
    uzenet: str | None


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


def napi_terv(temak: list[Tema], ma: date, dolgozat: date, b: Beallitas, *, napi_perc: int, szelet_perc: int,
              max_nap: int) -> TervEredmeny:
    if dolgozat < ma:
        return TervEredmeny([], "A dolgozat már lezárult.")
    if dolgozat == ma:
        return TervEredmeny([], "A dolgozat ma van.")
    if not temak:
        return TervEredmeny([], "Nincs téma: a felkészülési jegyzet nem hivatkozik jegyzetre.")
    kezdet = max(ma, dolgozat - timedelta(days=max_nap))
    napok = [kezdet + timedelta(days=i) for i in range((dolgozat - kezdet).days)]
    uzenet = f"A terv a dolgozat előtti {max_nap} napra készül." if kezdet > ma else None
    szelet_naponta = max(1, napi_perc // szelet_perc)
    hiany = {t.ut: round(b.cel if t.szam is None else max(0.0, b.cel - t.szam), 9) for t in temak}
    if not any(h > 0 for h in hiany.values()):
        return TervEredmeny([Nap(napok[-1].isoformat(), szelet_perc, (Szelet(None, "Átismétlés: minden téma", szelet_perc,
                                                                            "átismétlés"),))],
                            "A célszint fölött vagy minden témában: egy átismétlés elég.")
    sorrend = sorted(temak, key=lambda t: (-1.0 if t.szam is None else t.szam, t.nev, t.ut))     # a döntetlen rendje
    k = {t.ut: 0 for t in temak}
    szeletek: list[Tema] = []
    for _ in range(len(napok) * szelet_naponta):
        legjobb = max((t for t in sorrend if hiany[t.ut] > 0), key=lambda t: round(hiany[t.ut] / (1 + k[t.ut]), 9))
        k[legjobb.ut] += 1
        szeletek.append(legjobb)
    ki = []
    for i, nap in enumerate(napok):
        csoport: dict[str, int] = {}
        for t in szeletek[i * szelet_naponta:(i + 1) * szelet_naponta]:
            csoport[t.ut] = csoport.get(t.ut, 0) + 1
        nev = {t.ut: t for t in temak}
        sorok = []
        for ut, db in csoport.items():
            t = nev[ut]
            ok = ("nincs adat" if t.szam is None else
                  f"gyenge: {_pct(t.szam)}" if t.szam < b.gyenge else f"{_pct(t.szam)}, a cél {_pct(b.cel)}")
            sorok.append(Szelet(ut, t.nev, db * szelet_perc, ok))
        ki.append(Nap(nap.isoformat(), sum(s.perc for s in sorok), tuple(sorok)))
    return TervEredmeny(ki, uzenet)


def kozos_terv(vizsgak: list[tuple[str, date, list[Tema]]], ma: date, b: Beallitas, *, napi_perc: int,
               szelet_perc: int, max_nap: int, foglalt: dict[str, int] | None = None) -> dict[str, TervEredmeny]:
    """CX-009: egyetlen napi keret az összes vizsgának; sürgősség × tudáshiány, csökkenő hozammal.

    A már naptárban álló tanulás is fogyasztja a keretet. Mérési adat hiányában a téma prioritása magas,
    de a kimenet nem állít tudásszázalékot. A hátralévő töredék is pontosan a napi kereten belül marad.
    """
    foglalt = foglalt or {}
    aktiv = [(azon, nap, temak) for azon, nap, temak in vizsgak if nap > ma and temak]
    napok: dict[str, list[Nap]] = {azon: [] for azon, _, _ in vizsgak}
    if not aktiv:
        return {azon: TervEredmeny([], 'Nincs tervezhető téma vagy a dolgozat már elérkezett.') for azon in napok}
    kapott: dict[tuple[str, str], int] = {}
    for i in range(min(max_nap, max((nap - ma).days for _, nap, _ in aktiv))):
        nap = ma + timedelta(days=i)
        jeloltek = []
        for azon, hatar, temak in aktiv:
            if not (ma <= nap < hatar and (hatar - nap).days <= max_nap): continue
            hianyos = [t for t in temak if t.szam is None or t.szam < b.cel]
            if hianyos:
                jeloltek.extend((azon, hatar, t) for t in hianyos)
            elif nap == hatar - timedelta(days=1):
                jeloltek.append((azon, hatar, Tema('', 'Átismétlés: minden téma', b.cel)))
        keret = max(0, napi_perc - foglalt.get(nap.isoformat(), 0))
        kiosztott: dict[str, list[Szelet]] = {}
        while keret and jeloltek:
            def suly(j):
                azon, hatar, t = j
                hiany = b.cel if t.szam is None else max(0.05, b.cel - t.szam)
                return hiany / max(1, (hatar - nap).days) / (1 + kapott.get((azon, t.ut), 0))
            azon, hatar, t = max(sorted(jeloltek, key=lambda j: (j[1], j[0], j[2].ut)), key=suly)
            perc = min(szelet_perc, keret)
            ok = 'átismétlés' if not t.ut else 'nincs adat' if t.szam is None else f'mért tudás: {_pct(t.szam)}'
            kiosztott.setdefault(azon, []).append(Szelet(t.ut or None, t.nev, perc, ok))
            kapott[(azon, t.ut)] = kapott.get((azon, t.ut), 0) + 1
            keret -= perc
            if not t.ut: jeloltek.remove((azon, hatar, t))
        for azon, szeletek in kiosztott.items():
            csoport = {}
            for s in szeletek:
                regi = csoport.get(s.tema_ut)
                csoport[s.tema_ut] = Szelet(s.tema_ut, s.tema, s.perc + (regi.perc if regi else 0), s.ok)
            napok[azon].append(Nap(nap.isoformat(), sum(s.perc for s in szeletek), tuple(csoport.values())))
    return {azon: TervEredmeny(n, f'Közös keret: {napi_perc} perc/nap az összes dolgozatra.') for azon, n in napok.items()}
