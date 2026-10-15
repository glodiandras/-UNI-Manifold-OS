"""Videó- és hang-szint (`docs/C26-TERV.md` 3.3): az átirat időablakai → darabok, időkód-horgonyokkal.

A forrás az átirat (`<Téma>/Média/` réteg VTT-je, L44 olvasó szabálya); a VTT olvasása a C26b dolga, a magban a `cues`
tiszta bemenet: `[(másodperc, szöveg)]`. Egy időablak egy bekezdés (egy `ForrasSzoveg`-szakasz), a horgonya a `t=<mp>` link.
"""
from __future__ import annotations

from modulok.kapuk import forras as KF

from .formatum import ido_horgony
from .szakaszolas import Bekezdes, Bemenet, Darab, norm


def ablakok(cues, ablak_mp: int = 60) -> list[tuple[int, str]]:
    """A cue-k időablakokba: `(az ablak első cue-jának másodperce, az ablak szövege)`. Az ablak a legkorábbi cue-tól
    `ablak_mp` másodpercig tart; az üres cue kiesik, a sorrend az időé."""
    ki: list[tuple[int, list[str]]] = []
    kezd = None
    for mp, szoveg in sorted(((int(m), norm(s)) for m, s in cues), key=lambda x: x[0]):
        if not szoveg:
            continue
        if kezd is None or mp - kezd >= ablak_mp:
            ki.append((mp, []))
            kezd = mp
        ki[-1][1].append(szoveg)
    return [(mp, " ".join(r)) for mp, r in ki]


def video_bemenet(cues, cel: str, cim: str | None = None, ablak_mp: int = 60, max_karakter: int = 2200) -> Bemenet:
    """Az átirat → `Bemenet`. `cel`: a videó/hang vault-relatív útja kiterjesztéssel (`[[cel#t=125|2:05]]`)."""
    abl = ablakok(cues, ablak_mp)
    szakaszok = [KF.Szakasz((), None, None, szoveg) for _, szoveg in abl]
    fs = KF.ForrasSzoveg(szakaszok, cim)
    darabok: list[Darab] = []
    cur: Darab | None = None
    for si, (mp, szoveg) in enumerate(abl):
        b = Bekezdes(szoveg, si, ido_horgony(cel, mp))
        sor = f"[{ido_horgony(cel, mp).felirat}] {szoveg}"
        if cur is None or len(cur.szoveg) + len(sor) + 2 > max_karakter:
            cur = Darab("", 0)
            darabok.append(cur)
        cur.szoveg += ("\n\n" if cur.szoveg else "") + sor
        cur.karakter += len(szoveg)
        cur.szakaszok.append(si)
        cur.bekezdesek.append(b)
    return Bemenet(fs, darabok, cel)
