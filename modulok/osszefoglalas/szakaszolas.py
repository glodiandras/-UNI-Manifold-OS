"""Szakaszolás: a jegyzet fejezetei és blokkjai (az index táblái, tiszta bemenet) → a modell darabjai és a horgonyok.

- A **szakaszokat** a közös kapu előkészítése adja (`KF.elokeszit`: jelölés, link, megjegyzés, beágyazás és a gép írta
  `Füzet`/`Gyakorlás`/`Kitöltések` szakaszok nélkül), így a modell, a kapu és a horgony ugyanazt a szöveget látja.
- A **bekezdések** (üres sorral határolt blokkok) a szakaszok törzséből jönnek; mindegyik tudja a fejezet-horgonyát, és azt,
  hogy a forrásban mely `^blokk` azonosítók esnek rá (az index `blokk` táblája szerint).
- A **horgony** a találat bekezdésétől függ: `^blokk` (ha a találatot tartalmazó blokknak van azonosítója), különben a fejezet
  (ha az index ismeri a címet), különben a jegyzet.
- A **darab** egy modellhívás egysége: egymás utáni bekezdések `max_karakter`-ig, a fejezet-útvonallal fejlécezve.

Az index nem nyílik meg: a `fejezetek` (`{szint, szoveg, sor}`) és a `blokkok` (`{azon, sor, kezdo_sor}`) táblát a hívó adja
(a core-ban `core/index/elemzo.elemez(md)` ugyanezt adja). Fájlt nem olvasnak, és nem írnak.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from modulok.kapuk import forras as KF

from .formatum import Horgony

_AZON_SOR = re.compile(r"^\^[A-Za-z0-9-]+$")
_FRONT = re.compile(r"\A---\r?\n.*?\r?\n---\r?\n?", re.S)


def norm(s: str) -> str:
    """Összehasonlító alak: NFC, szóközök összevonva."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s or "")).strip()


@dataclass(frozen=True)
class Bekezdes:
    szoveg: str                                   # tisztított
    szakasz: int                                  # a `ForrasSzoveg.szakaszok` sorszáma
    horgony: Horgony                              # fejezet- (vagy jegyzet-, vagy idő-) horgony
    blokkok: tuple[tuple[str, str], ...] = ()     # (azonosító, a blokk tisztított, `norm`-olt szövege)


@dataclass
class Darab:
    szoveg: str                                   # a prompt törzse (fejlécekkel)
    karakter: int
    szakaszok: list[int] = field(default_factory=list)
    bekezdesek: list[Bekezdes] = field(default_factory=list)


@dataclass
class Bemenet:
    """Egy összefoglalás forrása: a kapu forrásszövege, a darabok és a lánc számára a horgony-keresés."""
    fs: KF.ForrasSzoveg
    darabok: list[Darab]
    cel: str                                      # a forrás vault-relatív útja `.md` nélkül

    def bekezdesek(self) -> list[Bekezdes]:
        return [b for d in self.darabok for b in d.bekezdesek]


def _tiszta_blokk(sorok: list[str]) -> str:
    """Egy blokk nyers sorai → a kapu előkészítésével tisztított, `norm`-olt szöveg (fejezet nélkül)."""
    szakaszok = KF.elokeszit("\n".join(sorok), kihagy=())
    return norm(" ".join(sz.szoveg for sz in szakaszok))


def _blokk_szovegek(md: str, blokkok: list[dict]) -> list[tuple[str, str]]:
    """(azonosító, tisztított szöveg) minden blokkhoz: a `kezdo_sor..sor` nyers sorai (1-alapú fájlsorok). A blokkazonosító
    maga nem része a szövegnek."""
    sorok = md.split("\n")
    ki = []
    for b in blokkok or []:
        a, z = max(int(b["kezdo_sor"]), 1), min(int(b["sor"]), len(sorok))
        if a > z:
            continue
        resz = [s for s in sorok[a - 1:z] if not _AZON_SOR.match(s.strip())]
        szoveg = _tiszta_blokk(resz)
        if szoveg:
            ki.append((str(b["azon"]), szoveg))
    return ki


def _fejezet_horgony(cel: str, szakasz: KF.Szakasz, fejezetek: list[dict] | None) -> Horgony:
    """A fejezet-link: a cím, ha az előkészítés szerint horgonyozható, és (ha van index-tábla) az index is ismeri."""
    if not szakasz.horgony:
        return Horgony(cel)
    if fejezetek:
        ismert = {norm(f["szoveg"]) for f in fejezetek}
        if norm(szakasz.horgony) not in ismert:
            return Horgony(cel)
    return Horgony(cel, szakasz.horgony)


def _bekezdesek(szakasz: KF.Szakasz) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", szakasz.szoveg) if p.strip() and not _AZON_SOR.match(p.strip())]


def _darabolas(egysegek: list[tuple[int, Bekezdes]], szakaszok: list[KF.Szakasz], max_k: int) -> list[Darab]:
    """Egymás utáni bekezdések darabokba `max_k` karakterig; a fejléc a fejezet-útvonal (szakaszváltáskor újra)."""
    ki: list[Darab] = []
    cur: Darab | None = None
    utolso_szakasz = -1
    for si, b in egysegek:
        fejlec = "[" + (" › ".join(szakaszok[si].ut) or "Bevezetés") + "]\n"
        fej = fejlec if si != utolso_szakasz else ""
        if cur is not None and cur.karakter and len(cur.szoveg) + len(fej) + len(b.szoveg) + 2 > max_k:
            cur = None
        if cur is None:
            cur, fej = Darab("", 0), fejlec
            ki.append(cur)
        cur.szoveg += ("\n\n" if cur.szoveg else "") + fej + b.szoveg[: max_k * 2]
        cur.karakter += len(b.szoveg)
        if si not in cur.szakaszok:
            cur.szakaszok.append(si)
        cur.bekezdesek.append(b)
        utolso_szakasz = si
    return ki


def jegyzet_bemenet(md: str, cel: str, cim: str | None = None, fejezetek: list[dict] | None = None,
                    blokkok: list[dict] | None = None, max_karakter: int = 2200, min_karakter: int = 20,
                    kihagy: tuple[str, ...] | None = None) -> Bemenet:
    """A jegyzet → `Bemenet`. `cel`: a vault-relatív út `.md` nélkül (a horgonyok célja); `fejezetek`, `blokkok`: az index
    táblái (nem kötelezők: nélkülük a horgony a kapu előkészítésének fejezetcíme, blokkazonosító nélkül)."""
    md = unicodedata.normalize("NFC", md).replace("\r\n", "\n").replace("\r", "\n")
    szakaszok = KF.elokeszit(md, min_karakter=min_karakter, kihagy=kihagy)
    fs = KF.ForrasSzoveg(szakaszok, cim)
    blokk_sz = _blokk_szovegek(md, blokkok or [])
    egysegek: list[tuple[int, Bekezdes]] = []
    for si, sz in enumerate(szakaszok):
        horgony = _fejezet_horgony(cel, sz, fejezetek)
        for p in _bekezdesek(sz):
            pn = norm(p)
            sajat = tuple((a, t) for a, t in blokk_sz if t in pn or pn in t)
            egysegek.append((si, Bekezdes(p, si, horgony, sajat)))
    return Bemenet(fs, _darabolas(egysegek, szakaszok, max_karakter), cel)


def horgony_keres(bemenet: Bemenet, szakasz: int | None, talalt: str) -> tuple[Horgony, Bekezdes | None]:
    """A kapu találatához (`Verdikt.szakasz`, a talált forrásszöveg) tartozó bekezdés és horgonya.

    A találatot a szakasz bekezdései közt keressük (`norm`-olt tartalmazás; ha a találat két bekezdésen át nyúlik, az első
    szavai alapján). A bekezdés blokkjai közül az, amelyik a találattal fedésben van, adja a `^blokk` horgonyt; blokk
    nélkül a fejezet. Nincs bekezdés → a szakasz fejezet-horgonya, ennek híján a jegyzet."""
    t = norm(talalt)
    jeloltek = [b for b in bemenet.bekezdesek() if szakasz is None or b.szakasz == szakasz] or bemenet.bekezdesek()
    if not jeloltek:
        return Horgony(bemenet.cel), None
    b = next((b for b in jeloltek if t and t in norm(b.szoveg)), None)
    if b is None and t:
        elso = " ".join(t.split()[:6])
        b = next((b for b in jeloltek if elso in norm(b.szoveg)), None)
    b = b or jeloltek[0]
    for azon, szoveg in b.blokkok:
        if t and (t in szoveg or szoveg in t):
            return Horgony(bemenet.cel, "^" + azon), b
    return b.horgony, b
