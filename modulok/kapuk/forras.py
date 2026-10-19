"""A forrásjegyzet előkészítése és az idézet megkeresése benne (a közös forráshűség-kapu alapja).

A modell a *megjelenített* szöveget idézi, nem a Markdown forrást: `**vastag**`, `[[cél|név]]`, listajel, `^blokk` nélkül.
Ezért az összevetés előtt a jegyzet tisztított alakot kap (`elokeszit`; a legacy kvízlánc `szakaszok` portja a core
kódmaszkjával). A szakaszok egy szöveggé fűződnek (`ForrasSzoveg`), amelyben a találat helye visszavezethető a
fejezetre — a visszajelzés linkje (`[[jegyzet#fejezet]]`) ebből jön.

Az idézet keresése a pontozó közös segédjére (`modulok/eval/kozos/idezet.Forras`) épül: szószintű pontos egyezés, utána
betűszintű csúszóablak, így a mérés és az éles kapu ugyanazt a találat-keresést használja.

Tiszta függvények és osztályok: fájlt nem olvasnak és nem írnak.
"""
from __future__ import annotations

import bisect
import os
import re
import unicodedata
from dataclasses import dataclass

from core.index.maszk import FM_RE, mask_code, megjegyzes_nelkul
from modulok.eval.kozos import idezet as _idezet

from . import tokenek

KIHAGYOTT_SZAKASZOK = ("Füzet", "Gyakorlás", "Kitöltések")      # gép írta vagy nem tartalmi szakaszok; alap, ha a `[kapuk] kihagyott_szakaszok` hiányzik


def kihagyott_szakaszok(cfg=None) -> tuple[str, ...]:
    """A kihagyott (gép írta, nem tartalmi) szakaszok fejezetcímei: a `[kapuk] kihagyott_szakaszok` lista, hiányában az alap
    (`KIHAGYOTT_SZAKASZOK`). Az üres lista: semmi nem marad ki."""
    if cfg is None:
        return KIHAGYOTT_SZAKASZOK
    ertek = cfg.section("kapuk").get("kihagyott_szakaszok")
    lista = tuple(str(x) for x in ertek) if isinstance(ertek, (list, tuple)) else KIHAGYOTT_SZAKASZOK
    fuzet = str(cfg.section("fuzet").get("szakasz") or "")           # a füzetlánc gép írta szakasza sosem kerülhet vissza forrásként a kapuba
    return lista if not fuzet or nfc(fuzet) in {nfc(x) for x in lista} else (*lista, fuzet)

_FEJ = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
_BEAGY = re.compile(r"!\[\[[^\]]*\]\]|!\[[^\]]*\]\([^)]*\)")
_WIKI = re.compile(r"\[\[([^\]|#]*)(?:#([^\]|]*))?(?:\|([^\]]*))?\]\]")
_MDLINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_LABJEGYZET = re.compile(r"\[\^[^\]]+\]")
_BLOKKAZON = re.compile(r"[ \t]+\^[A-Za-z0-9-]+[ \t]*$")
_IDEZET_JEL = re.compile(r"^\s*(?:>\s?)+(?:\[![^\]]*\][+-]?\s*)?")
_LISTA_JEL = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s+)?")
_KIEMELES = re.compile(r"\*\*|__|~~|==")                  # vastag, aláhúzott, áthúzott, kiemelt: a jelölés nem tartalom
_HTML_MEGJEGYZES = re.compile(r"<!--.*?-->", re.S)
# az Obsidian-link horgonyát ezek a jelek törik; ilyenkor a link csak a jegyzetre mutat
_HORGONY_TILOS = re.compile(r"[#|^\[\]:\\%$]")
_KEPLET = re.compile(r"\$\$.*?\$\$|(?<!\\)\$(?!\$)[^$\n]*?(?<!\\)\$", re.S)


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


@dataclass(frozen=True)
class Szakasz:
    ut: tuple[str, ...]           # a fejezetcímek lánca (H2–H6)
    cim: str | None               # None: a H1 alatti bevezető
    horgony: str | None           # a `[[jegyzet#horgony]]`-hoz; None, ha a cím tiltott jelet tartalmaz
    szoveg: str                   # a tisztított törzs


def _kiurit(szoveg: str, maszk: str, minta: re.Pattern) -> tuple[str, str]:
    """A minta találatai (a kódmaszk után keresve: a kódban álló jel nem számít) szóközzé, a sortörések maradnak."""
    ki, mk = list(szoveg), list(maszk)
    for m in minta.finditer(maszk):
        for i in range(m.start(), m.end()):
            if ki[i] != "\n":
                ki[i] = mk[i] = " "
    return "".join(ki), "".join(mk)


def _torzs_nezetek(md: str) -> tuple[str, str]:
    """Látható törzs és szerkezeti maszk azonos eltolásokkal; a valódi kód tartalma megmarad."""
    md = nfc(md).replace("\r\n", "\n").replace("\r", "\n")
    fm = FM_RE.match(md)
    torzs = md[fm.end():] if fm else md
    maszk = mask_code(torzs, frontmatter=False)
    lathato = megjegyzes_nelkul(torzs, frontmatter=False)
    return _kiurit(lathato, maszk, _HTML_MEGJEGYZES)


def _sor_tisztit(s: str) -> str:
    """Egy törzssor a jelölés nélkül: idézet- és callout-jel, lista- és feladatjel, beágyazás, link, lábjegyzet, `^blokk`."""
    s = _IDEZET_JEL.sub("", s)
    s = _LISTA_JEL.sub("", s)
    s = _BEAGY.sub(" ", s)
    s = _WIKI.sub(lambda m: m.group(3) if m.group(3) is not None else (os.path.basename(m.group(1)) or m.group(2) or ""), s)
    s = _MDLINK.sub(r"\1", s)
    s = _LABJEGYZET.sub("", s)
    s = _BLOKKAZON.sub("", s)
    s = _KIEMELES.sub("", s)
    return s.rstrip()


def elokeszit(md: str, min_karakter: int = 0, kihagy: tuple[str, ...] | None = None) -> list[Szakasz]:
    """A jegyzet szakaszai a tisztított törzzsel. Kiesik a frontmatter, a `%%megjegyzés%%`, a HTML-megjegyzés, a
    beágyazás és a `kihagy` nevű fejezetek (az alfejezeteikkel); a kódblokk szövege megmarad, de nem fejezet. A
    legalább `min_karakter` nem szóköz karakteres szakaszok maradnak (0: minden nem üres). `kihagy` hiányában az alap
    (`KIHAGYOTT_SZAKASZOK`); a konfigurációból a `kihagyott_szakaszok(cfg)` adja."""
    torzs, maszk = _torzs_nezetek(md)
    kihagy = {nfc(k) for k in (KIHAGYOTT_SZAKASZOK if kihagy is None else kihagy)}

    ki: list[Szakasz] = []
    verem: list[tuple[int, str]] = []
    sorok: list[str] = []
    kihagy_szint: int | None = None

    def lezar() -> None:
        t = "\n".join(sorok).strip()
        sorok.clear()
        if t and kihagy_szint is None and len(re.sub(r"\s+", "", t)) >= max(min_karakter, 1):
            cim = verem[-1][1] if verem else None
            ki.append(Szakasz(tuple(c for _, c in verem), cim,
                              cim if cim and not _HORGONY_TILOS.search(cim) else None, t))

    for sor, mk in zip(torzs.split("\n"), maszk.split("\n")):
        kod = bool(sor.strip()) and not mk.strip()             # a sor egésze kód: marad, de nem fejezet
        m = None if kod else _FEJ.match(mk)
        if m:
            lezar()
            szint = len(m.group(1))
            # A kódmaszk csak a fejezet helyét adja: a címben álló inline kód is tartalom.
            cim = nfc(_FEJ.match(sor).group(2).strip())
            if szint == 1:
                verem, kihagy_szint = [], None
                continue
            while verem and verem[-1][0] >= szint:
                verem.pop()
            if kihagy_szint is not None and szint <= kihagy_szint:
                kihagy_szint = None
            verem.append((szint, cim))
            if cim in kihagy and kihagy_szint is None:
                kihagy_szint = szint
            continue
        s = sor if kod else _sor_tisztit(sor)
        if s.strip() or (sorok and sorok[-1].strip()):
            sorok.append(s)
    lezar()
    return ki


def h1_cim(md: str) -> str | None:
    """A jegyzet első látható `# cím` sora (kódblokk és megjegyzés nélkül), ha van."""
    torzs, maszk = _torzs_nezetek(md)
    for sor, mk in zip(torzs.split("\n"), maszk.split("\n")):
        m = re.match(r"^#[ \t]+(.+?)[ \t]*#*[ \t]*$", mk)
        if m and mk.strip():
            cim = _FEJ.match(sor).group(2).strip()
            if cim:
                return nfc(cim)
    return None


# ---------------------------------------------------------------------- mondat

def kepletek_nelkul(s: str) -> str:
    """A szöveg a `$…$` és `$$…$$` képletek nélkül (a képletek helyén szóköz)."""
    return _KEPLET.sub(" ", s)


def _matek(t: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _KEPLET.finditer(t)]


def _dollar_paratlan(s: str) -> bool:
    return len(re.findall(r"(?<!\\)\$", s)) % 2 == 1 or s.count("$$") % 2 == 1


def _jeloles_ki(s: str) -> str:
    s = _KIEMELES.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


@dataclass(frozen=True)
class Talalat:
    hely: tuple[int, int]         # karakterhely a `ForrasSzoveg.szoveg`-ben
    hasonlosag: float             # 1,0: szó szerint; alatta: betűszintű hasonlóság
    szo: tuple[int, int]          # szóindex-tartomány
    szoszam: int                  # az idézet szavainak száma
    szakasz: int                  # a találat szakaszának sorszáma
    szoveg: str                   # a forrás szövege a találat helyén


class ForrasSzoveg:
    """A szakaszok egy szöveggé fűzve (az idézetkeresés egysége) és a hely → szakasz térkép."""

    def __init__(self, szakaszok: list[Szakasz], cim: str | None = None):
        self.szakaszok = szakaszok
        self.cim = nfc(cim) if cim else None                # a jegyzet címe: a bizonyíték része (a tárgya az egész jegyzet)
        reszek, self._kezd, hely = [], [], 0
        for sz in szakaszok:
            self._kezd.append(hely)
            reszek.append(sz.szoveg)
            hely += len(sz.szoveg) + 2
        self.szoveg = "\n\n".join(reszek)
        self._f = _idezet.Forras(self.szoveg, _idezet.SZO_ES_JEL)       # a szöveg már NFC: a helyek ugyanarra mutatnak
        self._nevtovek: frozenset[str] | None = None
        self._keresek: dict[tuple[str, float], Talalat | None] = {}
        self._kepletek: list[tuple[int, int]] | None = None

    @classmethod
    def jegyzetbol(cls, md: str, cim: str | None = None, **kw) -> "ForrasSzoveg":
        """A jegyzet szövegéből; a `cim` alapja a jegyzet neve (a hívó adja), különben az első H1."""
        return cls(elokeszit(md, **kw), cim or h1_cim(md))

    def nevtovek(self) -> frozenset[str]:
        """A jegyzet tulajdonnevei (tövek): a mondatkezdő nagybetű nem árul el nevet, de ami máshol mondat közben is
        nagybetűs, és sehol nincs kisbetűvel (`Mit`, `Ezért` mondatkezdőként is lehet kisbetűs), az név."""
        if self._nevtovek is None:
            kisbetus = {tokenek.to(w) for w in tokenek.szavak(self.szoveg) if w[0].islower()}
            self._nevtovek = frozenset(tokenek.to(w) for w, kezdo in tokenek.nagybetus(self.szoveg)
                                       if not kezdo and len(w) >= 3) - kisbetus
        return self._nevtovek

    def szakasz_hely(self, poz: int) -> int:
        """A karakterhely szakaszának sorszáma (üres forrásnál -1)."""
        return max(bisect.bisect_right(self._kezd, poz) - 1, 0) if self._kezd else -1

    def keres(self, idezet: str, kuszob: float = 0.85) -> Talalat | None:
        """Az idézet helye a forrásban, vagy `None`, ha nincs (a `kuszob` alatti hasonlóság is nincs)."""
        if not isinstance(idezet, str) or not idezet.strip():
            return None
        kulcs = (idezet, kuszob)
        if kulcs not in self._keresek:
            t = self._f.keres(nfc(idezet), kuszob)
            if not t["talalt"]:
                self._keresek[kulcs] = None
            else:
                a, b = t["hely"]
                self._keresek[kulcs] = Talalat((a, b), t["hasonlosag"], t["szo"], t["szoszam"], self.szakasz_hely(a),
                                               self.szoveg[a:b])
        return self._keresek[kulcs]

    def mondat(self, a: int, b: int, max_k: int = 420) -> str:
        """A talált tartomány kiterjesztése a mondat határaira (a képleten belül nem vág), jelölés nélkül. Ha a mondat
        hosszabb `max_k`-nál, vagy páratlan `$` marad benne, a talált rész jön (a képlethatárra igazítva)."""
        t = self.szoveg
        if self._kepletek is None:
            self._kepletek = _matek(t)
        mt = self._kepletek

        def bent(i: int) -> bool:
            return any(s <= i < e for s, e in mt)

        s = a
        while s > 0 and t[s - 1] != "\n" and not (t[s - 1] in ".!?" and not bent(s - 1) and s < len(t) and t[s].isspace()):
            s -= 1
        e = b
        while e < len(t) and t[e] != "\n":
            if t[e] in ".!?" and not bent(e) and (e + 1 == len(t) or t[e + 1].isspace()):
                e += 1
                break
            e += 1
        if e - s > max_k:
            s, e = a, b
            for ms, me in mt:
                if ms < s < me:
                    s = ms
                if ms < e < me:
                    e = me
        ki = _jeloles_ki(t[s:e].replace("\n", " "))
        return _jeloles_ki(t[a:b].replace("\n", " ")) if _dollar_paratlan(ki) else ki
