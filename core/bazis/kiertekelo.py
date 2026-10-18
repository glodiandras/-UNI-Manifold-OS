"""A Bases-kifejezések kiértékelője (C12): szintaxisfa → zárvány (`fordit`), kiértékelés `Kor`-ral.

A fordítás egyszer fut (LRU a szövegre), a zárvány soronként hívódik: `f(kor) → érték`.

Névfeloldás (`Nev`): helyi (`value`, `index`, `acc`, `values`) → `this` → `file` / `note` / `formula` → különben a
sor `note.<név>` tulajdonsága (a `note.` előtag nélkül is). Függvényhívásnál a név a globális függvények közül
oldódik fel (ismeretlen név: fordítási hiba). A `&&` és a `||` JavaScript-szerűen az operandus értékét adja.

A képletek (`KepletTar`) lustán, soronként egyszer értékelődnek (memó a `Kor.memo`-ban); a körkörös hivatkozás
fordításkor hiba (a körben állók), futásidőben őrzött.
"""
from __future__ import annotations

import functools
import time
from datetime import datetime

from . import fuggvenyek as fn
from ..hibakod import angol_uzenet
from .ertekek import (
    Datum, Fajl, FutasHiba, Hiba, IdokeretHiba, Regex, egyenlo, hasonlit, igaz_e, kivon, modulo, negal, oszt, osszead, szoroz,
)
from .kifejezes import (
    Binaris, Hivas, Index, KifejezesHiba, ListaL, Logikai, Nev, Null, ObjektumL, RegexL, Szam, Szoveg, Tag, Unaris,
    bejar, elemez,
)


# ================================================================ környezet

class Kor:
    """Kiértékelési környezet: az aktuális `sor`, a közös `tabla`, az `ez` (a `this`: `Fajl` vagy `None`), a
    `kepletek` (`KepletTar`), a `helyi` változók, a lekérdezés `most`-ja és a képletek közös memója."""
    __slots__ = ("sor", "tabla", "ez", "kepletek", "helyi", "most", "memo", "folyamatban", "_fajl", "hatarido",
                 "megszakitva", "keret")

    def __init__(self, sor=None, tabla=None, ez=None, kepletek=None, helyi=None, most=None, memo=None,
                 folyamatban=None, hatarido=None, megszakitva=None, keret=None):
        self.sor, self.tabla, self.ez, self.kepletek = sor, tabla, ez, kepletek
        self.helyi = helyi or {}
        self.most = most if most is not None else Datum(datetime.now().replace(microsecond=0), True)
        self.memo = {} if memo is None else memo
        self.folyamatban = set() if folyamatban is None else folyamatban
        self._fajl = None
        # T040/T041: a lekérdezés teljes időkerete (`time.monotonic()` határidő), a megszakítás jelzője és az értékkeret
        # (`ertekek.Keret`) — a környezet másolatai közösen használják
        self.hatarido, self.megszakitva, self.keret = hatarido, megszakitva, keret

    def _masol(self, sor, helyi) -> "Kor":
        k = Kor.__new__(Kor)
        k.sor, k.tabla, k.ez, k.kepletek, k.most, k.memo, k.folyamatban = \
            sor, self.tabla, self.ez, self.kepletek, self.most, self.memo, self.folyamatban
        k.helyi = helyi
        k._fajl = None
        k.hatarido, k.megszakitva, k.keret = self.hatarido, self.megszakitva, self.keret
        return k

    def ellenoriz(self) -> None:
        """A lekérdezés időkerete és megszakítása: `IdokeretHiba`, ha a határidő lejárt vagy a kérés elavult (T040)."""
        if self.megszakitva is not None and self.megszakitva():
            raise IdokeretHiba("bazis.futas.megszakitva", megszakitva=True)
        if self.hatarido is not None and time.monotonic() > self.hatarido:
            raise IdokeretHiba("bazis.futas.idokeret")

    def alkor(self, **helyi) -> "Kor":
        k = self._masol(self.sor, {**self.helyi, **helyi})
        k._fajl = self._fajl
        return k

    def sorra(self, sor) -> "Kor":
        """Ugyanez a környezet egy másik sorra (a helyi változók nélkül)."""
        return self._masol(sor, {})

    def tiszta(self) -> "Kor":
        k = self._masol(self.sor, {})
        k._fajl = self._fajl
        return k

    def fajl(self):
        if self._fajl is None and self.sor is not None:
            self._fajl = Fajl(self.sor, self.tabla)
        return self._fajl


class JegyzetNezet:
    """A `note` név értéke: a sor frontmatter-tulajdonságai (`note.price`, `note["price"]`)."""
    __slots__ = ("sor", "tabla")

    def __init__(self, sor, tabla):
        self.sor, self.tabla = sor, tabla

    def bazis_mezo(self, kor, nev):
        return self.sor.tulajdonsag(self.tabla, nev)

    def mint_dict(self) -> dict:
        return dict(self.sor.ertekek(self.tabla))


class KepletNezet:
    """A `formula` név értéke: a képletek a sorra (`formula.ppu`, `formula["ppu"]`)."""
    __slots__ = ("kor",)

    def __init__(self, kor):
        self.kor = kor

    def bazis_mezo(self, kor, nev):
        if kor.kepletek is None:
            raise FutasHiba("bazis.futas.nincs_keplet", {"nev": nev})
        return kor.kepletek.ertek(kor, nev)

    def mint_dict(self) -> dict:
        t = self.kor.kepletek
        ki = {}
        for nev in (t.nevek() if t else ()):
            try:
                ki[nev] = t.ertek(self.kor, nev)
            except FutasHiba as e:
                ki[nev] = Hiba(e.uzenet)
        return ki


def futtat(f, kor):
    """`f(kor)` úgy, hogy a Python-szintű hiba is `FutasHiba` (egy sor hibája nem állíthatja meg a nézetet). Minden
    kiértékelés előtt az időkeret és a megszakítás ellenőrzése (`IdokeretHiba`: az egész lekérdezést leállítja)."""
    kor.ellenoriz()
    try:
        return f(kor)
    except FutasHiba:
        raise
    except RecursionError:
        raise FutasHiba("bazis.futas.tul_melyen") from None
    except (ArithmeticError, ValueError, TypeError, IndexError) as e:
        raise FutasHiba("bazis.futas.vegrehajtas", {"tipus": type(e).__name__, "e": e}) from None


# ================================================================ fordítás

_ARITM = {"+": osszead, "-": kivon, "*": szoroz, "/": oszt, "%": modulo}
_HASONLIT = {"<": lambda c: c < 0, ">": lambda c: c > 0, "<=": lambda c: c <= 0, ">=": lambda c: c >= 0}


def _allando(v):
    return lambda kor: v


def fordit(c):
    """A szintaxisfa zárványa. Fordítási hiba (ismeretlen függvény, hibás regex) `KifejezesHiba`."""
    if isinstance(c, (Szam, Logikai)):
        return _allando(c.ertek)
    if isinstance(c, Szoveg):
        return _allando(c.ertek)
    if isinstance(c, Null):
        return _allando(None)
    if isinstance(c, RegexL):
        try:
            rx = Regex(c.minta, c.zaszlok)
        except FutasHiba as e:
            raise KifejezesHiba(e.kod, c.kezd, e.param) from None
        return _allando(rx)
    if isinstance(c, ListaL):
        fs = [fordit(e) for e in c.elemek]
        return lambda kor: [f(kor) for f in fs]
    if isinstance(c, ObjektumL):
        ps = [(k, fordit(v)) for k, v in c.parok]
        return lambda kor: {k: f(kor) for k, f in ps}
    if isinstance(c, Nev):
        return _nev(c.nev)
    if isinstance(c, Tag):
        return _tag(c)
    if isinstance(c, Index):
        o, k = fordit(c.obj), fordit(c.kulcs)
        return lambda kor: fn.index(kor, o(kor), k(kor))
    if isinstance(c, Hivas):
        return _hivas(c)
    if isinstance(c, Unaris):
        o = fordit(c.operandus)
        if c.muvelet == "!":
            return lambda kor: not igaz_e(o(kor))
        return lambda kor: negal(o(kor))
    if isinstance(c, Binaris):
        return _binaris(c)
    raise KifejezesHiba("bazis.kifejezes.nem_tamogatott", c.kezd, {"tipus": type(c).__name__})


def _nev(nev: str):
    if nev == "this":
        return lambda kor: kor.helyi[nev] if nev in kor.helyi else kor.ez
    if nev == "file":
        return lambda kor: kor.fajl()
    if nev == "note":
        return lambda kor: JegyzetNezet(kor.sor, kor.tabla) if kor.sor is not None else None
    if nev == "formula":
        return lambda kor: KepletNezet(kor)

    def f(kor):
        h = kor.helyi
        if h and nev in h:
            return h[nev]
        return kor.sor.tulajdonsag(kor.tabla, nev) if kor.sor is not None else None
    return f


def _tag(c: Tag):
    nev = c.nev
    if isinstance(c.obj, Nev):
        n = c.obj.nev
        if n == "file":
            return lambda kor: fn.fajl_mezo(kor, kor.fajl(), nev) if kor.sor is not None else None
        if n == "note":
            return lambda kor: kor.sor.tulajdonsag(kor.tabla, nev) if kor.sor is not None else None
        if n == "formula":
            return lambda kor: KepletNezet(kor).bazis_mezo(kor, nev)
    o = fordit(c.obj)
    return lambda kor: fn.mezo(kor, o(kor), nev)


def _hivas(c: Hivas):
    f = c.fn
    if isinstance(f, Nev):
        nev = f.nev
        if nev == "if":
            if not 2 <= len(c.argok) <= 3:
                raise KifejezesHiba("bazis.kifejezes.if_argumentum", c.kezd)
            felt, igaz = fordit(c.argok[0]), fordit(c.argok[1])
            hamis = fordit(c.argok[2]) if len(c.argok) == 3 else _allando(None)
            return lambda kor: igaz(kor) if igaz_e(felt(kor)) else hamis(kor)
        glob = fn.GLOBALIS.get(nev)
        if glob is None:
            raise KifejezesHiba("bazis.kifejezes.ismeretlen_fuggveny", f.kezd, {"nev": nev})
        argok = [fordit(a) for a in c.argok]
        return lambda kor: glob(kor, *[a(kor) for a in argok])
    if isinstance(f, Tag):
        nev = f.nev
        if nev not in fn.metodus_nevek():
            raise KifejezesHiba("bazis.kifejezes.ismeretlen_fuggveny", f.kezd, {"nev": nev})
        o = fordit(f.obj)
        argok = [fordit(a) for a in c.argok]
        if nev in fn.LUSTA_NEVEK:
            return lambda kor: fn.hivas_lusta(kor, o(kor), nev, argok)
        return lambda kor: fn.hivas_metodus(kor, o(kor), nev, [a(kor) for a in argok])
    raise KifejezesHiba("bazis.kifejezes.nem_hivhato", f.kezd)


def _binaris(c: Binaris):
    m = c.muvelet
    a, b = fordit(c.bal), fordit(c.jobb)
    if m == "&&":
        def es(kor):
            x = a(kor)
            return b(kor) if igaz_e(x) else x
        return es
    if m == "||":
        def vagy(kor):
            x = a(kor)
            return x if igaz_e(x) else b(kor)
        return vagy
    if m == "==":
        return lambda kor: egyenlo(a(kor), b(kor))
    if m == "!=":
        return lambda kor: not egyenlo(a(kor), b(kor))
    if m in _HASONLIT:
        ok = _HASONLIT[m]

        def hasonlitas(kor):
            r = hasonlit(a(kor), b(kor))
            return r is not None and ok(r)
        return hasonlitas
    op = _ARITM[m]
    return lambda kor: op(a(kor), b(kor))


@functools.lru_cache(maxsize=2048)
def fordit_szoveg(kifejezes: str):
    """Kifejezés-szöveg zárványa (LRU). Hibás szövegre `KifejezesHiba` (nem gyorsítótárazott)."""
    return fordit(elemez(kifejezes))


def ertekel(kifejezes: str, kor: Kor):
    """Kényelmi: elemzés + fordítás + kiértékelés. `KifejezesHiba` / `FutasHiba`."""
    return futtat(fordit_szoveg(kifejezes), kor)


# ================================================================ képletek

def _kepletek_hivatkozasai(csomo) -> set[str]:
    ki = set()
    for n in bejar(csomo):
        if isinstance(n, Tag) and isinstance(n.obj, Nev) and n.obj.nev == "formula":
            ki.add(n.nev)
        elif isinstance(n, Index) and isinstance(n.obj, Nev) and n.obj.nev == "formula" and \
                isinstance(n.kulcs, Szoveg):
            ki.add(n.kulcs.ertek)
    return ki


class KepletTar:
    """A `.base` `formulas` szekciója: név → kifejezés-szöveg. A hibás (nem elemezhető, körkörös) képlet értéke
    hiba; a többi képletet ez nem érinti. Az értékek soronként egyszer számolódnak (`Kor.memo`)."""

    def __init__(self, kepletek: dict[str, str]):
        self.forras = {str(k): v for k, v in kepletek.items()}
        self.fn: dict = {}
        self.hiba: dict[str, tuple] = {}              # név → (kod, param) a hibás képletre
        hiv: dict[str, set[str]] = {}
        for nev, szoveg in self.forras.items():
            if not isinstance(szoveg, str):
                self.hiba[nev] = ("bazis.futas.keplet_nem_szoveg", {})
                continue
            try:
                csomo = elemez(szoveg)
                self.fn[nev] = fordit(csomo)
                hiv[nev] = _kepletek_hivatkozasai(csomo)
            except KifejezesHiba as e:
                self.hiba[nev] = (e.kod, {**e.param, "hely": e.hely})
        for nev in hiv:
            if self._ciklusban(nev, hiv):
                self.hiba[nev] = ("bazis.futas.keplet_kor", {"nev": nev})
                self.fn.pop(nev, None)

    @staticmethod
    def _ciklusban(nev: str, hiv: dict) -> bool:
        lattuk, verem = set(), list(hiv.get(nev, ()))
        while verem:
            x = verem.pop()
            if x == nev:
                return True
            if x in lattuk:
                continue
            lattuk.add(x)
            verem.extend(hiv.get(x, ()))
        return False

    def hiba_szoveg(self, nev: str) -> str:
        """A hibás képlet hibájának angol mondata (elemzési hibánál a karakterhellyel)."""
        kod, param = self.hiba[nev]
        hely = param.get("hely")
        uzenet = angol_uzenet(kod, {k: v for k, v in param.items() if k != "hely"}, kod)
        return uzenet if hely is None else angol_uzenet("bazis.kifejezes.hely", {"uzenet": uzenet, "hely": hely + 1})

    def nevek(self) -> list[str]:
        return list(self.forras)

    def ertek(self, kor: Kor, nev: str):
        if nev in self.hiba:
            raise FutasHiba("bazis.futas.keplet_hibas", {"nev": nev, "reszlet": self.hiba_szoveg(nev)})
        f = self.fn.get(nev)
        if f is None:
            raise FutasHiba("bazis.futas.nincs_keplet", {"nev": nev})
        kulcs = (kor.sor.ut if kor.sor is not None else None, nev)
        m = kor.memo.get(kulcs)
        if m is not None:
            if m[0]:
                return m[1]
            raise FutasHiba(m[1].kod, m[1].param)
        if kulcs in kor.folyamatban:
            raise FutasHiba("bazis.futas.keplet_kor", {"nev": nev})
        kor.folyamatban.add(kulcs)
        try:
            v = futtat(f, kor.tiszta())
        except FutasHiba as e:
            kor.memo[kulcs] = (False, e)
            raise
        finally:
            kor.folyamatban.discard(kulcs)
        kor.memo[kulcs] = (True, v)
        return v
