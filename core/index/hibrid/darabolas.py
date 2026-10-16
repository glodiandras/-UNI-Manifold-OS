"""Blokkszintű darabolás az index meglévő tábláiból (tiszta függvények; fájlt nem olvas).

Bemenet: a jegyzet `fts.tartalom` szövege (`\\n` sorvégek, frontmatterrel — az index ezt tárolja), a `fejezet` sorai
(`szint`, `szoveg`, `sor`) és a `blokk` sorai (`azon`, `sor`, `kezdo_sor`); a sorszámok 1-től, a szövegre mutatnak.

Szabály: a frontmatter kimarad; a címsor új szakaszt nyit (a címsor-út a darab fejléce); a szakaszon belül a bekezdések
(üres sorral elválasztva; a kód- és a `$$`-blokkon belül nem vágunk) `darab_max` karakterig gyűlnek, az ennél hosszabb
bekezdés önálló darab, és ha `darab_max * 1,5`-nél is hosszabb, sorhatáron vágódik. A gép írta, nem tartalmi szakaszok
(a kapu listája: `modulok.kapuk.forras.kihagyott_szakaszok(cfg)`, a `[kapuk] kihagyott_szakaszok`; alap: Füzet, Gyakorlás, Kitöltések)
kimaradnak. A hívó a konfig listáját adja (`bekezdesek(…, kihagyott=…)`, `darabol(…, kihagyott=…)`); hiányában a kapu alapja.

Darabonként: a sorhatár (`sor_kezd`, `sor_veg`), a címsor-út, a darab bekezdéseinek `^blokk` azonosítói (a blokk záró
sorával: a horgony a bekezdésé, amelyben az idézet áll) és a szöveg sha1-e (`hash`: a változatlan darab vektora
újrahasznosul). A beágyazott szöveg (`beagyazando`) a jegyzet címét és a címsor-utat is hordozza: a kontextus nélküli
bekezdés („Ezért tiltja…”) is a tárgyához kerül.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from ..maszk import FM_RE

DARAB_MAX = 1200
_FEJ = re.compile(r"^(#{1,6})[ \t]+")
_KERITES = re.compile(r"^\s*(```|~~~)")


@dataclass(frozen=True)
class Bekezdes:
    sor_kezd: int
    sor_veg: int
    szoveg: str
    blokk: str | None = None              # a bekezdés `^azonosítója` (a záró sorában), ha van


@dataclass(frozen=True)
class Darab:
    ut: str
    sorszam: int                          # a jegyzeten belül 0-tól
    sor_kezd: int
    sor_veg: int
    fejezet: tuple[str, ...]              # a címsor-út (a legkülső elöl)
    szoveg: str
    bekezdesek: tuple[Bekezdes, ...] = field(default=(), compare=False)

    @property
    def cim(self) -> str:
        """A jegyzet címe: az alapnév kiterjesztés nélkül (a fájlnév; a wikilink célja is ez)."""
        return self.ut.rsplit("/", 1)[-1].rsplit(".", 1)[0]

    @property
    def blokkok(self) -> tuple[str, ...]:
        return tuple(b.blokk for b in self.bekezdesek if b.blokk)

    @property
    def hash(self) -> str:
        return hashlib.sha1(self.beagyazando.encode("utf-8")).hexdigest()

    @property
    def beagyazando(self) -> str:
        """A beágyazó bemenete: `cím › fejezet › alfejezet` fejléc és a darab szövege."""
        return " › ".join((self.cim, *self.fejezet)) + "\n\n" + self.szoveg


def _kihagyott() -> tuple[str, ...]:
    from modulok.kapuk.forras import KIHAGYOTT_SZAKASZOK          # a kapu listája (lusta import: a core nem esik el rajta)
    return KIHAGYOTT_SZAKASZOK


def bekezdesek(tartalom: str, fejezetek, blokkok, kihagyott: tuple[str, ...] | list[str] | None = None) -> list[tuple[tuple[str, ...], Bekezdes]]:
    """A jegyzet bekezdései a címsor-útjukkal, a frontmatter, a címsorok és a kihagyott szakaszok nélkül. `kihagyott`: a szakaszok
    címei (a `[kapuk] kihagyott_szakaszok`); hiányában a kapu alapja."""
    sorok = tartalom.split("\n")
    fm = FM_RE.match(tartalom)
    elso = tartalom[:fm.end()].count("\n") + 1 if fm else 1           # az első törzssor (1-től)
    fej_sorok = {int(f[2]): (int(f[0]), str(f[1])) for f in fejezetek}
    blokk_sorok = {int(b[1]): str(b[0]) for b in blokkok}
    kihagy = {k.casefold() for k in (_kihagyott() if kihagyott is None else kihagyott)}
    ut: list[tuple[int, str]] = []
    kihagyva_szint: int | None = None
    ki: list[tuple[tuple[str, ...], Bekezdes]] = []
    akt: list[int] = []
    kerites: str | None = None
    matek = False

    def lezar():
        if akt and kihagyva_szint is None:
            szoveg = "\n".join(sorok[i - 1] for i in akt).strip()
            if szoveg:
                blokk = next((blokk_sorok[i] for i in reversed(akt) if i in blokk_sorok), None)
                ki.append((tuple(s for _, s in ut), Bekezdes(akt[0], akt[-1], szoveg, blokk)))
        akt.clear()

    for i in range(elso, len(sorok) + 1):
        s = sorok[i - 1]
        if kerites is None and not matek and i in fej_sorok and _FEJ.match(s):
            lezar()
            szint, szoveg = fej_sorok[i]
            while ut and ut[-1][0] >= szint:
                ut.pop()
            if kihagyva_szint is not None and szint <= kihagyva_szint:
                kihagyva_szint = None
            ut.append((szint, szoveg))
            if kihagyva_szint is None and szoveg.strip().casefold() in kihagy:
                kihagyva_szint = szint
            continue
        m = _KERITES.match(s)
        if m and not matek:
            kerites = None if kerites == m.group(1) else (kerites or m.group(1))
        elif kerites is None and s.strip() == "$$":
            matek = not matek
        elif kerites is None and s.strip().startswith("$$") and s.strip().count("$$") == 1:
            matek = not matek
        if not s.strip() and kerites is None and not matek:
            lezar()
            continue
        akt.append(i)
    lezar()
    return ki


def darabol(ut: str, tartalom: str, fejezetek=(), blokkok=(), darab_max: int = DARAB_MAX,
            kihagyott: tuple[str, ...] | list[str] | None = None) -> list[Darab]:
    """A jegyzet darabjai (lásd a modul leírását). `fejezetek`: `(szint, szoveg, sor)`; `blokkok`: `(azon, sor, …)`; `kihagyott`: a
    kihagyott szakaszok címei (`[kapuk] kihagyott_szakaszok`; hiányában a kapu alapja)."""
    ki: list[Darab] = []
    csoport: list[Bekezdes] = []
    csoport_ut: tuple[str, ...] | None = None

    def kiad(bek: list[Bekezdes], fut: tuple[str, ...]):
        if bek:
            ki.append(Darab(ut, len(ki), bek[0].sor_kezd, bek[-1].sor_veg, fut,
                            "\n\n".join(b.szoveg for b in bek), tuple(bek)))

    for fut, b in bekezdesek(tartalom, fejezetek, blokkok, kihagyott):
        if csoport and (fut != csoport_ut or sum(len(x.szoveg) + 2 for x in csoport) + len(b.szoveg) > darab_max):
            kiad(csoport, csoport_ut)
            csoport = []
        if len(b.szoveg) > darab_max * 1.5:
            kiad(csoport, csoport_ut)
            csoport = []
            for resz in _vag(b, darab_max):
                kiad([resz], fut)
            continue
        csoport.append(b)
        csoport_ut = fut
    kiad(csoport, csoport_ut)
    return ki


def _vag(b: Bekezdes, darab_max: int) -> list[Bekezdes]:
    """A túl hosszú bekezdés sorhatáron vágva (egy sor sem vágódik ketté; a blokkazonosító az utolsó részé)."""
    sorok = b.szoveg.split("\n")
    reszek, akt, kezd = [], [], b.sor_kezd
    for j, s in enumerate(sorok):
        if akt and sum(len(x) + 1 for x in akt) + len(s) > darab_max:
            reszek.append(Bekezdes(kezd, kezd + len(akt) - 1, "\n".join(akt)))
            kezd += len(akt)
            akt = []
        akt.append(s)
    if akt:
        reszek.append(Bekezdes(kezd, kezd + len(akt) - 1, "\n".join(akt), b.blokk))
    return reszek
