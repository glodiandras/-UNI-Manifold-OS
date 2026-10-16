"""A router (TERV 4.): feladat → az első kalibrált, a pillanatnyi keretbe férő modell.

Nem modell dönt, hanem a mérésekből töltött tábla (`kalibracio`). Élesben csak kalibrált modell fut
(D9); ha nincs ilyen, a döntés hiba, nem tartalék-modell. Ha a legjobb kalibrált modell csak a
távol-keretbe fér: a `[router.feladat.<f>].tavolra_var` szerint vár rá („kész, ha távol vagy”), vagy a
keretbe férő gyengébbel fut.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .beallitas import Beallitas, Modell, RegiszterHiba
from .kalibracio import Tabla


class RoutingHiba(RuntimeError):
    """A feladatra nincs futtatható kalibrált modell."""


class NincsMasikCsalad(RoutingHiba):
    """A második vélemény (C24b): a kizárt családon kívül nincs kalibrált modell a feladatra."""


@dataclass(frozen=True)
class Dontes:
    modell: Modell | None
    var_tavolra: bool = False
    indok: str = ""

    def publikus(self) -> dict:
        return {"modell": self.modell.nev if self.modell else None, "var_tavolra": self.var_tavolra,
                "indok": self.indok}


def _befer(m: Modell, keret_gb: float) -> bool:
    return m.csucs_gb is None or m.csucs_gb <= keret_gb       # mérés nélkül a betöltő dönt (L24)


class Router:
    """`verziok`: router-feladat → az aranyhalmaz aktuális verziója (`halmaz.Verziok`; a worker mindig adja). Ha meg van
    adva, csak az aktuális verzión kalibrált sor routol (C19, T050); a `-vazlat` sort a tábla maga sem adja ki."""

    def __init__(self, b: Beallitas, tabla: Tabla, verziok: Callable[[str], str | None] | None = None):
        self.b = b
        self.tabla = tabla
        self.verziok = verziok

    def kalibralt_sorok(self, feladat: str) -> list[dict]:
        """A feladat routolható kalibrált sorai (a legjobb elöl): az aktuális aranyhalmaz-verzión mértek."""
        return self.tabla.kalibralt_sorrend(feladat, self.verziok)

    def valaszt(self, feladat: str, keret_gb: float, kizart_csalad: str | None = None) -> Dontes:
        """`kizart_csalad` (C24b, második vélemény): ennek a családnak a modelljei kimaradnak; ha így nem marad kalibrált jelölt:
        `NincsMasikCsalad`. A család a regiszterből jön (`[modellek.<n>] csalad`), új tábla-oszlop nincs."""
        if not feladat:
            raise RoutingHiba("a kérésben nincs feladat (és próba-modell sincs)")
        sorok = self.kalibralt_sorok(feladat)
        if not sorok and self.tabla.kalibralt_sorrend(feladat):
            raise RoutingHiba(f"a(z) {feladat} kalibrált sorai nem az aranyhalmaz aktuális verzióján "
                              f"({self.verziok(feladat) if self.verziok else '?'}) mértek — újra kell mérni; "
                              "Beállítások › AI › Kalibráció")
        jeloltek = []
        for sor in sorok:
            try:
                jeloltek.append(self.b.modell(sor["modell"]))
            except RegiszterHiba:
                continue                                           # a regiszterből kikerült modell nem futhat
        if jeloltek and kizart_csalad:
            jeloltek = [m for m in jeloltek if m.csalad != kizart_csalad]
            if not jeloltek:
                raise NincsMasikCsalad(f"a(z) {feladat} feladatra nincs a(z) {kizart_csalad} családon kívüli kalibrált modell "
                                       "(nincs második vélemény)")
        if not jeloltek:
            raise RoutingHiba(f"nincs kalibrált modell ehhez a feladathoz ({feladat}); Beállítások › AI › Kalibráció")
        tavol_gb = self.b.keret_gb("tavol") if self.b.keret_felulirva is None else keret_gb
        var = self.b.feladat_szabaly(feladat).get("tavolra_var", False)
        for i, m in enumerate(jeloltek):
            if _befer(m, keret_gb):
                if i > 0 and var and _befer(jeloltek[0], tavol_gb):
                    return Dontes(None, True, f"{jeloltek[0].nev} jobb, és csak a távol-keretbe fér — rá vár")
                return Dontes(m, False, "a legjobb kalibrált" if i == 0 else
                              f"a jobb ({jeloltek[0].nev}) nem fér a {keret_gb:g} GB-os keretbe")
        if any(_befer(m, tavol_gb) for m in jeloltek):
            return Dontes(None, True, f"a(z) {feladat} kalibrált modelljei csak a távol-keretbe férnek")
        raise RoutingHiba(f"a(z) {feladat} egyik kalibrált modellje sem fér a keretbe ({keret_gb:g} GB)")
